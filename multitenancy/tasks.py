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

# Avoid mixing our structured extras into gunicorn.access records
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
                        sql_logger.info(
                            "slow_sql",
                            **_log_extra(duration_ms=int(dt * 1000), many=bool(many), sql=str(sql)[:1000]),
                        )

            self._cm = connection.execute_wrapper(wrapper)
            self._cm.__enter__()  # type: ignore
        except Exception:
            self._cm = None
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc, tb)  # type: ignore
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


# --------------------------------------------------------------------------------------
# Planning: tokens & dependency graph
# --------------------------------------------------------------------------------------
def _is_numeric_id(token: str | int | None) -> bool:
    if token is None:
        return False
    if isinstance(token, int):
        return True
    s = str(token).strip()
    return s.isdigit()


@dataclass
class PlannedRow:
    model_name: str
    rid: str            # normalized __row_id (token or numeric str)
    is_token: bool      # True if rid is not purely numeric
    action: str         # "create" or "update"
    payload: Dict[str, Any]
    original_input: Dict[str, Any]
    observations: List[str]
    unknown_cols_now: List[str]
    preflight_error: Optional[Dict[str, Any]]
    parents: Set[str]   # tokens this row depends on (subset of all tokens in file)


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


def _build_dependency_graph(prepared_by_model: Dict[str, List[PlannedRow]]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, PlannedRow]]:
    """
    Returns:
      parents_of[child] = set(parent_tokens)
      children_of[parent] = set(child_rids)
      rows_by_rid
    """
    rows_by_rid: Dict[str, PlannedRow] = {}
    all_rids: Set[str] = set()
    token_set: Set[str] = set()

    for m, rows in prepared_by_model.items():
        for r in rows:
            rows_by_rid[r.rid] = r
            all_rids.add(r.rid)
            if r.is_token:
                token_set.add(r.rid)

    parents_of: Dict[str, Set[str]] = defaultdict(set)
    children_of: Dict[str, Set[str]] = defaultdict(set)

    # Build edges ONLY when *_fk references a token that exists in this file
    for m, rows in prepared_by_model.items():
        app_label = MODEL_APP_MAP[m]
        model = apps.get_model(app_label, m)
        fk_fields = [f for f in model._meta.get_fields() if isinstance(f, dj_models.ForeignKey)]
        fk_names = [f.name for f in fk_fields]

        for r in rows:
            parents = set()
            oi = r.original_input

            # Explicit *_fk columns
            for base in fk_names:
                v = oi.get(f"{base}_fk")
                if v in (None, ""):
                    continue
                # numeric id? => no token edge
                if _is_numeric_id(v):
                    continue
                # token value
                tok = _norm_row_key(str(v))
                if tok in token_set:
                    parents.add(tok)

            # Rescue: token typed into base field string
            for base in fk_names:
                base_val = r.payload.get(base)
                if isinstance(base_val, str) and not _is_numeric_id(base_val):
                    tok = _norm_row_key(base_val)
                    if tok in token_set:
                        parents.add(tok)

            r.parents = parents
            for p in parents:
                parents_of[r.rid].add(p)
                children_of[p].add(r.rid)

    # Ensure all rids appear in maps
    for rid in all_rids:
        parents_of.setdefault(rid, set())
        children_of.setdefault(rid, set())

    return parents_of, children_of, rows_by_rid


def _connected_components(nodes: Set[str], undirected_adj: Dict[str, Set[str]]) -> List[Set[str]]:
    """Return list of sets (each a connected component)."""
    seen: Set[str] = set()
    components: List[Set[str]] = []
    for n in nodes:
        if n in seen:
            continue
        comp = set()
        stack = [n]
        seen.add(n)
        while stack:
            u = stack.pop()
            comp.add(u)
            for v in undirected_adj.get(u, set()):
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        components.append(comp)
    return components


def _toposort_group(group_nodes: Set[str], parents_of: Dict[str, Set[str]], rows_by_rid: Dict[str, PlannedRow], order_hint: Dict[str, int]) -> Tuple[List[str], bool]:
    """
    Kahn's algorithm over this group's nodes.
    Returns (order, acyclic)
    Tie-break using model order hint, then by original appearance (rid).
    """
    indeg = {n: 0 for n in group_nodes}
    for child in group_nodes:
        indeg[child] = len([p for p in parents_of.get(child, set()) if p in group_nodes])

    def key_fn(rid: str):
        m = rows_by_rid[rid].model_name
        return (order_hint.get(m, 10_000), rid)

    q = deque(sorted([n for n in group_nodes if indeg[n] == 0], key=key_fn))
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in group_nodes:
            if u in parents_of.get(v, set()):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    acyclic = (len(out) == len(group_nodes))
    return out, acyclic


# --------------------------- NEW: FK application helper ---------------------------

def _apply_fk_inputs_into_attnames(
    model, payload: Dict[str, Any], original_input: Dict[str, Any], saved_by_token: Dict[str, Model]
) -> None:
    """
    For each ForeignKey on `model`, interpret original_input['<base>_fk'] if present:
      - numeric -> put into payload['<base>_id']
      - token   -> look up saved_by_token[token].pk and put into payload['<base>_id']
    Also 'rescue' if the base field itself contains a token string.
    Finally, REMOVE any '<base>_fk' leftovers from payload (and any stray *_fk).
    """
    fk_fields = [f for f in model._meta.get_fields() if isinstance(f, dj_models.ForeignKey)]

    for f in fk_fields:
        base = f.name
        att = getattr(f, "attname", base)

        # Prefer explicit *_fk from the original input (what user actually passed)
        raw = original_input.get(f"{base}_fk", None)

        if raw not in (None, ""):
            if _is_numeric_id(raw):
                # Existing PK in DB
                payload.pop(base, None)
                payload[att] = int(raw)
            else:
                tok = _norm_row_key(str(raw))
                if tok in saved_by_token:
                    payload.pop(base, None)
                    payload[att] = getattr(saved_by_token[tok], "pk", None)
                else:
                    # Planning should have ordered parents before; if not present, we'll fail validation later.
                    pass
        else:
            # 'Rescue' a token typed into the base field
            v = payload.get(base, payload.get(att))
            if isinstance(v, str) and not _is_numeric_id(v):
                tok = _norm_row_key(v)
                if tok in saved_by_token:
                    payload.pop(base, None)
                    payload[att] = getattr(saved_by_token[tok], "pk", None)

        # Always remove *_fk key from payload in case normalization kept it
        payload.pop(f"{base}_fk", None)

    # Defensive: purge any remaining *_fk that don't correspond to real FK fields
    for k in list(payload.keys()):
        if k.endswith("_fk"):
            payload.pop(k, None)


# --------------------------------------------------------------------------------------
# Core: plan → group → order → materialize (savepoint per group)
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
        dup_infos: Dict[str, Dict[str, Any]] = {}
        prepared_by_model: Dict[str, List[PlannedRow]] = {}
        models_in_file: List[str] = []
        any_prep_error = False

        for sheet in sheets:
            model_name = sheet["model"]
            _model_ctx.set(model_name)

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                logger.error("sheet_app_missing", **_log_extra(error=f"MODEL_APP_MAP missing entry for '{model_name}'"))
                prepared_by_model.setdefault(model_name, [])
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
            prepared_rows: List[PlannedRow] = []
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

                    action, _, _ = _infer_action_and_clean_id(payload, original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": payload})

                    status_val = "ok"
                    msg = "validated"
                    if unknown_cols_now:
                        status_val = "warning"
                        msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                    pe = None
                    if rid in preflight_err:
                        status_val = "error"
                        msg = preflight_err[rid]["message"]
                        pe = preflight_err[rid]
                        if unknown_cols_now:
                            msg = f"{msg} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"

                    pr = PlannedRow(
                        model_name=model_name,
                        rid=rid,
                        is_token=not _is_numeric_id(rid),
                        action=action,
                        payload=payload,
                        original_input=original_input,
                        observations=observations,
                        unknown_cols_now=unknown_cols_now,
                        preflight_error=pe,
                        parents=set(),
                    )
                    prepared_rows.append(pr)

                except Exception as e:
                    had_err = True
                    err = exception_to_dict(e, include_stack=False)
                    if not err.get("summary"):
                        err["summary"] = str(e)
                    tmp_filtered, _ = _filter_unknown(model, original_input)
                    tmp_payload = _normalize_payload_for_model(model, tmp_filtered, context_company_id=company_id)
                    tmp_payload = _coerce_boolean_fields(model, tmp_payload)
                    tmp_payload = _quantize_decimal_fields(model, tmp_payload)
                    action, _, _ = _infer_action_and_clean_id(dict(tmp_payload), original_input)
                    unknown_cols_now = _unknown_from_original_input(model, {"_original_input": original_input, "payload": tmp_payload})
                    base = err["summary"]
                    if unknown_cols_now:
                        base = f"{base} | Ignoring unknown columns: {', '.join(unknown_cols_now)}"
                    logger.error(
                        "[IMPORT][PREP][EXC] model=%s row_id=%s action=%s err=%s",
                        model_name, rid, action, base, exc_info=True, **_log_extra()
                    )
                    prepared_rows.append(PlannedRow(
                        model_name=model_name,
                        rid=rid,
                        is_token=not _is_numeric_id(rid),
                        action=action,
                        payload=tmp_payload,
                        original_input=original_input,
                        observations=observations,
                        unknown_cols_now=unknown_cols_now,
                        preflight_error={"code": "PREP_EXCEPTION", "message": base, "error": err},
                        parents=set(),
                    ))

            prepared_by_model[model_name] = prepared_rows
            models_in_file.append(model_name)
            any_prep_error = any_prep_error or had_err
            logger.info("sheet_end", **_log_extra(had_error=bool(had_err)))

        models_in_file = sorted(models_in_file, key=lambda m: ORDER_HINT.get(m, 1000))
        logger.info("order_resolved", **_log_extra(models=models_in_file))

        if commit and any(
            any(pr.preflight_error for pr in prepared_by_model[m])
            for m in models_in_file
        ):
            dt = int((time.monotonic() - t0) * 1000)
            logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=False, reason="prep_errors"))
            return {
                "committed": False,
                "reason": "prep_errors",
                "file_info": file_info,
                "imports": [
                    {
                        "model": m,
                        "dup_info": dup_infos.get(m),
                        "result": [
                            {
                                "__row_id": pr.rid,
                                "status": ("error" if pr.preflight_error else "warning" if pr.unknown_cols_now else "ok"),
                                "action": pr.action,
                                "data": pr.original_input or pr.payload or {},
                                "message": (pr.preflight_error or {}).get("message") if pr.preflight_error else (
                                    "validated" + (f" | Ignoring unknown columns: {', '.join(pr.unknown_cols_now)}" if pr.unknown_cols_now else "")
                                ),
                                "error": (pr.preflight_error or {}).get("error"),
                                "observations": pr.observations,
                                "external_id": None,
                            }
                            for pr in prepared_by_model[m]
                        ]
                    }
                    for m in models_in_file
                ],
            }

        # ---------------- PLAN: Graph & Groups ----------------
        parents_of, children_of, rows_by_rid = _build_dependency_graph(prepared_by_model)

        undirected_adj: Dict[str, Set[str]] = defaultdict(set)
        all_nodes: Set[str] = set(rows_by_rid.keys())
        for child, parents in parents_of.items():
            for p in parents:
                undirected_adj[child].add(p)
                undirected_adj[p].add(child)
        for n in all_nodes:
            undirected_adj.setdefault(n, set())

        groups: List[Set[str]] = _connected_components(all_nodes, undirected_adj)

        # ---------------- EXECUTE GROUPS ----------------
        row_outputs_by_model: Dict[str, List[Dict[str, Any]]] = {m: [] for m in models_in_file}
        models_touched: Set[str] = set()

        for gi, group in enumerate(groups, start=1):
            order, acyclic = _toposort_group(group, parents_of, rows_by_rid, ORDER_HINT)
            if not acyclic:
                msg = "Detected cyclic token dependencies inside the group; provide a numeric id for at least one side or split the cycle."
                for rid in sorted(group):
                    pr = rows_by_rid[rid]
                    _model_ctx.set(pr.model_name); _row_ctx.set(pr.rid)
                    row_outputs_by_model[pr.model_name].append({
                        "__row_id": pr.rid,
                        "status": "error",
                        "action": pr.action,
                        "data": pr.original_input or pr.payload or {},
                        "message": msg,
                        "observations": pr.observations,
                        "external_id": None,
                    })
                continue

            missing_refs = []
            for rid in order:
                for p in rows_by_rid[rid].parents:
                    if p not in rows_by_rid:
                        missing_refs.append((rid, p))
            if missing_refs:
                for rid, p in missing_refs:
                    pr = rows_by_rid[rid]
                    _model_ctx.set(pr.model_name); _row_ctx.set(pr.rid)
                    msg = f"Token {p!r} referenced by row {rid!r} ({pr.model_name}) not found in this import."
                    row_outputs_by_model[pr.model_name].append({
                        "__row_id": pr.rid,
                        "status": "error",
                        "action": pr.action,
                        "data": pr.original_input or pr.payload or {},
                        "message": msg,
                        "observations": pr.observations,
                        "external_id": None,
                    })
                continue

            logger.info("group_begin", **_log_extra(group_index=gi, size=len(group), order=order))

            group_failed = False
            failed_tokens: Set[str] = set()
            failure_messages_by_token: Dict[str, str] = {}
            saved_instances_by_token: Dict[str, Model] = {}
            group_outputs: List[Tuple[str, str, Dict[str, Any]]] = []

            with transaction.atomic():
                sp = transaction.savepoint()
                try:
                    for rid in order:
                        pr = rows_by_rid[rid]
                        _model_ctx.set(pr.model_name); _row_ctx.set(pr.rid)

                        if pr.preflight_error:
                            out = {
                                "__row_id": pr.rid,
                                "status": "error",
                                "action": pr.action,
                                "data": pr.original_input or pr.payload or {},
                                "message": pr.preflight_error.get("message") or "Preflight error",
                                "error": pr.preflight_error.get("error"),
                                "observations": pr.observations,
                                "external_id": None,
                            }
                            group_outputs.append((pr.model_name, pr.rid, out))
                            group_failed = True
                            failed_tokens.add(pr.rid)
                            failure_messages_by_token[pr.rid] = out["message"]
                            continue

                        blocking_parents = [p for p in pr.parents if p in failed_tokens]
                        if group_failed and blocking_parents:
                            msg = f"Parent row(s) {', '.join(sorted(blocking_parents))} failed; unable to validate or save this child."
                            out = {
                                "__row_id": pr.rid,
                                "status": "error",
                                "action": pr.action,
                                "data": pr.original_input or pr.payload or {},
                                "message": msg,
                                "observations": pr.observations,
                                "external_id": None,
                            }
                            group_outputs.append((pr.model_name, pr.rid, out))
                            continue

                        app_label = MODEL_APP_MAP[pr.model_name]
                        model = apps.get_model(app_label, pr.model_name)
                        models_touched.add(pr.model_name)

                        payload = dict(pr.payload)

                        # --------- FK resolution (no deferrals) + strip *_fk ----------
                        _apply_fk_inputs_into_attnames(model, payload, pr.original_input, saved_instances_by_token)

                        # MPTT parent resolution from path (if any)
                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload["parent"] = parent
                                payload.pop("parent_id", None)

                        try:
                            instance = model(**payload)
                            if hasattr(instance, "full_clean"):
                                instance.full_clean()
                            instance.save()
                            saved_instances_by_token[pr.rid] = instance

                            out = {
                                "__row_id": pr.rid,
                                "status": "success",
                                "action": ("update" if getattr(instance, "id", None) else pr.action),
                                "data": safe_model_dict(
                                    instance,
                                    exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"],
                                ),
                                "message": "ok" if not pr.unknown_cols_now else "ok | Ignoring unknown columns: " + ", ".join(pr.unknown_cols_now),
                                "observations": pr.observations,
                                "external_id": None,
                            }
                            group_outputs.append((pr.model_name, pr.rid, out))

                        except Exception as e:
                            err = exception_to_dict(e, include_stack=False)
                            base_msg = err.get("summary") or str(e)
                            if pr.unknown_cols_now:
                                base_msg += " | Ignoring unknown columns: " + ", ".join(pr.unknown_cols_now)
                            logger.error(
                                "[IMPORT][GROUP][EXC] model=%s row_id=%s action=%s err=%s",
                                pr.model_name, pr.rid, pr.action, base_msg, exc_info=True, **_log_extra()
                            )
                            out = {
                                "__row_id": pr.rid,
                                "status": "error",
                                "action": pr.action,
                                "data": pr.original_input or pr.payload or {},
                                "message": base_msg,
                                "error": {**err, "summary": base_msg},
                                "observations": pr.observations,
                                "external_id": None,
                            }
                            group_outputs.append((pr.model_name, pr.rid, out))
                            group_failed = True
                            failed_tokens.add(pr.rid)
                            failure_messages_by_token[pr.rid] = base_msg

                    if commit and not group_failed:
                        transaction.savepoint_commit(sp)
                    else:
                        transaction.savepoint_rollback(sp)
                        if commit and group_failed:
                            failed_list = sorted(list(failed_tokens))
                            rolled_msg = f"Rolled back due to error in group (failed: {', '.join(failed_list)})."
                            for i, (mname, rid, out) in enumerate(group_outputs):
                                if out.get("status") == "success":
                                    out["status"] = "error"
                                    out["message"] = rolled_msg
                                    group_outputs[i] = (mname, rid, out)

                except Exception as e:
                    transaction.savepoint_rollback(sp)
                    err = exception_to_dict(e, include_stack=False)
                    base_msg = err.get("summary") or str(e)
                    for rid in order:
                        pr = rows_by_rid[rid]
                        out = {
                            "__row_id": pr.rid,
                            "status": "error",
                            "action": pr.action,
                            "data": pr.original_input or pr.payload or {},
                            "message": "Aborted due to unexpected error: " + base_msg,
                            "error": err,
                            "observations": pr.observations,
                            "external_id": None,
                        }
                        group_outputs.append((pr.model_name, pr.rid, out))

                for mname, rid, out in group_outputs:
                    row_outputs_by_model[mname].append(out)

        if commit:
            for m in models_in_file:
                pre_rows = prepared_by_model.get(m, [])
                if not pre_rows:
                    continue
                app_label = MODEL_APP_MAP[m]
                model = apps.get_model(app_label, m)
                rows_src = [pr.original_input or pr.payload or {} for pr in pre_rows]
                fp = _table_fingerprint(model, rows_src)
                closest = (dup_infos.get(m) or {}).get("closest_match") or {}
                ImportSnapshot.objects.create(
                    company_id=company_id,
                    model_name=m,
                    row_count=fp["row_count"],
                    colnames=fp["colnames"],
                    row_hash_sample=fp["row_hashes"][:200],
                    table_hash=fp["table_hash"],
                    file_sha256=file_sha,
                    filename=filename,
                    jaccard_to_prev=closest.get("jaccard"),
                )

        if not commit and models_in_file:
            try:
                reset_pk_sequences([apps.get_model(MODEL_APP_MAP[m], m) for m in models_in_file])
            except Exception:
                logger.warning("reset_pk_sequences_failed", **_log_extra(models=models_in_file))

        result_payload: List[Dict[str, Any]] = []
        for m in models_in_file:
            result_payload.append({
                "model": m,
                "dup_info": dup_infos.get(m),
                "result": row_outputs_by_model.get(m, []),
            })

        dt = int((time.monotonic() - t0) * 1000)
        logger.info("import_end", **_log_extra(elapsed_ms=dt, committed=bool(commit)))

        committed_flag = bool(commit) and all(
            all(r.get("status") == "success" for r in (row_outputs_by_model.get(m) or []))
            for m in models_in_file
        )

        return {
            "committed": committed_flag,
            "reason": (None if commit else "preview"),
            "file_info": file_info,
            "imports": result_payload,
        }
