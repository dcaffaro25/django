# tasks.py (e.g. in multitenancy/tasks.py)
from celery import shared_task, group, chord
from django.core.mail import send_mail
from django.conf import settings
import smtplib
from django.apps import apps
from multitenancy.formula_engine import apply_substitutions
from django.db import transaction
from .api_utils import safe_model_dict, MODEL_APP_MAP, PATH_COLS, _is_mptt_model, _get_path_value, _split_path, _resolve_parent_from_path_chain
from multitenancy.models import IntegrationRule
from copy import deepcopy
from typing import Any, Dict, List, Tuple
import contextlib

from celery import shared_task
from django.apps import apps
from django.db import transaction
from core.utils.exception_utils import exception_to_dict



from django.core.exceptions import FieldDoesNotExist
from core.utils.exception_utils import exception_to_dict



@shared_task(bind=True, autoretry_for=(smtplib.SMTPException, ConnectionError), retry_backoff=True, max_retries=5)
def send_user_invite_email(self, subject, message, to_email):
    """
    Send user invite email with retry support.
    - retried on SMTP errors or connection failures
    - exponential backoff (default: 2^n seconds)
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_email(self, subject, message, to_email):
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
    )

@shared_task
def execute_integration_rule(rule_id, payload):
    """
    Executa uma IntegrationRule específica de forma assíncrona.
    """
    rule = IntegrationRule.objects.get(pk=rule_id)
    result = rule.run_rule(payload)
    return result

@shared_task
def trigger_integration_event(company_id, event_name, payload):
    """
    Executa todas as IntegrationRule ativas para determinado evento.
    """
    rules = IntegrationRule.objects.filter(
        company_id=company_id,
        is_active=True,
        triggers__icontains=event_name
    ).order_by('execution_order')
    for rule in rules:
        if rule.use_celery:
            execute_integration_rule.delay(rule.id, payload)
        else:
            execute_integration_rule(rule.id, payload)

def _to_int_or_none(x):
    if x in ("", None):
        return None
    try:
        return int(float(x))
    except Exception:
        return None

def _parse_json_or_empty(v):
    import json
    if v in ("", None):
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}

def _resolve_fk(model, field_name: str, raw_value, row_id_map: Dict[str, Any]):
    """
    Resolve a *_fk value to a model instance.
    Accepts:
      - '__row_id' string referencing a previously created row in this same import
      - numeric ID (int/float/'3'/'3.0')
    """
    # __row_id indirection
    if isinstance(raw_value, str) and raw_value in row_id_map:
        return row_id_map[raw_value]

    # numeric id path
    try:
        related_field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        raise ValueError(f"Unknown FK field '{field_name}' for model {model.__name__}")

    fk_model = getattr(related_field, "related_model", None)
    if fk_model is None:
        raise ValueError(f"Field '{field_name}' is not a ForeignKey on {model.__name__}")

    if raw_value in ("", None):
        return None

    if isinstance(raw_value, (int, float)) or (isinstance(raw_value, str) and raw_value.replace(".", "", 1).isdigit()):
        fk_id = _to_int_or_none(raw_value)
        if fk_id is None:
            raise ValueError(f"Invalid FK id '{raw_value}' for field '{field_name}'")
        try:
            return fk_model.objects.get(id=fk_id)
        except fk_model.DoesNotExist:
            raise ValueError(f"{fk_model.__name__} id={fk_id} not found for field '{field_name}'")
    raise ValueError(f"Invalid FK reference format '{raw_value}' for field '{field_name}'")

def _normalize_payload_for_model(model, payload: Dict[str, Any], *, context_company_id=None):
    """
    - map company_fk -> company_id / tenant_id if model has those fields
    - coerce known types (e.g., column_index)
    - parse JSON-ish fields (e.g., filter_conditions)
    - drop unknown keys (but keep *_id that match a real FK)
    """
    data = dict(payload)
    field_names = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}

    # company_fk -> company_id / tenant_id
    if "company_fk" in data:
        fk_val = data.pop("company_fk")
        if "company" in field_names:
            data["company_id"] = _to_int_or_none(fk_val)
        elif "tenant" in field_names:
            data["tenant_id"] = _to_int_or_none(fk_val)

    if context_company_id and "company" in field_names:
        data["company_id"] = context_company_id

    # common coercions
    if "column_index" in data:
        data["column_index"] = _to_int_or_none(data.get("column_index"))
    if "filter_conditions" in data:
        data["filter_conditions"] = _parse_json_or_empty(data.get("filter_conditions"))

    # drop unknown keys except *_id matching real fields
    for k in list(data.keys()):
        if k in ("id",):  # always allowed
            continue
        try:
            model._meta.get_field(k)
        except FieldDoesNotExist:
            if not (k.endswith("_id") and k[:-3] in field_names):
                # keep *_fk for later resolution; others drop
                if not k.endswith("_fk"):
                    data.pop(k, None)
    return data

def _path_depth(row: Dict[str, Any]) -> int:
    # used to sort MPTT rows so parents come first
    for c in PATH_COLS:
        if c in row and row[c]:
            return len(str(row[c]).strip().replace(" > ", "\\").split("\\"))
    return 0

@shared_task
def process_import_records(
    company_id: int,
    model_name: str,
    rows: List[Dict[str, Any]],
    *,
    commit: bool = True
) -> List[Dict[str, Any]]:
    """
    Processa registros de importação:
      - Aplica substituições com auditoria.
      - Resolve *_fk e company_fk (inclusive referência por __row_id).
      - Suporte a MPTT 'path' (define parent/nome, remove colunas de caminho).
      - Ignora alterações no campo '__row_id'.
      - Registra id e nome da regra aplicada em cada campo alterado.
      - Cria ou atualiza instâncias dependendo da presença de 'id'.
      - Quando commit=False, salva em savepoint para gerar IDs e faz rollback ao final.
    """
    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        raise LookupError(f"MODEL_APP_MAP missing entry for '{model_name}'")
    model = apps.get_model(app_label, model_name)

    # Preserva original (se precisar inspecionar)
    original_rows = deepcopy(rows)

    # Substituições com auditoria
    rows, audit = apply_substitutions(
        rows,
        company_id=company_id,
        model_name=model_name,
        return_audit=True
    )

    # Index de auditoria por __row_id
    audit_by_rowid: Dict[Any, List[Dict[str, Any]]] = {}
    for change in audit:
        audit_by_rowid.setdefault(change.get("__row_id"), []).append(change)

    # Se MPTT, ordenar por profundidade do path (pais antes de filhos)
    if _is_mptt_model(model):
        rows = sorted(rows, key=_path_depth)

    results: List[Dict[str, Any]] = []
    row_id_map: Dict[str, Any] = {}  # __row_id -> instance

    with transaction.atomic():
        savepoint_id = transaction.savepoint() if not commit else None

        for row in rows:
            row_id = row.get("__row_id")
            observations = []
            for chg in audit_by_rowid.get(row_id, []):
                if chg.get("field") == "__row_id":
                    continue
                observations.append(
                    f"campo '{chg['field']}' alterado de '{chg['old']}' para '{chg['new']}' "
                    f"(regra id={chg['rule_id']}')"
                )

            # Monta payload base
            raw_payload = {k: v for k, v in row.items() if k != "__row_id"}

            try:
                # Normalizações genéricas (company_fk, tipos, json, drop unknowns)
                payload = _normalize_payload_for_model(model, raw_payload, context_company_id=company_id)

                # Resolver todos os *_fk
                fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                for fk_key in fk_keys:
                    field_name = fk_key[:-3]
                    fk_val = payload.pop(fk_key)
                    resolved = _resolve_fk(model, field_name, fk_val, row_id_map)
                    payload[field_name] = resolved

                # ----- MPTT PATH SUPPORT
                if _is_mptt_model(model):
                    path_val = _get_path_value(payload)
                    if path_val:
                        parts = _split_path(path_val)
                        if not parts:
                            raise ValueError(f"{model_name}: empty path.")
                        leaf_name = parts[-1]
                        parent = None
                        if len(parts) > 1:
                            parent = _resolve_parent_from_path_chain(model, parts[:-1])
                        # Set/override name & parent
                        payload['name'] = payload.get('name', leaf_name) or leaf_name
                        payload['parent'] = parent
                        # Remove colunas de caminho e pistas de parent conflitantes
                        payload.pop('parent_id', None)
                        payload.pop('parent_fk', None)
                        for c in PATH_COLS:
                            payload.pop(c, None)

                # CREATE or UPDATE
                if payload.get("id"):
                    instance = model.objects.get(id=payload["id"])
                    for field, value in payload.items():
                        setattr(instance, field, value)
                    action = "update"
                else:
                    instance = model(**payload)
                    action = "create"

                if commit or (not commit):
                    # Mesmo com commit=False salvamos para obter PKs e permitir referências via __row_id,
                    # e depois faremos rollback do savepoint ao final.
                    instance.save()

                # Mapeia __row_id -> instance para FKs subsequentes nesta carga
                if row_id:
                    row_id_map[row_id] = instance

                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "success",
                    "action": action,
                    "data": safe_model_dict(
                        instance,
                        exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active']
                    ),
                    "observations": observations,
                    "message": "ok",
                })

            except Exception as e:
                error_meta = exception_to_dict(e, include_stack=True)
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": payload if 'payload' in locals() else raw_payload,
                    "observations": observations,
                    "message": error_meta["summary"],
                    "error": error_meta,
                })

        # rollback total se era apenas preview
        if savepoint_id is not None:
            transaction.savepoint_rollback(savepoint_id)

    return results

@shared_task
def process_import_records2(company_id, model_name, rows, commit=True):
    """
    Processa uma lista de dicionários (rows) criando ou atualizando objetos.
    Retorna lista de resultados por registro, incluindo observações de substituição.
    """
    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        raise LookupError(f"No app mapping for model '{model_name}'")
    model = apps.get_model(app_label, model_name)

    # Copia profunda para preservar valores originais
    original_rows = [row.copy() for row in rows]
    # Aplica substituições in-place
    rows, audits = apply_substitutions(rows, company_id=company_id, model_name=model_name, return_audit=True)
    
    audit_by_index = {a["record_index"]: a for a in audits}
    
    results = []
    with transaction.atomic():
        for idx, row_data in enumerate(rows):
            row_id = row_data.pop('__row_id', None)
            observations = []
            # Calcula diferenças entre original e transformado
            original_data = original_rows[idx]
            for key, orig_val in original_data.items():
                new_val = row_data.get(key)
                if orig_val != new_val:
                    observations.append(
                        f"campo '{key}' alterado de '{orig_val}' para '{new_val}'"
                    )

            try:
                if commit and row_data.get('id'):
                    instance = model.objects.get(id=row_data['id'])
                    for field, value in row_data.items():
                        setattr(instance, field, value)
                    action = 'update'
                else:
                    instance = model(**row_data)
                    action = 'create'
                if commit:
                    instance.save()
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "success",
                    "action": action,
                    "data": safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                    "observations": observations,
                    "message": "ok"
                })
            except Exception as e:
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": row_data,
                    "observations": observations,
                    "message": str(e),
                })
    return results

@shared_task
def process_import_records3(
    company_id: int,
    model_name: str,
    rows: List[Dict[str, Any]],
    *,
    commit: bool = True
) -> List[Dict[str, Any]]:
    """
    Processa registros de importação:
      - Aplica substituições com auditoria.
      - Ignora alterações no campo '__row_id'.
      - Registra id e nome da regra aplicada em cada campo alterado.
      - Cria ou atualiza instâncias dependendo da presença de 'id'.
    """
    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        raise LookupError(f"MODEL_APP_MAP missing entry for '{model_name}'")

    model = apps.get_model(app_label, model_name)

    # Copia original apenas se quiser preservar (para logs mais profundos).
    # Não é estritamente necessário com auditoria de substituições.
    original_rows = deepcopy(rows)

    # Aplica substituições e coleta auditoria
    rows, audit = apply_substitutions(
        rows,
        company_id=company_id,
        model_name=model_name,
        return_audit=True
    )

    # cria um índice de auditoria por __row_id
    audit_by_rowid: Dict[Any, List[Dict[str, Any]]] = {}
    for change in audit:
        rowid = change.get("__row_id")
        audit_by_rowid.setdefault(rowid, []).append(change)
    results: List[Dict[str, Any]] = []
    with transaction.atomic():
        for row in rows:
            row_id = row.get("__row_id")
            # monta observações baseadas na auditoria (ignorando __row_id)
            observations = []
            for chg in audit_by_rowid.get(row_id, []):
                if chg.get("field") == "__row_id":
                    continue
                observations.append(
                    f"campo '{chg['field']}' alterado de '{chg['old']}' para '{chg['new']}' "
                    f"(regra id={chg['rule_id']}')"
                )
            try:
                payload = {k: v for k, v in row.items() if k != "__row_id"}
                if commit and payload.get("id"):
                    instance = model.objects.get(id=payload["id"])
                    for field, value in payload.items():
                        setattr(instance, field, value)
                    action = "update"
                else:
                    instance = model(**payload)
                    action = "create"
                if commit:
                    instance.save()
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "success",
                    "action": action,
                    "data": safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                    "observations": observations,
                    "message": "ok",
                })
            except Exception as e:
                error_meta = exception_to_dict(e, include_stack=True)  # or False in prod
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": payload,              # keep if you need to debug the input row
                    "observations": observations,
                    "message": error_meta["summary"],   # short, human-readable line
                    "error": error_meta,                # full structured details
                })
    return results

@shared_task
def finalize_import(results, company_id, model_name, commit=True):
    """
    Callback de um chord: junta todos os resultados de substituição, aplica a importação
    em lote único, e retorna a soma dos resultados.
    """
    # "results" é uma lista de listas (uma por chunk)
    rows = []
    for subset in results:
        rows.extend(subset)
    # Reutiliza process_import_records para gravação final (commit=True)
    return process_import_records(company_id, model_name, rows, commit=commit)

@shared_task
def dispatch_import(company_id, model_name, rows, commit=True, use_celery=True):
    """
    Decide se processa sincronicamente ou cria subtarefas de substituição em lotes.
    Se use_celery=True e o total excede IMPORT_MAX_BATCH_SIZE, divide em chunks
    e cria um chord cujo callback finaliza a importação de uma vez.
    """
    batch_size = getattr(settings, 'IMPORT_MAX_BATCH_SIZE', 1000)
    if not use_celery or len(rows) <= batch_size:
        return process_import_records(company_id, model_name, rows, commit=commit)

    # Divide em lotes e cria chord
    header = []
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i+batch_size]
        header.append(apply_substitutions.s(chunk, company_id, model_name))
    # O callback finalize_import será chamado quando todos os chunks concluírem
    return chord(header)(finalize_import.s(company_id, model_name, commit))