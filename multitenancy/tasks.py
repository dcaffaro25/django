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
    DataError,
    DatabaseError,
    IntegrityError,
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
                        sql_logger.info("slow_sql", **_log_extra(duration_ms=int(dt * 1000), many=bool(many), sql=str(sql)[:1000]))
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
    pk = getattr(instance, "pk", None)
    global_row_map_inst[rid] = instance
    if isinstance(pk, int):
        global_row_map_pk[rid] = pk


def _resolve_token_from_maps(token: str,
                             local_inst: Dict[str, Any],
                             local_pk: Dict[str, int],
                             global_inst: Dict[str, Any],
                             global_pk: Dict[str, int]) -> Any:
    if token in local_inst:
        return local_inst[token]
    if token in global_inst:
        return global_inst[token]
    if token in local_pk:
        return local_pk[token]
    if token in global_pk:
        return global_pk[token]
    return None


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


def _resolve_fk(model_cls, field_name: str, raw_value: Any, row_id_map: Dict[str, Any]) -> Any:
    if raw_value in (None, ""):
        return None

    field = model_cls._meta.get_field(field_name)
    remote_model = getattr(field, "remote_field", None).model if getattr(field, "remote_field", None) else None

    if isinstance(raw_value, Model):
        if remote_model and not isinstance(raw_value, remote_model):
            raise ValueError(f"{model_cls.__name__}.{field_name} expects {remote_model.__name__} instance, got {raw_value.__class__.__name__}")
        return raw_value

    if isinstance(raw_value, int) or (isinstance(raw_value, str) and str(raw_value).strip().isdigit()):
        return int(raw_value)

    token = _norm_row_key(str(raw_value).strip())
    candidate = row_id_map.get(token)

    if candidate is None and ":" in token:
        _, maybe_token = token.split(":", 1)
        candidate = row_id_map.get(_norm_row_key(maybe_token))

    if candidate is not None:
        if isinstance(candidate, Model):
            if remote_model and not isinstance(candidate, remote_model):
                pk = getattr(candidate, "pk", None)
                if isinstance(pk, int):
                    return pk
                raise ValueError(f"Token {token!r} resolved to {candidate.__class__.__name__}, incompatible with {remote_model.__name__}")
            return candidate
        if isinstance(candidate, int):
            return candidate

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
        if (not f.null) and (not f.primary_key) and (not f.auto_created) and (not has_default) and (not is_auto_ts):
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


def _sanity_check_required_fks(model, payload: Dict[str, Any], original_input: Dict[str, Any], merged_map_keys: List[str]) -> List[Tuple[str, Any]]:
    issues: List[Tuple[str, Any]] = []
    for f in model._meta.get_fields():
        if not isinstance(f, dj_models.ForeignKey) or getattr(f, "null", False):
            continue
        base = f.name
        token = original_input.get(f"{base}_fk", None)
        missing_token = token is None or token == "" or (isinstance(token, float) and token != token)
        if missing_token:
            continue
        value = payload.get(base, payload.get(getattr(f, "attname", base)))
        if value is None:
            issues.append((base, token))
    return issues


# --------------------------------------------------------------------------------------
# Core import executor — ONE savepoint for the entire file with FK deferral
# --------------------------------------------------------------------------------------
DUP_CHECK_LAST_N = 10


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

    logger.info("import_start", **_log_extra(commit=bool(commit), import_filename=filename, file_sha=file_sha, file_size=file_size, sheet_count=len(sheets)))

    t0 = time.monotonic()
    with _SlowSQL(threshold_ms=200):
        # ---------------- PREP ----------------
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

                    logger.error("[IMPORT][PREP][EXC] model=%s row_id=%s action=%s err=%s", model_name, rid, action, base, exc_info=True, **_log_extra())
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

        models_in_order.sort(key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        if commit and any_prep_error:
            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="prep_errors"))
            return {
                "committed": False,
                "reason": "prep_errors",
                "file_info": file_info,
                "imports": [{"model": b["model"], "dup_info": dup_infos.get(b["model"]), "result": b["rows"]} for b in prepared],
            }

        # ---------------- ONE FILE-LEVEL TXN + SAVEPOINT ----------------
        models_touched: List[Any] = []
        result_payload: List[Dict[str, Any]] = []

        global_row_map_inst: Dict[str, Any] = {}
        global_row_map_pk: Dict[str, int] = {}

        # staged rows: per model, list of dict(row_id, instance, payload_used, original_input, deferred_fks)
        built_by_model: Dict[str, List[Dict[str, Any]]] = {}
        row_outputs_by_model: Dict[str, List[Dict[str, Any]]] = {m: [] for m in models_in_order}

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            sp = transaction.savepoint()
            try:
                # ------------ PASS 1: BUILD (FK resolution + deferred FK handling) ------------
                for model_name in models_in_order:
                    _model_ctx.set(model_name)
                    app_label = MODEL_APP_MAP[model_name]
                    model = apps.get_model(app_label, model_name)
                    models_touched.append(model)

                    rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                    built_by_model[model_name] = []

                    local_row_map_inst: Dict[str, Any] = {}
                    local_row_map_pk: Dict[str, int] = {}

                    logger.debug(
                        "model_begin_build_validate",
                        **_log_extra(
                            rows=len(rows),
                            global_map_inst_size=len(global_row_map_inst),
                            global_map_pk_size=len(global_row_map_pk),
                        ),
                    )

                    for row in rows:
                        rid = _norm_row_key(row["__row_id"])
                        _row_ctx.set(rid)

                        # carry through preflight errors
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

                            for fk_key in fk_keys:
                                base = fk_key[:-3]
                                raw = payload.pop(fk_key)
                                if _is_missing(raw):
                                    # explicit NULL
                                    payload[getattr(model._meta.get_field(base), "attname", base)] = None
                                    continue

                                token_norm = _norm_row_key(raw) if isinstance(raw, str) else raw
                                logger.debug("fk_resolve_attempt", **_log_extra(field=base, token=raw, token_norm=token_norm))
                                candidate = None
                                if isinstance(raw, str):
                                    candidate = _resolve_token_from_maps(
                                        token_norm, local_row_map_inst, local_row_map_pk, global_row_map_inst, global_row_map_pk
                                    )

                                if candidate is not None:
                                    resolved = _resolve_fk(model, base, candidate, {})
                                else:
                                    # allow direct id as string/number
                                    resolved = _resolve_fk(model, base, raw, {})

                                field = model._meta.get_field(base)
                                attname = getattr(field, "attname", base)

                                # If resolved is an instance without PK yet => DEFER
                                if isinstance(resolved, Model) and getattr(resolved, "pk", None) is None:
                                    deferred_fks.append((base, token_norm if isinstance(token_norm, str) else str(token_norm)))
                                    payload.pop(base, None)
                                    payload[attname] = None  # keep attname None until save pass
                                    logger.debug(
                                        "fk_deferred",
                                        **_log_extra(field=base, token=raw, reason="related instance has no PK yet"),
                                    )
                                else:
                                    where, assigned = _assign_fk_value(model, base, resolved, payload)
                                    logger.debug(
                                        "fk_resolved",
                                        **_log_extra(
                                            field=base,
                                            assigned_to=where,
                                            value=_stringify_instance(assigned) if isinstance(assigned, Model) else assigned,
                                        ),
                                    )

                            # rescue misplaced tokens typed into base field
                            for f in model._meta.get_fields():
                                if isinstance(f, dj_models.ForeignKey) and not getattr(f, "null", False):
                                    base = f.name
                                    val = payload.get(base)
                                    if isinstance(val, str):
                                        token = _norm_row_key(val)
                                        candidate = _resolve_token_from_maps(
                                            token, local_row_map_inst, local_row_map_pk, global_row_map_inst, global_row_map_pk
                                        )
                                        if candidate is not None:
                                            logger.warning("fk_rescue_base_field", **_log_extra(field=base, token=val))
                                            resolved = _resolve_fk(model, base, candidate, {})
                                            if isinstance(resolved, Model) and getattr(resolved, "pk", None) is None:
                                                deferred_fks.append((base, token))
                                                payload.pop(base, None)
                                                payload[getattr(f, "attname", base)] = None
                                                logger.debug("fk_deferred", **_log_extra(field=base, token=val, reason="rescued unsaved related"))
                                            else:
                                                where, assigned = _assign_fk_value(model, base, resolved, payload)
                                                logger.debug(
                                                    "fk_rescued",
                                                    **_log_extra(
                                                        field=base,
                                                        assigned_to=where,
                                                        value=_stringify_instance(assigned) if isinstance(assigned, Model) else assigned,
                                                    ),
                                                )

                            # MPTT support
                            if _is_mptt_model(model):
                                path_val = _get_path_value(payload)
                                if path_val:
                                    parts = _split_path(path_val)
                                    parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                    payload["parent"] = parent
                                    payload.pop("parent_id", None)
                                    logger.debug("mptt_parent_resolved", **_log_extra(parent=_stringify_instance(parent) if parent else None))

                            # sanity check: if user provided *_fk but we deferred, skip complaining now
                            issues = [
                                (base, tok)
                                for (base, tok) in _sanity_check_required_fks(
                                    model, payload, original_input, list({**global_row_map_inst, **local_row_map_inst}.keys())
                                )
                                if all(base != d_base for (d_base, _) in deferred_fks)
                            ]
                            if issues:
                                for base, token in issues:
                                    logger.error("fk_unresolved_required", **_log_extra(field=base, token=token))
                                raise ValidationError({base: [f"Unresolved FK token {token!r}"] for base, token in issues})

                            logger.debug("row_payload_after_resolution", **_log_extra(payload=payload))

                            # build instance (unsaved)
                            instance = model(**payload)

                            # validate; if we deferred any FK, exclude its attnames from validation for now
                            if hasattr(instance, "full_clean"):
                                exclude = []
                                if deferred_fks:
                                    for base, _ in deferred_fks:
                                        f = model._meta.get_field(base)
                                        exclude.append(getattr(f, "attname", base))
                                instance.full_clean(exclude=exclude or None)

                            # stage
                            built_by_model[model_name].append({
                                "row_id": rid,
                                "instance": instance,
                                "payload_used": payload,
                                "original_input": original_input,
                                "action": action,
                                "deferred_fks": deferred_fks,  # list[(field, token)]
                            })

                            # register token (instance only; pk will be added after save)
                            _register_row_token(local_row_map_inst, local_row_map_pk, rid, instance)
                            _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)
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

                # abort before save if any row errored
                if any(any(r.get("status") == "error" for r in row_outputs_by_model[m]) for m in models_in_order):
                    raise RuntimeError("validation_errors_before_save")

                # ------------ PASS 2: SAVE (fill deferred FKs first) ------------
                for model_name in models_in_order:
                    _model_ctx.set(model_name)
                    app_label = MODEL_APP_MAP[model_name]
                    model = apps.get_model(app_label, model_name)

                    staged = built_by_model.get(model_name, [])
                    logger.debug("model_begin_save_pass", **_log_extra(staged_rows=len(staged)))

                    for row_bundle in staged:
                        rid = row_bundle["row_id"]
                        instance = row_bundle["instance"]
                        deferred_fks: List[Tuple[str, str]] = row_bundle["deferred_fks"]
                        _row_ctx.set(rid or "-")

                        # resolve deferred FKs now that dependent models likely have PKs
                        for base, token in deferred_fks:
                            f = model._meta.get_field(base)
                            attname = getattr(f, "attname", base)
                            cand = _resolve_token_from_maps(token, {}, {}, global_row_map_inst, global_row_map_pk)
                            if isinstance(cand, Model):
                                pkv = getattr(cand, "pk", None)
                            else:
                                pkv = cand
                            if not isinstance(pkv, int):
                                raise ValidationError({base: [f"Could not resolve deferred FK token {token!r} to a saved id"]})
                            setattr(instance, attname, pkv)
                            logger.debug("fk_deferred_bound", **_log_extra(field=base, token=token, assigned_id=pkv))

                        action = "update" if getattr(instance, "id", None) else "create"
                        logger.debug("row_save_attempt_file_scope", **_log_extra(action=action))

                        if hasattr(instance, "full_clean"):
                            instance.full_clean()  # full validation now that FKs are bound
                        instance.save()

                        # update global maps with actual PK after save
                        if rid:
                            _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)

                        # finalize output
                        for r in row_outputs_by_model[model_name]:
                            if r.get("__row_id") == rid and r.get("status") == "pending":
                                r["status"] = "success"
                                r["action"] = action
                                r["data"] = safe_model_dict(
                                    instance,
                                    exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"],
                                )
                                r["message"] = "ok"
                                logger.debug("row_saved_output", **_log_extra(output=r["data"]))
                                break

                    logger.debug("model_end_save_pass", **_log_extra())

                # snapshots only if commit True
                if commit:
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

                if commit:
                    transaction.savepoint_commit(sp)
                else:
                    transaction.savepoint_rollback(sp)
                    reset_pk_sequences([apps.get_model(MODEL_APP_MAP[m], m) for m in models_in_order])

            except Exception as e:
                transaction.savepoint_rollback(sp)
                if not commit:
                    reset_pk_sequences([apps.get_model(MODEL_APP_MAP[m], m) for m in models_in_order])

                if str(e) != "validation_errors_before_save":
                    err = exception_to_dict(e, include_stack=False)
                    logger.error("[IMPORT][FILE][EXC] %s", err.get("summary") or str(e), exc_info=True, **_log_extra())

                for m in models_in_order:
                    for r in row_outputs_by_model[m]:
                        if r.get("status") == "pending":
                            r["status"] = "error"
                            r["message"] = "Aborted due to previous error"

        # ---------------- RESPONSE ----------------
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
