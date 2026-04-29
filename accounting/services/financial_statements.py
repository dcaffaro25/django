"""Pre-aggregated financial statements service.

The Demonstrativos page used to load every account in the chart
(~3MB on Evolat at prod-DB latency, 60-90s) just to sum 14 category
buckets client-side. This service does the same aggregation
server-side and returns a ~30KB payload that contains:

  * ``categories[]`` — per ``effective_category`` totals + drill-down
    accounts (drives DRE and Balanço Patrimonial tabs)
  * ``cashflow.by_category[]`` / ``cashflow.by_section`` — per
    ``effective_cashflow_category`` totals (drives DFC tab); reuses
    ``cashflow_service.compute_cashflow_direct`` so the proportional
    weighting and section resolution stay in one place.

The frontend then just renders — zero math, zero loading 356-row
account lists.

Sign convention matches the existing report stack:
  * Per-account JE deltas are sign-corrected by ``account_direction``
    (positive = balance increased).
  * Anchor balance (``Account.balance``) is included only on
    Balanço-side categories (asset / liability / PL); flow categories
    drop the anchor so opening figures don't pollute the period
    aggregate. The set of flow categories is duplicated from
    ``frontend/.../taxonomy_labels.ts`` -- when one changes, both must.
  * Both sums use ``effective_category`` (MPTT inheritance) so a leaf
    inherits its parent's category when it isn't explicitly set.

All amounts are emitted as Decimal-as-string per the rest of the
report stack.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from accounting.models import Account, JournalEntry
from accounting.services.cashflow_service import (
    compute_cashflow_direct,
    compute_cash_basis_book_deltas,
    _walk_taxonomy,
)
from accounting.services.report_cache import cached_payload
from accounting.services.taxonomy_meta import (
    REPORT_CATEGORY_META,
    CASHFLOW_CATEGORY_META,
)


# Categories that represent flow (income statement). Anchor balance
# must NOT be included for these — ``Account.balance`` is the lifetime
# opening figure, not a period flow. Mirror of
# ``taxonomy_labels.ts:FLOW_CATEGORIES``.
FLOW_CATEGORIES: frozenset[str] = frozenset({
    "receita_bruta",
    "deducao_receita",
    "custo",
    "despesa_operacional",
    "receita_financeira",
    "despesa_financeira",
    "outras_receitas",
    "imposto_sobre_lucro",
})


def _zero_decimal() -> Value:
    return Value(
        Decimal("0"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _net_expr():
    z = _zero_decimal()
    return Coalesce(F("debit_amount"), z) - Coalesce(F("credit_amount"), z)


def _accrual_per_account_deltas(
    company_id: int,
    *,
    date_from: Optional[str],
    date_to: Optional[str],
    entity_id: Optional[int],
    include_pending: bool,
    direction_by_id: Dict[int, int],
) -> Dict[int, Decimal]:
    """Sum ``debit - credit`` per account, sign-corrected by
    ``account_direction``. Mirrors the accrual-basis branch of
    ``AccountViewSet.get_serializer_context``: posted always, pending
    only when ``include_pending``. Date / entity filters narrow the
    JE base. Returns ``{account_id: signed_delta}``."""
    je_base = JournalEntry.objects.filter(account__company_id=company_id)
    if date_from is not None:
        je_base = je_base.filter(transaction__date__gte=date_from)
    if date_to is not None:
        je_base = je_base.filter(transaction__date__lte=date_to)
    if entity_id is not None:
        je_base = je_base.filter(transaction__entity_id=entity_id)

    states = ["posted", "pending"] if include_pending else ["posted"]
    je_base = je_base.filter(transaction__state__in=states)

    aggs = je_base.values("account_id").annotate(net=Sum(_net_expr()))

    out: Dict[int, Decimal] = {}
    for r in aggs:
        aid = r["account_id"]
        net = r["net"] or Decimal("0")
        if net == 0:
            continue
        direction = direction_by_id.get(aid) or 1
        out[aid] = net * direction
    return out


def compute_financial_statements(
    company_id: int,
    *,
    date_from=None,
    date_to=None,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
    basis: str = "accrual",
) -> dict:
    """Pre-aggregated DRE / Balanço / DFC payload for the
    Demonstrativos page.

    See module docstring for the input/output contract. Math:
        contribution(a) =
            (anchor(a) if leaf(a) and category(a) ∉ FLOW else 0)
          + own_flow(a)
        where own_flow(a) is per-account JE delta (accrual or
        cash-basis-weighted), sign-corrected by account_direction.
    """
    # ---- 1. Pull every account once (covers tree walks + aggregation) ----
    rows = list(
        Account.objects
        .filter(company_id=company_id)
        .values(
            "id", "name", "parent_id", "balance",
            "account_direction", "currency_id",
            "report_category", "tags", "cashflow_category",
        )
    )
    by_id = {r["id"]: r for r in rows}
    direction_by_id = {r["id"]: r["account_direction"] for r in rows}
    tax_map = _walk_taxonomy(rows)

    # leaf detection: an account is a leaf iff no other loaded row
    # claims it as parent. Anchor balance is only counted for leaves.
    parents_with_children: set = set()
    for r in rows:
        if r["parent_id"] is not None:
            parents_with_children.add(r["parent_id"])

    def is_leaf(aid: int) -> bool:
        return aid not in parents_with_children

    # ---- 2. Per-account JE deltas, by basis ----
    if basis == "cash" and date_from is not None and date_to is not None:
        # Cash basis: per-transaction weighted by bank-leg in-period
        # share (same logic the DRE cash toggle and DFC use).
        cash_map = compute_cash_basis_book_deltas(
            company_id, date_from, date_to,
            entity_id=entity_id,
            include_pending=include_pending,
        )
        # cash_map values are pre-formatted as ``{own_posted_delta,
        # own_pending_delta, own_unreconciled_delta}`` strings, ALREADY
        # sign-corrected. Reduce to a single signed Decimal per
        # account: posted + (pending if include_pending).
        deltas: Dict[int, Decimal] = {}
        for aid, bucket in cash_map.items():
            try:
                posted = Decimal(bucket.get("own_posted_delta") or "0")
            except Exception:
                posted = Decimal("0")
            pending = Decimal("0")
            if include_pending:
                try:
                    pending = Decimal(bucket.get("own_pending_delta") or "0")
                except Exception:
                    pending = Decimal("0")
            total = posted + pending
            if total != 0:
                deltas[aid] = total
    else:
        deltas = _accrual_per_account_deltas(
            company_id,
            date_from=date_from, date_to=date_to,
            entity_id=entity_id, include_pending=include_pending,
            direction_by_id=direction_by_id,
        )

    # ---- 3. Group by ``effective_category`` (drives DRE + Balanço) ----
    # Per-category bucket: amount + accounts list (sorted by abs amount).
    cat_buckets: Dict[str, dict] = {}
    for r in rows:
        aid = r["id"]
        eff_cat = (tax_map.get(aid) or {}).get("effective_category")
        if not eff_cat:
            continue
        own_flow = deltas.get(aid, Decimal("0"))
        # Anchor counted only at leaves AND only on Balanço categories.
        if is_leaf(aid) and eff_cat not in FLOW_CATEGORIES:
            anchor = Decimal(str(r.get("balance") or "0"))
        else:
            anchor = Decimal("0")
        contribution = anchor + own_flow
        if contribution == 0:
            continue
        bucket = cat_buckets.setdefault(eff_cat, {
            "key": eff_cat,
            "label": REPORT_CATEGORY_META.get(eff_cat, {}).get(
                "label_pt", eff_cat,
            ),
            "amount": Decimal("0"),
            "accounts": [],
        })
        bucket["amount"] += contribution
        bucket["accounts"].append({
            "id": aid,
            "name": r.get("name") or "",
            "amount": str(contribution),
        })

    # Sort accounts within each category by absolute amount, biggest
    # mover first. Sort categories by their CPC 26 display order.
    from accounting.services.taxonomy_meta import REPORT_CATEGORY_CHOICES
    cat_order = {code: i for i, (code, _) in enumerate(REPORT_CATEGORY_CHOICES)}
    categories = []
    for code in sorted(cat_buckets.keys(), key=lambda c: cat_order.get(c, 999)):
        b = cat_buckets[code]
        b["accounts"].sort(key=lambda x: -abs(Decimal(x["amount"])))
        b["account_count"] = len(b["accounts"])
        b["amount"] = str(b["amount"])
        categories.append(b)

    # ---- 4. Cashflow (delegated to existing service) ----
    cashflow_payload = None
    if date_from is not None and date_to is not None:
        try:
            cashflow_raw = compute_cashflow_direct(
                company_id,
                date_from=date_from,
                date_to=date_to,
                entity_id=entity_id,
                include_pending=include_pending,
            )
            # Rewrite by_category rows to attach pre-grouped accounts
            # (the cashflow service returns a flat by_account list; we
            # bucket it here so the frontend doesn't have to).
            accs_by_cf_cat: Dict[str, List[dict]] = defaultdict(list)
            for r in cashflow_raw.get("by_account", []):
                accs_by_cf_cat[r["category"]].append({
                    "id": r["account_id"],
                    "name": r["name"],
                    "amount": r["amount"],
                })
            cf_categories = []
            for cat_row in cashflow_raw.get("by_category", []):
                code = cat_row["category"]
                cf_categories.append({
                    "key": code,
                    "label": CASHFLOW_CATEGORY_META.get(code, {}).get(
                        "label_pt", code,
                    ),
                    "section": cat_row["section"],
                    "amount": cat_row["amount"],
                    "account_count": cat_row["account_count"],
                    "accounts": accs_by_cf_cat.get(code, []),
                })
            cashflow_payload = {
                "by_section": cashflow_raw.get("by_section", {}),
                "by_category": cf_categories,
            }
        except Exception:
            # Defensive: never let a DFC failure kill DRE/Balanço.
            cashflow_payload = None

    # ---- 5. Currency (most-common across accounts) ----
    currency_counts: Dict[int, int] = defaultdict(int)
    for r in rows:
        if r.get("currency_id"):
            currency_counts[r["currency_id"]] += 1
    primary_currency_id: Optional[int] = None
    if currency_counts:
        primary_currency_id = max(currency_counts.items(), key=lambda kv: kv[1])[0]
    primary_currency_code = "BRL"
    if primary_currency_id is not None:
        from accounting.models import Currency
        try:
            primary_currency_code = Currency.objects.values_list(
                "code", flat=True,
            ).get(id=primary_currency_id)
        except Exception:
            pass

    # ---- 6. Current cash balance (DFC tab "Saldo atual" KPI) ----
    # Sum of every leaf account whose effective_tags include ``cash``
    # or ``bank_account``. Anchor + own deltas, accrual, no date
    # filter -- this is the *current* position, independent of the
    # report period. Computing here lets the DFC tab skip a separate
    # accounts list fetch.
    cash_total = Decimal("0")
    if rows:
        cash_account_ids: set = set()
        for r in rows:
            tags = (tax_map.get(r["id"]) or {}).get("effective_tags") or []
            if "cash" in tags or "bank_account" in tags:
                if is_leaf(r["id"]):
                    cash_account_ids.add(r["id"])
        if cash_account_ids:
            # Pull lifetime accrual deltas for cash accounts -- ignore
            # date / entity filters here; this is a snapshot.
            lifetime = (
                JournalEntry.objects
                .filter(
                    account_id__in=list(cash_account_ids),
                    transaction__state="posted",
                )
                .values("account_id")
                .annotate(net=Sum(_net_expr()))
            )
            lifetime_by_acc = {r["account_id"]: r["net"] or Decimal("0") for r in lifetime}
            for aid in cash_account_ids:
                row = by_id.get(aid)
                if not row:
                    continue
                anchor = Decimal(str(row.get("balance") or "0"))
                direction = direction_by_id.get(aid) or 1
                delta = lifetime_by_acc.get(aid, Decimal("0")) * direction
                cash_total += anchor + delta

    return {
        "currency": primary_currency_code,
        "period": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "include_pending": include_pending,
        "basis": basis,
        "entity_id": entity_id,
        "categories": categories,
        "cashflow": cashflow_payload,
        "cash_total": str(cash_total),
    }


def compute_financial_statements_cached(
    company_id: int,
    *,
    date_from=None,
    date_to=None,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
    basis: str = "accrual",
    bypass_cache: bool = False,
) -> dict:
    """Cached wrapper around ``compute_financial_statements``.

    Cache key includes the tenant data version (see
    ``report_cache.data_version``); a write to any
    ``JournalEntry`` / ``Transaction`` / ``Account`` row in the
    tenant moves the version, so the next read rebuilds with
    fresh numbers. ``bypass_cache=True`` short-circuits to a
    direct rebuild for debug / ?nocache=1.

    The cached payload is the same dict shape as the underlying
    function -- callers can drop this in wherever they currently
    call ``compute_financial_statements`` directly.
    """
    key_parts = {
        "df": date_from.isoformat() if date_from else None,
        "dt": date_to.isoformat() if date_to else None,
        "ent": entity_id,
        "ip": bool(include_pending),
        "basis": basis,
    }

    def _build():
        return compute_financial_statements(
            company_id,
            date_from=date_from,
            date_to=date_to,
            entity_id=entity_id,
            include_pending=include_pending,
            basis=basis,
        )

    return cached_payload(
        "fs:v1", company_id, key_parts, _build, bypass=bypass_cache,
    )
