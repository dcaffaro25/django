# tasks.py (e.g. in multitenancy/tasks.py)
from django.db import transaction, connection, IntegrityError, DataError, DatabaseError
from django.core.exceptions import ValidationError
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
from core.utils.db_sequences import reset_pk_sequences


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

# ---------- utilities ----------
def _friendly_db_message(exc: Exception) -> str:
    from django.db import IntegrityError, DataError, DatabaseError
    from django.core.exceptions import ValidationError
    if isinstance(exc, IntegrityError):
        cause = getattr(exc, "__cause__", None)
        detail = getattr(cause, "diag", None)
        if detail and getattr(detail, "constraint_name", None):
            return f"Constraint violation ({detail.constraint_name})"
        return "Integrity constraint violation (duplicate, null, or FK error)"
    if isinstance(exc, DataError):
        return "Invalid or too-long data for a column"
    if isinstance(exc, ValidationError):
        return f"Validation error: {exc}"
    if isinstance(exc, DatabaseError):
        return "Database error"
    return str(exc)

def _row_observations(audit_by_rowid, row_id):
    obs = []
    for chg in audit_by_rowid.get(row_id, []):
        if chg.get("field") == "__row_id":
            continue
        obs.append(
            f"campo '{chg['field']}' alterado de '{chg['old']}' para '{chg['new']}' "
            f"(regra id={chg['rule_id']}')"
        )
    return obs

# ---------- 1) PREPARE PER MODEL (NO WRITES) ----------
@shared_task
def prepare_model_for_import(company_id: int, model_name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply substitutions and normalize payloads. Validate as much as possible
    WITHOUT writing to the DB, so we can parallelize safely.
    Returns per-row diagnostics and a normalized payload for commit phase.
    """
    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        return {"model": model_name, "error": f"MODEL_APP_MAP missing entry for '{model_name}'"}

    model = apps.get_model(app_label, model_name)

    # Substitutions + audit (pure-Python)
    rows, audit = apply_substitutions(rows, company_id=company_id, model_name=model_name, return_audit=True)
    audit_by_rowid: Dict[Any, List[Dict[str, Any]]] = {}
    for change in audit:
        audit_by_rowid.setdefault(change.get("__row_id"), []).append(change)

    # Reorder MPTT so parents come first (no DB writes yet)
    if _is_mptt_model(model):
        rows = sorted(rows, key=lambda r: len(str(_get_path_value(r) or "").replace(" > ", "\\").split("\\")) or 0)

    prepared = []
    had_error = False

    for row in rows:
        row_id = row.get("__row_id")
        raw_payload = {k: v for k, v in row.items() if k != "__row_id"}
        observations = _row_observations(audit_by_rowid, row_id)

        try:
            payload = _normalize_payload_for_model(model, raw_payload, context_company_id=company_id)

            # Resolve *_fk that are numeric or __row_id references to PREVIOUS rows only by marker.
            # We DO NOT hit DB here; we only keep the raw value for commit resolution.
            fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
            # Keep *_fk as is for the commit phase (where we will resolve with DB)
            for fk_key in fk_keys:
                pass

            # MPTT path cleanup (name/parent will be resolved at commit)
            if _is_mptt_model(model):
                path_val = _get_path_value(payload)
                if path_val:
                    parts = _split_path(path_val)
                    if not parts:
                        raise ValueError(f"{model_name}: empty path.")
                    leaf_name = parts[-1]
                    payload['name'] = payload.get('name', leaf_name) or leaf_name
                    # parent resolution deferred to commit
                    payload.pop('parent_id', None)
                    payload.pop('parent_fk', None)
                    for c in PATH_COLS:
                        payload.pop(c, None)

            prepared.append({
                "__row_id": row_id,
                "status": "ok",
                "payload": payload,
                "observations": observations,
                "message": "validated",
            })

        except Exception as e:
            had_error = True
            err = exception_to_dict(e, include_stack=False)
            if not err.get("summary"):
                err["summary"] = _friendly_db_message(e)
            prepared.append({
                "__row_id": row_id,
                "status": "error",
                "payload": raw_payload,
                "observations": observations,
                "message": err["summary"],
                "error": err,
            })

    return {"model": model_name, "had_error": had_error, "rows": prepared}

# ---------- 2) FINALIZE FOR WHOLE FILE (ONE ATOMIC TX ACROSS MODELS) ----------
@shared_task
def finalize_file_import(prepared_list: List[Dict[str, Any]], company_id: int, sheet_order: List[str], commit: bool):
    """
    Receives list of {"model": ..., "rows": [...], "had_error": bool} from all sheets.
    If commit=False -> return diagnostics only (no writes).
    If commit=True:
      - If any prep error -> NO WRITES, return diagnostics.
      - Else open ONE atomic() and apply all models. If any row fails -> rollback ALL.
    """
    # Sort outputs by original sheet order
    prepared_by_model = {x["model"]: x for x in prepared_list if isinstance(x, dict) and "model" in x}
    ordered_models = [m for m in sheet_order if m in prepared_by_model]

    # If preview or early prep errors, just return
    any_prep_error = any(prepared_by_model[m].get("had_error") for m in ordered_models)
    result_payload = []
    models_touched = []

    if not commit or any_prep_error:
        # Pass-through (no DB writes)
        for m in ordered_models:
            result_payload.append({"model": m, "result": prepared_by_model[m]["rows"]})
        return {
            "committed": False,
            "reason": "preview" if not commit else "prep_errors",
            "imports": result_payload
        }

    # COMMIT PHASE: one transaction for the whole file
    from django.db import IntegrityError
    # open a single atomic block covering ALL models
    with transaction.atomic():
        # Make deferrable constraints fire per statement (Postgres)
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

        outer_sp = transaction.savepoint()
        any_error = False

        # stash of __row_id -> instance for intra-model references (resets per model)
        for model_name in ordered_models:
            app_label = MODEL_APP_MAP[model_name]
            model = apps.get_model(app_label, model_name)
            models_touched.append(model)
            row_map = {}  # __row_id -> instance (for this model)

            rows = prepared_by_model[model_name]["rows"]

            for row in rows:
                row_id = row["__row_id"]
                observations = row.get("observations", [])
                payload = dict(row.get("payload", {}))
                raw_payload = dict(payload)

                # per-row savepoint: capture error but continue gathering diagnostics
                try:
                    # Resolve *_fk now (DB lookups + __row_id indirection within same model)
                    fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                    for fk_key in fk_keys:
                        field_name = fk_key[:-3]
                        fk_val = payload.pop(fk_key)
                        # resolve using prior created instances (row_map) or direct ids
                        payload[field_name] = _resolve_fk(model, field_name, fk_val, row_map)

                    # Resolve MPTT parent chain if applicable
                    if _is_mptt_model(model):
                        path_val = _get_path_value(payload)
                        if path_val:
                            parts = _split_path(path_val)
                            parent = None
                            if len(parts) > 1:
                                parent = _resolve_parent_from_path_chain(model, parts[:-1])
                            payload['parent'] = parent
                            payload.pop('parent_id', None)

                    with transaction.atomic():
                        if payload.get("id"):
                            instance = model.objects.select_for_update().get(id=payload["id"])
                            for field, value in payload.items():
                                setattr(instance, field, value)
                            action = "update"
                        else:
                            instance = model(**payload)
                            action = "create"

                        instance.save()

                    if row_id:
                        row_map[row_id] = instance

                    row.update({
                        "status": "success",
                        "action": action,
                        "data": safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active']),
                        "message": "ok",
                    })

                except Exception as e:
                    any_error = True
                    err = exception_to_dict(e, include_stack=False)
                    if not err.get("summary"):
                        err["summary"] = _friendly_db_message(e)
                    row.update({
                        "status": "error",
                        "action": None,
                        "data": raw_payload,
                        "message": err["summary"],
                        "error": err,
                    })

            # Append per model block into final payload (after processing all rows)
            result_payload.append({"model": model_name, "result": rows})

        if any_error:
            transaction.savepoint_rollback(outer_sp)
            # optional: reset sequences for all models touched (IDs may have advanced in failed rows)
            reset_pk_sequences(models_touched)
            return {
                "committed": False,
                "reason": "row_errors",
                "imports": result_payload
            }

        # No errors → let the outer atomic commit
        return {
            "committed": True,
            "imports": result_payload
        }