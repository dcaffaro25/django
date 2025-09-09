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
                results.append({
                    "model": model_name,
                    "__row_id": row_id,
                    "status": "error",
                    "action": None,
                    "data": payload,
                    "observations": observations,
                    "message": str(e),
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