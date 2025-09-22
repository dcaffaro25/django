# tasks.py (multitenancy/tasks.py)
from __future__ import annotations

import hashlib
import json
import re
import smtplib
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
)

# ----------------------------------------------------------------------
# Email helpers
# ----------------------------------------------------------------------

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

def _to_int_or_none(x):
    if x in ("", None):
        return None
    try:
        return int(float(x))
    except Exception:
        return None

def _parse_json_or_empty(v):
    if v in ("", None):
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}

def _to_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

def _norm_row_key(v):
    # normalize string-like row ids/FK tokens from Excel
    if v is None:
        return None
    s = str(v)
    s = s.replace("\u00A0", " ")  # non-breaking space
    return s.strip()

def _resolve_fk(model, field_name: str, raw_value, row_id_map: Dict[str, Any]):
    """
    Resolve a *_fk value to a model instance.

    Accepts:
      - '__row_id' token referencing a previously created row in this same import
      - numeric ID (int/float/'3'/'3.0')
    """
    # 0) Normalize strings (trim spaces, NBSP, etc.)
    if isinstance(raw_value, str):
        raw_value_norm = _norm_row_key(raw_value)
        # 1) __row_id indirection (after normalization)
        if raw_value_norm in row_id_map:
            return row_id_map[raw_value_norm]
    else:
        raw_value_norm = raw_value

    # 2) Treat missing-ish as None
    if _is_missing(raw_value_norm):
        return None

    # 3) Numeric id?
    if isinstance(raw_value_norm, (int, float)) or (isinstance(raw_value_norm, str) and raw_value_norm.replace(".", "", 1).isdigit()):
        fk_id = _to_int_or_none_soft(raw_value_norm)
        if fk_id is None:
            raise ValueError(f"Invalid FK id '{raw_value}' for field '{field_name}'")
        try:
            related_field = model._meta.get_field(field_name)
        except Exception:
            raise ValueError(f"Unknown FK field '{field_name}' for model {model.__name__}")
        fk_model = getattr(related_field, "related_model", None)
        if fk_model is None:
            raise ValueError(f"Field '{field_name}' is not a ForeignKey on {model.__name__}")
        try:
            return fk_model.objects.get(id=fk_id)
        except fk_model.DoesNotExist:
            raise ValueError(f"{fk_model.__name__} id={fk_id} not found for field '{field_name}'")

    # 4) Not a numeric id and not a known __row_id
    raise ValueError(f"Invalid FK reference format '{raw_value}' for field '{field_name}'")

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

def _path_depth(row: Dict[str, Any]) -> int:
    """Used to sort MPTT rows so parents come first."""
    for c in PATH_COLS:
        if c in row and row[c]:
            return len(str(row[c]).strip().replace(" > ", "\\").split("\\"))
    return 0

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
    for chg in audit_by_rowid.get(row_id, []):
        if chg.get("field") == "__row_id":
            continue
        obs.append(
            f"campo '{chg['field']}' alterado de '{chg['old']}' para '{chg['new']}' "
            f"(regra id={chg['rule_id']}')"
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

# Decide create vs update; normalize id
def _infer_action_and_clean_id(payload: Dict[str, Any], original_input: Dict[str, Any]):
    """
    Decide whether this row is a create or update.

    Rules:
      - If payload['id'] can be coerced cleanly to an integer (e.g., 5, '5', 5.0, '5.0'),
        normalize it to int and return ("update", id, None).
      - Otherwise treat it as create. If an unusable 'id' was present in original input,
        return it as external_id for traceability.
    """
    def _coerce_pk(val):
        if val is None or val == "":
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val) if float(val).is_integer() else None
        s = str(val).strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else None
        except Exception:
            return int(s) if s.isdigit() else None

    external_id = None
    pk = _coerce_pk(payload.get("id"))
    if pk is not None:
        payload["id"] = pk
        return "update", pk, None

    if "id" in payload:
        if "id" in original_input and original_input["id"] not in ("", None):
            external_id = str(original_input["id"])
        payload.pop("id", None)

    return "create", None, external_id

# ----------------------------------------------------------------------
# Core import executor
# ----------------------------------------------------------------------

DUP_CHECK_LAST_N = 10  # compare against last N snapshots per model

# Simple dependency hint so parents come before children
ORDER_HINT = {
    "Company": 10,
    "Currency": 10,
    "Entity": 20,
    "Bank": 20,
    "BankAccount": 30,
    "Account": 40,
    "CostCenter": 40,
    "Transaction": 50,     # parent of JournalEntry
    "JournalEntry": 60,    # depends on Transaction
}

def execute_import_job(
    company_id: int,
    sheets: List[Dict[str, Any]],
    commit: bool,
    *,
    file_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    One-shot import for all models in a file.

    Updated for:
      - Global __row_id map so cross-sheet FKs like JournalEntry.transaction_fk="t1" resolve.
      - NaN/NaT-safe canonicalization to avoid "cannot convert float NaN to integer".
      - Booleans/decimals coercion and basic dedupe fingerprints per sheet.
    """

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

    # --------------------------- prep per sheet ---------------------------
    prepared: List[Dict[str, Any]] = []
    models_in_order: List[str] = []
    any_prep_error = False
    dup_infos: Dict[str, Dict[str, Any]] = {}

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

        # ---- preflight for missing required ----
        preflight_err = _preflight_missing_required(model, rows)

        # ---- pack rows for downstream (message reflects unknown columns) ----
        packed_rows = []
        had_err = False

        for idx, row in enumerate(rows):
            rid = row.get("__row_id") or f"row{idx+1}"
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

                action, pk, ext_id = _infer_action_and_clean_id(payload, original_input)

                unknown_cols_now = _unknown_from_original_input(model, {
                    "_original_input": original_input, "payload": payload
                })

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

    # make processing deterministic/parent-first
    models_in_order.sort(key=lambda m: ORDER_HINT.get(m, 1000))

    # ------------------------------ PREVIEW ------------------------------
    if not commit:
        models_touched: List[Any] = []
        result_payload: List[Dict[str, Any]] = []

        # Global __row_id map shared across ALL sheets
        global_row_map: Dict[str, Any] = {}

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")

            outer_sp = transaction.savepoint()

            for model_name in models_in_order:
                app_label = MODEL_APP_MAP[model_name]
                model = apps.get_model(app_label, model_name)
                models_touched.append(model)

                row_map: Dict[str, Any] = {}
                rows = next(b["rows"] for b in prepared if b["model"] == model_name)
                out_rows: List[Dict[str, Any]] = []

                for row in rows:
                    rid = row["__row_id"]

                    # If preflight already failed, surface it and skip DB interaction
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
                        continue

                    payload = dict(row.get("payload") or {})
                    original_input = row.get("_original_input") or payload.copy()
                    action = row.get("action") or "create"

                    unknown_cols_now = _unknown_from_original_input(model, row)

                    try:
                        # Resolve *_fk using LOCAL + GLOBAL row maps
                        for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                            field_name = fk_key[:-3]
                            fk_val = payload.pop(fk_key)
                            merged_map = {**global_row_map, **row_map}
                            payload[field_name] = _resolve_fk(model, field_name, fk_val, merged_map)

                        # Resolve MPTT parent
                        if _is_mptt_model(model):
                            path_val = _get_path_value(payload)
                            if path_val:
                                parts = _split_path(path_val)
                                parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                                payload['parent'] = parent
                                payload.pop('parent_id', None)

                        # Coerce booleans/decimals just before save
                        payload = _coerce_boolean_fields(model, payload)
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
                            key = _norm_row_key(rid)
                            if key:
                                row_map[key] = instance
                                global_row_map[key] = instance  # <-- make visible to other sheets

                        msg = "ok"
                        status_val = "success"
                        if unknown_cols_now and row.get("status") != "error":
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

                result_payload.append({
                    "model": model_name,
                    "dup_info": dup_infos.get(model_name),
                    "result": out_rows
                })

            # Roll back all side-effects and reset sequences
            transaction.savepoint_rollback(outer_sp)
            reset_pk_sequences(models_touched)

        return {
            "committed": False,
            "reason": "preview",
            "file_info": file_info,
            "imports": result_payload
        }

    # ------------------------------ COMMIT ------------------------------
    if any_prep_error:
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
            app_label = MODEL_APP_MAP[model_name]
            model = apps.get_model(app_label, model_name)
            models_touched.append(model)

            row_map: Dict[str, Any] = {}
            rows = next(b["rows"] for b in prepared if b["model"] == model_name)

            for row in rows:
                rid = row["__row_id"]

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
                    continue

                payload = dict(row.get("payload") or {})
                original_input = row.get("_original_input") or payload.copy()
                action = row.get("action") or "create"

                unknown_cols_now = _unknown_from_original_input(model, row)

                try:
                    # Resolve *_fk using LOCAL + GLOBAL row maps
                    for fk_key in [k for k in list(payload.keys()) if k.endswith("_fk")]:
                        field_name = fk_key[:-3]
                        fk_val = payload.pop(fk_key)
                        merged_map = {**global_row_map, **row_map}
                        payload[field_name] = _resolve_fk(model, field_name, fk_val, merged_map)

                    # MPTT parent chain
                    if _is_mptt_model(model):
                        path_val = _get_path_value(payload)
                        if path_val:
                            parts = _split_path(path_val)
                            parent = _resolve_parent_from_path_chain(model, parts[:-1]) if len(parts) > 1 else None
                            payload['parent'] = parent
                            payload.pop('parent_id', None)

                    # Coerce booleans/decimals just before save
                    payload = _coerce_boolean_fields(model, payload)
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
                        key = _norm_row_key(rid)
                        if key:
                            row_map[key] = instance
                            global_row_map[key] = instance  # <-- make visible to other sheets

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

            result_payload.append({
                "model": model_name,
                "dup_info": dup_infos.get(model_name),
                "result": rows
            })

        if any_row_error:
            transaction.savepoint_rollback(outer_sp)
            reset_pk_sequences(models_touched)
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

        return {
            "committed": True,
            "file_info": file_info,
            "imports": result_payload
        }

# Celery entrypoint: one task per file
@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)
