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
from typing import Any, Dict, List, Optional, Tuple, Set

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

# Silence gunicorn.access propagation so our structured "extra" doesn't collide
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
    key = _norm_row_key(rid)
    global_row_map_inst[key] = instance
    pk = getattr(instance, "pk", None)
    if pk is not None:
        # All PKs are integers per your note, but we keep this tolerant.
        try:
            global_row_map_pk[key] = int(pk)
        except Exception:
            pass


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
    if isinstance(resolved_value, Model):
        payload[field_name] = resolved_value
        payload.pop(attname, None)
        return field_name, resolved_value
    else:
        payload.pop(field_name, None)
        payload[attname] = int(resolved_value) if resolved_value is not None else None
        return attname, resolved_value


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


def _sanity_check_required_fks(model, payload: Dict[str, Any], original_input: Dict[str, Any]) -> List[Tuple[str, Any]]:
    issues: List[Tuple[str, Any]] = []
    for f in model._meta.get_fields():
        if not isinstance(f, dj_models.ForeignKey) or getattr(f, "null", False):
            continue
        base = f.name
        token = original_input.get(f"{base}_fk", None)
        if token in (None, "", "null"):
            continue
        value = payload.get(base, payload.get(getattr(f, "attname", base)))
        if value is None:
            issues.append((base, token))
    return issues


def _coerce_pk_from_rowid(rid: str) -> Optional[int]:
    s = str(rid).strip()
    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------------------
# Row-level grouping and toposort
# --------------------------------------------------------------------------------------
def _build_row_groups(
    pending_tokens: Set[str],
    row_requires: Dict[str, Set[str]],
) -> List[List[str]]:
    """
    Build connected components (groups) from token dependencies.
    `row_requires` maps row_token -> {provider_token, ...} seen in *_fk.
    We treat edges as undirected for grouping, then later topo-sort directed inside each group.
    """
    neighbors: Dict[str, Set[str]] = defaultdict(set)
    for consumer, providers in row_requires.items():
        for prov in providers:
            if prov in pending_tokens and consumer in pending_tokens:
                neighbors[consumer].add(prov)
                neighbors[prov].add(consumer)

    # ensure isolated nodes present
    for t in pending_tokens:
        neighbors.setdefault(t, set())

    seen: Set[str] = set()
    groups: List[List[str]] = []
    for node in sorted(neighbors.keys()):
        if node in seen:
            continue
        comp = []
        dq = deque([node])
        seen.add(node)
        while dq:
            u = dq.popleft()
            comp.append(u)
            for v in sorted(neighbors[u]):
                if v not in seen:
                    seen.add(v)
                    dq.append(v)
        groups.append(sorted(comp))
    return groups


def _toposort_rows_in_group(
    group_nodes: List[str],
    edges_provider_to_consumer: Dict[str, Set[str]],
    rid_to_model: Dict[str, str],
    order_hint: Dict[str, int],
) -> List[str]:
    """
    Topologically sort row tokens in `group_nodes` using directed edges provider->consumer.
    Tie-break by model hint, then token.
    """
    node_set = set(group_nodes)
    indeg: Dict[str, int] = {n: 0 for n in node_set}
    adj: Dict[str, Set[str]] = {n: set() for n in node_set}

    for p, consumers in edges_provider_to_consumer.items():
        if p not in node_set:
            continue
        for c in consumers:
            if c in node_set:
                adj[p].add(c)
                indeg[c] += 1

    q = deque(sorted([n for n in node_set if indeg[n] == 0], key=lambda t: (order_hint.get(rid_to_model.get(t, ""), 10_000), t)))
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in sorted(adj[u], key=lambda t: (order_hint.get(rid_to_model.get(t, ""), 10_000), t)):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    # if cycle, fall back to deterministic order
    if len(out) != len(node_set):
        logger.warning("row_toposort_cycle_group_fallback", **_log_extra(group=sorted(list(group_nodes))))
        out = sorted(group_nodes, key=lambda t: (order_hint.get(rid_to_model.get(t, ""), 10_000), t))
    return out


# --------------------------------------------------------------------------------------
# Core import executor
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

    # run-scoped maps used for the entire file (only for resolution within a run)
    global_row_map_inst: Dict[str, Any] = {}
    global_row_map_pk: Dict[str, int] = {}

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

                    # Support numeric __row_id = update id
                    rid_pk = _coerce_pk_from_rowid(rid)
                    if rid_pk is not None:
                        payload["id"] = rid_pk

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

        # Deterministic baseline order
        models_in_order = sorted(models_in_order, key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_order))

        # Note: even if there were prep errors, we proceed to BUILD/SAVE with per-group savepoints
        # so we can surface all other group errors independently.

        # ---------------- BUILD (stage instances; record row-level deps) ----------------
        # Per-model staged rows: each item holds instance + metadata
        built_by_model: Dict[str, List[Dict[str, Any]]] = {m: [] for m in models_in_order}
        # Output rows bucketed by model (we will fill during the run)
        row_outputs_by_model: Dict[str, List[Dict[str, Any]]] = {m: [] for m in models_in_order}

        # Row-level dependency capture
        rid_to_model: Dict[str, str] = {}
        rid_to_bundle: Dict[str, Dict[str, Any]] = {}
        row_requires_tokens: Dict[str, Set[str]] = defaultdict(set)
        edges_provider_to_consumer: Dict[str, Set[str]] = defaultdict(set)

        with transaction.atomic():
            # Speed up constraint feedback
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            # Stage all instances first
            for model_name in models_in_order:
                _model_ctx.set(model_name)
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)

                rows = next(b["rows"] for b in prepared if b["model"] == model_name)

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
                    rid_to_model[rid] = model_name  # map now regardless of status for grouping

                    # If preflight error, just mirror it to outputs; do not stage
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
                        requires_tokens_this_row: Set[str] = set()

                        # Process declared *_fk foreign keys
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
                            # If looks like a token (non-numeric string), remember for grouping
                            if isinstance(token_norm, str) and not str(token_norm).isdigit():
                                requires_tokens_this_row.add(token_norm)

                            logger.debug("fk_resolve_attempt", **_log_extra(field=base, token=raw, token_norm=token_norm))
                            candidate = None
                            if isinstance(raw, str):
                                candidate = _resolve_token_from_maps(
                                    token_norm, local_row_map_inst, local_row_map_pk, global_row_map_inst, global_row_map_pk
                                )

                            # Resolve: instance or id
                            if candidate is not None:
                                resolved = candidate
                            else:
                                resolved = token_norm

                            field = model._meta.get_field(base)
                            attname = getattr(field, "attname", base)

                            # If we resolved to a staged instance but it has no PK yet -> defer binding of id, but keep the dependency
                            if isinstance(resolved, Model) and getattr(resolved, "pk", None) is None:
                                deferred_fks.append((base, str(token_norm)))
                                payload.pop(base, None)
                                payload[attname] = None
                                logger.debug("fk_deferred", **_log_extra(field=base, token=raw, reason="related instance has no PK yet"))

                            # If resolved is a Model with PK or a numeric id
                            elif isinstance(resolved, Model):
                                _assign_fk_value(model, base, resolved, payload)
                                logger.debug("fk_resolved_instance", **_log_extra(field=base, value=_stringify_instance(resolved)))
                            else:
                                # string or number; if number → bind id, if token string and not staged yet → truly defer
                                if isinstance(resolved, str) and not resolved.isdigit():
                                    # unresolved token now; will bind later during SAVE
                                    deferred_fks.append((base, resolved))
                                    payload[attname] = None
                                    logger.debug("fk_deferred_token", **_log_extra(field=base, token=resolved))
                                else:
                                    # numeric id
                                    _assign_fk_value(model, base, int(resolved), payload)
                                    logger.debug("fk_resolved_id", **_log_extra(field=base, id=int(resolved)))

                        # Rescue tokens accidentally placed into base field (not *_fk)
                        for f in model._meta.get_fields():
                            if isinstance(f, dj_models.ForeignKey):
                                base = f.name
                                val = payload.get(base)
                                if isinstance(val, str) and not val.isdigit():
                                    tok = _norm_row_key(val)
                                    requires_tokens_this_row.add(tok)
                                    candidate = _resolve_token_from_maps(tok, local_row_map_inst, local_row_map_pk, global_row_map_inst, global_row_map_pk)
                                    if candidate is not None:
                                        if isinstance(candidate, Model) and getattr(candidate, "pk", None) is None:
                                            deferred_fks.append((base, tok))
                                            payload.pop(base, None)
                                            payload[getattr(f, "attname", base)] = None
                                            logger.debug("fk_deferred_rescue", **_log_extra(field=base, token=tok))
                                        else:
                                            _assign_fk_value(model, base, candidate, payload)
                                            logger.debug("fk_rescued_bound", **_log_extra(field=base, value=_stringify_instance(candidate)))
                                    else:
                                        # truly a forward token; defer
                                        deferred_fks.append((base, tok))
                                        payload[getattr(f, "attname", base)] = None
                                        logger.debug("fk_deferred_rescue_forward", **_log_extra(field=base, token=tok))

                        # MPTT support
                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload["parent"] = parent
                                payload.pop("parent_id", None)
                                logger.debug("mptt_parent_resolved", **_log_extra(parent=_stringify_instance(parent) if parent else None))

                        issues = _sanity_check_required_fks(model, payload, original_input)
                        if issues:
                            for base, token in issues:
                                logger.error("fk_unresolved_required", **_log_extra(field=base, token=token))
                            raise ValidationError({base: [f"Unresolved FK token {token!r}"] for base, token in issues})

                        logger.debug("row_payload_after_resolution", **_log_extra(payload=payload))

                        # Build instance (unsaved)
                        instance = model(**payload)

                        # Validate; if we deferred any FK, exclude its field + attname for now
                        if hasattr(instance, "full_clean"):
                            exclude = []
                            if deferred_fks:
                                for base, _ in deferred_fks:
                                    exclude.append(base)
                                    f = model._meta.get_field(base)
                                    att = getattr(f, "attname", base)
                                    if att != base:
                                        exclude.append(att)
                            instance.full_clean(exclude=exclude or None)

                        bundle = {
                            "row_id": rid,
                            "instance": instance,
                            "payload_used": payload,
                            "original_input": original_input,
                            "action": action,
                            "deferred_fks": deferred_fks,            # list[(field, token)]
                            "requires_tokens": requires_tokens_this_row,  # set[str]
                        }
                        built_by_model[model_name].append(bundle)
                        rid_to_bundle[rid] = bundle

                        # Register token → instance (pk will be added after save)
                        _register_row_token(local_row_map_inst, local_row_map_pk, rid, instance)
                        _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)

                        # Row outputs start as pending
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
                        logger.error("[IMPORT][BUILD][EXC] model=%s row_id=%s action=%s err=%s", model_name, rid, action, base_msg, exc_info=True, **_log_extra())
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

            # Build row-level dependency edges from requires_tokens
            # Only include rows that are pending
            pending_tokens: Set[str] = set()
            for m in models_in_order:
                for out in row_outputs_by_model[m]:
                    if out.get("status") == "pending":
                        pending_tokens.add(out["__row_id"])
            # fill row_requires and edges
            for rid, bundle in rid_to_bundle.items():
                if rid not in pending_tokens:
                    continue
                reqs = set(bundle.get("requires_tokens") or [])
                row_requires_tokens[rid] |= reqs
                for prov in reqs:
                    # If provider is in this file (pending), create directed edge prov -> rid (parent -> child)
                    if prov in rid_to_bundle and prov in pending_tokens:
                        edges_provider_to_consumer[prov].add(rid)

            # Form groups (connected components by undirected view)
            groups = _build_row_groups(pending_tokens, row_requires_tokens)

            # ---------------- SAVE pass (per-group savepoints) ----------------
            models_touched = [apps.get_model(MODEL_APP_MAP[m], m) for m in models_in_order]

            for group_nodes in groups:
                # Determine row toposort order inside the group
                order_in_group = _toposort_rows_in_group(group_nodes, edges_provider_to_consumer, rid_to_model, ORDER_HINT)
                logger.info("group_begin", **_log_extra(group_nodes=group_nodes, topo_order=order_in_group))

                spg = transaction.savepoint()
                group_failed = False
                group_error_msg: Optional[str] = None

                try:
                    for rid in order_in_group:
                        bundle = rid_to_bundle.get(rid)
                        if not bundle:
                            # Shouldn't happen; skip safely
                            continue
                        instance = bundle["instance"]
                        deferred_fks: List[Tuple[str, str]] = bundle["deferred_fks"]
                        model_name = rid_to_model.get(rid, "-")
                        _model_ctx.set(model_name)
                        _row_ctx.set(rid)

                        # Resolve deferred FKs now; parents earlier in the order should be saved
                        for base, token in deferred_fks:
                            f = instance._meta.get_field(base)
                            attname = getattr(f, "attname", base)
                            tok = _norm_row_key(token)
                            cand = _resolve_token_from_maps(tok, {}, {}, global_row_map_inst, global_row_map_pk)
                            pkv = cand.pk if isinstance(cand, Model) else cand
                            if pkv is None or (not isinstance(pkv, int)):
                                # FK target not available → group fails
                                logger.error("[IMPORT][GROUP][FK_RESOLVE_MISSING] token=%r field=%r rid=%s", token, base, rid, **_log_extra())
                                raise ValidationError({base: [f"Could not resolve deferred FK token {token!r} to a saved id"]})
                            setattr(instance, attname, int(pkv))
                            logger.debug("fk_deferred_bound", **_log_extra(field=base, token=token, assigned_id=pkv))

                        # Final clean & save
                        if hasattr(instance, "full_clean"):
                            instance.full_clean()
                        action = "update" if getattr(instance, "id", None) else "create"
                        instance.save()

                        # register token → pk
                        _register_row_token(global_row_map_inst, global_row_map_pk, rid, instance)

                        # Update output
                        outs = row_outputs_by_model.get(model_name, [])
                        for r in outs:
                            if r.get("__row_id") == rid and r.get("status") == "pending":
                                r["status"] = "success"
                                r["action"] = action
                                data = safe_model_dict(instance, exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"])
                                # ensure id present
                                data["id"] = getattr(instance, "pk", data.get("id"))
                                r["data"] = data
                                r["message"] = "ok"
                                logger.debug("row_saved_output", **_log_extra(output=r["data"]))
                                break

                    # Group done: preview → rollback, commit → keep
                    if not commit:
                        transaction.savepoint_rollback(spg)
                    else:
                        transaction.savepoint_commit(spg)

                except Exception as e:
                    group_failed = True
                    group_error = exception_to_dict(e, include_stack=False)
                    group_error_msg = group_error.get("summary") or str(e)
                    logger.error("[IMPORT][GROUP][EXC] %s", group_error_msg, exc_info=True, **_log_extra(group=group_nodes))
                    transaction.savepoint_rollback(spg)

                    # Mark all rows in this group that were still pending as error
                    for rid in order_in_group:
                        model_name = rid_to_model.get(rid, "-")
                        outs = row_outputs_by_model.get(model_name, [])
                        for r in outs:
                            if r.get("__row_id") == rid and r.get("status") == "pending":
                                r["status"] = "error"
                                r["message"] = group_error_msg or "Aborted due to previous error in group"
                                r["error"] = group_error
                                break

            # After all groups, reset sequences if preview
            if not commit:
                try:
                    reset_pk_sequences(models_touched)
                except Exception:
                    logger.warning("reset_pk_sequences_failed", **_log_extra())

            # Snapshots (only on commit)
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

        committed_flag = bool(commit) and all(
            all(r.get("status") == "success" for r in (row_outputs_by_model.get(m) or []))
            for m in models_in_order
        )

        return {
            "committed": committed_flag,
            "reason": (None if commit else "preview"),
            "file_info": file_info,
            "imports": result_payload,
        }
