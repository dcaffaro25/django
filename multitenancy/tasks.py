# multitenancy/tasks.py
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import smtplib
import time
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.mail import send_mail
from django.db import (
    connection,
    models as dj_models,
    transaction,
)
from django.db.models import NOT_PROVIDED, Model

from core.utils.db_sequences import reset_pk_sequences
from core.utils.exception_utils import exception_to_dict
from multitenancy.formula_engine import apply_substitutions
from multitenancy.models import ImportSnapshot, IntegrationRule
from .api_utils import (
    MODEL_APP_MAP,
    PATH_COLS,
    _get_path_value,
    _is_mptt_model,
    _norm_row_key,
    _parse_json_or_empty,
    _path_depth,
    _resolve_parent_from_path_chain,
    _split_path,
    _to_bool,
    _to_int_or_none,
    _to_int_or_none_soft,
    _is_missing,
    safe_model_dict,
)

# --------------------------------------------------------------------------------------
# Logging setup (defensive against gunicorn's access formatter)
# --------------------------------------------------------------------------------------
logger = logging.getLogger("importer")
sql_logger = logging.getLogger("importer.sql")

try:
    # Keep gunicorn.access from reformatting our structured "extra" fields
    logging.getLogger("gunicorn.access").propagate = False
except Exception:
    pass

_run_id_ctx = ContextVar("run_id", default="-")
_company_ctx = ContextVar("company_id", default="-")
_model_ctx = ContextVar("model", default="-")
_row_ctx = ContextVar("row_id", default="-")


def _import_debug_enabled() -> bool:
    val = getattr(settings, "IMPORT_DEBUG", None)
    if val is None:
        val = os.getenv("IMPORT_DEBUG", "0")
    return str(val).lower() in {"1", "true", "yes", "y", "on"}


def _log_extra(**kw):
    return {
        "extra": {
            "run_id": _run_id_ctx.get(),
            "company": _company_ctx.get(),
            "company_id": _company_ctx.get(),
            "model": _model_ctx.get(),
            "row_id": _row_ctx.get(),
            **kw,
        }
    }


class _EnsureCtxKeysFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for k in ("run_id", "company", "company_id", "model", "row_id"):
            if not hasattr(record, k):
                setattr(record, k, "-")
        return True


if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter(
        "%(levelname)s %(asctime)s importer %(message)s | run_id=%(run_id)s company=%(company)s model=%(model)s row_id=%(row_id)s"
    )
    h.setFormatter(fmt)
    h.addFilter(_EnsureCtxKeysFilter())
    logger.addHandler(h)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if _import_debug_enabled() else logging.INFO)

if not sql_logger.handlers:
    h2 = logging.StreamHandler()
    fmt2 = logging.Formatter("SQL %(levelname)s %(asctime)s %(message)s | run_id=%(run_id)s")
    h2.setFormatter(fmt2)
    h2.addFilter(_EnsureCtxKeysFilter())
    sql_logger.addHandler(h2)
    sql_logger.propagate = False
    sql_logger.setLevel(logging.DEBUG if _import_debug_enabled() else logging.INFO)

IMPORT_VERBOSE_FK = os.getenv("IMPORT_VERBOSE_FK", "0").lower() in {"1", "true", "yes", "y", "on"}


class _SlowSQL:
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
                        sql_logger.info(
                            "slow_sql",
                            **_log_extra(duration_ms=int(dt * 1000), many=bool(many), sql=str(sql)[:1000]),
                        )

            self._cm = connection.execute_wrapper(wrapper)
            self._cm.__enter__()
        except Exception:
            self._cm = None
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc, tb)
        finally:
            return False


# --------------------------------------------------------------------------------------
# Email helpers
# --------------------------------------------------------------------------------------
@shared_task(bind=True, autoretry_for=(smtplib.SMTPException, ConnectionError), retry_backoff=True, max_retries=5)
def send_user_invite_email(self, subject, message, to_email):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_email(self, subject, message, to_email):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


# --------------------------------------------------------------------------------------
# Integration triggers
# --------------------------------------------------------------------------------------
@shared_task
def execute_integration_rule(rule_id, payload):
    rule = IntegrationRule.objects.get(pk=rule_id)
    return rule.run_rule(payload)


@shared_task
def trigger_integration_event(company_id, event_name, payload):
    rules = (
        IntegrationRule.objects
        .filter(company_id=company_id, is_active=True, triggers__icontains=event_name)
        .order_by("execution_order")
    )
    for rule in rules:
        if rule.use_celery:
            execute_integration_rule.delay(rule.id, payload)
        else:
            execute_integration_rule(rule.id, payload)


# --------------------------------------------------------------------------------------
# Import helpers
# --------------------------------------------------------------------------------------
@dataclass
class ImportContext:
    run_id: str
    company_id: int
    commit: bool


def _stringify_instance(obj: Model) -> str:
    try:
        return f"{obj.__class__.__name__}(id={getattr(obj, 'pk', None)})"
    except Exception:
        return f"{obj.__class__.__name__}(id=?)"


def _repr_map_inst(m: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in m.items():
        out[k] = _stringify_instance(v) if isinstance(v, Model) else v
    return out


def _register_row_token(global_row_map_inst: Dict[str, Any], global_row_map_pk: Dict[str, int], rid: str, instance: Any):
    if not rid:
        return
    key = _norm_row_key(rid)
    pk = getattr(instance, "pk", None)
    global_row_map_inst[key] = instance
    if isinstance(pk, int):
        global_row_map_pk[key] = pk


def _assign_fk_value(model_cls, field_name: str, resolved_value: Any, payload: dict) -> tuple[str, Any]:
    field = model_cls._meta.get_field(field_name)
    attname = getattr(field, "attname", field_name)
    if isinstance(resolved_value, int):
        payload.pop(field_name, None)
        payload[attname] = resolved_value
        return attname, resolved_value
    else:
        payload[field_name] = resolved_value
        payload.pop(attname, None)
        return field_name, resolved_value


def _resolve_fk(model_cls, field_name: str, raw_value: Any) -> Any:
    """
    Accepts:
      - Model instance
      - integer id (or stringified integer)
      - token string (we don't resolve here)
    Returns:
      - instance or int id
    Raises:
      - ValueError for invalid formats
    """
    if raw_value in (None, ""):
        return None

    field = model_cls._meta.get_field(field_name)
    remote_model = getattr(field, "remote_field", None).model if getattr(field, "remote_field", None) else None

    # direct model instance
    if isinstance(raw_value, Model):
        if remote_model and not isinstance(raw_value, remote_model):
            raise ValueError(f"{model_cls.__name__}.{field_name} expects {remote_model.__name__} instance, got {raw_value.__class__.__name__}")
        return raw_value

    # direct numeric id
    if isinstance(raw_value, int) or (isinstance(raw_value, str) and str(raw_value).strip().isdigit()):
        return int(raw_value)

    # token-ish – leave resolution to SAVE pass
    if isinstance(raw_value, str):
        s = str(raw_value).strip()
        if s:
            return s  # token; will be handled as deferred if needed

    raise ValueError(f"Invalid FK reference {raw_value!r} for '{field_name}'")


def _normalize_payload_for_model(model, payload: Dict[str, Any], *, context_company_id=None):
    data = dict(payload)
    field_names = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}

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

    # strip unknowns except *_fk aliases
    for k in list(data.keys()):
        if k in ("id",):
            continue
        try:
            model._meta.get_field(k)
        except FieldDoesNotExist:
            if not (k.endswith("_id") and k[:-3] in field_names) and not k.endswith("_fk"):
                data.pop(k, None)
    return data


def _row_observations(audit_by_rowid, row_id):
    obs = []
    for ch in audit_by_rowid.get(row_id, []):
        if ch.get("field") == "__row_id":
            continue
        obs.append(f"campo '{ch.get('field')}' alterado de '{ch.get('old')}' para '{ch.get('new')}' (regra id={ch.get('rule_id')})")
    return obs


def _allowed_keys(model):
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
    """
    Only checks for required fields that are *not FK tokens slated for deferral*.
    The actual FK token resolution happens during the SAVE pass.
    """
    errors = {}
    # Collect required fields (non-null, no default, not auto)
    required_fields = []
    field_map = {}
    for f in model._meta.fields:
        if not hasattr(f, "attname"):
            continue
        is_auto_ts = ((getattr(f, "auto_now", False)) or (getattr(f, "auto_now_add", False)))
        has_default = (getattr(f, "default", NOT_PROVIDED) is not NOT_PROVIDED)
        if (not f.null) and (not f.primary_key) and (not f.auto_created) and (not has_default) and (not is_auto_ts):
            required_fields.append(f)
        base = f.name
        attn = getattr(f, "attname", f.name)
        accepted = {base, attn, f"{base}_fk"}
        field_map[base] = accepted

    for i, row in enumerate(rows):
        rid = _norm_row_key(row.get("__row_id") or f"row{i+1}")
        payload = {k: v for k, v in row.items() if k != "__row_id"}

        missing = []
        for f in required_fields:
            base = f.name
            present = any((k in payload and payload.get(k) not in ("", None)) for k in field_map.get(base, {base}))
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
            name = getattr(f, "attname", f.name)
            if name in out and out[name] not in (None, ""):
                dp = int(getattr(f, "decimal_places", 0) or 0)
                q = Decimal("1").scaleb(-dp)
                out[name] = Decimal(str(out[name])).quantize(q, rounding=ROUND_HALF_UP)
    return out


def _coerce_boolean_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.BooleanField):
            name = getattr(f, "attname", f.name)
            if name in out:
                out[name] = _to_bool(out[name])
    return out


_WS_RE = re.compile(r"\s+")


def _norm_scalar(val):
    if val is None:
        return None
    if isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        return float(str(val))
    if isinstance(val, Decimal):
        return str(val)
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
            dp = int(getattr(f, "decimal_places", 0) or 0)
            q = Decimal("1").scaleb(-dp)
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
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni


def _unknown_from_original_input(model, row_obj: Dict[str, Any]) -> List[str]:
    allowed = _allowed_keys(model)
    orig = row_obj.get("_original_input") or row_obj.get("payload") or {}
    return sorted([k for k in orig.keys() if k not in allowed and k != "__row_id"])


# --------------------------------------------------------------------------------------
# Simple helpers for actions / tokens
# --------------------------------------------------------------------------------------
def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
    def _coerce_pk(val):
        if val is None or val == "":
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val) if float(val).is_integer() else None
        s = str(val).strip()
        if s.isdigit():
            return int(s)
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


# --------------------------------------------------------------------------------------
# Topological sort (used for tokens within a group)
# --------------------------------------------------------------------------------------
def _toposort_nodes(nodes: List[str], depends_on: Dict[str, set], tie_break_key) -> List[str]:
    all_nodes = set(nodes)
    for n in list(depends_on.keys()):
        all_nodes.add(n)
        all_nodes |= set(depends_on[n])

    indeg = {n: 0 for n in all_nodes}
    adj = {n: set() for n in all_nodes}
    for a in all_nodes:
        for b in depends_on.get(a, set()):
            if b in all_nodes:
                adj[b].add(a)  # b -> a
                indeg[a] += 1

    q = deque(sorted([n for n in all_nodes if indeg[n] == 0], key=tie_break_key))
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in sorted(adj[u], key=tie_break_key):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    # If cycle, just fall back to tie-break order for the remaining nodes
    if len(out) != len(all_nodes):
        rem = [n for n in all_nodes if n not in out]
        out.extend(sorted(rem, key=tie_break_key))

    # Return only requested nodes in produced order
    final = [n for n in out if n in set(nodes)]
    for n in nodes:
        if n not in final:
            final.append(n)
    return final


# --------------------------------------------------------------------------------------
# Core import executor — per-group savepoints with FK deferral
# --------------------------------------------------------------------------------------
DUP_CHECK_LAST_N = 10


@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)


def execute_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool, *, file_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ORDER_HINT = {name: i for i, name in enumerate(MODEL_APP_MAP.keys())}

    run_id = uuid.uuid4().hex[:8]
    _run_id_ctx.set(run_id)
    _company_ctx.set(str(company_id))
    _model_ctx.set("-")
    _row_ctx.set("-")

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
        **_log_extra(commit=bool(commit), import_filename=filename, file_sha=file_sha, file_size=file_size, sheet_count=len(sheets)),
    )

    t0 = time.monotonic()
    with _SlowSQL(threshold_ms=200):
        # ---------------- PREP ----------------
        prepared: List[Dict[str, Any]] = []
        models_in_order: List[str] = []
        dup_infos: Dict[str, Dict[str, Any]] = {}

        # run-wide instance + pk maps (for token staging; pk entries are populated only during per-group saves)
        global_row_map_inst: Dict[str, Any] = {}  # token -> instance (possibly unsaved)
        global_row_map_pk: Dict[str, int] = {}    # token -> pk (only after save)

        # For grouping and ordering
        staged_by_token: Dict[str, Dict[str, Any]] = {}  # token -> row_bundle skeleton (filled later)
        token_to_model: Dict[str, str] = {}
        token_insertion_index: Dict[str, int] = {}  # stable tie-break across whole file

        insertion_counter = 0

        for sheet in sheets:
            model_name = sheet["model"]
            _model_ctx.set(model_name)

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                logger.error("sheet_app_missing", **_log_extra(error=f"MODEL_APP_MAP missing entry for '{model_name}'"))
                prepared.append({"model": model_name, "rows": [], "had_error": True, "sheet_error": f"MODEL_APP_MAP missing entry for '{model_name}'"})
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

                    if _is_mptt_model(model):
                        path_val = _get_path_value(payload)
                        if path_val:
                            parts = _split_path(path_val)
                            if not parts:
                                raise ValueError(f"{model_name}: empty path.")
                            leaf = parts[-1]
                            payload["name"] = payload.get("name", leaf) or leaf
                            payload.pop("parent_id", None)
                            payload.pop("parent_fk", None)
                            for c in PATH_COLS:
                                payload.pop(c, None)

                    payload = _coerce_boolean_fields(model, payload)
                    payload = _quantize_decimal_fields(model, payload)

                    action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": payload})

                    status_val = "ok"
                    msg = "validated"
                    if unknown_cols_now:
                        status_val = "warning"
                        msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                    if rid in preflight_err:
                        status_val = "error"
                        msg = preflight_err[rid]["message"]
                        if unknown_cols_now:
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
                    if status_val == "error":
                        row_obj["preflight_error"] = preflight_err[rid]
                        had_err = True

                    packed_rows.append(row_obj)

                except Exception as e:
                    had_err = True
                    err = exception_to_dict(e, include_stack=False)
                    if not err.get("summary"):
                        err["summary"] = str(e)
                    tmp_filtered, _ = _filter_unknown(model, original_input)
                    tmp_payload = _normalize_payload_for_model(model, tmp_filtered, context_company_id=company_id)
                    tmp_payload = _coerce_boolean_fields(model, tmp_payload)
                    tmp_payload = _quantize_decimal_fields(model, tmp_payload)
                    action, pk, ext_id = _infer_action_and_clean_id(dict(tmp_payload), original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": tmp_payload})
                    base = err["summary"]
                    if unknown_cols_now:
                        base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                    logger.error(
                        "[IMPORT][PREP][EXC] model=%s row_id=%s action=%s err=%s",
                        model_name,
                        rid,
                        action,
                        base,
                        exc_info=True,
                        **_log_extra(),
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

            prepared.append({"model": model_name, "rows": packed_rows, "had_error": had_err})
            models_in_order.append(model_name)
            logger.info("sheet_end", **_log_extra(had_error=bool(had_err)))

        # Stable baseline model order
        models_in_order = sorted(models_in_order, key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        # ---------------- BUILD (stage instances, collect token deps) ----------------
        # Outputs by model for the final API response
        row_outputs_by_model: Dict[str, List[Dict[str, Any]]] = {m: [] for m in models_in_order}

        # Keep a simple undirected graph to build groups and a directed depends_on for topo inside the group
        undirected_adj: Dict[str, set] = defaultdict(set)  # token <-> token (for connected components)
        token_depends_on: Dict[str, set] = defaultdict(set)  # dependent_token -> {provider_tokens}

        # Track models touched for sequence reset
        models_touched: set = set()

        insertion_counter = 0

        for model_name in models_in_order:
            _model_ctx.set(model_name)
            app_label = MODEL_APP_MAP[model_name]
            model = apps.get_model(app_label, model_name)
            models_touched.add(model)

            rows = next(b["rows"] for b in prepared if b["model"] == model_name)

            logger.debug(
                "model_begin_build_validate",
                **_log_extra(rows=len(rows), global_map_inst_size=len(global_row_map_inst), global_map_pk_size=len(global_row_map_pk)),
            )

            local_row_map_inst: Dict[str, Any] = {}
            local_row_map_pk: Dict[str, int] = {}

            for row in rows:
                rid = _norm_row_key(row["__row_id"])
                _row_ctx.set(rid)

                # Carry through preflight errors directly to output
                if row.get("status") == "error" and row.get("preflight_error"):
                    row_outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "error",
                        "action": row.get("action"),
                        "data": row.get("_original_input") or row.get("payload") or {},
                        "message": row["preflight_error"]["message"],
                        "error": row["preflight_error"],
                        "observations": row.get("observations", []),
                        "external_id": row.get("external_id"),
                    })
                    continue

                payload = dict(row.get("payload") or {})
                original_input = row.get("_original_input") or {}
                action = row.get("action") or "create"
                unknown_cols_now = _unknown_from_original_input(model, row)

                logger.debug("row_input_data", **_log_extra(data=original_input))
                logger.debug("row_payload_before_resolution", **_log_extra(payload=payload))

                try:
                    deferred_fks: List[Tuple[str, str]] = []  # (field_name, token_string)

                    fk_keys = [k for k in list(payload.keys()) if k.endswith("_fk")]
                    if fk_keys:
                        logger.debug(
                            "fk_keys_detected",
                            **_log_extra(keys=fk_keys),
                        )
                        logger.debug(
                            "fk_context_before_resolution",
                            **_log_extra(
                                local_map_inst=_repr_map_inst(local_row_map_inst),
                                local_map_pk=dict(local_row_map_pk),
                                global_map_inst=_repr_map_inst(global_row_map_inst),
                                global_row_map_pk=dict(global_row_map_pk),
                            ),
                        )

                    # Resolve each *_fk key into either an id, instance, or a deferred token
                    for fk_key in fk_keys:
                        base = fk_key[:-3]
                        raw = payload.pop(fk_key)
                        field = model._meta.get_field(base)
                        attname = getattr(field, "attname", base)

                        if _is_missing(raw):
                            payload[attname] = None
                            continue

                        resolved = _resolve_fk(model, base, raw)

                        # If resolved is a str and not a digit, treat it as a token => DEFER
                        if isinstance(resolved, str) and (not resolved.isdigit()):
                            token_norm = _norm_row_key(resolved)
                            deferred_fks.append((base, token_norm))
                            payload.pop(base, None)
                            payload[attname] = None

                            # Graph: dependent rid depends on provider token_norm
                            undirected_adj[rid].add(token_norm)
                            undirected_adj[token_norm].add(rid)
                            token_depends_on[rid].add(token_norm)
                            logger.debug("fk_deferred", **_log_extra(field=base, token=resolved, reason="token placeholder"))
                        else:
                            # assign either integer id or instance
                            where, assigned = _assign_fk_value(model, base, resolved, payload)
                            logger.debug(
                                "fk_resolved",
                                **_log_extra(
                                    field=base,
                                    assigned_to=where,
                                    value=_stringify_instance(assigned) if isinstance(assigned, Model) else assigned,
                                ),
                            )

                    # Rescue base-field token misuse: transaction="t1"
                    for f in model._meta.get_fields():
                        if isinstance(f, dj_models.ForeignKey):
                            base = f.name
                            val = payload.get(base)
                            if isinstance(val, str) and (not val.isdigit()):
                                tok = _norm_row_key(val)
                                deferred_fks.append((base, tok))
                                payload.pop(base, None)
                                payload[getattr(f, "attname", base)] = None
                                undirected_adj[rid].add(tok)
                                undirected_adj[tok].add(rid)
                                token_depends_on[rid].add(tok)
                                logger.warning("fk_rescue_base_field", **_log_extra(field=base, token=val))

                    # MPTT support
                    if _is_mptt_model(model):
                        path_val = _get_path_value(payload)
                        if path_val:
                            parts = _split_path(path_val)
                            parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                            payload["parent"] = parent
                            payload.pop("parent_id", None)
                            logger.debug("mptt_parent_resolved", **_log_extra(parent=_stringify_instance(parent) if parent else None))

                    # Important: DO NOT raise on missing required FK if it was deferred
                    # We validate with excluded fields below and bind in SAVE pass.
                    logger.debug("row_payload_after_resolution", **_log_extra(payload=payload))

                    # Build (unsaved) instance
                    instance = model(**payload)

                    # Validate with deferred FKs excluded
                    if hasattr(instance, "full_clean"):
                        exclude = []
                        for base, _tok in deferred_fks:
                            exclude.append(base)
                            f = model._meta.get_field(base)
                            att = getattr(f, "attname", base)
                            if att != base:
                                exclude.append(att)
                        instance.full_clean(exclude=exclude or None)

                    # Stage
                    bundle = {
                        "row_id": rid,
                        "instance": instance,
                        "payload_used": payload,
                        "original_input": original_input,
                        "action": action,
                        "deferred_fks": deferred_fks,  # list[(field, token)]
                        "model_name": model_name,
                    }
                    token_to_model[rid] = model_name
                    token_insertion_index[rid] = insertion_counter
                    insertion_counter += 1
                    staged_by_token[rid] = bundle

                    _register_row_token(local_row_map_inst, {}, rid, instance)
                    _register_row_token(global_row_map_inst, {}, rid, instance)

                    logger.debug(
                        "row_token_staged",
                        **_log_extra(
                            token=rid,
                            instance=_stringify_instance(instance),
                            local_map_inst=_repr_map_inst(local_row_map_inst),
                            global_map_inst=_repr_map_inst(global_row_map_inst),
                        ),
                    )

                    row_outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "pending",
                        "action": action,
                        "data": payload,
                        "message": "validated",
                        "observations": row.get("observations", []),
                        "external_id": row.get("external_id"),
                    })

                except Exception as e:
                    err = exception_to_dict(e, include_stack=False)
                    base_msg = err.get("summary") or str(e)
                    if unknown_cols_now:
                        base_msg += " | Ignoring unknown columns: " + ", ".join(unknown_cols_now)
                    logger.error(
                        "[IMPORT][BUILD][EXC] model=%s row_id=%s action=%s err=%s",
                        model_name,
                        rid,
                        action,
                        base_msg,
                        exc_info=True,
                        **_log_extra(),
                    )
                    row_outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "error",
                        "action": action,
                        "data": original_input,
                        "message": base_msg,
                        "error": {**err, "summary": base_msg},
                        "observations": row.get("observations", []),
                        "external_id": row.get("external_id"),
                    })

            logger.debug(
                "model_end_build_validate",
                **_log_extra(
                    local_map_inst_size=len(local_row_map_inst),
                    global_map_inst_size=len(global_row_map_inst),
                ),
            )

        # ---------------- GROUPING (connected components on tokens) ----------------
        # Only consider tokens that are currently "pending"
        pending_tokens = {
            r["__row_id"]
            for m in models_in_order
            for r in row_outputs_by_model[m]
            if r.get("status") == "pending"
        }

        # Ensure we include isolated tokens too
        for tok in pending_tokens:
            undirected_adj.setdefault(tok, set())

        # Build connected components
        groups: List[List[str]] = []
        seen = set()
        for start in sorted(pending_tokens, key=lambda t: (ORDER_HINT.get(token_to_model.get(t, ""), 1000), token_insertion_index.get(t, 10_000_000))):
            if start in seen:
                continue
            comp = []
            q = deque([start])
            seen.add(start)
            while q:
                u = q.popleft()
                comp.append(u)
                for v in undirected_adj.get(u, set()):
                    if (v in pending_tokens) and (v not in seen):
                        seen.add(v)
                        q.append(v)
            groups.append(comp)

        logger.info("group_count", **_log_extra(groups=len(groups)))

        # ---------------- SAVE (per-group savepoints) ----------------
        models_touched_final: set = set()

        for comp in groups:
            # order inside the group by token-level topo (providers before dependents),
            # tie-break by model order then by insertion index
            def _tie_key(tok: str):
                return (ORDER_HINT.get(token_to_model.get(tok, ""), 1000), token_insertion_index.get(tok, 10_000_000), tok)

            ordered_tokens = _toposort_nodes(comp, token_depends_on, _tie_key)

            # Open a group savepoint
            with transaction.atomic():
                sp = transaction.savepoint()
                _model_ctx.set(",".join(sorted({token_to_model.get(t, "?") for t in ordered_tokens})))
                logger.info("group_begin", **_log_extra(size=len(ordered_tokens), tokens=ordered_tokens))

                group_failed = False
                error_summary = None
                saved_tokens_this_group: List[str] = []

                try:
                    for tok in ordered_tokens:
                        bundle = staged_by_token.get(tok)
                        if not bundle:
                            # Should not happen for pending tokens; skip defensively
                            continue

                        model_name = bundle["model_name"]
                        app_label = MODEL_APP_MAP[model_name]
                        model = apps.get_model(app_label, model_name)
                        instance = bundle["instance"]
                        deferred_fks: List[Tuple[str, str]] = bundle["deferred_fks"]

                        _model_ctx.set(model_name)
                        _row_ctx.set(tok)

                        # Bind deferred FKs using pks from tokens saved earlier in THIS or previous groups
                        for base, ref_token in deferred_fks:
                            f = model._meta.get_field(base)
                            attname = getattr(f, "attname", base)
                            ref_t = _norm_row_key(ref_token)
                            pkv = global_row_map_pk.get(ref_t)
                            if not isinstance(pkv, int):
                                # Can't bind token -> missing provider
                                msg = f"Could not resolve deferred FK token {ref_token!r} to a saved id"
                                logger.error("[IMPORT][GROUP][FK_RESOLVE_MISSING] %s", msg, **_log_extra())
                                raise ValidationError({base: [msg]})
                            setattr(instance, attname, pkv)
                            logger.debug("fk_deferred_bound", **_log_extra(field=base, token=ref_token, assigned_id=pkv))

                        if hasattr(instance, "full_clean"):
                            instance.full_clean()

                        instance.save()
                        models_touched_final.add(model)

                        # ensure PK is captured for downstream bindings in the same group
                        _register_row_token(global_row_map_inst, global_row_map_pk, tok, instance)
                        saved_tokens_this_group.append(tok)

                        # finalize output for this row
                        out_list = row_outputs_by_model[model_name]
                        for r in out_list:
                            if r.get("__row_id") == tok and r.get("status") == "pending":
                                r["status"] = "success"
                                r["action"] = ("update" if getattr(instance, "id", None) else "create")
                                data = safe_model_dict(
                                    instance,
                                    exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"],
                                )
                                # Make sure id is present (even in preview)
                                data["id"] = getattr(instance, "pk", data.get("id"))
                                r["data"] = data
                                r["message"] = "ok"
                                logger.debug("row_saved_output", **_log_extra(output=r["data"]))
                                break

                except Exception as e:
                    group_failed = True
                    err = exception_to_dict(e, include_stack=False)
                    error_summary = err.get("summary") or str(e)
                    logger.error("[IMPORT][GROUP][EXC] %s", error_summary, exc_info=True, **_log_extra())
                    transaction.savepoint_rollback(sp)

                    # Mark all *pending* rows in this group as error
                    for tok in comp:
                        bundle = staged_by_token.get(tok)
                        if not bundle:
                            continue
                        model_name = bundle["model_name"]
                        out_list = row_outputs_by_model[model_name]
                        for r in out_list:
                            if r.get("__row_id") == tok and r.get("status") == "pending":
                                r["status"] = "error"
                                r["message"] = error_summary or "Aborted due to previous error"
                    # Remove any pks that were registered for this group (they no longer exist)
                    for tok in saved_tokens_this_group:
                        global_row_map_pk.pop(tok, None)

                else:
                    # No exceptions: if preview, rollback; if commit, keep
                    if commit:
                        transaction.savepoint_commit(sp)
                    else:
                        transaction.savepoint_rollback(sp)
                        # Remove this group's PK entries (they were rolled back)
                        for tok in saved_tokens_this_group:
                            global_row_map_pk.pop(tok, None)

                logger.info("group_end", **_log_extra(size=len(ordered_tokens), failed=group_failed))

        # ---------------- SNAPSHOTS & SEQUENCES ----------------
        if commit:
            # Snapshots reflect original inputs (by model)
            for model_name in models_in_order:
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)
                pre = next(b for b in prepared if b["model"] == model_name)
                rows_src = [r.get("_original_input") or r.get("payload") or {} for r in pre["rows"]]
                fp = _table_fingerprint(model, rows_src)
                closest = (dup_infos.get(model_name) or {}).get("closest_match") or {}
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
        else:
            # In preview, sequences may have advanced; reset to current max(id)
            try:
                reset_pk_sequences([apps.get_model(MODEL_APP_MAP[m], m) for m in models_in_order])
            except Exception:
                logger.warning("sequence_reset_failed", **_log_extra(models=models_in_order))

        # ---------------- RESPONSE ----------------
        result_payload: List[Dict[str, Any]] = []
        for model_name in models_in_order:
            result_payload.append({
                "model": model_name,
                "dup_info": dup_infos.get(model_name),
                "result": row_outputs_by_model.get(model_name, []),
            })

        dt = int((time.monotonic() - t0) * 1000)
        logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=bool(commit)))

        return {
            "committed": bool(commit) and all(
                all(r.get("status") == "success" for r in (row_outputs_by_model.get(m) or []))
                for m in models_in_order
            ),
            "reason": (None if commit else "preview"),
            "file_info": file_info,
            "imports": result_payload,
        }
