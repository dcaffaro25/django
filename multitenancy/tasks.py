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
def _friendly_db_message(exc: Exception) -> str:
    # quick mapper; expand as needed
    cause = getattr(exc, "__cause__", None)
    code = getattr(cause, "pgcode", None)
    if isinstance(exc, IntegrityError):
        if code == "23505": return "Unique constraint violation (duplicate)"
        if code == "23503": return "Foreign key violation (related row missing)"
        if code == "23502": return "NOT NULL violation (required field missing)"
        if code == "23514": return "CHECK constraint violation"
        return "Integrity constraint violation"
    if isinstance(exc, DataError):
        return "Invalid/too long value for column"
    if isinstance(exc, ValidationError):
        return "Validation error"
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

def _allowed_keys(model):
    return (
        {f.name for f in model._meta.fields}
        | {f.name + "_fk" for f in model._meta.fields}
        | set(PATH_COLS)
        | {"__row_id", "id"}
    )

def _filter_unknown(model, row: Dict[str, Any]):
    """Return (filtered_row, unknown_keys) keeping only allowed keys for this model."""
    allowed = _allowed_keys(model)
    filtered = {k: v for k, v in row.items() if k in allowed}
    unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
    return filtered, unknown

def _preflight_basic(model, rows: List[Dict[str, Any]]):
    """
    DB-free checks.
    - Missing required -> ERROR (blocks commit/preview row)
    - Unknown columns  -> WARN (row proceeds; columns will be ignored)
    Returns (errors_map, warnings_map) keyed by __row_id.
    """
    errors, warns = {}, {}

    required = {
        f.name for f in model._meta.fields
        if not f.null and not f.auto_created and not getattr(f, "has_default", False)
    }
    allowed = _allowed_keys(model)

    for i, row in enumerate(rows):
        rid = row.get("__row_id") or f"row{i+1}"
        payload = {k: v for k, v in row.items() if k != "__row_id"}

        missing = sorted([f for f in required if f not in payload or payload.get(f) in ("", None)])
        unknown = sorted([k for k in payload.keys() if k not in allowed])

        if missing:
            errors[rid] = {
                "code": "E-PREFLIGHT",
                "message": f"Missing required: {', '.join(missing)}",
                "fields": {"missing": missing, "unknown": []},
            }
        if unknown:
            warns[rid] = {
                "code": "W-UNKNOWN-COLS",
                "message": f"Ignoring unknown columns: {', '.join(unknown)}",
                "fields": {"missing": [], "unknown": unknown},
            }

    return errors, warns

def _quantize_decimal_fields(model, payload: dict) -> dict:
    """
    For every DecimalField in `model`, coerce payload[field] to Decimal and
    quantize to the field's decimal_places. Leaves missing/blank values alone.
    """
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, models.DecimalField):
            name = getattr(f, 'attname', f.name)
            if name in out and out[name] not in (None, ''):
                dp = getattr(f, 'decimal_places', 0) or 0
                q = Decimal('1').scaleb(-dp)  # 0.01 when dp=2, 1 when dp=0, etc.
                # go through str() to avoid binary float artifacts coming from Excel
                out[name] = Decimal(str(out[name])).quantize(q, rounding=ROUND_HALF_UP)
    return out


# ---- core executor ---------------------------------------------------------

from typing import Any, Dict, List
from django.db import transaction, connection
from django.apps import apps

# Assumes these exist in your project:
# MODEL_APP_MAP, apply_substitutions
# safe_model_dict, exception_to_dict, reset_pk_sequences
# _is_mptt_model, _path_depth, _get_path_value, _split_path, _resolve_parent_from_path_chain
# _normalize_payload_for_model, _resolve_fk, PATH_COLS

def execute_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    """
    One-shot import for all models in a file.
    - commit=False: DB-backed dry run (validates exactly like commit), then rollback
    - commit=True : cross-model atomic; if any row fails, rollback everything
    Unknown columns are treated as WARNINGS (status='warning') and ignored.
    The full warning text is appended to the row 'message'; no 'warnings' column is created.
    Always returns per-row diagnostics and includes the inferred 'action'.
    """

    # ----------------- helpers -----------------
    def _friendly_db_message(exc: Exception) -> str:
        from django.db import IntegrityError, DataError, DatabaseError
        from django.core.exceptions import ValidationError
        cause = getattr(exc, "__cause__", None)
        code = getattr(cause, "pgcode", None)
        if isinstance(exc, IntegrityError):
            if code == "23505": return "Unique constraint violation (duplicate)"
            if code == "23503": return "Foreign key violation (related row missing)"
            if code == "23502": return "NOT NULL violation (required field missing)"
            if code == "23514": return "CHECK constraint violation"
            return "Integrity constraint violation"
        if isinstance(exc, DataError):
            return "Invalid/too long value for column"
        if isinstance(exc, ValidationError):
            return "Validation error"
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

    def _allowed_keys(model):
        return (
            {f.name for f in model._meta.fields}
            | {f.name + "_fk" for f in model._meta.fields}
            | set(PATH_COLS) | {"__row_id", "id"}
        )

    def _filter_unknown(model, row: Dict[str, Any]):
        """
        Return (filtered_row, unknown_keys). Unknown keys are dropped and returned.
        """
        allowed = _allowed_keys(model)
        filtered = {k: v for k, v in row.items() if k in allowed}
        unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
        return filtered, unknown

    def _unknown_from_original_input(model, row_obj: Dict[str, Any]) -> List[str]:
        """
        Compute unknown keys from the original input for this row (used to compose message).
        """
        allowed = _allowed_keys(model)
        orig = row_obj.get("_original_input") or row_obj.get("payload") or {}
        return sorted([k for k in orig.keys() if k not in allowed and k != "__row_id"])

    def _preflight_missing_required(model, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        DB-free check: only missing required fields (true error).
        Returns a map: rid -> {"code": "...", "message": "...", "fields": {"missing":[...]} }
        """
        errors = {}
        required = {
            f.name for f in model._meta.fields
            if not f.null and not f.auto_created and not getattr(f, "has_default", False)
        }
        for i, row in enumerate(rows):
            rid = row.get("__row_id") or f"row{i+1}"
            payload = {k: v for k, v in row.items() if k != "__row_id"}
            missing = sorted([f for f in required if f not in payload or payload.get(f) in ("", None)])
            if missing:
                errors[rid] = {
                    "code": "E-PREFLIGHT",
                    "message": f"Missing required: {', '.join(missing)}",
                    "fields": {"missing": missing},
                }
        return errors

    def _coerce_pk(val):
        """Return int PK if val looks numeric (e.g., 3, '3', '3.0'); else None."""
        if val is None or val == "": return None
        if isinstance(val, int): return val
        if isinstance(val, float): return int(val) if float(val).is_integer() else None
        s = str(val).strip()
        if s.isdigit(): return int(s)
        try:
            f = float(s)
            return int(f) if f.is_integer() else None
        except Exception:
            return None

    def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
        """
        Decide 'create' vs 'update' and make payload safe for the ORM.
        Returns (action, pk or None, external_id or None)
        """
        ext_id = None
        pk = _coerce_pk(payload.get("id"))
        if pk is not None:
            payload["id"] = pk
            return "update", pk, None
        if "id" in payload:
            if "id" in original_input and original_input["id"] not in ("", None):
                ext_id = str(original_input["id"])
            payload.pop("id", None)
        return "create", None, ext_id
    # -------------------------------------------

    # 1) Prepare & normalize each sheet (no writes)
    prepared: List[Dict[str, Any]] = []
    models_in_order: List[str] = []
    any_prep_error = False

    for sheet in sheets:
        model_name = sheet["model"]
        app_label = MODEL_APP_MAP.get(model_name)
        if not app_label:
            prepared.append({
                "model": model_name,
                "rows": [],
                "had_error": True,
                "sheet_error": f"MODEL_APP_MAP missing entry for '{model_name}'",
            })
            any_prep_error = True
            continue

        model = apps.get_model(app_label, model_name)
        raw_rows = sheet["rows"]

        # substitutions + audit (pure-Python)
        rows, audit = apply_substitutions(
            raw_rows, company_id=company_id, model_name=model_name, return_audit=True
        )
        audit_by_rowid = {}
        for ch in audit:
            audit_by_rowid.setdefault(ch.get("__row_id"), []).append(ch)

        # ensure parents first for MPTT
        if _is_mptt_model(model):
            rows = sorted(rows, key=_path_depth)

        # preflight (only missing required -> error)
        preflight_err = _preflight_missing_required(model, rows)

        packed_rows = []
        had_err = False

        for idx, row in enumerate(rows):
            rid = row.get("__row_id") or f"row{idx+1}"
            observations = _row_observations(audit_by_rowid, rid)
            original_input = {k: v for k, v in row.items() if k != "__row_id"}

            try:
                # Drop unknown columns now (they will be warned in message later)
                filtered_input, _unknown_cols = _filter_unknown(model, original_input)

                payload = _normalize_payload_for_model(
                    model, filtered_input, context_company_id=company_id
                )
                
                payload = _quantize_decimal_fields(model, payload)
                
                # MPTT: keep name; defer parent resolution to commit
                if _is_mptt_model(model):
                    path_val = _get_path_value(payload)
                    if path_val:
                        parts = _split_path(path_val)
                        if not parts:
                            raise ValueError(f"{model_name}: empty path.")
                        leaf = parts[-1]
                        payload['name'] = payload.get('name', leaf) or leaf
                        payload.pop('parent_id', None)
                        payload.pop('parent_fk', None)
                        for c in PATH_COLS:
                            payload.pop(c, None)

                # Infer action now (so it's available even on error)
                action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)

                row_obj = {
                    "__row_id": rid,
                    "payload": payload,
                    "_original_input": original_input,
                    "observations": observations,
                    "action": action,
                    "external_id": ext_id,
                }

                # Errors (missing required)
                if rid in preflight_err:
                    # Append unknown detail into message as well
                    unknown_cols_now = _unknown_from_original_input(model, row_obj)
                    msg = preflight_err[rid]["message"]
                    if unknown_cols_now:
                        msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                    row_obj.update({
                        "status": "error",
                        "preflight_error": {**preflight_err[rid], "message": msg},
                        "message": msg,
                    })
                    had_err = True
                else:
                    # Decide warning/ok based on unknowns
                    unknown_cols_now = _unknown_from_original_input(model, row_obj)
                    if unknown_cols_now:
                        row_obj.update({
                            "status": "warning",
                            "message": f"validated; Ignoring unknown columns: {', '.join(unknown_cols_now)}",
                        })
                    else:
                        row_obj.update({
                            "status": "ok",
                            "message": "validated",
                        })

                packed_rows.append(row_obj)

            except Exception as e:
                had_err = True
                err = exception_to_dict(e, include_stack=False)
                if not err.get("summary"):
                    err["summary"] = _friendly_db_message(e)
                # best-effort normalize for action display
                try:
                    tmp_payload = _normalize_payload_for_model(model, filtered_input, context_company_id=company_id)
                except Exception:
                    tmp_payload = filtered_input
                action, pk, ext_id = _infer_action_and_clean_id(dict(tmp_payload), original_input)
                # Include unknowns in message as well
                unknown_cols_now = _unknown_from_original_input(model, {
                    "_original_input": original_input, "payload": tmp_payload
                })
                msg = err["summary"]
                if unknown_cols_now:
                    msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                packed_rows.append({
                    "__row_id": rid,
                    "status": "error",
                    "payload": tmp_payload,
                    "_original_input": original_input,
                    "observations": observations,
                    "message": msg,
                    "error": {**err, "summary": msg},
                    "action": action,
                    "external_id": ext_id,
                })

        any_prep_error = any_prep_error or had_err
        prepared.append({"model": model_name, "rows": packed_rows, "had_error": had_err})
        models_in_order.append(model_name)

    # 2) PREVIEW (DB-backed dry run with rollback)
    if not commit:
        models_touched = []
        result_payload = []
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            outer_sp = transaction.savepoint()
            for model_name in models_in_order:
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)
                models_touched.append(model)

                row_map = {}  # __row_id -> instance (intra-model)
                rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                out_rows = []

                for row in rows:
                    rid = row["__row_id"]

                    # If preflight already failed, surface it and skip DB interaction
                    if row.get("status") == "error" and row.get("preflight_error"):
                        out_rows.append({
                            "__row_id": rid,
                            "status": "error",
                            "action": row.get("action"),
                            "data": row.get("_original_input") or row.get("payload") or {},
                            "message": row["preflight_error"]["message"],  # already includes unknown detail
                            "error": row["preflight_error"],
                            "observations": row.get("observations", []),
                            "external_id": row.get("external_id"),
                        })
                        continue

                    payload = dict(row.get("payload") or {})
                    original_input = row.get("_original_input") or payload.copy()
                    action = row.get("action") or "create"

                    # Recompute unknowns from original input for the final message
                    unknown_cols_now = _unknown_from_original_input(model, row)

                    try:
                        # Resolve *_fk
                        for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                            field_name = fk_key[:-3]
                            fk_val = payload.pop(fk_key)
                            payload[field_name] = _resolve_fk(model, field_name, fk_val, row_map)

                        # Resolve MPTT parent
                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload['parent'] = parent
                                payload.pop('parent_id', None)
                            
                        payload = _quantize_decimal_fields(model, payload)    
                        
                        with transaction.atomic():
                            if action == "update":
                                instance = model.objects.select_for_update().get(id=payload["id"])
                                for f, v in payload.items():
                                    setattr(instance, f, v)
                            else:
                                instance = model(**payload)

                            if hasattr(instance, "full_clean"):
                                instance.full_clean()  # includes validate_unique()

                            instance.save()

                        if rid:
                            row_map[rid] = instance

                        msg = "ok"
                        status_val = "success"
                        if unknown_cols_now:
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        out_rows.append({
                            "__row_id": rid,
                            "status": status_val,
                            "action": action,
                            "data": safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active']),
                            "message": msg,
                            "observations": row.get("observations", []),
                            "external_id": row.get("external_id"),
                        })

                    except Exception as e:
                        err = exception_to_dict(e, include_stack=False)
                        base = err.get("summary") or _friendly_db_message(e)
                        if unknown_cols_now:
                            base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                        out_rows.append({
                            "__row_id": rid,
                            "status": "error",
                            "action": action,
                            "data": original_input,
                            "message": base,
                            "error": {**err, "summary": base},
                            "observations": row.get("observations", []),
                            "external_id": row.get("external_id"),
                        })

                result_payload.append({"model": model_name, "result": out_rows})

            # Rollback all side-effects and reset sequences
            transaction.savepoint_rollback(outer_sp)
            reset_pk_sequences(models_touched)

        return {"committed": False, "reason": "preview", "imports": result_payload}

    # 3) COMMIT (cross-model atomic), but bail early on prep errors (warnings do NOT block)
    if any_prep_error:
        return {
            "committed": False,
            "reason": "prep_errors",
            "imports": [{"model": b["model"], "result": b["rows"]} for b in prepared],
        }

    models_touched: List[Any] = []
    result_payload: List[Dict[str, Any]] = []
    any_row_error = False

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

        outer_sp = transaction.savepoint()

        for model_name in models_in_order:
            app_label = MODEL_APP_MAP[model_name]
            model = apps.get_model(app_label, model_name)
            models_touched.append(model)

            row_map = {}  # __row_id -> instance (within this model)
            rows = next(b["rows"] for b in prepared if b["model"] == model_name)

            for row in rows:
                rid = row["__row_id"]

                # Skip rows that already failed preflight (warnings don't block)
                if row.get("status") == "error" and row.get("preflight_error"):
                    row.update({
                        "status": "error",
                        "action": row.get("action"),
                        "data": row.get("_original_input") or row.get("payload") or {},
                        "message": row["preflight_error"]["message"],
                        "error": row["preflight_error"],
                    })
                    any_row_error = True
                    continue

                payload = dict(row.get("payload") or {})
                original_input = row.get("_original_input") or payload.copy()
                action = row.get("action") or "create"

                # Recompute unknowns (from original input) for final message
                unknown_cols_now = _unknown_from_original_input(model, row)

                try:
                    # Resolve *_fk now
                    for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                        field_name = fk_key[:-3]
                        fk_val = payload.pop(fk_key)
                        payload[field_name] = _resolve_fk(model, field_name, fk_val, row_map)

                    # Resolve MPTT parent chain
                    if _is_mptt_model(model):
                        path_val = _get_path_value(payload)
                        if path_val:
                            parts = _split_path(path_val)
                            parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                            payload['parent'] = parent
                            payload.pop('parent_id', None)
                    
                    payload = _quantize_decimal_fields(model, payload)
                    
                    with transaction.atomic():
                        if action == "update":
                            instance = model.objects.select_for_update().get(id=payload["id"])
                            for f, v in payload.items():
                                setattr(instance, f, v)
                        else:
                            instance = model(**payload)

                        if hasattr(instance, "full_clean"):
                            instance.full_clean()

                        instance.save()

                    if rid:
                        row_map[rid] = instance

                    msg = "ok"
                    status_val = "success"
                    if unknown_cols_now:
                        status_val = "warning"
                        msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                    row.update({
                        "status": status_val,
                        "action": action,
                        "data": safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active']),
                        "message": msg,
                    })

                except Exception as e:
                    any_row_error = True
                    err = exception_to_dict(e, include_stack=False)
                    base = err.get("summary") or _friendly_db_message(e)
                    if unknown_cols_now:
                        base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                    row.update({
                        "status": "error",
                        "action": action,
                        "data": original_input,
                        "message": base,
                        "error": {**err, "summary": base},
                    })

            result_payload.append({"model": model_name, "result": rows})

        if any_row_error:
            transaction.savepoint_rollback(outer_sp)
            reset_pk_sequences(models_touched)
            return {"committed": False, "reason": "row_errors", "imports": result_payload}

        # Success → commit all
        return {"committed": True, "imports": result_payload}


# Celery entrypoint: one task per file
@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)