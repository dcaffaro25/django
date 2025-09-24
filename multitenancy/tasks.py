# tasks.py (multitenancy/tasks.py)
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import smtplib
import logging
import time
import uuid
from contextvars import ContextVar
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.mail import send_mail
from django.db import (
    IntegrityError,
    DataError,
    DatabaseError,
    connection,
    models as dj_models,
    transaction,
)
from django.db.models import NOT_PROVIDED

from core.utils.db_sequences import reset_pk_sequences
from core.utils.exception_utils import exception_to_dict
from multitenancy.formula_engine import apply_substitutions
from multitenancy.models import ImportSnapshot, IntegrationRule
from .api_utils import (
    MODEL_APP_MAP,
    PATH_COLS,
    _get_path_value,
    _is_mptt_model,
    _resolve_parent_from_path_chain,
    _split_path,
    safe_model_dict,
    # NaN/NaT-safe helpers used in canonicalization:
    _is_missing,
    _to_int_or_none_soft,
    _to_int_or_none,
    _parse_json_or_empty,
    _to_bool,
    _norm_row_key,
    _path_depth,
)

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

from django.db import transaction as db_txn, models
from django.core.exceptions import ValidationError

# ----------------------------------------------------------------------
# Logging / verbosity
# ----------------------------------------------------------------------
logger = logging.getLogger("importer")
sql_logger = logging.getLogger("importer.sql")

# Reserved LogRecord attribute names — MUST NOT be in `extra`
_RESERVED_LOG_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName", "process",
    "processName", "asctime", "message", "stacklevel"
}

# Per-run contextual fields (propagated via logger.extra)
_run_id_ctx = ContextVar("run_id", default="-")
_company_ctx = ContextVar("company_id", default="-")
_model_ctx = ContextVar("model", default="-")
_row_ctx = ContextVar("row_id", default="-")

def _log_extra(**kw):
    # Sanitize any accidental reserved keys passed in
    cleaned = {}
    for k, v in kw.items():
        cleaned[("ctx_" + k) if k in _RESERVED_LOG_ATTRS else k] = v
    return {
        "extra": {
            "run_id": _run_id_ctx.get(),
            "company_id": _company_ctx.get(),
            "model": _model_ctx.get(),
            "row_id": _row_ctx.get(),
            **cleaned,
        }
    }

def _import_debug_enabled() -> bool:
    # Prefer settings flag; fallback to env
    val = getattr(settings, "IMPORT_DEBUG", None)
    if val is None:
        val = os.getenv("IMPORT_DEBUG", "0")
    return str(val).lower() in {"1", "true", "yes", "y", "on"}

def _vlog(msg: str, **fields):
    """Verbose log at INFO when IMPORT_DEBUG=1, otherwise DEBUG (so it’s visible with DEBUG on)."""
    if _import_debug_enabled():
        logger.info(msg, **_log_extra(**fields))
    else:
        logger.debug(msg, **_log_extra(**fields))

IMPORT_VERBOSE_FK = os.getenv("IMPORT_VERBOSE_FK", "0").lower() in {"1", "true", "yes", "y", "on"}

class _SlowSQL:
    """Capture slow queries during an import run only (keeps global DB logs quiet)."""
    def __init__(self, threshold_ms: int = 200):
        self.threshold = threshold_ms / 1000.0
        self._cm = None

    def __enter__(self):
        try:
            def wrapper(execute, sql, params, many, context):
                t0 = time.monotonic()
                try:
                    return execute(sql, params, many, context)
                finally:
                    dt = time.monotonic() - t0
                    if dt >= self.threshold:
                        # keep the log lean; params may be large/noisy
                        sql_logger.info(
                            "slow_sql",
                            **_log_extra(duration_ms=int(dt * 1000), many=bool(many), sql=sql[:1000])
                        )
            self._cm = connection.execute_wrapper(wrapper)
            self._cm.__enter__()  # type: ignore[attr-defined]
        except Exception:
            # Older Django versions or non-standard backends: just no-op
            self._cm = None
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc, tb)  # type: ignore[attr-defined]
        finally:
            return False

# ----------------------------------------------------------------------
# Email helpers
# ----------------------------------------------------------------------

def _sanity_check_required_fks(model, payload: Dict[str, Any], original_input: Dict[str, Any], merged_map_keys: List[str]) -> List[Tuple[str, Any]]:
    """
    Return a list of (field_name, token) for non-nullable FKs that were provided as <field>_fk
    in the original input but remain unresolved (payload[<field>] and payload[<field>_id] are both None).
    """
    issues: List[Tuple[str, Any]] = []
    for f in model._meta.get_fields():
        if not isinstance(f, dj_models.ForeignKey) or getattr(f, "null", False):
            continue

        base = f.name
        token = original_input.get(f"{base}_fk", None)

        # Was *_fk provided in input?
        provided = token not in (None, "")
        if provided and isinstance(token, float) and token != token:
            provided = False  # NaN

        if not provided:
            continue

        # Consider both field and its attname
        value = payload.get(base, None)
        if value is None:
            attname = getattr(f, "attname", None)
            if attname:
                value = payload.get(attname, None)

        if value is None:
            issues.append((base, token))
    return issues

@shared_task(bind=True, autoretry_for=(smtplib.SMTPException, ConnectionError), retry_backoff=True, max_retries=5)
def send_user_invite_email(self, subject, message, to_email):
    """Send user invite email with retry/backoff."""
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_email(self, subject, message, to_email):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)

# ----------------------------------------------------------------------
# Integration triggers
# ----------------------------------------------------------------------

@shared_task
def execute_integration_rule(rule_id, payload):
    rule = IntegrationRule.objects.get(pk=rule_id)
    return rule.run_rule(payload)

@shared_task
def trigger_integration_event(company_id, event_name, payload):
    rules = (
        IntegrationRule.objects
        .filter(company_id=company_id, is_active=True, triggers__icontains=event_name)
        .order_by('execution_order')
    )
    for rule in rules:
        if rule.use_celery:
            execute_integration_rule.delay(rule.id, payload)
        else:
            execute_integration_rule(rule.id, payload)

# ----------------------------------------------------------------------
# Import helpers
# ----------------------------------------------------------------------

@dataclass
class PendingRef:
    """Represents an FK pointing to a row created in this run (unsaved pk)."""
    model: type
    token: str  # e.g. 't1'

@dataclass
class ImportContext:
    run_id: str
    company_id: int
    commit: bool
    row_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})
    pk_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})

def _log(level: int, msg: str, ic: ImportContext, *, model: str = "-", row_id: str = "-", **fields):
    extra = {"run_id": ic.run_id, "company": ic.company_id, "model": model, "row_id": row_id, **fields}
    logger.log(level, msg, extra=extra)

class RateLimitFilter(logging.Filter):
    def __init__(self, burst=200, cache=None):
        super().__init__()
        self.cache = {} if cache is None else cache
        self.burst = burst
    def filter(self, record):
        key = getattr(record, "msg", "")
        count = self.cache.get(key, 0)
        if count >= self.burst:
            return False
        self.cache[key] = count + 1
        return True

def _stringify_instance(obj: models.Model) -> str:
    try:
        return str(obj)
    except Exception:
        return f"{obj.__class__.__name__}(id={getattr(obj, 'pk', None)})"

def _register_row_token(global_map_inst: Dict[str, Any],
                        global_map_pk: Dict[str, int],
                        rid: str,
                        instance: Any):
    """Store both instance and its PK by token."""
    if not rid:
        return
    pk = getattr(instance, "pk", None)
    global_map_inst[_norm_row_key(rid)] = instance
    if isinstance(pk, int):
        global_map_pk[_norm_row_key(rid)] = pk

def _resolve_token_from_maps(token: str,
                             local_inst: Dict[str, Any],
                             local_pk: Dict[str, int],
                             global_inst: Dict[str, Any],
                             global_pk: Dict[str, int]) -> Any:
    token = _norm_row_key(token)
    if token in local_inst:
        return local_inst[token]
    if token in global_inst:
        return global_inst[token]
    if token in local_pk:
        return local_pk[token]
    if token in global_pk:
        return global_pk[token]
    return None

def _get_field_and_remote_model(model_cls, field_name: str):
    field = model_cls._meta.get_field(field_name)
    rel = getattr(field, "remote_field", None)
    if rel is None or rel.model is None:
        raise LookupError(f"{model_cls.__name__}.{field_name} is not a ForeignKey")
    remote_model = rel.model
    remote_name = remote_model._meta.object_name
    return field, remote_model, remote_name

def _assign_fk_value(model_cls, field_name: str, resolved_value: Any, payload: dict) -> tuple[str, Any]:
    """
    Assign resolved FK value into payload using either base field (instance)
    or attname (pk int). Returns (where_key, value_assigned) for logging.
    """
    field = model_cls._meta.get_field(field_name)
    attname = getattr(field, "attname", field_name)
    if isinstance(resolved_value, int):
        payload.pop(field_name, None)        # avoid "entity=9"
        payload[attname] = resolved_value    # use "entity_id=9"
        return attname, resolved_value
    else:
        payload[field_name] = resolved_value # instance -> "entity"
        payload.pop(attname, None)
        return field_name, resolved_value

def _resolve_fk(model_cls, field_name: str, raw_value: Any, row_id_map: Dict[str, Any]) -> Any:
    """
    Return a value suitable for assignment via _assign_fk_value:
      - int PK   -> will be written to <attname> (e.g. entity_id)
      - instance -> will be written to <field>   (e.g. entity)
      - token    -> looked up in row_id_map (instance or int expected)
    """
    if raw_value in (None, ""):
        return None

    field = model_cls._meta.get_field(field_name)
    remote_model = getattr(field, "remote_field", None).model if getattr(field, "remote_field", None) else None
    known_tokens = list(row_id_map.keys())

    # Instance?
    if isinstance(raw_value, models.Model):
        if remote_model and not isinstance(raw_value, remote_model):
            raise ValueError(f"{model_cls.__name__}.{field_name} expects {remote_model.__name__} instance, got {raw_value.__class__.__name__}")
        return raw_value

    # int or "123"?
    if isinstance(raw_value, int) or (isinstance(raw_value, str) and raw_value.strip().isdigit()):
        return int(raw_value)

    # token form (e.g., "t1" or "Model:t1")
    token = _norm_row_key(str(raw_value).strip())
    candidate = row_id_map.get(token)

    if candidate is None and ":" in token:
        maybe_model, maybe_token = token.split(":", 1)
        candidate = row_id_map.get(_norm_row_key(maybe_token))

    if candidate is not None:
        if isinstance(candidate, models.Model):
            if remote_model and not isinstance(candidate, remote_model):
                pk = getattr(candidate, "pk", None)
                if isinstance(pk, int):
                    return pk
                raise ValueError(f"Token {token!r} resolved to {candidate.__class__.__name__}, incompatible with {remote_model.__name__}")
            return candidate
        if isinstance(candidate, int):
            return candidate

    preview = ", ".join(known_tokens[:20]) + (" ..." if len(known_tokens) > 20 else "")
    raise ValueError(
        f"Invalid FK reference format {raw_value!r} for field '{field_name}'. "
        f"Expected numeric id, instance of {remote_model.__name__ if remote_model else 'related model'}, "
        f"or a run token present in known __row_id keys [{preview}]"
    )

def _build_instance(model_cls: type, payload: dict) -> models.Model:
    return model_cls(**payload)

def _full_clean_preview(instance: models.Model, exclude_fields: List[str]):
    instance.full_clean(exclude=exclude_fields, validate_unique=False)

def _normalize_payload_for_model(model, payload: Dict[str, Any], *, context_company_id=None):
    """
    - map company_fk -> company_id / tenant_id if model has those fields
    - coerce known types (column_index, filter_conditions)
    - drop unknown keys (but keep *_id that match a real FK and keep *_fk for resolution)
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

    if "column_index" in data:
        data["column_index"] = _to_int_or_none(data.get("column_index"))
    if "filter_conditions" in data:
        data["filter_conditions"] = _parse_json_or_empty(data.get("filter_conditions"))

    # drop unknown keys except *_id matching real fields and *_fk (will be resolved later)
    for k in list(data.keys()):
        if k in ("id",):
            continue
        try:
            model._meta.get_field(k)
        except FieldDoesNotExist:
            if not (k.endswith("_id") and k[:-3] in field_names) and not k.endswith("_fk"):
                data.pop(k, None)
    return data

def _friendly_db_message(exc: Exception) -> str:
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
    for ch in audit_by_rowid.get(row_id, []):
        if ch.get("field") == "__row_id":
            continue
        obs.append(
            f"campo '{ch.get('field')}' alterado de '{ch.get('old')}' para '{ch.get('new')}' "
            f"(regra id={ch.get('rule_id')})"
        )
    return obs

def _allowed_keys(model):
    """Accept base names, attnames, '*_fk', path cols, '__row_id', 'id'."""
    names = set()
    for f in model._meta.fields:
        names.add(f.name)
        att = getattr(f, "attname", None)
        if att:
            names.add(att)
    fk_aliases = {n + "_fk" for n in names}
    return names | fk_aliases | set(PATH_COLS) | {"__row_id", "id"}

def _filter_unknown(model, row: Dict[str, Any]):
    allowed = _allowed_keys(model)
    filtered = {k: v for k, v in row.items() if k in allowed}
    unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
    return filtered, unknown

def _preflight_missing_required(model, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    errors = {}
    required_fields = []
    field_map = {}
    for f in model._meta.fields:
        if not hasattr(f, "attname"):
            continue

        is_auto_ts = (
            (hasattr(f, "auto_now") and getattr(f, "auto_now")) or
            (hasattr(f, "auto_now_add") and getattr(f, "auto_now_add"))
        )
        has_default = (getattr(f, "default", NOT_PROVIDED) is not NOT_PROVIDED)

        if (
            (not f.null)
            and (not f.primary_key)
            and (not f.auto_created)
            and (not has_default)
            and (not is_auto_ts)
        ):
            required_fields.append(f)

        base = f.name
        attn = getattr(f, "attname", f.name)
        accepted = {base, attn, f"{base}_fk"}
        field_map[base] = accepted

    for i, row in enumerate(rows):
        rid = row.get("__row_id") or f"row{i+1}"
        rid = _norm_row_key(rid)
        payload = {k: v for k, v in row.items() if k != "__row_id"}

        missing = []
        for f in required_fields:
            base = f.name
            accepted_keys = field_map.get(base, {base})
            present = False
            for k in accepted_keys:
                if k in payload and payload.get(k) not in ("", None):
                    present = True
                    break
            if not present:
                missing.append(base)

        if missing:
            errors[rid] = {
                "code": "E-PREFLIGHT",
                "message": f"Missing required: {', '.join(sorted(missing))}",
                "fields": {"missing": sorted(missing)},
            }
    return errors

def _quantize_decimal_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.DecimalField):
            name = getattr(f, 'attname', f.name)
            if name in out and out[name] not in (None, ''):
                dp = int(getattr(f, 'decimal_places', 0) or 0)
                q = Decimal('1').scaleb(-dp)
                out[name] = Decimal(str(out[name])).quantize(q, rounding=ROUND_HALF_UP)
    return out

def _coerce_boolean_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.BooleanField):
            name = getattr(f, 'attname', f.name)
            if name in out:
                out[name] = _to_bool(out[name])
    return out

_WS_RE = re.compile(r"\s+")
def _norm_scalar(val):
    if val is None: return None
    if isinstance(val, (bool, int)): return val
    if isinstance(val, float): return float(str(val))
    if isinstance(val, Decimal): return str(val)
    s = str(val).strip()
    return _WS_RE.sub(" ", s)

IGNORE_FIELDS = {"id", "created_at", "updated_at", "created_by", "updated_by", "is_deleted", "is_active"}

def _canonicalize_row(model, row: Dict[str, Any]) -> Dict[str, Any]:
    field_by = {f.name: f for f in model._meta.get_fields() if hasattr(f, "attname")}
    allowed = set(field_by.keys())
    incoming = {}
    for k, v in row.items():
        if k == "__row_id":
            continue
        incoming[k[:-3] if k.endswith("_fk") else k] = v
    ident = {k for k in incoming.keys() if k in allowed and k not in IGNORE_FIELDS}
    out = {}
    for k in sorted(ident):
        v = incoming.get(k)
        f = field_by.get(k)
        if _is_missing(v):
            out[k] = None
            continue
        if isinstance(f, dj_models.DecimalField):
            dp = int(getattr(f, 'decimal_places', 0) or 0)
            q = Decimal('1').scaleb(-dp)
            vq = Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP)
            out[k] = str(vq)
        elif isinstance(f, dj_models.DateField):
            out[k] = str(v)
        elif isinstance(f, dj_models.ForeignKey):
            out[k] = _to_int_or_none_soft(v)
        else:
            out[k] = _norm_scalar(v)
    return out

def _row_hash(model, row: Dict[str, Any]) -> str:
    c = _canonicalize_row(model, row)
    blob = json.dumps(c, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def _table_fingerprint(model, rows: List[Dict[str, Any]], sample_n: int = 200) -> Dict[str, Any]:
    rhashes = [_row_hash(model, r) for r in rows]
    unique_sorted = sorted(set(rhashes))
    cols = sorted(_canonicalize_row(model, rows[0]).keys()) if rows else []
    header_blob = json.dumps(cols, separators=(",", ":"), sort_keys=True)
    concat = header_blob + "|" + "|".join(unique_sorted)
    thash = hashlib.sha256(concat.encode("utf-8")).hexdigest()
    return {
        "row_count": len(rows),
        "colnames": cols,
        "row_hashes": unique_sorted,
        "row_hash_sample": unique_sorted[:sample_n],
        "table_hash": thash,
    }

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b: return 1.0
    if not a or not b:  return 0.0
    inter = len(a & b); uni = len(a | b)
    return inter / uni

def _unknown_from_original_input(model, row_obj: Dict[str, Any]) -> List[str]:
    allowed = _allowed_keys(model)
    orig = row_obj.get("_original_input") or row_obj.get("payload") or {}
    return sorted([k for k in orig.keys() if k not in allowed and k != "__row_id"])

# ---------- pretty snapshots for logs ----------
def _snapshot_inst_map(d: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
    out = []
    for i, (k, v) in enumerate(d.items()):
        if i >= limit:
            out.append({"...": f"{len(d)-limit} more"})
            break
        out.append({"token": k, "model": v.__class__.__name__, "pk": getattr(v, "pk", None)})
    return out

def _snapshot_pk_map(d: Dict[str, int], limit: int = 30) -> List[Dict[str, Any]]:
    out = []
    for i, (k, v) in enumerate(d.items()):
        if i >= limit:
            out.append({"...": f"{len(d)-limit} more"})
            break
        out.append({"token": k, "pk": v})
    return out

# ----------------------------------------------------------------------
# Core import executor
# ----------------------------------------------------------------------

DUP_CHECK_LAST_N = 10

def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
    def _coerce_pk(val):
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

def execute_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool, *, file_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ORDER_HINT = {name: i for i, name in enumerate(MODEL_APP_MAP.keys())}

    run_id = uuid.uuid4().hex[:8]
    ic = ImportContext(run_id=run_id, company_id=company_id, commit=commit)

    _run_id_ctx.set(run_id)
    _company_ctx.set(str(company_id))
    _model_ctx.set("-")
    _row_ctx.set("-")
    verbose = _import_debug_enabled()

    # file-level dedupe info
    file_sha = (file_meta or {}).get("sha256")
    filename = (file_meta or {}).get("filename")
    file_size = (file_meta or {}).get("size")
    exact_file_dupe_of: Optional[ImportSnapshot] = None

    if file_sha:
        exact_file_dupe_of = (
            ImportSnapshot.objects
            .filter(company_id=company_id, file_sha256=file_sha)
            .order_by("-created_at")
            .first()
        )

    file_info = {
        "filename": filename,
        "size": file_size,
        "file_sha256": file_sha,
        "exact_file_duplicate": bool(exact_file_dupe_of),
        "exact_file_duplicate_of": (
            {
                "model_name": exact_file_dupe_of.model_name,
                "created_at": exact_file_dupe_of.created_at.isoformat(),
                "row_count": exact_file_dupe_of.row_count,
                "table_hash": exact_file_dupe_of.table_hash,
            } if exact_file_dupe_of else None
        ),
    }

    logger.info(
        "import_start",
        **_log_extra(commit=bool(commit), import_filename=filename, file_sha=file_sha, file_size=file_size, sheet_count=len(sheets))
    )

    t0 = time.monotonic()
    with _SlowSQL(threshold_ms=200):
        prepared: List[Dict[str, Any]] = []
        models_in_order: List[str] = []
        any_prep_error = False
        dup_infos: Dict[str, Dict[str, Any]] = {}

        for sheet in sheets:
            model_name = sheet["model"]
            _model_ctx.set(model_name)

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                logger.error("sheet_app_missing", **_log_extra(error=f"MODEL_APP_MAP missing entry for '{model_name}'"))
                prepared.append({"model": model_name, "rows": [], "had_error": True, "sheet_error": f"MODEL_APP_MAP missing entry for '{model_name}'"})
                any_prep_error = True
                continue

            model = apps.get_model(app_label, model_name)
            raw_rows = sheet["rows"]
            logger.info("sheet_start", **_log_extra(row_count=len(raw_rows)))

            rows, audit = apply_substitutions(raw_rows, company_id=company_id, model_name=model_name, return_audit=True)
            audit_by_rowid = {}
            for ch in audit:
                audit_by_rowid.setdefault(ch.get("__row_id"), []).append(ch)

            if _is_mptt_model(model):
                rows = sorted(rows, key=_path_depth)

            fp = _table_fingerprint(model, rows)
            exact_table_dupe_of = (
                ImportSnapshot.objects
                .filter(company_id=company_id, model_name=model_name, table_hash=fp["table_hash"], row_count=fp["row_count"])
                .order_by("-created_at")
                .first()
            )

            prev_snaps = list(
                ImportSnapshot.objects
                .filter(company_id=company_id, model_name=model_name)
                .only("id", "row_count", "row_hash_sample", "table_hash", "file_sha256", "created_at", "filename")
                .order_by("-created_at")
            )[:DUP_CHECK_LAST_N]

            curr_set = set(fp["row_hashes"])
            best_match: Optional[Tuple[ImportSnapshot, float]] = None
            for s in prev_snaps:
                prev_set = set(s.row_hash_sample or [])
                sim = _jaccard(curr_set, prev_set) if prev_set else 0.0
                if (best_match is None) or (sim > best_match[1]):
                    best_match = (s, sim)

            dup_infos[model_name] = {
                "table_row_count": fp["row_count"],
                "table_hash": fp["table_hash"],
                "exact_table_duplicate": bool(exact_table_dupe_of),
                "exact_table_duplicate_of": (
                    {
                        "snapshot_id": exact_table_dupe_of.id,
                        "created_at": exact_table_dupe_of.created_at.isoformat(),
                        "row_count": exact_table_dupe_of.row_count,
                        "table_hash": exact_table_dupe_of.table_hash,
                        "file_sha256": exact_table_dupe_of.file_sha256,
                        "filename": exact_table_dupe_of.filename,
                    } if exact_table_dupe_of else None
                ),
                "closest_match": (
                    {
                        "snapshot_id": best_match[0].id,
                        "created_at": best_match[0].created_at.isoformat(),
                        "row_count": best_match[0].row_count,
                        "table_hash": best_match[0].table_hash,
                        "file_sha256": best_match[0].file_sha256,
                        "filename": best_match[0].filename,
                        "jaccard": round(float(best_match[1]), 6),
                    } if best_match else None
                ),
            }

            preflight_err = _preflight_missing_required(model, rows)

            packed_rows = []
            had_err = False

            for idx, row in enumerate(rows):
                rid_raw = row.get("__row_id") or f"row{idx+1}"
                rid = _norm_row_key(rid_raw)
                _row_ctx.set(rid)

                observations = _row_observations(audit_by_rowid, rid)
                original_input = {k: v for k, v in row.items() if k != "__row_id"}

                try:
                    filtered_input, _ = _filter_unknown(model, original_input)
                    payload = _normalize_payload_for_model(model, filtered_input, context_company_id=company_id)
                    payload = _coerce_boolean_fields(model, payload)
                    payload = _quantize_decimal_fields(model, payload)

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

                    action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)

                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": payload})

                    if rid in preflight_err:
                        msg = preflight_err[rid]["message"]
                        if unknown_cols_now:
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                        row_obj = {
                            "__row_id": rid,
                            "status": "error",
                            "preflight_error": {**preflight_err[rid], "message": msg},
                            "message": msg,
                            "payload": payload,
                            "_original_input": original_input,
                            "observations": observations,
                            "action": action,
                            "external_id": ext_id,
                        }
                        had_err = True
                    else:
                        status_val = "ok"
                        msg = "validated"
                        if unknown_cols_now:
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                        row_obj = {
                            "__row_id": rid,
                            "status": status_val,
                            "message": msg,
                            "payload": payload,
                            "_original_input": original_input,
                            "observations": observations,
                            "action": action,
                            "external_id": ext_id,
                        }

                    packed_rows.append(row_obj)

                except Exception as e:
                    had_err = True
                    err = exception_to_dict(e, include_stack=False)
                    if not err.get("summary"):
                        err["summary"] = _friendly_db_message(e)
                    try:
                        tmp_filtered, _ = _filter_unknown(model, original_input)
                        tmp_payload = _normalize_payload_for_model(model, tmp_filtered, context_company_id=company_id)
                        tmp_payload = _coerce_boolean_fields(model, tmp_payload)
                        tmp_payload = _quantize_decimal_fields(model, tmp_payload)
                    except Exception:
                        tmp_payload = original_input

                    action, pk, ext_id = _infer_action_and_clean_id(dict(tmp_payload), original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": tmp_payload})
                    base = err["summary"]
                    if unknown_cols_now:
                        base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                    logger.error(
                        "[IMPORT][PREP][EXC] model=%s row_id=%s action=%s err=%s",
                        model_name, rid, action, base,
                        exc_info=True,
                        **_log_extra()
                    )

                    packed_rows.append({
                        "__row_id": rid,
                        "status": "error",
                        "payload": tmp_payload,
                        "_original_input": original_input,
                        "observations": observations,
                        "message": base,
                        "error": {**err, "summary": base},
                        "action": action,
                        "external_id": ext_id,
                    })

            any_prep_error = any_prep_error or had_err
            prepared.append({"model": model_name, "rows": packed_rows, "had_error": had_err})
            logger.info("sheet_end", **_log_extra(had_error=bool(had_err)))

        models_in_order.sort(key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        # ------------------------------ PREVIEW ------------------------------
        if not commit:
            models_touched: List[Any] = []
            result_payload: List[Dict[str, Any]] = []

            # Global maps for PREVIEW
            global_row_map_inst: Dict[str, Any] = {}
            global_row_map_pk: Dict[str, int] = {}

            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cur:
                        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
                outer_sp = transaction.savepoint()

                for model_name in models_in_order:
                    _model_ctx.set(model_name)
                    app_label = MODEL_APP_MAP[model_name]
                    model = apps.get_model(app_label, model_name)
                    models_touched.append(model)

                    row_map_inst: Dict[str, Any] = {}
                    row_map_pk: Dict[str, int] = {}

                    rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                    out_rows: List[Dict[str, Any]] = []

                    _vlog("model_begin_preview", rows=len(rows), global_inst_size=len(global_row_map_inst), global_pk_size=len(global_row_map_pk))

                    for row in rows:
                        rid_raw = row.get("__row_id") or f"row{len(out_rows)+1}"
                        rid = _norm_row_key(rid_raw)
                        _row_ctx.set(rid)

                        original_input = row.get("_original_input") or {}
                        action = row.get("action") or "create"
                        _vlog("row_data_entry_original", action=action, data_entry=original_input)

                        if row.get("status") == "error" and row.get("preflight_error"):
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": row.get("action"),
                                "data": original_input or row.get("payload") or {},
                                "message": row["preflight_error"]["message"],
                                "error": row["preflight_error"],
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })
                            continue

                        payload = dict(row.get("payload") or {})
                        unknown_cols_now = _unknown_from_original_input(model, row)

                        try:
                            # 1) Resolve *_fk using LOCAL + GLOBAL maps
                            fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                            if fk_keys:
                                logger.debug("fk_keys_detected", **_log_extra(keys=fk_keys))
                            for fk_key in fk_keys:
                                field_name = fk_key[:-3]
                                fk_val = payload.pop(fk_key)

                                # show storage maps prior to resolution
                                _vlog(
                                    "fk_context_before_resolution",
                                    fk_field=field_name,
                                    fk_token=fk_val,
                                    global_inst_size=len(global_row_map_inst),
                                    global_pk_size=len(global_row_map_pk),
                                    global_inst_head=_snapshot_inst_map(global_row_map_inst, 50),
                                    global_pk_head=_snapshot_pk_map(global_row_map_pk, 50),
                                    local_inst_size=len(row_map_inst),
                                    local_pk_size=len(row_map_pk),
                                    local_inst_head=_snapshot_inst_map(row_map_inst, 50),
                                    local_pk_head=_snapshot_pk_map(row_map_pk, 50),
                                )

                                candidate = None
                                if isinstance(fk_val, str):
                                    candidate = _resolve_token_from_maps(
                                        _norm_row_key(fk_val),
                                        row_map_inst, row_map_pk,
                                        global_row_map_inst, global_row_map_pk
                                    )
                                merged_maps = {**global_row_map_inst, **row_map_inst}
                                resolved = _resolve_fk(model, field_name, candidate if candidate is not None else fk_val, {})

                                where_key, where_val = _assign_fk_value(model, field_name, resolved, payload)

                                # very explicit detail of what we set
                                field = model._meta.get_field(field_name)
                                attname = getattr(field, "attname", field_name)
                                _vlog(
                                    "fk_resolved_detail",
                                    fk_field=field_name,
                                    fk_token=fk_val,
                                    written_key=where_key,
                                    written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                    payload_fk_field_value=payload.get(field_name, None),
                                    payload_attname_value=payload.get(attname, None),
                                )

                            # 2) Rescue tokens misplaced in base FK field
                            for f in model._meta.get_fields():
                                if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                    base = f.name
                                    val = payload.get(base)
                                    if isinstance(val, str):
                                        token = _norm_row_key(val)
                                        candidate = _resolve_token_from_maps(token, row_map_inst, row_map_pk, global_row_map_inst, global_row_map_pk)
                                        if candidate is not None:
                                            _vlog("fk_rescue_misplaced_token", fk_field=base, token=val)
                                            resolved = _resolve_fk(model, base, candidate, {**global_row_map_inst, **row_map_inst})
                                            where_key, where_val = _assign_fk_value(model, base, resolved, payload)
                                            _vlog(
                                                "fk_rescue_applied",
                                                fk_field=base,
                                                written_key=where_key,
                                                written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                            )

                            # 3) MPTT
                            if _is_mptt_model(model):
                                path_val = _get_path_value(payload)
                                if path_val:
                                    parts = _split_path(path_val)
                                    parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                    payload["parent"] = parent
                                    payload.pop("parent_id", None)

                            # 4) Sanity check unresolved required FKs
                            merged_keys = list({**global_row_map_inst, **row_map_inst}.keys())
                            issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                            if issues:
                                for base, token in issues:
                                    logger.error("unresolved_required_fk", **_log_extra(field=base, token=token, known_row_ids=merged_keys[:50]))
                                raise ValidationError({base: [f"Unresolved FK token {token!r}. Known __row_id keys: {merged_keys[:50]}"] for base, token in issues})

                            payload = _coerce_boolean_fields(model, payload)
                            payload = _quantize_decimal_fields(model, payload)

                            _vlog("row_payload_before_clean", keys=sorted(payload.keys())[:60], sample= {k: payload[k] for k in sorted(payload.keys())[:25]})

                            with transaction.atomic():
                                if (row.get("action") or "create") == "update":
                                    instance = model.objects.select_for_update().get(id=payload["id"])
                                    for f, v in payload.items():
                                        setattr(instance, f, v)
                                else:
                                    instance = model(**payload)

                                sp = transaction.savepoint()
                                try:
                                    if hasattr(instance, "full_clean"):
                                        instance.full_clean()
                                    instance.save()
                                    transaction.savepoint_commit(sp)
                                except Exception:
                                    transaction.savepoint_rollback(sp)
                                    raise

                            # 5) Register __row_id → instance + PK in both local and global maps
                            if rid:
                                _register_row_token(row_map_inst, row_map_pk, rid, instance)
                                _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)
                                _vlog("row_token_mapped", token=rid, instance=_stringify_instance(instance), pk=getattr(instance, "id", None))

                            saved_dict = safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active'])
                            _vlog("row_output_after_save", output=saved_dict)

                            msg = "ok"
                            status_val = "success"
                            if unknown_cols_now and row.get("status") != "error":
                                status_val = "warning"
                                msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)

                            out_rows.append({
                                "__row_id": rid,
                                "status": status_val,
                                "action": row.get("action") or "create",
                                "data": saved_dict,
                                "message": msg,
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })

                        except Exception as e:
                            err = exception_to_dict(e, include_stack=False)
                            base_msg = err.get("summary") or _friendly_db_message(e)
                            if unknown_cols_now:
                                base_msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)
                            logger.error(
                                "[IMPORT][PREVIEW][EXC] model=%s row_id=%s action=%s err=%s",
                                model_name, rid, row.get("action") or "create", base_msg,
                                exc_info=True, **_log_extra()
                            )
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": row.get("action") or "create",
                                "data": original_input,
                                "message": base_msg,
                                "error": {**err, "summary": base_msg},
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })

                    _vlog("model_end_preview", local_map_size=len(row_map_inst), global_map_size=len(global_row_map_inst))

                    result_payload.append({
                        "model": model_name,
                        "dup_info": dup_infos.get(model_name),
                        "result": out_rows
                    })

                transaction.savepoint_rollback(outer_sp)
                reset_pk_sequences(models_touched)

            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="preview"))
            return {
                "committed": False,
                "reason": "preview",
                "file_info": file_info,
                "imports": result_payload
            }

        # ------------------------------ COMMIT ------------------------------
        if any_prep_error:
            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="prep_errors"))
            return {
                "committed": False,
                "reason": "prep_errors",
                "file_info": file_info,
                "imports": [{"model": b["model"], "dup_info": dup_infos.get(b["model"]), "result": b["rows"]} for b in prepared],
            }

        models_touched: List[Any] = []
        result_payload: List[Dict[str, Any]] = []
        any_row_error = False

        # Global map for COMMIT
        global_row_map: Dict[str, Any] = {}

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            outer_sp = transaction.savepoint()

            for model_name in models_in_order:
                _model_ctx.set(model_name)
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)
                models_touched.append(model)

                row_map: Dict[str, Any] = {}
                rows = next(b["rows"] for b in prepared if b["model"] == model_name)

                _vlog("model_begin_commit", rows=len(rows), global_inst_size=len(global_row_map))

                for row in rows:
                    rid = _norm_row_key(row["__row_id"])
                    _row_ctx.set(rid)

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
                    _vlog("row_data_entry_original", action=action, data_entry=original_input)

                    unknown_cols_now = _unknown_from_original_input(model, row)

                    try:
                        # Resolve *_fk using LOCAL + GLOBAL row maps
                        for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                            field_name = fk_key[:-3]
                            fk_val = payload.pop(fk_key)

                            _vlog(
                                "fk_context_before_resolution_commit",
                                fk_field=field_name,
                                fk_token=fk_val,
                                global_inst_size=len(global_row_map),
                                global_inst_head=_snapshot_inst_map(global_row_map, 50),
                                local_inst_size=len(row_map),
                                local_inst_head=_snapshot_inst_map(row_map, 50),
                            )

                            merged_map = {**global_row_map, **row_map}
                            resolved = _resolve_fk(model, field_name, fk_val, merged_map)
                            where_key, where_val = _assign_fk_value(model, field_name, resolved, payload)

                            field = model._meta.get_field(field_name)
                            attname = getattr(field, "attname", field_name)
                            _vlog(
                                "fk_resolved_detail_commit",
                                fk_field=field_name,
                                fk_token=fk_val,
                                written_key=where_key,
                                written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                payload_fk_field_value=payload.get(field_name, None),
                                payload_attname_value=payload.get(attname, None),
                            )

                        # Optional rescue: wrong column (token under base field)
                        for f in model._meta.get_fields():
                            if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                base = f.name
                                val = payload.get(base)
                                if isinstance(val, str):
                                    merged_map = {**global_row_map, **row_map}
                                    resolved = _resolve_fk(model, base, val, merged_map)
                                    # BUGFIX: assign using 'base' (not some outer 'field_name')
                                    _assign_fk_value(model, base, resolved, payload)
                                    _vlog("fk_rescue_applied_commit", fk_field=base, written_to=("instance" if isinstance(resolved, models.Model) else "id"))

                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload['parent'] = parent
                                payload.pop('parent_id', None)

                        # Sanity unresolved FKs that had *_fk in input
                        merged_keys = list(({**global_row_map, **row_map}).keys())
                        issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                        if issues:
                            for base, token in issues:
                                logger.warning("[FK][UNRESOLVED]", **_log_extra(field=base, token=token, known_row_ids=merged_keys[:50]))
                            raise ValidationError({
                                base: [f"Unresolved FK token {token!r}. Known __row_id keys (first 50): {merged_keys[:50]}"]
                                for base, token in issues
                            })

                        payload = _coerce_boolean_fields(model, payload)
                        payload = _quantize_decimal_fields(model, payload)
                        _vlog("row_payload_before_clean", keys=sorted(payload.keys())[:60], sample= {k: payload[k] for k in sorted(payload.keys())[:25]})

                        with transaction.atomic():
                            if action == "update":
                                instance = model.objects.select_for_update().get(id=payload["id"])
                                for f, v in payload.items():
                                    setattr(instance, f, v)
                            else:
                                instance = model(**payload)

                            sp = transaction.savepoint()
                            try:
                                if hasattr(instance, "full_clean"):
                                    instance.full_clean()
                                instance.save()
                                transaction.savepoint_commit(sp)
                            except Exception:
                                transaction.savepoint_rollback(sp)
                                raise

                        if rid:
                            row_map[rid] = instance
                            global_row_map[rid] = instance
                            _vlog("row_token_mapped_commit", token=rid, instance=_stringify_instance(instance), pk=getattr(instance, "id", None))

                        saved_dict = safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active'])
                        _vlog("row_output_after_save_commit", output=saved_dict)

                        msg = "ok"
                        status_val = "success"
                        if unknown_cols_now and row.get("status") != "error":
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        row.update({
                            "status": status_val,
                            "action": action,
                            "data": saved_dict,
                            "message": msg,
                        })

                    except Exception as e:
                        any_row_error = True
                        err = exception_to_dict(e, include_stack=False)
                        base = err.get("summary") or _friendly_db_message(e)
                        if unknown_cols_now:
                            base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        logger.error(
                            "[IMPORT][COMMIT][EXC] model=%s row_id=%s action=%s err=%s",
                            model_name, rid, action, base,
                            exc_info=True,
                            **_log_extra()
                        )

                        row.update({
                            "status": "error",
                            "action": action,
                            "data": original_input,
                            "message": base,
                            "error": {**err, "summary": base},
                        })

                _vlog("model_end_commit", local_map_size=len(row_map), global_map_size=len(global_row_map))

                result_payload.append({
                    "model": model_name,
                    "dup_info": dup_infos.get(model_name),
                    "result": rows
                })

            if any_row_error:
                transaction.savepoint_rollback(outer_sp)
                reset_pk_sequences(models_touched)
                dt = int((time.monotonic() - t0) * 1000)
                logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="row_errors"))
                return {
                    "committed": False,
                    "reason": "row_errors",
                    "file_info": file_info,
                    "imports": result_payload
                }

            # snapshots on success
            for item in result_payload:
                model_name = item["model"]
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)

                pre = next(b for b in prepared if b["model"] == model_name)
                rows_src = [r.get("_original_input") or r.get("payload") or {} for r in pre["rows"]]
                fp = _table_fingerprint(model, rows_src)
                closest = (item.get("dup_info") or {}).get("closest_match") or {}
                ImportSnapshot.objects.create(
                    company_id=company_id,
                    model_name=model_name,
                    row_count=fp["row_count"],
                    colnames=fp["colnames"],
                    row_hash_sample=fp["row_hashes"][:200],
                    table_hash=fp["table_hash"],
                    file_sha256=file_sha,
                    filename=filename,
                    jaccard_to_prev=closest.get("jaccard"),
                )

            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=True))
            return {
                "committed": True,
                "file_info": file_info,
                "imports": result_payload
            }

# Celery entrypoint: one task per file
@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)
# tasks.py (multitenancy/tasks.py)
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import smtplib
import logging
import time
import uuid
from contextvars import ContextVar
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.mail import send_mail
from django.db import (
    IntegrityError,
    DataError,
    DatabaseError,
    connection,
    models as dj_models,
    transaction,
)
from django.db.models import NOT_PROVIDED

from core.utils.db_sequences import reset_pk_sequences
from core.utils.exception_utils import exception_to_dict
from multitenancy.formula_engine import apply_substitutions
from multitenancy.models import ImportSnapshot, IntegrationRule
from .api_utils import (
    MODEL_APP_MAP,
    PATH_COLS,
    _get_path_value,
    _is_mptt_model,
    _resolve_parent_from_path_chain,
    _split_path,
    safe_model_dict,
    # NaN/NaT-safe helpers used in canonicalization:
    _is_missing,
    _to_int_or_none_soft,
    _to_int_or_none,
    _parse_json_or_empty,
    _to_bool,
    _norm_row_key,
    _path_depth,
)

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

from django.db import transaction as db_txn, models
from django.core.exceptions import ValidationError

# ----------------------------------------------------------------------
# Logging / verbosity
# ----------------------------------------------------------------------
logger = logging.getLogger("importer")
sql_logger = logging.getLogger("importer.sql")

# Reserved LogRecord attribute names — MUST NOT be in `extra`
_RESERVED_LOG_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName", "process",
    "processName", "asctime", "message", "stacklevel"
}

# Per-run contextual fields (propagated via logger.extra)
_run_id_ctx = ContextVar("run_id", default="-")
_company_ctx = ContextVar("company_id", default="-")
_model_ctx = ContextVar("model", default="-")
_row_ctx = ContextVar("row_id", default="-")

def _log_extra(**kw):
    # Sanitize any accidental reserved keys passed in
    cleaned = {}
    for k, v in kw.items():
        cleaned[("ctx_" + k) if k in _RESERVED_LOG_ATTRS else k] = v
    return {
        "extra": {
            "run_id": _run_id_ctx.get(),
            "company_id": _company_ctx.get(),
            "model": _model_ctx.get(),
            "row_id": _row_ctx.get(),
            **cleaned,
        }
    }

def _import_debug_enabled() -> bool:
    # Prefer settings flag; fallback to env
    val = getattr(settings, "IMPORT_DEBUG", None)
    if val is None:
        val = os.getenv("IMPORT_DEBUG", "0")
    return str(val).lower() in {"1", "true", "yes", "y", "on"}

def _vlog(msg: str, **fields):
    """Verbose log at INFO when IMPORT_DEBUG=1, otherwise DEBUG (so it’s visible with DEBUG on)."""
    if _import_debug_enabled():
        logger.info(msg, **_log_extra(**fields))
    else:
        logger.debug(msg, **_log_extra(**fields))

IMPORT_VERBOSE_FK = os.getenv("IMPORT_VERBOSE_FK", "0").lower() in {"1", "true", "yes", "y", "on"}

class _SlowSQL:
    """Capture slow queries during an import run only (keeps global DB logs quiet)."""
    def __init__(self, threshold_ms: int = 200):
        self.threshold = threshold_ms / 1000.0
        self._cm = None

    def __enter__(self):
        try:
            def wrapper(execute, sql, params, many, context):
                t0 = time.monotonic()
                try:
                    return execute(sql, params, many, context)
                finally:
                    dt = time.monotonic() - t0
                    if dt >= self.threshold:
                        # keep the log lean; params may be large/noisy
                        sql_logger.info(
                            "slow_sql",
                            **_log_extra(duration_ms=int(dt * 1000), many=bool(many), sql=sql[:1000])
                        )
            self._cm = connection.execute_wrapper(wrapper)
            self._cm.__enter__()  # type: ignore[attr-defined]
        except Exception:
            # Older Django versions or non-standard backends: just no-op
            self._cm = None
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc, tb)  # type: ignore[attr-defined]
        finally:
            return False

# ----------------------------------------------------------------------
# Email helpers
# ----------------------------------------------------------------------

def _sanity_check_required_fks(model, payload: Dict[str, Any], original_input: Dict[str, Any], merged_map_keys: List[str]) -> List[Tuple[str, Any]]:
    """
    Return a list of (field_name, token) for non-nullable FKs that were provided as <field>_fk
    in the original input but remain unresolved (payload[<field>] and payload[<field>_id] are both None).
    """
    issues: List[Tuple[str, Any]] = []
    for f in model._meta.get_fields():
        if not isinstance(f, dj_models.ForeignKey) or getattr(f, "null", False):
            continue

        base = f.name
        token = original_input.get(f"{base}_fk", None)

        # Was *_fk provided in input?
        provided = token not in (None, "")
        if provided and isinstance(token, float) and token != token:
            provided = False  # NaN

        if not provided:
            continue

        # Consider both field and its attname
        value = payload.get(base, None)
        if value is None:
            attname = getattr(f, "attname", None)
            if attname:
                value = payload.get(attname, None)

        if value is None:
            issues.append((base, token))
    return issues

@shared_task(bind=True, autoretry_for=(smtplib.SMTPException, ConnectionError), retry_backoff=True, max_retries=5)
def send_user_invite_email(self, subject, message, to_email):
    """Send user invite email with retry/backoff."""
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_email(self, subject, message, to_email):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)

# ----------------------------------------------------------------------
# Integration triggers
# ----------------------------------------------------------------------

@shared_task
def execute_integration_rule(rule_id, payload):
    rule = IntegrationRule.objects.get(pk=rule_id)
    return rule.run_rule(payload)

@shared_task
def trigger_integration_event(company_id, event_name, payload):
    rules = (
        IntegrationRule.objects
        .filter(company_id=company_id, is_active=True, triggers__icontains=event_name)
        .order_by('execution_order')
    )
    for rule in rules:
        if rule.use_celery:
            execute_integration_rule.delay(rule.id, payload)
        else:
            execute_integration_rule(rule.id, payload)

# ----------------------------------------------------------------------
# Import helpers
# ----------------------------------------------------------------------

@dataclass
class PendingRef:
    """Represents an FK pointing to a row created in this run (unsaved pk)."""
    model: type
    token: str  # e.g. 't1'

@dataclass
class ImportContext:
    run_id: str
    company_id: int
    commit: bool
    row_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})
    pk_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})

def _log(level: int, msg: str, ic: ImportContext, *, model: str = "-", row_id: str = "-", **fields):
    extra = {"run_id": ic.run_id, "company": ic.company_id, "model": model, "row_id": row_id, **fields}
    logger.log(level, msg, extra=extra)

class RateLimitFilter(logging.Filter):
    def __init__(self, burst=200, cache=None):
        super().__init__()
        self.cache = {} if cache is None else cache
        self.burst = burst
    def filter(self, record):
        key = getattr(record, "msg", "")
        count = self.cache.get(key, 0)
        if count >= self.burst:
            return False
        self.cache[key] = count + 1
        return True

def _stringify_instance(obj: models.Model) -> str:
    try:
        return str(obj)
    except Exception:
        return f"{obj.__class__.__name__}(id={getattr(obj, 'pk', None)})"

def _register_row_token(global_map_inst: Dict[str, Any],
                        global_map_pk: Dict[str, int],
                        rid: str,
                        instance: Any):
    """Store both instance and its PK by token."""
    if not rid:
        return
    pk = getattr(instance, "pk", None)
    global_map_inst[_norm_row_key(rid)] = instance
    if isinstance(pk, int):
        global_map_pk[_norm_row_key(rid)] = pk

def _resolve_token_from_maps(token: str,
                             local_inst: Dict[str, Any],
                             local_pk: Dict[str, int],
                             global_inst: Dict[str, Any],
                             global_pk: Dict[str, int]) -> Any:
    token = _norm_row_key(token)
    if token in local_inst:
        return local_inst[token]
    if token in global_inst:
        return global_inst[token]
    if token in local_pk:
        return local_pk[token]
    if token in global_pk:
        return global_pk[token]
    return None

def _get_field_and_remote_model(model_cls, field_name: str):
    field = model_cls._meta.get_field(field_name)
    rel = getattr(field, "remote_field", None)
    if rel is None or rel.model is None:
        raise LookupError(f"{model_cls.__name__}.{field_name} is not a ForeignKey")
    remote_model = rel.model
    remote_name = remote_model._meta.object_name
    return field, remote_model, remote_name

def _assign_fk_value(model_cls, field_name: str, resolved_value: Any, payload: dict) -> tuple[str, Any]:
    """
    Assign resolved FK value into payload using either base field (instance)
    or attname (pk int). Returns (where_key, value_assigned) for logging.
    """
    field = model_cls._meta.get_field(field_name)
    attname = getattr(field, "attname", field_name)
    if isinstance(resolved_value, int):
        payload.pop(field_name, None)        # avoid "entity=9"
        payload[attname] = resolved_value    # use "entity_id=9"
        return attname, resolved_value
    else:
        payload[field_name] = resolved_value # instance -> "entity"
        payload.pop(attname, None)
        return field_name, resolved_value

def _resolve_fk(model_cls, field_name: str, raw_value: Any, row_id_map: Dict[str, Any]) -> Any:
    """
    Return a value suitable for assignment via _assign_fk_value:
      - int PK   -> will be written to <attname> (e.g. entity_id)
      - instance -> will be written to <field>   (e.g. entity)
      - token    -> looked up in row_id_map (instance or int expected)
    """
    if raw_value in (None, ""):
        return None

    field = model_cls._meta.get_field(field_name)
    remote_model = getattr(field, "remote_field", None).model if getattr(field, "remote_field", None) else None
    known_tokens = list(row_id_map.keys())

    # Instance?
    if isinstance(raw_value, models.Model):
        if remote_model and not isinstance(raw_value, remote_model):
            raise ValueError(f"{model_cls.__name__}.{field_name} expects {remote_model.__name__} instance, got {raw_value.__class__.__name__}")
        return raw_value

    # int or "123"?
    if isinstance(raw_value, int) or (isinstance(raw_value, str) and raw_value.strip().isdigit()):
        return int(raw_value)

    # token form (e.g., "t1" or "Model:t1")
    token = _norm_row_key(str(raw_value).strip())
    candidate = row_id_map.get(token)

    if candidate is None and ":" in token:
        maybe_model, maybe_token = token.split(":", 1)
        candidate = row_id_map.get(_norm_row_key(maybe_token))

    if candidate is not None:
        if isinstance(candidate, models.Model):
            if remote_model and not isinstance(candidate, remote_model):
                pk = getattr(candidate, "pk", None)
                if isinstance(pk, int):
                    return pk
                raise ValueError(f"Token {token!r} resolved to {candidate.__class__.__name__}, incompatible with {remote_model.__name__}")
            return candidate
        if isinstance(candidate, int):
            return candidate

    preview = ", ".join(known_tokens[:20]) + (" ..." if len(known_tokens) > 20 else "")
    raise ValueError(
        f"Invalid FK reference format {raw_value!r} for field '{field_name}'. "
        f"Expected numeric id, instance of {remote_model.__name__ if remote_model else 'related model'}, "
        f"or a run token present in known __row_id keys [{preview}]"
    )

def _build_instance(model_cls: type, payload: dict) -> models.Model:
    return model_cls(**payload)

def _full_clean_preview(instance: models.Model, exclude_fields: List[str]):
    instance.full_clean(exclude=exclude_fields, validate_unique=False)

def _normalize_payload_for_model(model, payload: Dict[str, Any], *, context_company_id=None):
    """
    - map company_fk -> company_id / tenant_id if model has those fields
    - coerce known types (column_index, filter_conditions)
    - drop unknown keys (but keep *_id that match a real FK and keep *_fk for resolution)
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

    if "column_index" in data:
        data["column_index"] = _to_int_or_none(data.get("column_index"))
    if "filter_conditions" in data:
        data["filter_conditions"] = _parse_json_or_empty(data.get("filter_conditions"))

    # drop unknown keys except *_id matching real fields and *_fk (will be resolved later)
    for k in list(data.keys()):
        if k in ("id",):
            continue
        try:
            model._meta.get_field(k)
        except FieldDoesNotExist:
            if not (k.endswith("_id") and k[:-3] in field_names) and not k.endswith("_fk"):
                data.pop(k, None)
    return data

def _friendly_db_message(exc: Exception) -> str:
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
    for ch in audit_by_rowid.get(row_id, []):
        if ch.get("field") == "__row_id":
            continue
        obs.append(
            f"campo '{ch.get('field')}' alterado de '{ch.get('old')}' para '{ch.get('new')}' "
            f"(regra id={ch.get('rule_id')})"
        )
    return obs

def _allowed_keys(model):
    """Accept base names, attnames, '*_fk', path cols, '__row_id', 'id'."""
    names = set()
    for f in model._meta.fields:
        names.add(f.name)
        att = getattr(f, "attname", None)
        if att:
            names.add(att)
    fk_aliases = {n + "_fk" for n in names}
    return names | fk_aliases | set(PATH_COLS) | {"__row_id", "id"}

def _filter_unknown(model, row: Dict[str, Any]):
    allowed = _allowed_keys(model)
    filtered = {k: v for k, v in row.items() if k in allowed}
    unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
    return filtered, unknown

def _preflight_missing_required(model, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    errors = {}
    required_fields = []
    field_map = {}
    for f in model._meta.fields:
        if not hasattr(f, "attname"):
            continue

        is_auto_ts = (
            (hasattr(f, "auto_now") and getattr(f, "auto_now")) or
            (hasattr(f, "auto_now_add") and getattr(f, "auto_now_add"))
        )
        has_default = (getattr(f, "default", NOT_PROVIDED) is not NOT_PROVIDED)

        if (
            (not f.null)
            and (not f.primary_key)
            and (not f.auto_created)
            and (not has_default)
            and (not is_auto_ts)
        ):
            required_fields.append(f)

        base = f.name
        attn = getattr(f, "attname", f.name)
        accepted = {base, attn, f"{base}_fk"}
        field_map[base] = accepted

    for i, row in enumerate(rows):
        rid = row.get("__row_id") or f"row{i+1}"
        rid = _norm_row_key(rid)
        payload = {k: v for k, v in row.items() if k != "__row_id"}

        missing = []
        for f in required_fields:
            base = f.name
            accepted_keys = field_map.get(base, {base})
            present = False
            for k in accepted_keys:
                if k in payload and payload.get(k) not in ("", None):
                    present = True
                    break
            if not present:
                missing.append(base)

        if missing:
            errors[rid] = {
                "code": "E-PREFLIGHT",
                "message": f"Missing required: {', '.join(sorted(missing))}",
                "fields": {"missing": sorted(missing)},
            }
    return errors

def _quantize_decimal_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.DecimalField):
            name = getattr(f, 'attname', f.name)
            if name in out and out[name] not in (None, ''):
                dp = int(getattr(f, 'decimal_places', 0) or 0)
                q = Decimal('1').scaleb(-dp)
                out[name] = Decimal(str(out[name])).quantize(q, rounding=ROUND_HALF_UP)
    return out

def _coerce_boolean_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.BooleanField):
            name = getattr(f, 'attname', f.name)
            if name in out:
                out[name] = _to_bool(out[name])
    return out

_WS_RE = re.compile(r"\s+")
def _norm_scalar(val):
    if val is None: return None
    if isinstance(val, (bool, int)): return val
    if isinstance(val, float): return float(str(val))
    if isinstance(val, Decimal): return str(val)
    s = str(val).strip()
    return _WS_RE.sub(" ", s)

IGNORE_FIELDS = {"id", "created_at", "updated_at", "created_by", "updated_by", "is_deleted", "is_active"}

def _canonicalize_row(model, row: Dict[str, Any]) -> Dict[str, Any]:
    field_by = {f.name: f for f in model._meta.get_fields() if hasattr(f, "attname")}
    allowed = set(field_by.keys())
    incoming = {}
    for k, v in row.items():
        if k == "__row_id":
            continue
        incoming[k[:-3] if k.endswith("_fk") else k] = v
    ident = {k for k in incoming.keys() if k in allowed and k not in IGNORE_FIELDS}
    out = {}
    for k in sorted(ident):
        v = incoming.get(k)
        f = field_by.get(k)
        if _is_missing(v):
            out[k] = None
            continue
        if isinstance(f, dj_models.DecimalField):
            dp = int(getattr(f, 'decimal_places', 0) or 0)
            q = Decimal('1').scaleb(-dp)
            vq = Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP)
            out[k] = str(vq)
        elif isinstance(f, dj_models.DateField):
            out[k] = str(v)
        elif isinstance(f, dj_models.ForeignKey):
            out[k] = _to_int_or_none_soft(v)
        else:
            out[k] = _norm_scalar(v)
    return out

def _row_hash(model, row: Dict[str, Any]) -> str:
    c = _canonicalize_row(model, row)
    blob = json.dumps(c, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def _table_fingerprint(model, rows: List[Dict[str, Any]], sample_n: int = 200) -> Dict[str, Any]:
    rhashes = [_row_hash(model, r) for r in rows]
    unique_sorted = sorted(set(rhashes))
    cols = sorted(_canonicalize_row(model, rows[0]).keys()) if rows else []
    header_blob = json.dumps(cols, separators=(",", ":"), sort_keys=True)
    concat = header_blob + "|" + "|".join(unique_sorted)
    thash = hashlib.sha256(concat.encode("utf-8")).hexdigest()
    return {
        "row_count": len(rows),
        "colnames": cols,
        "row_hashes": unique_sorted,
        "row_hash_sample": unique_sorted[:sample_n],
        "table_hash": thash,
    }

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b: return 1.0
    if not a or not b:  return 0.0
    inter = len(a & b); uni = len(a | b)
    return inter / uni

def _unknown_from_original_input(model, row_obj: Dict[str, Any]) -> List[str]:
    allowed = _allowed_keys(model)
    orig = row_obj.get("_original_input") or row_obj.get("payload") or {}
    return sorted([k for k in orig.keys() if k not in allowed and k != "__row_id"])

# ---------- pretty snapshots for logs ----------
def _snapshot_inst_map(d: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
    out = []
    for i, (k, v) in enumerate(d.items()):
        if i >= limit:
            out.append({"...": f"{len(d)-limit} more"})
            break
        out.append({"token": k, "model": v.__class__.__name__, "pk": getattr(v, "pk", None)})
    return out

def _snapshot_pk_map(d: Dict[str, int], limit: int = 30) -> List[Dict[str, Any]]:
    out = []
    for i, (k, v) in enumerate(d.items()):
        if i >= limit:
            out.append({"...": f"{len(d)-limit} more"})
            break
        out.append({"token": k, "pk": v})
    return out

# ----------------------------------------------------------------------
# Core import executor
# ----------------------------------------------------------------------

DUP_CHECK_LAST_N = 10

def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
    def _coerce_pk(val):
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

def execute_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool, *, file_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ORDER_HINT = {name: i for i, name in enumerate(MODEL_APP_MAP.keys())}

    run_id = uuid.uuid4().hex[:8]
    ic = ImportContext(run_id=run_id, company_id=company_id, commit=commit)

    _run_id_ctx.set(run_id)
    _company_ctx.set(str(company_id))
    _model_ctx.set("-")
    _row_ctx.set("-")
    verbose = _import_debug_enabled()

    # file-level dedupe info
    file_sha = (file_meta or {}).get("sha256")
    filename = (file_meta or {}).get("filename")
    file_size = (file_meta or {}).get("size")
    exact_file_dupe_of: Optional[ImportSnapshot] = None

    if file_sha:
        exact_file_dupe_of = (
            ImportSnapshot.objects
            .filter(company_id=company_id, file_sha256=file_sha)
            .order_by("-created_at")
            .first()
        )

    file_info = {
        "filename": filename,
        "size": file_size,
        "file_sha256": file_sha,
        "exact_file_duplicate": bool(exact_file_dupe_of),
        "exact_file_duplicate_of": (
            {
                "model_name": exact_file_dupe_of.model_name,
                "created_at": exact_file_dupe_of.created_at.isoformat(),
                "row_count": exact_file_dupe_of.row_count,
                "table_hash": exact_file_dupe_of.table_hash,
            } if exact_file_dupe_of else None
        ),
    }

    logger.info(
        "import_start",
        **_log_extra(commit=bool(commit), import_filename=filename, file_sha=file_sha, file_size=file_size, sheet_count=len(sheets))
    )

    t0 = time.monotonic()
    with _SlowSQL(threshold_ms=200):
        prepared: List[Dict[str, Any]] = []
        models_in_order: List[str] = []
        any_prep_error = False
        dup_infos: Dict[str, Dict[str, Any]] = {}

        for sheet in sheets:
            model_name = sheet["model"]
            _model_ctx.set(model_name)

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                logger.error("sheet_app_missing", **_log_extra(error=f"MODEL_APP_MAP missing entry for '{model_name}'"))
                prepared.append({"model": model_name, "rows": [], "had_error": True, "sheet_error": f"MODEL_APP_MAP missing entry for '{model_name}'"})
                any_prep_error = True
                continue

            model = apps.get_model(app_label, model_name)
            raw_rows = sheet["rows"]
            logger.info("sheet_start", **_log_extra(row_count=len(raw_rows)))

            rows, audit = apply_substitutions(raw_rows, company_id=company_id, model_name=model_name, return_audit=True)
            audit_by_rowid = {}
            for ch in audit:
                audit_by_rowid.setdefault(ch.get("__row_id"), []).append(ch)

            if _is_mptt_model(model):
                rows = sorted(rows, key=_path_depth)

            fp = _table_fingerprint(model, rows)
            exact_table_dupe_of = (
                ImportSnapshot.objects
                .filter(company_id=company_id, model_name=model_name, table_hash=fp["table_hash"], row_count=fp["row_count"])
                .order_by("-created_at")
                .first()
            )

            prev_snaps = list(
                ImportSnapshot.objects
                .filter(company_id=company_id, model_name=model_name)
                .only("id", "row_count", "row_hash_sample", "table_hash", "file_sha256", "created_at", "filename")
                .order_by("-created_at")
            )[:DUP_CHECK_LAST_N]

            curr_set = set(fp["row_hashes"])
            best_match: Optional[Tuple[ImportSnapshot, float]] = None
            for s in prev_snaps:
                prev_set = set(s.row_hash_sample or [])
                sim = _jaccard(curr_set, prev_set) if prev_set else 0.0
                if (best_match is None) or (sim > best_match[1]):
                    best_match = (s, sim)

            dup_infos[model_name] = {
                "table_row_count": fp["row_count"],
                "table_hash": fp["table_hash"],
                "exact_table_duplicate": bool(exact_table_dupe_of),
                "exact_table_duplicate_of": (
                    {
                        "snapshot_id": exact_table_dupe_of.id,
                        "created_at": exact_table_dupe_of.created_at.isoformat(),
                        "row_count": exact_table_dupe_of.row_count,
                        "table_hash": exact_table_dupe_of.table_hash,
                        "file_sha256": exact_table_dupe_of.file_sha256,
                        "filename": exact_table_dupe_of.filename,
                    } if exact_table_dupe_of else None
                ),
                "closest_match": (
                    {
                        "snapshot_id": best_match[0].id,
                        "created_at": best_match[0].created_at.isoformat(),
                        "row_count": best_match[0].row_count,
                        "table_hash": best_match[0].table_hash,
                        "file_sha256": best_match[0].file_sha256,
                        "filename": best_match[0].filename,
                        "jaccard": round(float(best_match[1]), 6),
                    } if best_match else None
                ),
            }

            preflight_err = _preflight_missing_required(model, rows)

            packed_rows = []
            had_err = False

            for idx, row in enumerate(rows):
                rid_raw = row.get("__row_id") or f"row{idx+1}"
                rid = _norm_row_key(rid_raw)
                _row_ctx.set(rid)

                observations = _row_observations(audit_by_rowid, rid)
                original_input = {k: v for k, v in row.items() if k != "__row_id"}

                try:
                    filtered_input, _ = _filter_unknown(model, original_input)
                    payload = _normalize_payload_for_model(model, filtered_input, context_company_id=company_id)
                    payload = _coerce_boolean_fields(model, payload)
                    payload = _quantize_decimal_fields(model, payload)

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

                    action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)

                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": payload})

                    if rid in preflight_err:
                        msg = preflight_err[rid]["message"]
                        if unknown_cols_now:
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                        row_obj = {
                            "__row_id": rid,
                            "status": "error",
                            "preflight_error": {**preflight_err[rid], "message": msg},
                            "message": msg,
                            "payload": payload,
                            "_original_input": original_input,
                            "observations": observations,
                            "action": action,
                            "external_id": ext_id,
                        }
                        had_err = True
                    else:
                        status_val = "ok"
                        msg = "validated"
                        if unknown_cols_now:
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                        row_obj = {
                            "__row_id": rid,
                            "status": status_val,
                            "message": msg,
                            "payload": payload,
                            "_original_input": original_input,
                            "observations": observations,
                            "action": action,
                            "external_id": ext_id,
                        }

                    packed_rows.append(row_obj)

                except Exception as e:
                    had_err = True
                    err = exception_to_dict(e, include_stack=False)
                    if not err.get("summary"):
                        err["summary"] = _friendly_db_message(e)
                    try:
                        tmp_filtered, _ = _filter_unknown(model, original_input)
                        tmp_payload = _normalize_payload_for_model(model, tmp_filtered, context_company_id=company_id)
                        tmp_payload = _coerce_boolean_fields(model, tmp_payload)
                        tmp_payload = _quantize_decimal_fields(model, tmp_payload)
                    except Exception:
                        tmp_payload = original_input

                    action, pk, ext_id = _infer_action_and_clean_id(dict(tmp_payload), original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": tmp_payload})
                    base = err["summary"]
                    if unknown_cols_now:
                        base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                    logger.error(
                        "[IMPORT][PREP][EXC] model=%s row_id=%s action=%s err=%s",
                        model_name, rid, action, base,
                        exc_info=True,
                        **_log_extra()
                    )

                    packed_rows.append({
                        "__row_id": rid,
                        "status": "error",
                        "payload": tmp_payload,
                        "_original_input": original_input,
                        "observations": observations,
                        "message": base,
                        "error": {**err, "summary": base},
                        "action": action,
                        "external_id": ext_id,
                    })

            any_prep_error = any_prep_error or had_err
            prepared.append({"model": model_name, "rows": packed_rows, "had_error": had_err})
            logger.info("sheet_end", **_log_extra(had_error=bool(had_err)))

        models_in_order.sort(key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        # ------------------------------ PREVIEW ------------------------------
        if not commit:
            models_touched: List[Any] = []
            result_payload: List[Dict[str, Any]] = []

            # Global maps for PREVIEW
            global_row_map_inst: Dict[str, Any] = {}
            global_row_map_pk: Dict[str, int] = {}

            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cur:
                        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
                outer_sp = transaction.savepoint()

                for model_name in models_in_order:
                    _model_ctx.set(model_name)
                    app_label = MODEL_APP_MAP[model_name]
                    model = apps.get_model(app_label, model_name)
                    models_touched.append(model)

                    row_map_inst: Dict[str, Any] = {}
                    row_map_pk: Dict[str, int] = {}

                    rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                    out_rows: List[Dict[str, Any]] = []

                    _vlog("model_begin_preview", rows=len(rows), global_inst_size=len(global_row_map_inst), global_pk_size=len(global_row_map_pk))

                    for row in rows:
                        rid_raw = row.get("__row_id") or f"row{len(out_rows)+1}"
                        rid = _norm_row_key(rid_raw)
                        _row_ctx.set(rid)

                        original_input = row.get("_original_input") or {}
                        action = row.get("action") or "create"
                        _vlog("row_data_entry_original", action=action, data_entry=original_input)

                        if row.get("status") == "error" and row.get("preflight_error"):
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": row.get("action"),
                                "data": original_input or row.get("payload") or {},
                                "message": row["preflight_error"]["message"],
                                "error": row["preflight_error"],
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })
                            continue

                        payload = dict(row.get("payload") or {})
                        unknown_cols_now = _unknown_from_original_input(model, row)

                        try:
                            # 1) Resolve *_fk using LOCAL + GLOBAL maps
                            fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                            if fk_keys:
                                logger.debug("fk_keys_detected", **_log_extra(keys=fk_keys))
                            for fk_key in fk_keys:
                                field_name = fk_key[:-3]
                                fk_val = payload.pop(fk_key)

                                # show storage maps prior to resolution
                                _vlog(
                                    "fk_context_before_resolution",
                                    fk_field=field_name,
                                    fk_token=fk_val,
                                    global_inst_size=len(global_row_map_inst),
                                    global_pk_size=len(global_row_map_pk),
                                    global_inst_head=_snapshot_inst_map(global_row_map_inst, 50),
                                    global_pk_head=_snapshot_pk_map(global_row_map_pk, 50),
                                    local_inst_size=len(row_map_inst),
                                    local_pk_size=len(row_map_pk),
                                    local_inst_head=_snapshot_inst_map(row_map_inst, 50),
                                    local_pk_head=_snapshot_pk_map(row_map_pk, 50),
                                )

                                candidate = None
                                if isinstance(fk_val, str):
                                    candidate = _resolve_token_from_maps(
                                        _norm_row_key(fk_val),
                                        row_map_inst, row_map_pk,
                                        global_row_map_inst, global_row_map_pk
                                    )
                                merged_maps = {**global_row_map_inst, **row_map_inst}
                                resolved = _resolve_fk(model, field_name, candidate if candidate is not None else fk_val, {})

                                where_key, where_val = _assign_fk_value(model, field_name, resolved, payload)

                                # very explicit detail of what we set
                                field = model._meta.get_field(field_name)
                                attname = getattr(field, "attname", field_name)
                                _vlog(
                                    "fk_resolved_detail",
                                    fk_field=field_name,
                                    fk_token=fk_val,
                                    written_key=where_key,
                                    written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                    payload_fk_field_value=payload.get(field_name, None),
                                    payload_attname_value=payload.get(attname, None),
                                )

                            # 2) Rescue tokens misplaced in base FK field
                            for f in model._meta.get_fields():
                                if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                    base = f.name
                                    val = payload.get(base)
                                    if isinstance(val, str):
                                        token = _norm_row_key(val)
                                        candidate = _resolve_token_from_maps(token, row_map_inst, row_map_pk, global_row_map_inst, global_row_map_pk)
                                        if candidate is not None:
                                            _vlog("fk_rescue_misplaced_token", fk_field=base, token=val)
                                            resolved = _resolve_fk(model, base, candidate, {**global_row_map_inst, **row_map_inst})
                                            where_key, where_val = _assign_fk_value(model, base, resolved, payload)
                                            _vlog(
                                                "fk_rescue_applied",
                                                fk_field=base,
                                                written_key=where_key,
                                                written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                            )

                            # 3) MPTT
                            if _is_mptt_model(model):
                                path_val = _get_path_value(payload)
                                if path_val:
                                    parts = _split_path(path_val)
                                    parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                    payload["parent"] = parent
                                    payload.pop("parent_id", None)

                            # 4) Sanity check unresolved required FKs
                            merged_keys = list({**global_row_map_inst, **row_map_inst}.keys())
                            issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                            if issues:
                                for base, token in issues:
                                    logger.error("unresolved_required_fk", **_log_extra(field=base, token=token, known_row_ids=merged_keys[:50]))
                                raise ValidationError({base: [f"Unresolved FK token {token!r}. Known __row_id keys: {merged_keys[:50]}"] for base, token in issues})

                            payload = _coerce_boolean_fields(model, payload)
                            payload = _quantize_decimal_fields(model, payload)

                            _vlog("row_payload_before_clean", keys=sorted(payload.keys())[:60], sample= {k: payload[k] for k in sorted(payload.keys())[:25]})

                            with transaction.atomic():
                                if (row.get("action") or "create") == "update":
                                    instance = model.objects.select_for_update().get(id=payload["id"])
                                    for f, v in payload.items():
                                        setattr(instance, f, v)
                                else:
                                    instance = model(**payload)

                                sp = transaction.savepoint()
                                try:
                                    if hasattr(instance, "full_clean"):
                                        instance.full_clean()
                                    instance.save()
                                    transaction.savepoint_commit(sp)
                                except Exception:
                                    transaction.savepoint_rollback(sp)
                                    raise

                            # 5) Register __row_id → instance + PK in both local and global maps
                            if rid:
                                _register_row_token(row_map_inst, row_map_pk, rid, instance)
                                _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)
                                _vlog("row_token_mapped", token=rid, instance=_stringify_instance(instance), pk=getattr(instance, "id", None))

                            saved_dict = safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active'])
                            _vlog("row_output_after_save", output=saved_dict)

                            msg = "ok"
                            status_val = "success"
                            if unknown_cols_now and row.get("status") != "error":
                                status_val = "warning"
                                msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)

                            out_rows.append({
                                "__row_id": rid,
                                "status": status_val,
                                "action": row.get("action") or "create",
                                "data": saved_dict,
                                "message": msg,
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })

                        except Exception as e:
                            err = exception_to_dict(e, include_stack=False)
                            base_msg = err.get("summary") or _friendly_db_message(e)
                            if unknown_cols_now:
                                base_msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)
                            logger.error(
                                "[IMPORT][PREVIEW][EXC] model=%s row_id=%s action=%s err=%s",
                                model_name, rid, row.get("action") or "create", base_msg,
                                exc_info=True, **_log_extra()
                            )
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": row.get("action") or "create",
                                "data": original_input,
                                "message": base_msg,
                                "error": {**err, "summary": base_msg},
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })

                    _vlog("model_end_preview", local_map_size=len(row_map_inst), global_map_size=len(global_row_map_inst))

                    result_payload.append({
                        "model": model_name,
                        "dup_info": dup_infos.get(model_name),
                        "result": out_rows
                    })

                transaction.savepoint_rollback(outer_sp)
                reset_pk_sequences(models_touched)

            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="preview"))
            return {
                "committed": False,
                "reason": "preview",
                "file_info": file_info,
                "imports": result_payload
            }

        # ------------------------------ COMMIT ------------------------------
        if any_prep_error:
            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="prep_errors"))
            return {
                "committed": False,
                "reason": "prep_errors",
                "file_info": file_info,
                "imports": [{"model": b["model"], "dup_info": dup_infos.get(b["model"]), "result": b["rows"]} for b in prepared],
            }

        models_touched: List[Any] = []
        result_payload: List[Dict[str, Any]] = []
        any_row_error = False

        # Global map for COMMIT
        global_row_map: Dict[str, Any] = {}

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            outer_sp = transaction.savepoint()

            for model_name in models_in_order:
                _model_ctx.set(model_name)
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)
                models_touched.append(model)

                row_map: Dict[str, Any] = {}
                rows = next(b["rows"] for b in prepared if b["model"] == model_name)

                _vlog("model_begin_commit", rows=len(rows), global_inst_size=len(global_row_map))

                for row in rows:
                    rid = _norm_row_key(row["__row_id"])
                    _row_ctx.set(rid)

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
                    _vlog("row_data_entry_original", action=action, data_entry=original_input)

                    unknown_cols_now = _unknown_from_original_input(model, row)

                    try:
                        # Resolve *_fk using LOCAL + GLOBAL row maps
                        for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                            field_name = fk_key[:-3]
                            fk_val = payload.pop(fk_key)

                            _vlog(
                                "fk_context_before_resolution_commit",
                                fk_field=field_name,
                                fk_token=fk_val,
                                global_inst_size=len(global_row_map),
                                global_inst_head=_snapshot_inst_map(global_row_map, 50),
                                local_inst_size=len(row_map),
                                local_inst_head=_snapshot_inst_map(row_map, 50),
                            )

                            merged_map = {**global_row_map, **row_map}
                            resolved = _resolve_fk(model, field_name, fk_val, merged_map)
                            where_key, where_val = _assign_fk_value(model, field_name, resolved, payload)

                            field = model._meta.get_field(field_name)
                            attname = getattr(field, "attname", field_name)
                            _vlog(
                                "fk_resolved_detail_commit",
                                fk_field=field_name,
                                fk_token=fk_val,
                                written_key=where_key,
                                written_value=(getattr(where_val, "pk", None) if isinstance(where_val, models.Model) else where_val),
                                payload_fk_field_value=payload.get(field_name, None),
                                payload_attname_value=payload.get(attname, None),
                            )

                        # Optional rescue: wrong column (token under base field)
                        for f in model._meta.get_fields():
                            if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                base = f.name
                                val = payload.get(base)
                                if isinstance(val, str):
                                    merged_map = {**global_row_map, **row_map}
                                    resolved = _resolve_fk(model, base, val, merged_map)
                                    # BUGFIX: assign using 'base' (not some outer 'field_name')
                                    _assign_fk_value(model, base, resolved, payload)
                                    _vlog("fk_rescue_applied_commit", fk_field=base, written_to=("instance" if isinstance(resolved, models.Model) else "id"))

                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload['parent'] = parent
                                payload.pop('parent_id', None)

                        # Sanity unresolved FKs that had *_fk in input
                        merged_keys = list(({**global_row_map, **row_map}).keys())
                        issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                        if issues:
                            for base, token in issues:
                                logger.warning("[FK][UNRESOLVED]", **_log_extra(field=base, token=token, known_row_ids=merged_keys[:50]))
                            raise ValidationError({
                                base: [f"Unresolved FK token {token!r}. Known __row_id keys (first 50): {merged_keys[:50]}"]
                                for base, token in issues
                            })

                        payload = _coerce_boolean_fields(model, payload)
                        payload = _quantize_decimal_fields(model, payload)
                        _vlog("row_payload_before_clean", keys=sorted(payload.keys())[:60], sample= {k: payload[k] for k in sorted(payload.keys())[:25]})

                        with transaction.atomic():
                            if action == "update":
                                instance = model.objects.select_for_update().get(id=payload["id"])
                                for f, v in payload.items():
                                    setattr(instance, f, v)
                            else:
                                instance = model(**payload)

                            sp = transaction.savepoint()
                            try:
                                if hasattr(instance, "full_clean"):
                                    instance.full_clean()
                                instance.save()
                                transaction.savepoint_commit(sp)
                            except Exception:
                                transaction.savepoint_rollback(sp)
                                raise

                        if rid:
                            row_map[rid] = instance
                            global_row_map[rid] = instance
                            _vlog("row_token_mapped_commit", token=rid, instance=_stringify_instance(instance), pk=getattr(instance, "id", None))

                        saved_dict = safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active'])
                        _vlog("row_output_after_save_commit", output=saved_dict)

                        msg = "ok"
                        status_val = "success"
                        if unknown_cols_now and row.get("status") != "error":
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        row.update({
                            "status": status_val,
                            "action": action,
                            "data": saved_dict,
                            "message": msg,
                        })

                    except Exception as e:
                        any_row_error = True
                        err = exception_to_dict(e, include_stack=False)
                        base = err.get("summary") or _friendly_db_message(e)
                        if unknown_cols_now:
                            base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        logger.error(
                            "[IMPORT][COMMIT][EXC] model=%s row_id=%s action=%s err=%s",
                            model_name, rid, action, base,
                            exc_info=True,
                            **_log_extra()
                        )

                        row.update({
                            "status": "error",
                            "action": action,
                            "data": original_input,
                            "message": base,
                            "error": {**err, "summary": base},
                        })

                _vlog("model_end_commit", local_map_size=len(row_map), global_map_size=len(global_row_map))

                result_payload.append({
                    "model": model_name,
                    "dup_info": dup_infos.get(model_name),
                    "result": rows
                })

            if any_row_error:
                transaction.savepoint_rollback(outer_sp)
                reset_pk_sequences(models_touched)
                dt = int((time.monotonic() - t0) * 1000)
                logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="row_errors"))
                return {
                    "committed": False,
                    "reason": "row_errors",
                    "file_info": file_info,
                    "imports": result_payload
                }

            # snapshots on success
            for item in result_payload:
                model_name = item["model"]
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)

                pre = next(b for b in prepared if b["model"] == model_name)
                rows_src = [r.get("_original_input") or r.get("payload") or {} for r in pre["rows"]]
                fp = _table_fingerprint(model, rows_src)
                closest = (item.get("dup_info") or {}).get("closest_match") or {}
                ImportSnapshot.objects.create(
                    company_id=company_id,
                    model_name=model_name,
                    row_count=fp["row_count"],
                    colnames=fp["colnames"],
                    row_hash_sample=fp["row_hashes"][:200],
                    table_hash=fp["table_hash"],
                    file_sha256=file_sha,
                    filename=filename,
                    jaccard_to_prev=closest.get("jaccard"),
                )

            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=True))
            return {
                "committed": True,
                "file_info": file_info,
                "imports": result_payload
            }

# Celery entrypoint: one task per file
@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)
