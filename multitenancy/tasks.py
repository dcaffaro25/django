# multitenancy/tasks.py
from __future__ import annotations

import logging
import os
import re
import smtplib
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction, models as dj_models
from django.forms.models import model_to_dict

# ⬇️ Substitutions engine (kept local; no api_utils dependency)
from multitenancy.formula_engine import apply_substitutions

# --------------------------------------------------------------------------------------
# Minimal logging
# --------------------------------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter("%(levelname)s %(asctime)s importer %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
    logger.setLevel(logging.INFO if os.getenv("IMPORT_DEBUG", "0") not in {"1", "true", "yes"} else logging.DEBUG)

# --------------------------------------------------------------------------------------
# Email helpers (kept)
# --------------------------------------------------------------------------------------
@shared_task(bind=True, autoretry_for=(smtplib.SMTPException, ConnectionError), retry_backoff=True, max_retries=5)
def send_user_invite_email(self, subject: str, message: str, to_email: str):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_email(self, subject: str, message: str, to_email: str):
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


# --------------------------------------------------------------------------------------
# Simple integration trigger (kept)
# --------------------------------------------------------------------------------------
@shared_task
def execute_integration_rule(rule_id: int, payload: dict):
    from multitenancy.models import IntegrationRule  # local import to avoid heavy imports on module load
    rule = IntegrationRule.objects.get(pk=rule_id)
    return rule.run_rule(payload)


@shared_task
def trigger_integration_event(company_id: int, event_name: str, payload: dict):
    from multitenancy.models import IntegrationRule
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
# Barebones importer (no dependency on api_utils.py)
# --------------------------------------------------------------------------------------

# Map Excel sheet names -> app labels
MODEL_APP_MAP: Dict[str, str] = {
    # multitenancy
    "Entity": "multitenancy",
    "Company": "multitenancy",
    "IntegrationRule": "multitenancy",
    "SubstitutionRule": "multitenancy",
    # accounting
    "Currency": "accounting",
    "Bank": "accounting",
    "BankAccount": "accounting",
    "Account": "accounting",
    "CostCenter": "accounting",
    "Transaction": "accounting",
    "JournalEntry": "accounting",
    "BankTransaction": "accounting",
    # billing
    "BusinessPartnerCategory": "billing",
    "BusinessPartner": "billing",
    "ProductServiceCategory": "billing",
    "ProductService": "billing",
    "Contract": "billing",
    "Invoice": "billing",
    "InvoiceLine": "billing",
    # core
    "FinancialIndex": "core",
    "IndexQuote": "core",
    "FinancialIndexQuoteForecast": "core",
    # hr
    "Employee": "hr",
    "Position": "hr",
    "TimeTracking": "hr",
    "KPI": "hr",
    "Bonus": "hr",
    "RecurringAdjustment": "hr",
}

PATH_COLS = ("path", "Caminho")
PATH_SEP = " > "

_WS_RE = re.compile(r"\s+")


def _is_missing(v) -> bool:
    if v is None or v == "":
        return True
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return True
    except Exception:
        pass
    if isinstance(v, str) and v.strip().lower() in {"nan", "nat"}:
        return True
    return False


def _to_int_or_none_soft(v):
    if _is_missing(v):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if float(v).is_integer() else None
    s = str(v).strip()
    if s.isdigit():
        return int(s)
    try:
        f = float(s)
        return int(f) if f.is_integer() else None
    except Exception:
        return None


def _to_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _norm_row_key(key: Any) -> Any:
    if isinstance(key, str):
        return key.replace("\u00A0", " ").strip().lower()
    return key


def _is_mptt_model(model) -> bool:
    # simple heuristic: has _mptt_meta and a "parent" field
    return hasattr(model, "_mptt_meta") and any(f.name == "parent" for f in model._meta.fields)


def _get_path_value(d: Dict[str, Any]) -> Optional[str]:
    for c in PATH_COLS:
        v = d.get(c)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _split_path(path_str: str) -> List[str]:
    return [p.strip() for p in str(path_str).split(PATH_SEP) if p and p.strip()]


def _path_depth(row: Dict[str, Any]) -> int:
    p = _get_path_value(row)
    return len(_split_path(p)) if p else 0


def _resolve_parent_from_path_chain(model, chain: List[str]):
    """
    Resolve an existing parent chain in DB (or earlier created rows).
    Assumes each node is uniquely identified by (name, parent) within the model.
    """
    parent = None
    for idx, node_name in enumerate(chain):
        inst = model.objects.filter(name=node_name, parent=parent).first()
        if not inst:
            missing = PATH_SEP.join(chain[: idx + 1])
            raise ValueError(f"{model.__name__}: missing ancestor '{missing}'. Ensure parents are created before children.")
        parent = inst
    return parent


def _allowed_keys(model) -> set:
    names = set()
    for f in model._meta.fields:
        names.add(f.name)
        att = getattr(f, "attname", None)
        if att:
            names.add(att)  # e.g. entity_id
    fk_aliases = {n + "_fk" for n in names}
    # allow path helper + id + __row_id and company_fk convenience
    return names | fk_aliases | set(PATH_COLS) | {"__row_id", "id", "company_fk"}


def _filter_unknown(model, row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    allowed = _allowed_keys(model)
    filtered = {k: v for k, v in row.items() if k in allowed}
    unknown = sorted([k for k in row.keys() if k not in allowed and k != "__row_id"])
    return filtered, unknown


def _coerce_boolean_fields(model, payload: dict) -> dict:
    out = dict(payload)
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.BooleanField):
            name = getattr(f, "attname", f.name)
            if name in out:
                out[name] = _to_bool(out[name])
    return out


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


def _attach_company_context(model, payload: dict, company_id: Optional[int]) -> dict:
    """
    If the model has a 'company' FK and we have a company_id, ensure payload['company_id'] is set,
    unless caller explicitly provided one (company or company_id or company_fk).
    """
    out = dict(payload)
    has_company = any(getattr(f, "name", "") == "company" for f in model._meta.fields)
    if not has_company or not company_id:
        return out

    # explicit overrides
    if "company_id" in out or "company" in out or "company_fk" in out:
        # if they provided company_fk, convert to company_id if it's numeric
        if "company_fk" in out:
            cid = _to_int_or_none_soft(out.get("company_fk"))
            if cid:
                out["company_id"] = cid
            out.pop("company_fk", None)
        return out

    out["company_id"] = int(company_id)
    return out


def _resolve_fk_on_field(model, field_name: str, raw_value, token_map: Dict[str, Any]):
    """
    Resolve a ForeignKey for `field_name`.
    - If raw_value is a string token and exists in token_map -> return that instance
    - If raw_value numeric-ish -> fetch by id
    - None/"" -> None
    Return the *instance* (safe to assign to FK field).
    """
    if _is_missing(raw_value):
        return None

    # Token indirection
    if isinstance(raw_value, str) and not raw_value.isdigit():
        tok = _norm_row_key(raw_value)
        if tok in token_map:
            return token_map[tok]

    related_field = model._meta.get_field(field_name)
    fk_model = getattr(related_field, "related_model", None)
    if fk_model is None:
        raise ValueError(f"Field '{field_name}' is not a ForeignKey on {model.__name__}")

    fk_id = _to_int_or_none_soft(raw_value)
    if fk_id is None:
        raise ValueError(f"Invalid FK reference '{raw_value}' for field '{field_name}'")
    try:
        return fk_model.objects.get(id=fk_id)
    except fk_model.DoesNotExist:
        raise ValueError(f"{fk_model.__name__} id={fk_id} not found for field '{field_name}'")


def _apply_fk_inputs(model, payload: dict, original_input: dict, saved_by_token: Dict[str, Any]) -> dict:
    """
    Interpret '<field>_fk' keys (if present) into actual FK instances on '<field>'.
    Also rescue tokens typed directly into the base field (string matching a saved token).
    """
    out = dict(payload)

    # First pass: explicit *_fk keys
    for k in list(out.keys()):
        if not k.endswith("_fk"):
            continue
        base = k[:-3]
        raw = out.pop(k, None)
        if raw in (None, ""):
            out[base] = None
            continue
        # Resolve token or ID
        resolved_obj = _resolve_fk_on_field(model, base, raw, saved_by_token)
        if isinstance(resolved_obj, dj_models.Model):
            # Use the PK for assignment to avoid 'null' issues on unsaved instances
            out[f"{base}_id"] = resolved_obj.pk
        else:
            out[base] = resolved_obj  # for numeric IDs, _resolve_fk_on_field returns the object or raises

    # Rescue: token in base field
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.ForeignKey):
            base = f.name
            v = out.get(base, None)
            if isinstance(v, str) and not v.isdigit():
                tok = _norm_row_key(v)
                if tok in saved_by_token:
                    out[base] = saved_by_token[tok]

    return out


def _safe_model_dict(instance, exclude_fields=None) -> dict:
    data = model_to_dict(instance)
    exclude_fields = set(exclude_fields or [])
    for field in exclude_fields:
        data.pop(field, None)
    # Convert relations to ids for readability
    for field in instance._meta.fields:
        if field.is_relation:
            name = field.name
            data[name] = getattr(instance, f"{name}_id", None)
    return data


def _row_observations(audit_by_rowid: Dict[Any, List[dict]], rid_norm: Any) -> List[str]:
    obs: List[str] = []
    for ch in audit_by_rowid.get(rid_norm, []):
        if ch.get("field") == "__row_id":
            continue
        obs.append(
            f"campo '{ch.get('field')}' alterado de '{ch.get('old')}' para '{ch.get('new')}' (regra id={ch.get('rule_id')})"
        )
    return obs


@dataclass
class RowResult:
    __row_id: Optional[str]
    status: str
    action: Optional[str]
    data: dict
    message: str


@shared_task
def run_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    return execute_import_job(company_id, sheets, commit)


def execute_import_job(company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    """
    Very small importer with substitutions:
    - Per sheet: apply_substitutions (returns rows + audit)
    - Iterates rows
    - Filters unknown keys
    - Applies company context
    - Resolves *_fk (numeric id or __row_id token)
    - Supports MPTT via 'path'/'Caminho' (parents first; will error if missing)
    - create vs update based on 'id'
    - Attaches per-row substitution observations
    """
    run_id = uuid.uuid4().hex[:8]
    logger.info("import_start run_id=%s commit=%s sheet_count=%d", run_id, bool(commit), len(sheets))

    # Global token map across *all* sheets
    saved_by_token: Dict[str, Any] = {}
    outputs_by_model: Dict[str, List[dict]] = {}

    t0 = time.monotonic()
    with transaction.atomic():
        # roll back everything if preview
        savepoint = transaction.savepoint()

        for sheet in sheets:
            model_name = sheet.get("model")
            outputs_by_model.setdefault(model_name or "Unknown", [])

            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                msg = f"Unknown model '{model_name}'"
                logger.error(msg)
                outputs_by_model[model_name].append({
                    "__row_id": None,
                    "status": "error",
                    "action": None,
                    "data": {},
                    "message": msg,
                    "observations": [],
                })
                continue

            model = apps.get_model(app_label, model_name)
            raw_rows: List[Dict[str, Any]] = sheet.get("rows") or []

            # ---------- substitutions + audit ----------
            rows, audit = apply_substitutions(
                raw_rows,
                company_id=company_id,
                model_name=model_name,
                return_audit=True
            )
            audit_by_rowid: Dict[Any, List[dict]] = {}
            for ch in (audit or []):
                key_norm = _norm_row_key(ch.get("__row_id"))
                audit_by_rowid.setdefault(key_norm, []).append(ch)

            logger.info("processing sheet '%s' rows=%d (after substitutions)", model_name, len(rows))

            # If MPTT and path present, sort parents first
            if _is_mptt_model(model):
                rows = sorted(rows, key=_path_depth)

            for idx, row in enumerate(rows):
                raw = dict(row or {})
                rid_raw = raw.pop("__row_id", None)
                rid = _norm_row_key(rid_raw)

                try:
                    # 1) unknowns filtered (but keep *_fk)
                    filtered, unknown = _filter_unknown(model, raw)

                    # 2) company context (if model has company)
                    filtered = _attach_company_context(model, filtered, company_id)

                    # 3) MPTT: derive name/parent from path (if provided)
                    if _is_mptt_model(model):
                        path_val = _get_path_value(filtered)
                        if path_val:
                            parts = _split_path(path_val)
                            if not parts:
                                raise ValueError(f"{model_name}: empty path")
                            leaf = parts[-1]
                            parent = None
                            if len(parts) > 1:
                                parent = _resolve_parent_from_path_chain(model, parts[:-1])
                            filtered["name"] = filtered.get("name", leaf) or leaf
                            filtered["parent"] = parent
                            filtered.pop("parent_id", None)
                            filtered.pop("parent_fk", None)
                            for c in PATH_COLS:
                                filtered.pop(c, None)

                    # 4) FK application: handle *_fk + token rescue
                    filtered = _apply_fk_inputs(model, filtered, raw, saved_by_token)

                    # 5) coercions
                    filtered = _coerce_boolean_fields(model, filtered)
                    filtered = _quantize_decimal_fields(model, filtered)

                    # 6) create/update
                    action = "create"
                    instance = None
                    if "id" in filtered and filtered["id"]:
                        pk = _to_int_or_none_soft(filtered["id"])
                        if not pk:
                            raise ValueError("Invalid 'id' for update")
                        instance = model.objects.get(id=pk)
                        for k, v in filtered.items():
                            setattr(instance, k, v)
                        action = "update"
                    else:
                        instance = model(**filtered)

                    # 7) validate & save
                    if hasattr(instance, "full_clean"):
                        instance.full_clean()
                    instance.save()

                    # 8) register token
                    if rid:
                        saved_by_token[rid] = instance

                    msg = "ok"
                    if unknown:
                        msg += f" | Ignoring unknown columns: {', '.join(unknown)}"

                    outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "success",
                        "action": action,
                        "data": _safe_model_dict(instance, exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"]),
                        "message": msg,
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })

                except Exception as e:
                    outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": str(e),
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })
                    logger.exception("row error on %s rid=%s: %s", model_name, rid, e)

        # Preview? roll back changes
        committed_flag = bool(commit)
        if not commit:
            transaction.savepoint_rollback(savepoint)
        else:
            transaction.savepoint_commit(savepoint)

    dt_ms = int((time.monotonic() - t0) * 1000)
    logger.info("import_end run_id=%s committed=%s elapsed_ms=%d", run_id, committed_flag, dt_ms)

    return {
        "committed": committed_flag,
        "reason": (None if commit else "preview"),
        "imports": [
            {"model": m, "result": outputs_by_model.get(m, [])}
            for m in outputs_by_model.keys()
        ],
    }
