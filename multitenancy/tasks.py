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
            self._cm.__enter__()
        except Exception:
            # Older Django versions or non-standard backends: just no-op
            self._cm = None
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc, tb)
        finally:
            return False

# ----------------------------------------------------------------------
# Email helpers
# ----------------------------------------------------------------------

def _sanity_check_required_fks(model, payload: Dict[str, Any], original_input: Dict[str, Any], merged_map_keys: List[str]) -> List[Tuple[str, Any]]:
    """
    Return a list of (field_name, token) for non-nullable FKs that were provided as <field>_fk
    in the original input but remain unresolved (payload[<field>] is None).

    The original implementation looked only for the base field name in the normalized payload,
    which can cause false positives when the importer saves resolved foreign keys under the
    underlying attname (e.g., ``company_id``).  This version checks both the field name and
    the attname for a resolved value.
    """
    issues: List[Tuple[str, Any]] = []
    for f in model._meta.get_fields():
        # Skip anything that's not a ForeignKey or is nullable
        if not isinstance(f, dj_models.ForeignKey) or getattr(f, "null", False):
            continue

        base = f.name
        token = original_input.get(f"{base}_fk", None)
        # Only care if they provided a *_fk token that isn't obviously missing
        # Note: float("nan") is not equal to itself, so we detect NaNs via this trick.
        missing_token = token is None or token == ""
        if not missing_token:
            # Treat float('nan') as missing as well
            if isinstance(token, float) and token != token:
                missing_token = True
        if missing_token:
            continue
        # Determine if the foreign key has been resolved in the normalized payload.
        # The importer stores FK values under either the field name (e.g. 'transaction')
        # or the underlying attname (e.g. 'transaction_id').  We check both.
        value = None
        # Prefer the field name if presents
        if base in payload:
            value = payload.get(base)
        else:
            attname = getattr(f, "attname", None)
            if attname:
                value = payload.get(attname)
        # If still None, the FK is unresolved.
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
    # row_map keeps unsaved instances keyed by sheet token per model, e.g. row_map["Transaction"]["t1"] = instance
    row_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})
    # pk_map keeps resolved PKs when available (commit mode or existing ids)
    pk_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})

def _log(level: int, msg: str, ic: ImportContext, *, model: str = "-", row_id: str = "-", **fields):
    # always include context so the formatter has these keys
    extra = {"run_id": ic.run_id, "company": ic.company_id, "model": model, "row_id": row_id, **fields}
    logger.log(level, msg, extra=extra)

class RateLimitFilter(logging.Filter):
    # naive per-message throttle to avoid Railway 500 logs/sec drop
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
    """
    Keep both the instance and its PK available to downstream sheets/rows.
    Using PKs too makes resolution robust even if instance identity gets weird in nested transactions.
    """
    if not rid:
        return
    pk = getattr(instance, "pk", None)
    global_map_inst[rid] = instance
    if isinstance(pk, int):
        global_map_pk[rid] = pk

def _resolve_token_from_maps(token: str,
                             local_inst: Dict[str, Any],
                             local_pk: Dict[str, int],
                             global_inst: Dict[str, Any],
                             global_pk: Dict[str, int]) -> Any:
    """
    Return instance if we have one; otherwise resolve via PK if available.
    """
    if token in local_inst:
        return local_inst[token]
    if token in global_inst:
        return global_inst[token]
    # Fall back to PKs
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

def _remember_row(ic: ImportContext, model_name: str, token: str, instance: Any):
    ic.row_map.setdefault(model_name, {})[token] = instance
    _log(logging.INFO, f"Mapped __row_id '{token}' -> {model_name}(id={getattr(instance, 'pk', None)})",
         ic, model=model_name, row_id=token)

def _resolve_fk(model_cls, field_name: str, raw_value: Any, row_id_map: Optional[Dict[str, Any]] = None) -> Any:
    """
    Accepts:
      - instance of the remote model  -> returns the instance (OK to assign to FK)
      - primary key as int/str        -> returns int(pk)
      - token (e.g., 't1', 'Transaction:t1') -> resolved via row_id_map to instance or pk
    Returns a value directly assignable to the model's FK field (instance or pk).
    """
    if raw_value in (None, ""):
        return None

    field, remote_model, remote_name = _get_field_and_remote_model(model_cls, field_name)

    # already an instance?
    if isinstance(raw_value, remote_model):
        return raw_value

    # primary key as int?
    if isinstance(raw_value, int):
        return raw_value

    # primary key as numeric string?
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value.strip())

    # token lookup in provided row-id map(s)
    token = str(raw_value).strip()
    norm_token = _norm_row_key(token)
    maps = row_id_map or {}

    # direct token
    candidate = maps.get(norm_token)
    if candidate is None and ":" in token:
        # allow "Model:token" form
        maybe_model, maybe_token = token.split(":", 1)
        if maybe_model.strip() == remote_name:
            candidate = maps.get(_norm_row_key(maybe_token.strip()))

    # if we found something, normalize return type
    if candidate is not None:
        if isinstance(candidate, remote_model):
            return candidate
        if isinstance(candidate, int):
            return candidate
        # sometimes callers stash pk under an instance-like wrapper; try to pick pk
        pk = getattr(candidate, "pk", getattr(candidate, "id", None))
        if pk is not None:
            return pk

        # fallthrough → bad candidate type
        raise ValueError(
            f"Resolved token {token!r} for {model_cls.__name__}.{field_name} but got unsupported type "
            f"{type(candidate).__name__}"
        )

    # Could not resolve token
    known = list(maps.keys())
    preview = ", ".join(known[:20]) + (" ..." if len(known) > 20 else "")
    logger.error(
        "Unresolved FK token for %s.%s | token=%r | known_row_ids=[%s]",
        model_cls.__name__, field_name, token, preview, **_log_extra()
    )
    raise ValueError(
        f"Invalid FK reference format {token!r} for field '{field_name}'. "
        f"Expected numeric id, instance of {remote_name}, or a run token present in known __row_id keys."
    )
    
def _build_instance(model_cls: type, payload: dict) -> models.Model:
    return model_cls(**payload)

def _full_clean_preview(instance: models.Model, exclude_fields: List[str]):
    # Skip `validate_unique` in preview to avoid DB queries/false errors.
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

    # common coercions
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
    """
    Accept base names (e.g., 'entity'), DB attnames (e.g., 'entity_id'),
    and importer aliases '*_fk'. Also path cols, '__row_id', 'id'.
    """
    names = set()
    for f in model._meta.fields:
        names.add(f.name)
        att = getattr(f, "attname", None)
        if att:
            names.add(att)  # e.g., 'entity_id'
    fk_aliases = {n + "_fk" for n in names}
    return names | fk_aliases | set(PATH_COLS) | {"__row_id", "id"}

def _filter_unknown(model, row: Dict[str, Any]):
    """Return (filtered_row, unknown_keys) keeping only allowed keys for this model."""
    allowed = _allowed_keys(model)
    filtered = {k: v for k, v in row.items() if k in allowed}
    unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
    return filtered, unknown

def _preflight_missing_required(model, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Only flag truly required fields (concrete/not-null/no default/not auto/not timestamp).
    Treat presence of either <field>, <field>_id, or <field>_fk as satisfying the requirement.
    """
    errors = {}

    # Build metadata for required fields and map base -> accepted keys
    required_fields = []
    field_map = {}  # base name -> {accepted keys}
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
    """Quantize all DecimalField values to the model's decimal_places."""
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
    """Coerce stringy booleans to bool for BooleanFields."""
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.BooleanField):
            name = getattr(f, 'attname', f.name)
            if name in out:
                out[name] = _to_bool(out[name])
    return out

# --------- canonicalization & fingerprint for table-level dedupe ----------
_WS_RE = re.compile(r"\s+")
def _norm_scalar(val):
    if val is None: return None
    if isinstance(val, (bool, int)): return val
    if isinstance(val, float): return float(str(val))  # reduce float noise
    if isinstance(val, Decimal): return str(val)
    s = str(val).strip()
    return _WS_RE.sub(" ", s)

IGNORE_FIELDS = {"id", "created_at", "updated_at", "created_by", "updated_by", "is_deleted", "is_active"}

def _canonicalize_row(model, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stable identity using "all non-volatile fields present in row & on model".
    Folds *_fk into base name; quantizes DecimalFields; ISO for dates; NaN/NaT-safe FK ids.
    """
    field_by = {f.name: f for f in model._meta.get_fields() if hasattr(f, "attname")}
    allowed = set(field_by.keys())

    # fold *_fk
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

        # Normalize missing-ish values first (None, "", NaN, NaT, "NaT")
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
            out[k] = _to_int_or_none_soft(v)  # NaN-safe FK id coercion
        else:
            out[k] = _norm_scalar(v)
    return out

def _row_hash(model, row: Dict[str, Any]) -> str:
    c = _canonicalize_row(model, row)
    blob = json.dumps(c, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def _table_fingerprint(model, rows: List[Dict[str, Any]], sample_n: int = 200) -> Dict[str, Any]:
    rhashes = [_row_hash(model, r) for r in rows]
    unique_sorted = sorted(set(rhashes))  # order-insensitive, dedup
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

# ----------------------------------------------------------------------
# Core import executor
# ----------------------------------------------------------------------

DUP_CHECK_LAST_N = 10  # compare against last N snapshots per model



def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
    """
    Decide create/update, normalize 'id' for ORM, and carry external text id (if any).
    Returns: (action: 'create'|'update', pk_or_none: Optional[int], external_id: Optional[str])
    """
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
    """
    One-shot import for all models in a file.

    - Global __row_id map so cross-sheet FKs like JournalEntry.transaction_fk="t1" resolve.
    - NaN/NaT-safe canonicalization to avoid "cannot convert float NaN to integer".
    - Booleans/decimals coercion and basic dedupe fingerprints per sheet.
    - Never special-cases a model; model-level validation enforces invariants.
    """
    ORDER_HINT = {name: i for i, name in enumerate(MODEL_APP_MAP.keys())}
    
    run_id = uuid.uuid4().hex[:8]
    ic = ImportContext(run_id=run_id, company_id=company_id, commit=commit)
    
    _run_id_ctx.set(run_id)
    _company_ctx.set(str(company_id))
    _model_ctx.set("-")
    _row_ctx.set("-")
    verbose = _import_debug_enabled()

    # --------------------------- file-level dedupe ---------------------------
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
        # --------------------------- prep per sheet ---------------------------
        prepared: List[Dict[str, Any]] = []
        models_in_order: List[str] = []
        any_prep_error = False
        dup_infos: Dict[str, Dict[str, Any]] = {}

        for sheet in sheets:
            model_name = sheet["model"]
            _model_ctx.set(model_name)

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                logger.error(
                    "sheet_app_missing",
                    **_log_extra(error=f"MODEL_APP_MAP missing entry for '{model_name}'")
                )
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
            logger.info("sheet_start", **_log_extra(row_count=len(raw_rows)))

            # substitutions + audit
            rows, audit = apply_substitutions(raw_rows, company_id=company_id, model_name=model_name, return_audit=True)
            audit_by_rowid = {}
            for ch in audit:
                audit_by_rowid.setdefault(ch.get("__row_id"), []).append(ch)

            # MPTT: ensure parents first
            if _is_mptt_model(model):
                rows = sorted(rows, key=_path_depth)

            # ---- table-level fingerprint (order-insensitive) ----
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
            if verbose:
                logger.debug("dup_info", **_log_extra(**dup_infos[model_name]))

            # ---- preflight for missing required ----
            preflight_err = _preflight_missing_required(model, rows)
            if preflight_err and verbose:
                logger.debug("preflight_summary", **_log_extra(missing_required=len(preflight_err)))

            # ---- pack rows for downstream (message reflects unknown columns) ----
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

                    # MPTT: keep name, defer parent resolution
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
                            if verbose:
                                logger.debug("mptt_path_folded", **_log_extra(path_value=path_val, parent_chain=parts[:-1], leaf=leaf))

                    action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)
                    if verbose:
                        logger.debug("row_pre", **_log_extra(action=action, has_unknown_cols=False))

                    unknown_cols_now = _unknown_from_original_input(model, {
                        "_original_input": original_input, "payload": payload
                    })
                    if unknown_cols_now and verbose:
                        logger.debug("row_unknown_cols", **_log_extra(count=len(unknown_cols_now), cols=unknown_cols_now[:30]))

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
                    unknown_cols_now = _unknown_from_original_input(model, {
                        "_original_input": original_input, "payload": tmp_payload
                    })
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
            models_in_order.append(model_name)
            logger.info("sheet_end", **_log_extra(had_error=bool(had_err)))

        # make processing deterministic/parent-first
        models_in_order.sort(key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        # ------------------------------ PREVIEW ------------------------------
        if not commit:
            models_touched: List[Any] = []
            result_payload: List[Dict[str, Any]] = []

            # Global maps available across all sheets (instances + PKs)
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
            
                    # Per-model maps (instances + PKs)
                    row_map_inst: Dict[str, Any] = {}
                    row_map_pk: Dict[str, int] = {}
            
                    rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                    out_rows: List[Dict[str, Any]] = []
            
                    if verbose:
                        logger.debug("model_begin_preview", **_log_extra(rows=len(rows),
                                                                         global_map_size=len(global_row_map_inst)))
            
                    for row in rows:
                        rid_raw = row.get("__row_id") or f"row{len(out_rows)+1}"
                        rid = _norm_row_key(rid_raw)
                        _row_ctx.set(rid)
            
                        if row.get("status") == "error" and row.get("preflight_error"):
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": row.get("action"),
                                "data": row.get("_original_input") or row.get("payload") or {},
                                "message": row["preflight_error"]["message"],
                                "error": row["preflight_error"],
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })
                            if verbose:
                                logger.debug("row_skip_preflight", **_log_extra())
                            continue
            
                        payload = dict(row.get("payload") or {})
                        original_input = row.get("_original_input") or payload.copy()
                        action = row.get("action") or "create"
                        unknown_cols_now = _unknown_from_original_input(model, row)
            
                        try:
                            # 1) Resolve *_fk tokens using LOCAL + GLOBAL maps
                            fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                            for fk_key in fk_keys:
                                field_name = fk_key[:-3]
                                fk_val = payload.pop(fk_key)
                                if _is_missing(fk_val):
                                    payload[field_name] = None
                                    continue
            
                                # merged key sets (only for logging)
                                known_tokens = list({**global_row_map_inst, **row_map_inst}.keys())
                                if isinstance(fk_val, str):
                                    preview = ", ".join(known_tokens[:20]) + (" ..." if len(known_tokens) > 20 else "")
                                    logger.info(
                                        "Resolving FK token for %s.%s | token=%r | known_row_ids=[%s]",
                                        model.__name__, field_name, fk_val, preview,
                                        **_log_extra()
                                    )
            
                                # resolve: try instances first, then PKs, else numeric
                                candidate = None
                                if isinstance(fk_val, str):
                                    candidate = _resolve_token_from_maps(
                                        _norm_row_key(fk_val),
                                        row_map_inst, row_map_pk,
                                        global_row_map_inst, global_row_map_pk
                                    )
            
                                merged_maps = {**global_row_map_inst, **row_map_inst}

                                if candidate is not None:
                                    payload[field_name] = _resolve_fk(model, field_name, candidate, merged_maps)
                                else:
                                    payload[field_name] = _resolve_fk(model, field_name, fk_val, merged_maps)
                                
                                # Log resolution result (only if it was a string token)
                                if isinstance(fk_val, str):
                                    resolved_obj = payload[field_name]
                                    if resolved_obj is None:
                                        logger.warning(
                                            "FK token %r for %s.%s could not be resolved",
                                            fk_val, model.__name__, field_name, **_log_extra()
                                        )
                                    else:
                                        logger.info(
                                            "Resolved %s.%s: %r -> %s(id=%s)",
                                            model.__name__, field_name, fk_val,
                                            resolved_obj.__class__.__name__, getattr(resolved_obj, "id", None),
                                            **_log_extra()
                                        )
            
                            # 2) Optional rescue — token mistakenly placed in base FK field
                            for f in model._meta.get_fields():
                                if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                    base = f.name
                                    val = payload.get(base)
                                    if isinstance(val, str):
                                        token = _norm_row_key(val)
                                        candidate = _resolve_token_from_maps(
                                            token, row_map_inst, row_map_pk, global_row_map_inst, global_row_map_pk
                                        )
                                        if candidate is not None:
                                            logger.warning(
                                                "Rescuing misplaced token in %s.%s: %r",
                                                model.__name__, base, val, **_log_extra()
                                            )
                                            payload[base] = _resolve_fk(model, base, candidate, {**global_row_map_inst, **row_map_inst})
                                        else:
                                            # leave as-is; full_clean will complain and we’ll show a clear error
                                            pass
            
                            # 3) MPTT parent resolution (unchanged)
                            if _is_mptt_model(model):
                                path_val = _get_path_value(payload)
                                if path_val:
                                    parts = _split_path(path_val)
                                    parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                    payload["parent"] = parent
                                    payload.pop("parent_id", None)
                                    if verbose:
                                        logger.debug("mptt_parent_resolved", **_log_extra(parent_chain=parts[:-1],
                                                                                           has_parent=bool(parent)))
            
                            # 4) Sanity check unresolved non-nullable FKs (friendly message)
                            merged_keys = list({**global_row_map_inst, **row_map_inst}.keys())
                            issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                            if issues:
                                for base, token in issues:
                                    logger.error(
                                        "Unresolved FK token %r for required field %s.%s (known row_ids: %s)",
                                        token, model.__name__, base, merged_keys[:50], **_log_extra()
                                    )
                                raise ValidationError({
                                    base: [f"Unresolved FK token {token!r}. Known __row_id keys: {merged_keys[:50]}"]
                                    for base, token in issues
                                })
            
                            # 5) Coerce types, then save in a savepoint
                            payload = _coerce_boolean_fields(model, payload)
                            payload = _quantize_decimal_fields(model, payload)
            
                            if verbose:
                                logger.debug("row_payload_before_clean", **_log_extra(keys=sorted(payload.keys())[:40]))
            
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
            
                            # 6) Register __row_id → instance + PK in both local and global maps
                            if rid:
                                _register_row_token(row_map_inst, row_map_pk, rid, instance)
                                _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)
                                logger.info("Mapped __row_id '%s' -> %s(id=%s)",
                                            rid, model.__name__, getattr(instance, "id", None),
                                            **_log_extra())
            
                            # 7) Build response row
                            msg = "ok"
                            status_val = "success"
                            if unknown_cols_now and row.get("status") != "error":
                                status_val = "warning"
                                msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)
            
                            out_rows.append({
                                "__row_id": rid,
                                "status": status_val,
                                "action": action,
                                "data": safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                                "message": msg,
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })
                            if verbose:
                                logger.debug("row_ok", **_log_extra(action=action, status=status_val))
            
                        except Exception as e:
                            err = exception_to_dict(e, include_stack=False)
                            base_msg = err.get("summary") or _friendly_db_message(e)
                            if unknown_cols_now:
                                base_msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)
                            logger.error(
                                "[IMPORT][PREVIEW][EXC] model=%s row_id=%s action=%s err=%s",
                                model_name, rid, action, base_msg,
                                exc_info=True, **_log_extra()
                            )
                            out_rows.append({
                                "__row_id": rid,
                                "status": "error",
                                "action": action,
                                "data": original_input,
                                "message": base_msg,
                                "error": {**err, "summary": base_msg},
                                "observations": row.get("observations", []),
                                "external_id": row.get("external_id"),
                            })
            
                    if verbose:
                        logger.debug("model_end_preview", **_log_extra(local_map_size=len(row_map_inst),
                                                                       global_map_size=len(global_row_map_inst)))
            
                    result_payload.append({
                        "model": model_name,
                        "dup_info": dup_infos.get(model_name),
                        "result": out_rows
                    })
            
                # Roll back preview and reset sequences (unchanged)
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

        # Global __row_id map shared across ALL sheets
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

                if verbose:
                    logger.debug("model_begin_commit", **_log_extra(rows=len(rows),
                                                                    global_map_size=len(global_row_map)))

                for row in rows:
                    rid = _norm_row_key(row["__row_id"])
                    _row_ctx.set(rid)

                    # Skip rows that already failed preflight
                    if row.get("status") == "error" and row.get("preflight_error"):
                        row.update({
                            "status": "error",
                            "action": row.get("action"),
                            "data": row.get("_original_input") or row.get("payload") or {},
                            "message": row["preflight_error"]["message"],
                            "error": row["preflight_error"],
                        })
                        any_row_error = True
                        if verbose:
                            logger.debug("row_skip_preflight_error", **_log_extra())
                        continue

                    payload = dict(row.get("payload") or {})
                    original_input = row.get("_original_input") or payload.copy()
                    action = row.get("action") or "create"

                    unknown_cols_now = _unknown_from_original_input(model, row)

                    try:
                        # Resolve *_fk using LOCAL + GLOBAL row maps (keys normalized)
                        for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                            field_name = fk_key[:-3]
                            fk_val = payload.pop(fk_key)
                            merged_map = {**global_row_map, **row_map}
                            if IMPORT_VERBOSE_FK and isinstance(fk_val, str):
                                logger.debug(
                                    "[FK] %s.%s -> %r (norm=%r); known row_ids: %s%s",
                                    model.__name__, field_name, fk_val, _norm_row_key(fk_val),
                                    list(merged_map.keys())[:20], " ..." if len(merged_map) > 20 else ""
                                )
                            payload[field_name] = _resolve_fk(model, field_name, fk_val, merged_map)

                        # Optional rescue: wrong column used (token put directly under base FK)
                        for f in model._meta.get_fields():
                            if isinstance(f, dj_models.ForeignKey) and getattr(f, "null", False) is False:
                                base = f.name
                                val = payload.get(base)
                                if isinstance(val, str):
                                    merged_map = {**global_row_map, **row_map}
                                    if IMPORT_VERBOSE_FK:
                                        logger.debug("[FK][RESCUE] %s.%s had string token %r; attempting row-id resolution",
                                                     model.__name__, base, val)
                                    payload[base] = _resolve_fk(model, base, val, merged_map)

                        # MPTT parent chain
                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload['parent'] = parent
                                payload.pop('parent_id', None)
                                if verbose:
                                    logger.debug("mptt_parent_resolved", **_log_extra(parent_chain=parts[:-1],
                                                                                       has_parent=bool(parent)))

                        # --- sanity check unresolved non-nullable FKs that had *_fk in input ---
                        merged_keys = list(({**global_row_map, **row_map}).keys())
                        issues = _sanity_check_required_fks(model, payload, original_input, merged_keys)
                        if issues:
                            for base, token in issues:
                                logger.warning(
                                    "[FK][UNRESOLVED] %s.%s token=%r norm=%r known_row_ids=%s",
                                    model.__name__, base, token,
                                    _norm_row_key(token) if isinstance(token, str) else token,
                                    merged_keys[:50],
                                    **_log_extra()
                                )
                            raise ValidationError({
                                base: [f"Unresolved FK token {token!r}. Known __row_id keys (first 50): {merged_keys[:50]}"]
                                for base, token in issues
                            })

                        # Coerce booleans/decimals just before save
                        payload = _coerce_boolean_fields(model, payload)
                        payload = _quantize_decimal_fields(model, payload)

                        if verbose:
                            logger.debug("row_payload_before_clean", **_log_extra(keys=sorted(payload.keys())[:40]))

                        with transaction.atomic():
                            # Build instance
                            if action == "update":
                                instance = model.objects.select_for_update().get(id=payload["id"])
                                for f, v in payload.items():
                                    setattr(instance, f, v)
                            else:
                                instance = model(**payload)

                            # --- Clean first so model.save() sees proper types ---
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
                            global_row_map[rid] = instance  # <-- make visible to other sheets

                        msg = "ok"
                        status_val = "success"
                        if unknown_cols_now and row.get("status") != "error":
                            status_val = "warning"
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                        row.update({
                            "status": status_val,
                            "action": action,
                            "data": safe_model_dict(instance, exclude_fields=['created_by','updated_by','is_deleted','is_active']),
                            "message": msg,
                        })
                        if verbose:
                            logger.debug("row_ok", **_log_extra(action=action, status=status_val))

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

                if verbose:
                    logger.debug("model_end_commit", **_log_extra(local_map_size=len(row_map),
                                                                  global_map_size=len(global_row_map)))

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

            # ---------- Persist snapshots per sheet (commit success only) ----------
            for item in result_payload:
                model_name = item["model"]
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)

                pre = next(b for b in prepared if b["model"] == model_name)
                rows_src = [r.get("_original_input") or r.get("payload") or {} for r in pre["rows"]]
                fp = _table_fingerprint(model, rows_src)

                closest = (item.get("dup_info") or {}).get("closest_match") or {}
                if verbose:
                    logger.debug("snapshot_prepare", **_log_extra(model=model_name,
                                                                  row_count=fp["row_count"],
                                                                  col_count=len(fp["colnames"])))
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
