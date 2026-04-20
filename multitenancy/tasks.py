# multitenancy/tasks.py

from __future__ import annotations

import logging
import math
import os
import re
import smtplib
import unicodedata
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from operator import attrgetter
from typing import Any, Dict, List, Optional, Set, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.core.mail import send_mail
from django.db import router, transaction, models as dj_models
from django.db.models.deletion import Collector
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
        .filter(company_id=company_id, is_active=True, trigger_event=event_name)
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
    "NotaFiscal": "billing",
    "NotaFiscalItem": "billing",
    "NotaFiscalReferencia": "billing",
    "NFeEvento": "billing",
    "NFeInutilizacao": "billing",
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
    "DocTypeRule": "npl",
    "SpanRule": "npl",
}

PATH_COLS = ("path", "Caminho")
PATH_SEP = " > "

_WS_RE = re.compile(r"\s+")


def _model_has_erp_id(model) -> bool:
    return any(getattr(f, "name", None) == "erp_id" for f in model._meta.fields)


def _merge_sheet_import_options(import_metadata: Optional[Dict[str, Any]], sheet: Dict[str, Any]) -> Dict[str, Any]:
    """Merge per-request and per-sheet import options (ETL passes options on each sheet dict)."""
    meta_opts = (import_metadata or {}).get("import_options") or {}
    sheet_opts = (sheet or {}).get("import_options") or {}
    out: Dict[str, Any] = {**meta_opts, **sheet_opts}
    if "erp_key_coalesce" not in out:
        out["erp_key_coalesce"] = True
    if "erp_duplicate_behavior" not in out:
        out["erp_duplicate_behavior"] = "update"
    if "mptt_path_create_missing_ancestors" not in out:
        out["mptt_path_create_missing_ancestors"] = False
    return out


def _erp_delete_key_parts(val: Any) -> Tuple[bool, str]:
    """Return (delete_intent, key_without_leading_minus) for ERP row keys."""
    if _is_missing(val):
        return False, ""
    s = str(val).strip()
    if s.startswith("-"):
        return True, s[1:].strip()
    return False, s


def _erp_keys_conflict_message(left: Any, right: Any) -> Optional[str]:
    dl, vl = _erp_delete_key_parts(left)
    dr, vr = _erp_delete_key_parts(right)
    if (dl, vl) != (dr, vr):
        return f"__erp_id and mapped erp_id disagree ({left!r} vs {right!r})"
    return None


def _resolve_row_erp_identifier(
    raw: Dict[str, Any],
    popped__erp_id: Any,
    model,
    import_options: Dict[str, Any],
) -> Tuple[Any, Optional[str]]:
    """
    Unify __erp_id column and mapped erp_id on the row when erp_key_coalesce is True.

    Returns (effective_value_for_upsert_logic, error_message_or_none).
    """
    coalesce = bool(import_options.get("erp_key_coalesce", True))
    if coalesce and _model_has_erp_id(model):
        mapped_erp = raw.get("erp_id")
        if not _is_missing(popped__erp_id) and not _is_missing(mapped_erp):
            msg = _erp_keys_conflict_message(popped__erp_id, mapped_erp)
            if msg:
                return None, msg
        if _is_missing(popped__erp_id) and not _is_missing(mapped_erp):
            return mapped_erp, None
    return popped__erp_id, None


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


def _parse_import_row_id(rid_raw: Any) -> Tuple[str, Any, Any]:
    """
    Classify __row_id for bulk import (single discriminator for create / update / delete).

    Returns (mode, detail, display_rid):
      - mode 'error': detail is an error message string; display_rid is None.
      - mode 'create': detail is normalized token (str) or None (no token_to_id); display_rid for output.
      - mode 'update': detail is pk (int); display_rid for output (usually same as pk).
      - mode 'delete': detail is pk (int) to delete; display_rid is the original negative __row_id for output.

    Rules:
      - Alphanumeric (non-integer string): create + token for FK map.
      - Integer > 0: update existing row with that id.
      - Integer < 0: delete row with id abs(value).
      - Integer 0: error.
    """
    if rid_raw is None:
        return ("create", None, None)

    if isinstance(rid_raw, bool):
        return ("error", "Invalid __row_id: boolean value not allowed", None)

    if isinstance(rid_raw, float):
        if math.isnan(rid_raw) or not float(rid_raw).is_integer():
            return ("error", "Invalid __row_id: non-integer number", None)
        rid_raw = int(rid_raw)

    if isinstance(rid_raw, int):
        if rid_raw == 0:
            return ("error", "Invalid __row_id: zero not allowed", None)
        if rid_raw > 0:
            return ("update", rid_raw, rid_raw)
        return ("delete", abs(rid_raw), rid_raw)

    s = str(rid_raw).replace("\u00A0", " ").strip()
    if not s:
        return ("create", None, None)
    try:
        n = int(s)
    except (ValueError, TypeError):
        tok = _norm_row_key(rid_raw)
        return ("create", tok if tok else None, tok)

    if n == 0:
        return ("error", "Invalid __row_id: zero not allowed", None)
    if n > 0:
        return ("update", n, n)
    return ("delete", abs(n), n)


def _assert_import_tenant_scope(instance: Any, company_id: Optional[int]) -> None:
    """Ensure imported row targets the current tenant when the model is company-scoped."""
    if company_id is None:
        return
    if not hasattr(instance, "company_id"):
        return
    cid = getattr(instance, "company_id", None)
    if cid is not None and int(cid) != int(company_id):
        raise ValueError(
            f"Record id={instance.pk} belongs to company {cid}, not import target {company_id}. "
            f"Send company_id={cid} in the bulk-import multipart form (field company_id), "
            f"or call the API under /{cid}/api/... so the tenant matches the rows you delete."
        )


def _model_has_soft_delete_field(model) -> bool:
    return any(getattr(f, "name", None) == "is_deleted" for f in model._meta.fields)


def _soft_delete_with_collector(instance: Any) -> str:
    """
    Mirror Django's delete() graph (CASCADE, PROTECT, RESTRICT, fast_deletes) but
    apply ``is_deleted=True`` for models that define it, and ``QuerySet.delete()``
    for models that do not (so their FK on_delete still applies).

    We intentionally **do not** apply ``Collector.field_updates`` (SET_NULL, etc.):
    soft-deleted parents remain in the database, so FKs pointing to them stay valid.
    Processing order matches ``Collector.delete()`` (sort → fast_deletes → batches).
    """
    # db_for_write(model, **hints) — instance must be a keyword arg (not positional).
    using = getattr(instance._state, "db", None) or router.db_for_write(
        instance.__class__, instance=instance
    )
    collector = Collector(using=using, origin=instance.__class__)
    collector.collect([instance])

    parts: List[str] = []

    # Match Collector.delete(): sort PKs within each model, then dependency order.
    for model, instances in collector.data.items():
        collector.data[model] = sorted(instances, key=attrgetter("pk"))
    collector.sort()

    # Fast deletes (same position as Django: after sort, before main batches).
    for qs in collector.fast_deletes:
        m = qs.model
        if _model_has_soft_delete_field(m):
            n = qs.update(is_deleted=True)
            parts.append(f"{m.__name__}:{n} soft")
        else:
            n = qs._raw_delete(using=using)
            parts.append(f"{m.__name__}:{n} hard")

    # field_updates intentionally skipped — rows are not removed from DB.

    for instances in collector.data.values():
        instances.reverse()

    for model, instances in collector.data.items():
        pks = [obj.pk for obj in instances]
        if not pks:
            continue
        if _model_has_soft_delete_field(model):
            n = model._base_manager.using(using).filter(pk__in=pks).update(is_deleted=True)
            parts.append(f"{model.__name__}:{n} soft")
        else:
            n, _ = model._base_manager.using(using).filter(pk__in=pks).delete()
            parts.append(f"{model.__name__}:{n} hard")

    summary = ", ".join(parts) if parts else "0 rows"
    return f"soft_cascade({summary})"


def _apply_import_delete(instance: Any, model) -> str:
    """
    Delete semantics aligned with Django model FK ``on_delete``:

    - If the model has no ``is_deleted`` field: ``instance.delete()`` (full collector;
      CASCADE / PROTECT / RESTRICT / SET_NULL as defined on the model).
    - If the model has ``is_deleted``: run the same collector graph as a real delete,
      but rows on soft-delete models are flagged; related rows without ``is_deleted``
      are removed with normal ``QuerySet.delete()``.
    """
    if not _model_has_soft_delete_field(model):
        instance.delete()
        return "hard"
    return _soft_delete_with_collector(instance)


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


def _normalize_path_segment(label: str) -> str:
    """Normalize a single path label for comparison (NBSP, Unicode compatibility, case-insensitive)."""
    t = (label or "").replace("\u00a0", " ").strip()
    try:
        t = unicodedata.normalize("NFKC", t)
    except Exception:
        pass
    return t.casefold()


def _normalize_full_path(path_str: str) -> str:
    parts = [_normalize_path_segment(p) for p in str(path_str).split(PATH_SEP) if p.strip()]
    return PATH_SEP.join(parts)


def _mptt_rendered_path_for_import_match(node) -> str:
    """
    Same string shape as ``node.get_path()`` for path matching, without N+1 parent fetches.

    Uses django-mptt ``get_ancestors`` (one query) instead of walking ``parent`` in Python.
    """
    get_anc = getattr(node, "get_ancestors", None)
    if callable(get_anc):
        try:
            anc = get_anc(include_self=True).order_by("lft")
            return PATH_SEP.join(anc.values_list("name", flat=True))
        except Exception:
            pass
    return node.get_path()


def _import_path_matches_db_path(expected_norm: str, db_path_raw: str) -> bool:
    """
    True if the chart row ``db_path_raw`` is the same trail as ``expected_norm`` (normalized).

    Accepts DB paths that have extra leading segments (e.g. a grouping node above ``Resultado``)
    as long as the trail ends with the import path: ``… > Resultado > … > Leaf``.
    """
    db_norm = _normalize_full_path(db_path_raw)
    if not expected_norm or not db_norm:
        return False
    if db_norm == expected_norm:
        return True
    return db_norm.endswith(PATH_SEP + expected_norm)


def _path_depth(row: Dict[str, Any]) -> int:
    p = _get_path_value(row)
    return len(_split_path(p)) if p else 0


def _model_has_concrete_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _mptt_qs_active(qs, model):
    if _model_has_concrete_field(model, "is_deleted"):
        return qs.filter(is_deleted=False)
    return qs


def _fk_scalar_from_import_row(filtered: Dict[str, Any], raw: Dict[str, Any], base: str) -> Optional[int]:
    """Resolve ``{base}_id`` or ``{base}_fk`` from row dicts before ``_apply_fk_inputs`` runs."""
    for d in (filtered, raw):
        for key in (f"{base}_id", f"{base}_fk"):
            if key in d and not _is_missing(d.get(key)):
                return _to_int_or_none_soft(d.get(key))
    return None


def _mptt_create_missing_ancestor(
    model,
    node_name: str,
    parent: Any,
    company_id: Optional[int],
    filtered: Dict[str, Any],
    raw: Dict[str, Any],
):
    """
    Insert one intermediate MPTT node so a deeper path can attach.
    Uses the same company and (for Account) currency / direction / balance fields as the leaf row.
    """
    kwargs: Dict[str, Any] = {"name": node_name, "parent": parent}
    if _model_has_concrete_field(model, "company"):
        if not company_id:
            raise ValueError(
                f"{model.__name__}: cannot auto-create path ancestor {node_name!r} without company_id on the row."
            )
        kwargs["company_id"] = int(company_id)

    model_name = model.__name__
    if model_name == "Entity":
        inst = model(**kwargs)
        if hasattr(inst, "full_clean"):
            inst.full_clean()
        inst.save()
        return inst

    if model_name == "Account":
        cid = _fk_scalar_from_import_row(filtered, raw, "currency")
        if not cid:
            raise ValueError(
                f"{model.__name__}: cannot auto-create path ancestor {node_name!r} without "
                f"currency_id or currency_fk on the row."
            )
        kwargs["currency_id"] = cid
        for key in ("account_direction", "balance_date", "balance"):
            if key in filtered and not _is_missing(filtered.get(key)):
                kwargs[key] = filtered[key]
        missing_req = [
            k
            for k in ("account_direction", "balance_date", "balance")
            if k not in kwargs or _is_missing(kwargs.get(k))
        ]
        if missing_req:
            raise ValueError(
                f"{model.__name__}: cannot auto-create path ancestor {node_name!r}; "
                f"the row must include {', '.join(missing_req)} (copied to intermediate nodes)."
            )
        inst = model(**kwargs)
        if hasattr(inst, "full_clean"):
            inst.full_clean()
        inst.save()
        return inst

    raise ValueError(
        f"{model.__name__}: missing path ancestor {node_name!r}; automatic creation is only "
        f"supported for Account and Entity. Add parent rows to the import or implement stubs for this model."
    )


def _pick_mptt_child_by_name(
    model,
    node_name: str,
    parent: Any,
    company_id: Optional[int],
    has_company: bool,
    *,
    active_only: bool = True,
):
    """
    Find a direct child of ``parent`` whose ``name`` matches the path segment (case-insensitive).

    Parents are expected to exist in the chart (or earlier import rows); spelling may differ in case
    from the import file. When ``active_only`` is False, soft-deleted rows are included as a second pass.
    """
    segment = (node_name or "").strip()
    if not segment:
        return None
    qs = model.objects.filter(parent=parent, name__iexact=segment)
    if has_company and company_id is not None:
        qs = qs.filter(company_id=int(company_id))
    if active_only:
        qs = _mptt_qs_active(qs, model)
    return qs.order_by("id").first()


def _find_mptt_node_matching_path_string(
    model,
    chain: List[str],
    company_id: Optional[int],
) -> Optional[Any]:
    """
    Locate the node for path prefix ``chain`` without scanning the whole tree.

    Only rows whose **deepest segment name** matches ``chain[-1]`` (case-insensitive DB ``name``)
    are considered; each candidate's rendered path is compared to the expected trail (normalized,
    case-folded per segment), including DB paths that end with the import trail when the chart has
    extra leading segments.

    If nothing matches, callers fall back to a per-level parent walk (also case-insensitive ``name``).
    """
    if not chain or not hasattr(model, "get_path"):
        return None
    expected = _normalize_full_path(PATH_SEP.join(chain))
    leaf_name = (chain[-1] or "").strip()
    if not leaf_name:
        return None

    def _scan(qs_base, use_active_filter: bool) -> Optional[Any]:
        qs = qs_base
        if use_active_filter:
            qs = _mptt_qs_active(qs, model)
        qs_leaf = qs.filter(name__iexact=leaf_name)
        best: Optional[Any] = None
        best_depth: Optional[int] = None

        for cand in qs_leaf.iterator(chunk_size=400):
            try:
                raw_gp = _mptt_rendered_path_for_import_match(cand)
            except Exception:
                continue
            if not _import_path_matches_db_path(expected, raw_gp):
                continue
            nd = _normalize_full_path(raw_gp)
            depth = len(_split_path(nd))
            if nd == expected:
                return cand
            if best is None or (best_depth is not None and depth < best_depth):
                best, best_depth = cand, depth

        return best

    qs0 = model.objects.all()
    if company_id is not None and _model_has_concrete_field(model, "company"):
        qs0 = qs0.filter(company_id=int(company_id))

    found = _scan(qs0, use_active_filter=True)
    if found is not None:
        return found
    if _model_has_concrete_field(model, "is_deleted"):
        return _scan(qs0, use_active_filter=False)
    return None


def _debug_mptt_parent_resolution_failure(
    model,
    chain: List[str],
    company_id: Optional[int],
    failed_idx: int,
    parent_inst: Optional[Any],
    source_path_for_errors: Optional[str],
) -> str:
    """
    Build a multi-line diagnostic block for import/API responses when parent path resolution fails.
    """
    node_name = chain[failed_idx]
    missing_prefix = PATH_SEP.join(chain[: failed_idx + 1])
    full_expected = PATH_SEP.join(chain)
    norm_exp = _normalize_full_path(full_expected)
    lines: List[str] = [
        "Debug (MPTT parent resolution):",
        f"  import_row_path_raw={source_path_for_errors!r}" if source_path_for_errors else "  import_row_path_raw=<not passed>",
        f"  parent_prefix_segments={len(chain)} expected_parent_path={full_expected!r}",
        f"  parent_prefix_normalized={norm_exp!r}",
        f"  failed_step_index={failed_idx} missing_prefix_so_far={missing_prefix!r} missing_node_name={node_name!r}",
        f"  company_id_for_scope={company_id!r}",
    ]
    if parent_inst is None:
        lines.append("  reached_parent=None (walker expected a root with this name next).")
    else:
        try:
            pp = parent_inst.get_path()
        except Exception as ex:
            pp = f"<get_path() failed: {ex!r}>"
        del_p = getattr(parent_inst, "is_deleted", None)
        lines.append(
            f"  reached_parent=id={parent_inst.pk} is_deleted={del_p!r} get_path()={pp!r}"
        )

    base = model.objects.all()
    if _model_has_concrete_field(model, "company"):
        if company_id is not None:
            base = base.filter(company_id=int(company_id))
        else:
            lines.append(
                "  warning: company_id is None but model is company-scoped; "
                "candidate counts below are not filtered by tenant."
            )

    exact = base.filter(name=node_name)
    n_exact = exact.count()
    lines.append(f"  db_rows_same_company_exact_name={n_exact} (name={node_name!r})")

    if parent_inst is not None and n_exact == 0:
        sib = base.filter(parent_id=parent_inst.pk)
        sib_active = _mptt_qs_active(sib, model)
        n_children = sib_active.count()
        lines.append(f"  active_children_under_reached_parent={n_children}")
        if 0 < n_children <= 24:
            sample = list(sib_active.order_by("id").values_list("name", flat=True)[:12])
            lines.append(f"  sample_child_names={sample!r}")
        want = _normalize_path_segment(node_name)
        if want:
            n_norm = 0
            for nm in sib_active.order_by("id").values_list("name", flat=True).iterator(chunk_size=300):
                if _normalize_path_segment(nm or "") == want:
                    n_norm += 1
            lines.append(f"  children_matching_normalized_missing_name={n_norm}")

    if n_exact:
        lines.append("  sample_rows_with_that_name (id, parent_id, is_deleted, get_path):")
        for obj in exact.order_by("id")[:8]:
            try:
                gp = obj.get_path()
            except Exception as ex:
                gp = f"<get_path() failed: {ex!r}>"
            del_o = getattr(obj, "is_deleted", None)
            pid = getattr(obj, "parent_id", None)
            under = ""
            if parent_inst is not None:
                under = " under_reached_parent" if pid == parent_inst.pk else " WRONG_PARENT"
            lines.append(f"    id={obj.pk} parent_id={pid} is_deleted={del_o!r} path={gp!r}{under}")

    lines.append(
        "  hints: case-insensitive name per segment (trimmed) and normalized case-folded full-path "
        "match on rows sharing the deepest segment name (no whole-tree scan). Order the sheet "
        "parents-before-children when inserting both in one import; or enable "
        "mptt_path_create_missing_ancestors."
    )
    return "\n".join(lines)


def _resolve_parent_from_path_chain(
    model,
    chain: List[str],
    *,
    company_id: Optional[int] = None,
    create_missing: bool = False,
    row_for_defaults: Optional[Dict[str, Any]] = None,
    raw_row: Optional[Dict[str, Any]] = None,
    source_path_for_errors: Optional[str] = None,
    path_cache: Optional[Dict[Tuple[Any, str, Tuple[str, ...]], Any]] = None,
):
    """
    Resolve the MPTT instance for the path prefix ``chain`` (the parent path of the row being imported).

    Resolution order:
      1) Among nodes whose ``name`` matches the last path segment (case-insensitive), pick the one
         whose rendered path matches the full prefix (normalized; allows DB suffix when the chart has extra roots).
      2) Walk root-to-node with one small query per segment: ``parent`` + ``name__iexact`` (after strip).
      3) Optionally create missing intermediate nodes (``mptt_path_create_missing_ancestors``).

    ``source_path_for_errors``: original path cell from the row (shown in error messages for debugging).
    ``path_cache``: optional per-sheet memo ``{(company_id, model_name, path_tuple): parent_instance}``
    to avoid repeated expensive path resolution across many rows sharing the same prefix.
    """
    if not chain:
        return None

    cache_key: Optional[Tuple[Any, str, Tuple[str, ...]]] = None
    if path_cache is not None:
        cache_key = (company_id, model.__name__, tuple(chain))
        hit = path_cache.get(cache_key)
        if hit is not None:
            return hit

    inst = _find_mptt_node_matching_path_string(model, chain, company_id)
    if inst:
        if path_cache is not None and cache_key is not None:
            path_cache[cache_key] = inst
        return inst

    has_company = _model_has_concrete_field(model, "company")
    fd = dict(row_for_defaults or {})
    raw = dict(raw_row or {})
    parent = None

    for idx, node_name in enumerate(chain):
        row = _pick_mptt_child_by_name(
            model, node_name, parent, company_id, has_company, active_only=True
        )
        if not row and _model_has_concrete_field(model, "is_deleted"):
            row = _pick_mptt_child_by_name(
                model, node_name, parent, company_id, has_company, active_only=False
            )
        if not row:
            if not create_missing:
                missing = PATH_SEP.join(chain[: idx + 1])
                detail = _debug_mptt_parent_resolution_failure(
                    model,
                    chain,
                    company_id,
                    idx,
                    parent,
                    source_path_for_errors,
                )
                raise ValueError(
                    f"{model.__name__}: missing ancestor '{missing}'. Ensure parents exist under the correct "
                    f"parent chain, or set import_options mptt_path_create_missing_ancestors=true to auto-create "
                    f"intermediate nodes.\n{detail}"
                )
            row = _mptt_create_missing_ancestor(
                model, node_name, parent, company_id, fd, raw
            )
        parent = row
    if path_cache is not None and cache_key is not None:
        path_cache[cache_key] = parent
    return parent


def _allowed_keys(model) -> set:
    names = set()
    for f in model._meta.fields:
        names.add(f.name)
        att = getattr(f, "attname", None)
        if att:
            names.add(att)  # e.g. entity_id
    fk_aliases = {n + "_fk" for n in names}
    
    path_aliases = set()
    erp_id_aliases = set()
    for f in model._meta.fields:
        if isinstance(f, dj_models.ForeignKey):
            related_model = getattr(f, "related_model", None)
            if related_model and _is_mptt_model(related_model):
                base_name = f.name
                path_aliases.add(f"{base_name}_path")
                if related_model.__name__ == "Account":
                    path_aliases.add(f"{base_name}_code")
            if related_model and _model_has_erp_id(related_model):
                erp_id_aliases.add(f"{f.name}_erp_id")

    return (
        names | fk_aliases | path_aliases | erp_id_aliases
        | set(PATH_COLS)
        | {"__row_id", "__erp_id", "id", "company_fk"}
    )


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


def _resolve_path_to_id(model, field_name: str, path_value: str, company_id: int, path_separator: str = PATH_SEP, lookup_cache: Optional[Any] = None) -> Optional[int]:
    """
    Resolve a path value to an ID for a foreign key field.
    Supports Account and CostCenter (MPTT models) path lookups.
    
    Args:
        model: The model containing the FK field
        field_name: The FK field name (e.g., 'account', 'cost_center')
        path_value: The path string (e.g., 'Assets > Banks > Bradesco')
        company_id: Company ID for filtering
        path_separator: Path separator (default: ' > ')
        
    Returns:
        ID of the found record, or None if not found
    """
    if _is_missing(path_value):
        return None
    
    try:
        related_field = model._meta.get_field(field_name)
        related_model = getattr(related_field, "related_model", None)
        
        if not related_model:
            return None
        
        # Only support path lookups for MPTT models
        if not _is_mptt_model(related_model):
            return None
        
        # Use lookup cache if available (for Account model)
        if lookup_cache and related_model.__name__ == "Account":
            account = lookup_cache.get_account_by_path(path_value, path_separator)
            return account.id if account else None
        
        # Fallback to database query
        # Split path and traverse
        path_parts = _split_path(str(path_value).strip())
        if not path_parts:
            return None
        
        # Traverse the tree
        parent = None
        instance = None
        
        for part_name in path_parts:
            instance = related_model.objects.filter(
                company_id=company_id,
                name__iexact=part_name,
                parent=parent
            ).first()
            
            if not instance:
                return None
            
            parent = instance
        
        return instance.id if instance else None
        
    except Exception as e:
        logger.warning(f"Error resolving path '{path_value}' for field '{field_name}': {e}")
        return None


def _resolve_code_to_id(model, field_name: str, code_value: str, company_id: int, lookup_cache: Optional[Any] = None) -> Optional[int]:
    """
    Resolve a code value to an ID for a foreign key field.
    Currently supports Account code lookups.
    
    Args:
        model: The model containing the FK field
        field_name: The FK field name (e.g., 'account')
        code_value: The code string (e.g., '1.1.1.001')
        company_id: Company ID for filtering
        
    Returns:
        ID of the found record, or None if not found
    """
    if _is_missing(code_value):
        return None
    
    try:
        related_field = model._meta.get_field(field_name)
        related_model = getattr(related_field, "related_model", None)
        
        if not related_model:
            return None
        
        # Only support code lookups for Account model
        if related_model.__name__ != "Account":
            return None
        
        # Use lookup cache if available
        if lookup_cache:
            account = lookup_cache.get_account_by_code(code_value)
            return account.id if account else None
        
        # Fallback to database query
        instance = related_model.objects.filter(
            company_id=company_id,
            account_code__iexact=str(code_value).strip()
        ).first()
        
        return instance.id if instance else None
        
    except Exception as e:
        logger.warning(f"Error resolving code '{code_value}' for field '{field_name}': {e}")
        return None


def _apply_path_inputs(model, payload: dict, company_id: int, lookup_cache: Optional[Any] = None) -> dict:
    """
    Resolve '*_path' and '*_code' fields to '*_id' assignments.
    Similar to _apply_fk_inputs but for path/code-based lookups.
    
    Supports:
    - account_path -> account_id (for Account MPTT model)
    - cost_center_path -> cost_center_id (for CostCenter MPTT model)
    - account_code -> account_id (for Account model)
    """
    out = dict(payload)
    
    # Process *_path fields
    for k in list(out.keys()):
        if not k.endswith("_path"):
            continue
        
        base = k[:-5]  # Remove '_path' suffix
        path_value = out.pop(k, None)
        
        # Skip if already have *_id or if path is empty
        if f"{base}_id" in out and out[f"{base}_id"]:
            continue
        
        if _is_missing(path_value):
            continue
        
        # Resolve path to ID
        fk_id = _resolve_path_to_id(model, base, path_value, company_id, lookup_cache=lookup_cache)
        if fk_id:
            out[f"{base}_id"] = fk_id
        # Don't raise error if path not found - let validation handle it
    
    # Process *_code fields (for Account)
    for k in list(out.keys()):
        if not k.endswith("_code"):
            continue
        
        base = k[:-5]  # Remove '_code' suffix
        code_value = out.pop(k, None)
        
        # Skip if already have *_id or if code is empty
        if f"{base}_id" in out and out[f"{base}_id"]:
            continue
        
        if _is_missing(code_value):
            continue
        
        # Resolve code to ID
        fk_id = _resolve_code_to_id(model, base, code_value, company_id, lookup_cache=lookup_cache)
        if fk_id:
            out[f"{base}_id"] = fk_id
    
    return out


def _resolve_erp_id_to_fk_id(
    model,
    field_name: str,
    erp_id_value: str,
    company_id: Optional[int],
    lookup_cache: Optional[Any] = None,
) -> Optional[int]:
    """
    Resolve an external key string against ``related_model.erp_id`` and return the PK.

    ``field_name`` is the parent model's FK attribute (e.g. ``entity`` for ``entity_erp_id``).
    Company-scoped when the related model has a ``company_id`` field.
    """
    if _is_missing(erp_id_value):
        return None

    erp_val = str(erp_id_value).strip()
    if not erp_val:
        return None

    try:
        related_field = model._meta.get_field(field_name)
        related_model = getattr(related_field, "related_model", None)
        if not related_model or not _model_has_erp_id(related_model):
            return None

        if lookup_cache:
            cached = _lookup_cache_erp_id(lookup_cache, related_model, erp_val)
            if cached is not None:
                return cached

        qs = related_model.objects.filter(erp_id=erp_val)
        if company_id and any(
            getattr(f, "name", "") == "company" for f in related_model._meta.fields
        ):
            qs = qs.filter(company_id=company_id)
        obj = qs.first()
        if obj:
            return obj.pk

        raise ValueError(
            f"{related_model.__name__} with erp_id='{erp_val}' not found "
            f"for field '{field_name}'"
        )

    except ValueError:
        raise
    except Exception as e:
        logger.warning(
            "Error resolving erp_id '%s' for field '%s': %s", erp_val, field_name, e
        )
        return None


def _lookup_cache_erp_id(cache, related_model, erp_val: str) -> Optional[int]:
    """Try LookupCache for known model types; return None to fall through to DB."""
    name = related_model.__name__
    if name == "Account":
        obj = cache.get_account_by_erp_id(erp_val) if hasattr(cache, "get_account_by_erp_id") else None
        return obj.id if obj else None
    if name == "Entity":
        obj = cache.get_entity_by_erp_id(erp_val) if hasattr(cache, "get_entity_by_erp_id") else None
        return obj.id if obj else None
    if name == "Currency":
        obj = cache.get_currency_by_erp_id(erp_val) if hasattr(cache, "get_currency_by_erp_id") else None
        return obj.id if obj else None
    return None


def _apply_erp_id_inputs(
    model,
    payload: dict,
    company_id: Optional[int],
    lookup_cache: Optional[Any] = None,
) -> dict:
    """
    Resolve ``*_erp_id`` columns to ``*_id`` assignments by looking up
    ``erp_id`` on the related model.

    E.g. ``account_erp_id="ACC-001"`` → look up Account where
    ``erp_id="ACC-001"`` → set ``account_id=<pk>``.
    """
    out = dict(payload)
    for k in list(out.keys()):
        if not k.endswith("_erp_id"):
            continue
        # A real non-relation column named ``..._erp_id`` on this model must stay on the row
        # (do not treat it as a virtual FK input). Virtual inputs use ``<fk>_erp_id`` where
        # ``<fk>`` is a ForeignKey field on this model and there is no scalar column with that
        # exact name.
        try:
            direct_field = model._meta.get_field(k)
        except FieldDoesNotExist:
            direct_field = None
        if direct_field is not None and not direct_field.is_relation:
            continue

        base = k[: -len("_erp_id")]  # strip '_erp_id'
        erp_value = out.pop(k, None)

        if f"{base}_id" in out and out[f"{base}_id"]:
            continue
        if _is_missing(erp_value):
            continue

        fk_id = _resolve_erp_id_to_fk_id(
            model, base, erp_value, company_id, lookup_cache=lookup_cache
        )
        if fk_id:
            out[f"{base}_id"] = fk_id
    return out


def _resolve_row_by_erp_id(model, erp_id_value, company_id: Optional[int]):
    """
    Look up an existing row by ``erp_id`` on the *target* model
    (the model being imported, not a related model).

    Returns (instance, pk) or (None, None).
    """
    if _is_missing(erp_id_value):
        return None, None

    erp_val = str(erp_id_value).strip()
    if not erp_val:
        return None, None

    if not _model_has_erp_id(model):
        raise ValueError(
            f"Model {model.__name__} does not have an erp_id field; "
            f"cannot use __erp_id for row identification"
        )

    qs = model.objects.filter(erp_id=erp_val)
    if company_id and any(
        getattr(f, "name", "") == "company" for f in model._meta.fields
    ):
        qs = qs.filter(company_id=company_id)
    obj = qs.first()
    if obj:
        return obj, obj.pk
    return None, None


def _collect_transaction_erp_id_counts_for_sheet(
    rows: Optional[List[Dict[str, Any]]],
    sheet: Dict[str, Any],
    import_metadata: Optional[Dict[str, Any]],
    model,
) -> Tuple[Dict[str, int], Set[str]]:
    """
    Count import rows per erp_id (after __erp_id / erp_id coalescing). Used by ETL split imports.

    Ignores rows whose __row_id resolves to delete mode, delete-prefixed erp keys, and rows
    with erp resolution errors or missing erp_id.
    """
    counts: Dict[str, int] = {}
    sheet_opts = _merge_sheet_import_options(import_metadata, sheet)
    for row in rows or []:
        rc = dict(row or {})
        rid_raw = rc.pop("__row_id", None)
        popped_erp = rc.pop("__erp_id", None)
        erp_id_raw, erp_resolve_err = _resolve_row_erp_identifier(
            rc, popped_erp, model, sheet_opts
        )
        if erp_resolve_err:
            continue
        mode, _, _ = _parse_import_row_id(rid_raw)
        if mode == "delete":
            continue
        if _is_missing(erp_id_raw):
            continue
        erp_str = str(erp_id_raw).strip()
        if erp_str.startswith("-"):
            continue
        counts[erp_str] = counts.get(erp_str, 0) + 1
    return counts, set(counts.keys())


def _delete_transactions_for_erp_ids_replace_import(
    model,
    company_id: int,
    erp_ids: Set[str],
) -> int:
    """
    Remove existing Transactions for this company whose erp_id is in ``erp_ids`` (import delete semantics).

    Intended only for **split imports**: the same ``erp_id`` appears on multiple rows in one file, so
    existing DB rows for those keys must be cleared before creating multiple new transactions.
    Do not pass every key in the file for a normal one-row-per-erp_id re-import (use upsert instead).

    Journal entries cascade hard-delete with Transaction when is_deleted is not used; otherwise
    soft-delete follows the same collector rules as normal import deletes.
    """
    if not erp_ids:
        return 0
    removed = 0
    for erp_val in erp_ids:
        qs = model.objects.filter(company_id=company_id, erp_id=erp_val)
        for inst in list(qs):
            _assert_import_tenant_scope(inst, company_id)
            _apply_import_delete(inst, model)
            removed += 1
    if removed:
        logger.info(
            "import_erp_replace removed=%d transaction(s) across %d erp_id key(s) for company_id=%s",
            removed,
            len(erp_ids),
            company_id,
        )
    return removed


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


@shared_task(bind=True, name='import.run_import_job')
def run_import_job(self, company_id: int, sheets: List[Dict[str, Any]], commit: bool) -> Dict[str, Any]:
    """
    Legacy Celery task wrapper for import job.
    
    For new code, use process_import_template_task from etl_tasks.py which includes
    better statistics and error handling.
    """
    from .etl_tasks import process_import_template_task
    return process_import_template_task(
        company_id=company_id,
        sheets=sheets,
        commit=commit,
        file_meta=None
    )


def execute_import_job(
    company_id: int, 
    sheets: List[Dict[str, Any]], 
    commit: bool,
    import_metadata: Dict[str, Any] = None,
    lookup_cache: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Importer with token->id mapping for FK resolution and a single atomic transaction.

    __row_id semantics:
      - Alphanumeric token: create row; token is registered in token_to_id for *_fk on other sheets.
      - Positive integer: update row with that primary key (legacy: explicit id column also updates).
      - Negative integer: delete row with id abs(value); soft-delete if model has is_deleted.

    ERP row key (__erp_id vs erp_id):
      - By default (import_options.erp_key_coalesce=True), the dedicated ``__erp_id`` column and a mapped
        ``erp_id`` on the same row are interchangeable for upsert/delete-by-ERP-key (models that
        define ``erp_id``). If both are set, they must agree or the row errors.
      - import_options.erp_duplicate_behavior: ``update`` (default), ``skip``, or ``error`` when a match
        by ERP key is found.
      - Per-sheet options: pass ``import_options`` on each sheet dict, or under import_metadata.import_options.

    Flow:
      - Sort sheets using MODEL_APP_MAP order
      - For each row: substitutions -> filter -> company context -> MPTT path -> *_fk resolution to *_id
      - Save; register token->id only for new rows (alphanumeric __row_id)
      - On preview (commit=False): rollback entire transaction at the end
    
    Args:
        company_id: Company ID for the import
        sheets: List of sheet dictionaries with model and rows
        commit: Whether to commit (True) or preview (False)
        import_metadata: Optional metadata dict for notes (source, filename, function, etc.)
        lookup_cache: Optional LookupCache instance for efficient FK resolution (ETL context)
    """
    run_id = uuid.uuid4().hex[:8]
    logger.info("import_start run_id=%s commit=%s sheet_count=%d", run_id, bool(commit), len(sheets))
    
    # Default import metadata
    if import_metadata is None:
        import_metadata = {
            'source': 'Import',
            'function': 'execute_import_job'
        }

    # enforce sheet processing order using MODEL_APP_MAP key order
    model_order = {name: idx for idx, name in enumerate(MODEL_APP_MAP.keys())}
    sheets.sort(key=lambda s: model_order.get(s.get("model"), len(model_order)))
    logger.debug("sheet_order=%s", [s.get("model") for s in sheets])

    token_to_id: Dict[str, int] = {}  # GLOBAL token->id registry across all sheets
    outputs_by_model: Dict[str, List[dict]] = {}
    processed_substitution_rows: set = set()  # Track processed rows for commit substitutions
    substitution_cache: Dict[str, Dict[str, Dict[Any, Any]]] = {}  # Cache substitutions: {model_name: {field_name: {original: substituted}}}

    t0 = time.monotonic()
    with transaction.atomic():
        # One big atomic block; in preview, we'll mark rollback at the end
        for sheet in sheets:
            model_name = sheet.get("model")
            outputs_by_model.setdefault(model_name or "Unknown", [])
            
            # Get sheet-specific metadata (e.g., sheet_name from ETL)
            sheet_metadata = import_metadata.copy() if import_metadata else {}
            sheet_name = sheet.get("sheet_name")
            if sheet_name:
                sheet_metadata['sheet_name'] = sheet_name

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
            # Use a savepoint to isolate substitution queries from transaction errors
            try:
                sid = transaction.savepoint()
                try:
                    rows, audit = apply_substitutions(
                        raw_rows,
                        company_id=company_id,
                        model_name=model_name,
                        return_audit=True,
                        commit=commit,
                        processed_row_ids=processed_substitution_rows,
                        sheet_name=sheet_name,
                        substitution_cache=substitution_cache
                    )
                except Exception as e:
                    # Rollback the savepoint if substitution fails
                    transaction.savepoint_rollback(sid)
                    logger.exception(f"Error applying substitutions for {model_name}: {e}")
                    # Continue with raw rows if substitutions fail
                    rows = raw_rows
                    audit = []
            except Exception as e:
                # If savepoint creation fails (transaction already aborted), use raw rows
                logger.warning(f"Transaction in failed state, skipping substitutions for {model_name}: {e}")
                rows = raw_rows
                audit = []
            audit_by_rowid: Dict[Any, List[dict]] = {}
            for ch in (audit or []):
                key_norm = _norm_row_key(ch.get("__row_id"))
                audit_by_rowid.setdefault(key_norm, []).append(ch)

            logger.info("processing sheet '%s' rows=%d (after substitutions)", model_name, len(rows))

            sheet_import_options = _merge_sheet_import_options(import_metadata, sheet)

            # If MPTT and path present, sort parents first
            if _is_mptt_model(model):
                rows = sorted(rows, key=_path_depth)

            # Reuse resolved parent chains across rows (same prefix = one DB path walk).
            mptt_parent_path_cache: Dict[Tuple[Any, str, Tuple[str, ...]], Any] = {}

            for row in rows:
                raw = dict(row or {})
                rid_raw = raw.pop("__row_id", None)
                popped_erp = raw.pop("__erp_id", None)
                erp_id_raw, erp_resolve_err = _resolve_row_erp_identifier(
                    raw, popped_erp, model, sheet_import_options
                )
                if erp_resolve_err:
                    outputs_by_model[model_name].append({
                        "__row_id": rid_raw,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": erp_resolve_err,
                        "observations": [],
                        "external_id": None,
                    })
                    continue

                mode, row_detail, rid_display = _parse_import_row_id(rid_raw)
                rid = _norm_row_key(rid_display)

                dup_beh = str(sheet_import_options.get("erp_duplicate_behavior") or "update").lower()

                # __erp_id / coalesced erp_id: upsert by erp_id on the target model.
                # If an existing record is found → update (or skip/error per erp_duplicate_behavior).
                # Prefix with "-" to delete (e.g. __erp_id = "-ERP123" or erp_id = "-ERP123").
                if not _is_missing(erp_id_raw) and mode != "delete":
                    erp_str = str(erp_id_raw).strip()
                    if erp_str.startswith("-"):
                        erp_lookup = erp_str[1:]
                        existing, existing_pk = _resolve_row_by_erp_id(model, erp_lookup, company_id)
                        if not existing:
                            raise_msg = (
                                f"{model_name} with erp_id='{erp_lookup}' not found for delete"
                            )
                            outputs_by_model[model_name].append({
                                "__row_id": rid_display,
                                "status": "error",
                                "action": None,
                                "data": raw,
                                "message": raise_msg,
                                "observations": [],
                                "external_id": erp_lookup,
                            })
                            continue
                        mode = "delete"
                        row_detail = existing_pk
                    else:
                        existing, existing_pk = _resolve_row_by_erp_id(model, erp_str, company_id)
                        if existing:
                            if dup_beh == "error":
                                outputs_by_model[model_name].append({
                                    "__row_id": rid_display,
                                    "status": "error",
                                    "action": None,
                                    "data": raw,
                                    "message": (
                                        f"{model_name} already exists for ERP key erp_id="
                                        f"{erp_str!r} (erp_duplicate_behavior=error)"
                                    ),
                                    "observations": _row_observations(audit_by_rowid, rid),
                                    "external_id": erp_str,
                                })
                                continue
                            if dup_beh == "skip":
                                outputs_by_model[model_name].append({
                                    "__row_id": rid_display,
                                    "status": "success",
                                    "action": "skipped_duplicate",
                                    "data": {"id": existing_pk, "erp_id": erp_str},
                                    "message": (
                                        f"Skipped: {model_name} id={existing_pk} already has "
                                        f"erp_id={erp_str!r}"
                                    ),
                                    "observations": _row_observations(audit_by_rowid, rid),
                                    "external_id": erp_str,
                                })
                                continue
                            mode = "update"
                            row_detail = existing_pk
                            if rid_display is None:
                                rid_display = existing_pk
                                rid = _norm_row_key(rid_display)
                        # else: stays as create

                if mode == "error":
                    outputs_by_model[model_name].append({
                        "__row_id": rid_raw,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": str(row_detail),
                        "observations": [],
                        "external_id": None,
                    })
                    continue

                # Use a savepoint for each row to isolate errors
                row_sid = None
                try:
                    row_sid = transaction.savepoint()
                except Exception:
                    logger.warning(f"Transaction in failed state, skipping row {rid_display} in {model_name}")
                    outputs_by_model[model_name].append({
                        "__row_id": rid_display,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": "Transaction in failed state - previous error occurred",
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })
                    continue

                try:
                    # ---- delete (only needs pk from __row_id or __erp_id) ----
                    if mode == "delete":
                        pk_del = int(row_detail)
                        instance_del = model.objects.get(pk=pk_del)
                        _assert_import_tenant_scope(instance_del, company_id)
                        del_kind = _apply_import_delete(instance_del, model)
                        msg_del = f"deleted ({del_kind})"
                        outputs_by_model[model_name].append({
                            "__row_id": rid_display,
                            "status": "success",
                            "action": "delete",
                            "data": {"id": pk_del, "delete_mode": del_kind},
                            "message": msg_del,
                            "observations": _row_observations(audit_by_rowid, rid),
                            "external_id": None,
                        })
                        if row_sid:
                            transaction.savepoint_commit(row_sid)
                        continue

                    # 2) filter unknowns (keep *_fk)
                    filtered, unknown = _filter_unknown(model, raw)

                    # Legacy: explicit `id` column means update (same as positive numeric __row_id)
                    if mode == "create" and filtered.get("id"):
                        legacy_pk = _to_int_or_none_soft(filtered["id"])
                        if legacy_pk:
                            logger.info(
                                "import_legacy_id_column model=%s pk=%s (prefer numeric __row_id for updates)",
                                model_name,
                                legacy_pk,
                            )
                            mode = "update"
                            row_detail = legacy_pk

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
                                create_missing = bool(
                                    sheet_import_options.get("mptt_path_create_missing_ancestors", False)
                                )
                                row_company_id = _to_int_or_none_soft(filtered.get("company_id"))
                                parent = _resolve_parent_from_path_chain(
                                    model,
                                    parts[:-1],
                                    company_id=row_company_id,
                                    create_missing=create_missing,
                                    row_for_defaults=filtered,
                                    raw_row=raw,
                                    source_path_for_errors=path_val,
                                    path_cache=mptt_parent_path_cache,
                                )
                            filtered["name"] = filtered.get("name", leaf) or leaf
                            filtered["parent"] = parent
                            filtered.pop("parent_id", None)
                            filtered.pop("parent_fk", None)
                            for c in PATH_COLS:
                                filtered.pop(c, None)

                    # 5) Path resolution: *_path and *_code -> *_id (before FK resolution)
                    filtered = _apply_path_inputs(model, filtered, company_id, lookup_cache=lookup_cache)

                    # 5.5) ERP ID resolution: *_erp_id -> *_id (erp_id on related model)
                    filtered = _apply_erp_id_inputs(model, filtered, company_id, lookup_cache=lookup_cache)

                    # 6) FK application: *_fk -> *_id and rescue base tokens to *_id
                    filtered = _apply_fk_inputs(model, filtered, raw, token_to_id)

                    # 7) coercions
                    filtered = _coerce_boolean_fields(model, filtered)
                    filtered = _quantize_decimal_fields(model, filtered)

                    # 8) create/update (__row_id positive int or legacy id column)
                    action = "create"
                    create_token = row_detail if mode == "create" else None

                    if mode == "update":
                        pk = int(row_detail)
                        if "id" in filtered:
                            col_id = _to_int_or_none_soft(filtered["id"])
                            if col_id is not None and col_id != pk:
                                raise ValueError(
                                    f"id column ({col_id}) conflicts with __row_id update target ({pk})"
                                )
                        filtered.pop("id", None)
                        instance = model.objects.get(id=pk)
                        for k, v in filtered.items():
                            setattr(instance, k, v)
                        if hasattr(instance, "is_deleted"):
                            instance.is_deleted = False
                        action = "update"
                    else:
                        instance = model(**filtered)
                    
                    # 8.5) Add notes metadata if notes field exists and this is a new record
                    logger.info(f"IMPORT NOTES DEBUG: model={model_name}, action={action}, hasattr(instance, 'notes')={hasattr(instance, 'notes')}, import_metadata={import_metadata}")
                    if action == "create" and hasattr(instance, 'notes'):
                        # Import here to avoid circular import issues
                        try:
                            from multitenancy.utils import build_notes_metadata
                            from crum import get_current_user
                        except ImportError:
                            # Fallback: if import fails, create a simple notes string
                            from crum import get_current_user
                            def build_notes_metadata(source, function=None, filename=None, user=None, user_id=None, **kwargs):
                                parts = [f"Source: {source}"]
                                if function:
                                    parts.append(f"Function: {function}")
                                if filename:
                                    parts.append(f"File: {filename}")
                                if user:
                                    parts.append(f"User: {user}")
                                return " | ".join(parts)
                        
                        # Get current user for notes
                        current_user = get_current_user()
                        user_name = current_user.username if current_user and current_user.is_authenticated else None
                        user_id = current_user.id if current_user and current_user.is_authenticated else None
                        
                        # Build notes with metadata
                        notes_metadata = {
                            'source': import_metadata.get('source', 'Import') if import_metadata else 'Import',
                            'function': import_metadata.get('function', 'execute_import_job') if import_metadata else 'execute_import_job',
                            'user': user_name,
                            'user_id': user_id,
                        }
                        
                        # Add filename if available
                        if import_metadata and 'filename' in import_metadata:
                            notes_metadata['filename'] = import_metadata['filename']
                        
                        # Add sheet-specific metadata if available (use sheet_metadata which may have sheet_name)
                        if sheet_metadata:
                            if 'sheet_name' in sheet_metadata:
                                notes_metadata['sheet_name'] = sheet_metadata['sheet_name']
                            if 'log_id' in sheet_metadata:
                                notes_metadata['log_id'] = sheet_metadata['log_id']
                        # Also check import_metadata for log_id if not in sheet_metadata
                        if import_metadata and 'log_id' in import_metadata and 'log_id' not in notes_metadata:
                            notes_metadata['log_id'] = import_metadata['log_id']
                        
                        # Add Excel row metadata from raw data if available (these override sheet-level metadata)
                        excel_row_id = raw.get('__excel_row_id')
                        excel_row_number = raw.get('__excel_row_number')
                        excel_sheet_name = raw.get('__excel_sheet_name')
                        
                        if excel_row_id:
                            notes_metadata['excel_row_id'] = excel_row_id
                        if excel_row_number:
                            notes_metadata['row_number'] = excel_row_number
                        if excel_sheet_name:
                            notes_metadata['sheet_name'] = excel_sheet_name
                        
                        instance.notes = build_notes_metadata(**notes_metadata)
                        logger.info(f"IMPORT NOTES DEBUG: Set notes to: {instance.notes[:100] if instance.notes else 'None'}...")
                    else:
                        logger.warning(f"IMPORT NOTES DEBUG: NOT setting notes - action={action}, hasattr notes={hasattr(instance, 'notes')}")

                    # 9) validate & save
                    if hasattr(instance, "full_clean"):
                        instance.full_clean()
                    instance.save()  # assign PK now (even in preview; will rollback later)
                    # Verify notes were saved
                    logger.info(f"IMPORT NOTES DEBUG: After save, instance.notes = {instance.notes[:100] if instance.notes else 'None'}...")

                    # 10) register token->id only for addition rows (alphanumeric __row_id)
                    if create_token is not None:
                        token_to_id[create_token] = int(instance.pk)

                    # 11) success output
                    msg = "ok"
                    if unknown:
                        msg += f" | Ignoring unknown columns: {', '.join(unknown)}"

                    outputs_by_model[model_name].append({
                        "__row_id": rid_display,
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
                    # Commit the savepoint on success
                    if row_sid:
                        transaction.savepoint_commit(row_sid)

                except Exception as e:
                    # Check if this is a database error that would abort the transaction
                    from django.db import DatabaseError, IntegrityError
                    is_db_error = isinstance(e, (DatabaseError, IntegrityError))
                    
                    logger.exception("row error on %s rid=%s: %s (is_db_error=%s)", 
                                   model_name, rid_display, e, is_db_error)
                    
                    # Rollback the savepoint to isolate this error
                    if row_sid:
                        try:
                            transaction.savepoint_rollback(row_sid)
                        except Exception as rollback_err:
                            # If rollback fails, the transaction is likely already aborted
                            logger.warning(f"Failed to rollback savepoint for row {rid_display}: {rollback_err}")
                    
                    error_message = str(e)
                    if is_db_error:
                        error_message = f"Database error: {error_message}"
                    
                    outputs_by_model[model_name].append({
                        "__row_id": rid_display,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": error_message,
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

    # Trigger embedding generation for imported records (only if committed, not preview)
    if committed_flag:
        try:
            # Import here to avoid circular dependencies
            from accounting.tasks import generate_missing_embeddings
            
            logger.info(
                "import_end run_id=%s triggering generate_missing_embeddings task",
                run_id,
            )
            # Call asynchronously so it doesn't block the import response
            generate_missing_embeddings.delay()
        except Exception as e:
            # Don't fail the import if embedding generation fails
            logger.warning(
                "import_end run_id=%s failed to trigger embedding generation: %s",
                run_id,
                e,
            )

    return {
        "committed": committed_flag,
        "reason": (None if commit else "preview"),
        "imports": [
            {"model": m, "result": outputs_by_model.get(m, [])}
            for m in outputs_by_model.keys()
        ],
    }


