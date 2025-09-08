# tasks.py (e.g. in multitenancy/tasks.py)
from celery import shared_task, group, chord
from django.core.mail import send_mail
from django.conf import settings
import smtplib
from django.apps import apps
from multitenancy.formula_engine import apply_substitutions
from django.db import transaction
from .api_utils import safe_model_dict, MODEL_APP_MAP
from multitenancy.models import IntegrationRule
from copy import deepcopy
from typing import Any, Dict, List, Tuple
import contextlib

from celery import shared_task
from django.apps import apps
from django.db import transaction

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
                    "data": safe_model_dict(instance),
                    "observations": observations,
                    "message": "ok"
                })
            except Exception as e:
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": {},
                    "observations": observations,
                    "message": str(e),
                })
    return results

@shared_task
def process_import_records(
    company_id: int,
    model_name: str,
    rows: List[Dict[str, Any]],
    commit: bool = True,
) -> List[Dict[str, Any]]:
    """
    Processa um lote de registros (list[dict]) e retorna um relatório por linha:
      - 'status': success/error
      - 'action': 'create' ou 'update'
      - 'data': dicionário serializado do modelo criado/atualizado (quando success)
      - 'observations': lista de textos explicando cada alteração (campo, de, para, e regras aplicadas)
      - Ignora qualquer mudança no campo especial '__row_id'
      - Inclui id e nome da(s) regra(s) de substituição aplicada(s)

    Caso commit=False, a função simula a importação e não salva no banco (mas ainda aplica substituições para fins de preview).
    """
    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        return [{
            "model": model_name,
            "__row_id": None,
            "status": "error",
            "action": None,
            "data": {},
            "observations": [],
            "message": f"Unknown model '{model_name}' (MODEL_APP_MAP missing).",
        }]

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError as e:
        return [{
            "model": model_name,
            "__row_id": None,
            "status": "error",
            "action": None,
            "data": {},
            "observations": [],
            "message": f"Model lookup error: {e}",
        }]

    # Copia profunda das linhas originais para diff (quando audit não traz 'from')
    originals: List[Dict[str, Any]] = deepcopy(rows)

    # Aplica substituições com auditoria
    rows_sub, audit_map = apply_substitutions(rows, company_id=company_id, model_name=model_name, return_audit=True)


    results: List[Dict[str, Any]] = []

    # Bloco atomic único para todo o lote (rollback se commit=False simulando)
    with transaction.atomic():
        for idx, row_data in enumerate(rows_sub):
            # Certifique-se de trabalhar com dicts; não suportamos listas/tuplas aqui
            if not isinstance(row_data, dict):
                results.append({
                    "model": model_name,
                    "__row_id": None,
                    "status": "error",
                    "action": None,
                    "data": {},
                    "observations": [],
                    "message": "Row is not a dict; only dict-based imports are supported.",
                })
                continue

            original = originals[idx]
            row_id = row_data.get("__row_id")
            # Monta observações de acordo com a auditoria e ignora __row_id
            observations: List[str] = []
            rec_audit = audit_map.get(idx, {})

            for field, changes in rec_audit.items():
                if field == "__row_id":
                    continue  # ignora mudanças no identificador temporário

                for change in changes:
                    # Usa valores da auditoria (old, new) se disponíveis
                    old_val = change.get("from", original.get(field))
                    new_val = change.get("to", row_data.get(field))
                    rules_info = ", ".join(
                        f"{r['name']}({r['id']})" for r in change.get("rules", [])
                    )
                    observations.append(
                        f"campo '{field}' alterado de '{old_val}' para '{new_val}' (regras: {rules_info or 'n/a'})"
                    )

            try:
                # Decide se atualiza ou cria
                instance = None
                action = None

                # Retira __row_id antes de persistir
                row_data = {k: v for k, v in row_data.items() if k != "__row_id"}

                if commit and row_data.get("id"):
                    # UPDATE
                    instance = model.objects.get(id=row_data["id"])
                    for f, v in row_data.items():
                        setattr(instance, f, v)
                    action = "update"
                    if commit:
                        instance.save()
                else:
                    # CREATE
                    instance = model(**row_data)
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
                # Em caso de falha por linha, ainda registra as observações
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": {},
                    "observations": observations,
                    "message": str(e),
                })

        # Se commit=False, desfaz qualquer alteração para simular a importação
        if not commit:
            # Provoca um rollback ao final, mas mantém o 'results'
            with contextlib.suppress(Exception):
                raise transaction.TransactionManagementError("Preview mode: rolling back all changes")

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