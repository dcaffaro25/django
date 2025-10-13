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

# Substitutions engine (kept local; no api_utils dependency)
from multitenancy.formula_engine import apply_substitutions


# --------------------------------------------------------------------------------------
# Minimal logging
# --------------------------------------------------------------------------------------

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter("%(levelname)s %(asctime)s importer %(message)s")
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
logger.setLevel(
    logging.INFO if os.getenv("IMPORT_DEBUG", "0") not in {"1", "true", "yes"} else logging.DEBUG
)


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
# Barebones importer (no dependency on api_utils.py), with token->id FK resolution
# --------------------------------------------------------------------------------------

# Map Excel sheet names -> app labels (ORDER MATTERS)
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
        if "company_fk" in out:
            cid = _to_int_or_none_soft(out.get("company_fk"))
            if cid:
                out["company_id"] = cid
            out.pop("company_fk", None)
        return out

    out["company_id"] = int(company_id)
    return out


def _resolve_fk_id_on_field(model, field_name: str, raw_value, token_to_id: Dict[str, int]) -> Optional[int]:
    """
    Resolve an FK assignment for `field_name` to an integer id using:
      - token_to_id for string tokens (non-numeric)
      - numeric coercion for numeric-like values
    Additionally, validates that the FK target exists (by id) to give a clear error early.
    """
    if _is_missing(raw_value):
        return None

    # token?
    if isinstance(raw_value, str) and not raw_value.isdigit():
        tok = _norm_row_key(raw_value)
        if tok in token_to_id:
            fk_id = token_to_id[tok]
        else:
            raise ValueError(f"Unresolved foreign key token '{raw_value}' for field '{field_name}'")
    else:
        fk_id = _to_int_or_none_soft(raw_value)

    if fk_id is None:
        raise ValueError(f"Invalid FK reference '{raw_value}' for field '{field_name}'")

    # Validate existence
    related_field = model._meta.get_field(field_name)
    fk_model = getattr(related_field, "related_model", None)
    if fk_model is None:
        raise ValueError(f"Field '{field_name}' is not a ForeignKey on {model.__name__}")
    if not fk_model.objects.filter(id=fk_id).exists():
        raise ValueError(f"{fk_model.__name__} id={fk_id} not found for field '{field_name}'")

    return fk_id


def _apply_fk_inputs(model, payload: dict, original_input: dict, token_to_id: Dict[str, int]) -> dict:
    """
    Interpret '<field>_fk' keys into '<field>_id' assignments (integer IDs), and
    rescue tokens placed directly in base FK fields (e.g., 'transaction': 't1').
    Uses only IDs (no in-memory instances).
    """
    out = dict(payload)

    # First pass: explicit *_fk keys -> *_id
    for k in list(out.keys()):
        if not k.endswith("_fk"):
            continue
        base = k[:-3]
        raw = out.pop(k, None)
        if raw in (None, ""):
            out[f"{base}_id"] = None
            # ensure we don't pass stray base textual value
            out.pop(base, None)
            continue

        # Resolve to id (token or numeric)
        fk_id = _resolve_fk_id_on_field(model, base, raw, token_to_id)
        out[f"{base}_id"] = fk_id
        out.pop(base, None)  # prefer explicit *_id over any stray base

    # Rescue: token/numeric in base FK field -> *_id
    for f in model._meta.get_fields():
        if isinstance(f, dj_models.ForeignKey):
            base = f.name
            if base in out:
                v = out.get(base, None)
                # numeric-like str
                if isinstance(v, str) and v.isdigit():
                    out[f"{base}_id"] = int(v)
                    out.pop(base, None)
                # token-like str
                elif isinstance(v, str) and not v.isdigit():
                    tok = _norm_row_key(v)
                    if tok in token_to_id:
                        out[f"{base}_id"] = token_to_id[tok]
                        out.pop(base, None)
                    else:
                        raise ValueError(f"Unresolved foreign key token '{v}' for field '{base}'")
                # int stays as is if user provided '<base>_id' explicitly; if they provided int on 'base', coerce to *_id
                elif isinstance(v, int):
                    out[f"{base}_id"] = v
                    out.pop(base, None)
                elif v is None:
                    out[f"{base}_id"] = None
                    out.pop(base, None)

    return out


def _safe_model_dict(instance, exclude_fields=None) -> dict:
    """
    Safer serializer:
      - Always include 'id'
      - Convert FK relations to their '<field>_id' values
      - Remove sensitive/non-informative fields if requested
    """
    exclude_fields = set(exclude_fields or [])
    data: Dict[str, Any] = {"id": getattr(instance, "pk", None)}

    for field in instance._meta.fields:
        name = field.name
        if name in exclude_fields:
            continue
        if field.is_relation:
            data[name] = getattr(instance, f"{name}_id", None)
        else:
            # model_to_dict excludes id; reading from instance ensures we include all editables
            data[name] = getattr(instance, name)

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
    Importer with token->id mapping for FK resolution and a single atomic transaction.

    Flow:
      - Sort sheets using MODEL_APP_MAP order
      - For each row: substitutions -> filter -> company context -> MPTT path -> *_fk resolution to *_id
      - Save, record token->id
      - On preview (commit=False): rollback entire transaction at the end
    """
    run_id = uuid.uuid4().hex[:8]
    logger.info("import_start run_id=%s commit=%s sheet_count=%d", run_id, bool(commit), len(sheets))

    # enforce sheet processing order using MODEL_APP_MAP key order
    model_order = {name: idx for idx, name in enumerate(MODEL_APP_MAP.keys())}
    sheets.sort(key=lambda s: model_order.get(s.get("model"), len(model_order)))
    logger.debug("sheet_order=%s", [s.get("model") for s in sheets])

    token_to_id: Dict[str, int] = {}  # GLOBAL token->id registry across all sheets
    outputs_by_model: Dict[str, List[dict]] = {}

    t0 = time.monotonic()
    with transaction.atomic():
        # One big atomic block; in preview, we'll mark rollback at the end
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
                    "external_id": None,
                })
                continue

            model = apps.get_model(app_label, model_name)
            raw_rows: List[Dict[str, Any]] = sheet.get("rows") or []

            # 1) substitutions + audit
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

            for row in rows:
                raw = dict(row or {})
                rid_raw = raw.pop("__row_id", None)
                rid = _norm_row_key(rid_raw)

                try:
                    # 2) filter unknowns (keep *_fk)
                    filtered, unknown = _filter_unknown(model, raw)

                    # 3) company context
                    filtered = _attach_company_context(model, filtered, company_id)

                    # 4) MPTT handling: derive name/parent from path
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

                    # 5) FK application: *_fk -> *_id and rescue base tokens to *_id
                    filtered = _apply_fk_inputs(model, filtered, raw, token_to_id)

                    # 6) coercions
                    filtered = _coerce_boolean_fields(model, filtered)
                    filtered = _quantize_decimal_fields(model, filtered)

                    # 7) create/update
                    action = "create"
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

                    # 8) validate & save
                    if hasattr(instance, "full_clean"):
                        instance.full_clean()
                    instance.save()  # assign PK now (even in preview; will rollback later)

                    # 9) register token->id (AFTER save to ensure an id exists)
                    if rid:
                        token_to_id[rid] = int(instance.pk)

                    # 10) success output
                    msg = "ok"
                    if unknown:
                        msg += f" | Ignoring unknown columns: {', '.join(unknown)}"

                    outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "success",
                        "action": action,
                        "data": _safe_model_dict(
                            instance,
                            exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"]
                        ),
                        "message": msg,
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })

                except Exception as e:
                    logger.exception("row error on %s rid=%s: %s", model_name, rid, e)
                    outputs_by_model[model_name].append({
                        "__row_id": rid,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": str(e),
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })

        # Preview? Roll back everything at the end
        committed_flag = bool(commit)
        if not commit:
            # Mark the outer transaction to rollback
            transaction.set_rollback(True)

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


