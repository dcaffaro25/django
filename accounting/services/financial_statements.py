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

Balanço (non-FLOW) category math is anchor-aware: closing balance at
``date_to`` = ``Account.balance`` + Σ JE deltas where
``transaction.date > Account.balance_date AND <= date_to``. ``date_from``
is intentionally ignored for Balanço categories — a snapshot has no
"start" and applying ``date_from`` would either skip pre-window flow
already-not-in-anchor or double-count flow already baked into anchor.
DRE/DFC categories (FLOW_CATEGORIES) keep the [date_from, date_to]
window because they're flow lines, not snapshots.

Optional features (off by default; back-compat shape unchanged):

  * ``series=month|quarter|semester|year`` — break the requested
    range into sub-periods, return a ``series.periods[]`` sibling
    with per-bucket totals per sub-period. Drives the per-period
    columns in the Demonstrativos tabs.
  * ``compare=previous_period|previous_year`` — add a ``comparison``
    sibling with the same per-bucket totals computed for the
    comparison window. Drives the Δ% / Δ-abs deltas in the UI.

Both features carry only totals (no per-account drill-down) to keep
the payload light and avoid an N×accounts blow-up.

All amounts are emitted as Decimal-as-string per the rest of the
report stack.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as _date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
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


# Maximum number of sub-periods we'll generate per series request.
# Keeps a malformed request (daily over five years) from triggering an
# expensive multi-thousand-window expansion. 36 covers monthly over
# three years which is the realistic upper bound for an operator UI.
_SERIES_MAX_PERIODS = 36

_SUPPORTED_SERIES = frozenset({"month", "quarter", "semester", "year"})
_SUPPORTED_COMPARE = frozenset({"previous_period", "previous_year"})


def _zero_decimal() -> Value:
    return Value(
        Decimal("0"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _net_expr():
    z = _zero_decimal()
    return Coalesce(F("debit_amount"), z) - Coalesce(F("credit_amount"), z)


# ---------------------------------------------------------------------
# Per-account JE delta builders
# ---------------------------------------------------------------------


def _accrual_flow_deltas(
    company_id: int,
    *,
    date_from: Optional[_date],
    date_to: Optional[_date],
    entity_id: Optional[int],
    include_pending: bool,
    direction_by_id: Dict[int, int],
) -> Dict[int, Decimal]:
    """Sum signed JE deltas in [date_from, date_to] — flow window. Used
    for FLOW_CATEGORIES (DRE/DFC) where the line is a period activity,
    not a balance snapshot. ``include_pending`` widens the state filter."""
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


def _accrual_post_anchor_deltas(
    company_id: int,
    *,
    date_to: _date,
    entity_id: Optional[int],
    include_pending: bool,
    direction_by_id: Dict[int, int],
) -> Dict[int, Decimal]:
    """Sum signed JE deltas where ``transaction.date > Account.balance_date
    AND <= date_to``. Used for Balanço (non-FLOW) categories where the
    line is a closing balance snapshot. The result is added to
    ``Account.balance`` to recover the closing balance at ``date_to``.

    Why anchor-aware: ``Account.balance`` is the snapshot at
    ``Account.balance_date`` (set by the close-period workflow), so any
    JE on or before ``balance_date`` is already baked in. Filtering by
    ``date_from`` instead — as the legacy single-window code did — was
    correct only when ``date_from = balance_date + 1``; it double-counts
    or skips flow otherwise (the bug surfacing the user's "wrong
    numbers" report). Posted entries respect the anchor; pending entries
    are NOT yet baked into the anchor and therefore use a pure
    ``transaction.date <= date_to`` filter. We compute both legs and
    union them per-account.
    """
    out: Dict[int, Decimal] = {}

    # Posted leg: anchor-aware via correlated subquery on
    # Account.balance_date — same shape the legacy CoA delta builder
    # uses, single GROUP BY of only the post-anchor rows.
    anchor_sq = Subquery(
        Account.objects.filter(pk=OuterRef("account_id"))
        .values("balance_date")[:1]
    )
    posted_qs = (
        JournalEntry.objects
        .filter(account__company_id=company_id)
        .filter(transaction__state="posted", transaction__date__lte=date_to)
        .annotate(_anchor_date=anchor_sq)
        .filter(transaction__date__gt=F("_anchor_date"))
    )
    if entity_id is not None:
        posted_qs = posted_qs.filter(transaction__entity_id=entity_id)
    posted_aggs = posted_qs.values("account_id").annotate(net=Sum(_net_expr()))
    for r in posted_aggs:
        aid = r["account_id"]
        net = r["net"] or Decimal("0")
        if net == 0:
            continue
        out[aid] = (out.get(aid) or Decimal("0")) + net * (
            direction_by_id.get(aid) or 1
        )

    if include_pending:
        # Pending leg: not yet baked into anchor, so the anchor filter
        # would wrongly drop legitimate pending JEs whose date sits at
        # or before balance_date. Use a pure ``date <= date_to`` window.
        pending_qs = (
            JournalEntry.objects
            .filter(account__company_id=company_id)
            .filter(transaction__state="pending", transaction__date__lte=date_to)
        )
        if entity_id is not None:
            pending_qs = pending_qs.filter(transaction__entity_id=entity_id)
        pending_aggs = pending_qs.values("account_id").annotate(net=Sum(_net_expr()))
        for r in pending_aggs:
            aid = r["account_id"]
            net = r["net"] or Decimal("0")
            if net == 0:
                continue
            out[aid] = (out.get(aid) or Decimal("0")) + net * (
                direction_by_id.get(aid) or 1
            )

    return out


def _cash_basis_flow_deltas(
    company_id: int,
    *,
    date_from: _date,
    date_to: _date,
    entity_id: Optional[int],
    include_pending: bool,
) -> Dict[int, Decimal]:
    """Per-account flow under the cash basis. Wraps
    ``compute_cash_basis_book_deltas`` and reduces its
    ``{posted, pending, unrec}`` triplet to a single signed Decimal."""
    cash_map = compute_cash_basis_book_deltas(
        company_id, date_from, date_to,
        entity_id=entity_id, include_pending=include_pending,
    )
    out: Dict[int, Decimal] = {}
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
            out[aid] = total
    return out


# ---------------------------------------------------------------------
# Window aggregation (categories + cashflow + cash KPI)
# ---------------------------------------------------------------------


def _category_buckets_for_window(
    *,
    rows: List[dict],
    by_id: Dict[int, dict],
    direction_by_id: Dict[int, int],
    tax_map: Dict[int, dict],
    parents_with_children: set,
    company_id: int,
    date_from: Optional[_date],
    date_to: Optional[_date],
    entity_id: Optional[int],
    include_pending: bool,
    basis: str,
    include_accounts: bool,
) -> Tuple[List[dict], Dict[str, Decimal]]:
    """Build the per-category list (DRE + Balanço) for one window.

    Returns ``(categories_list, totals_by_key)``. ``include_accounts``
    controls whether each category carries its drill-down list — the
    main window includes them (the UI drills); series and comparison
    windows omit them to keep the payload light.

    For FLOW categories (DRE/DFC): per-account delta is the
    ``[date_from, date_to]`` flow, possibly cash-basis-weighted. No
    anchor.
    For non-FLOW categories (Balanço): closing balance at ``date_to``
    via ``anchor + post-anchor flow``. ``date_from`` is intentionally
    ignored here. (Cash basis on Balanço falls back to the same
    closing-balance logic — cash basis doesn't change a Balanço
    snapshot's meaning.)
    """
    def is_leaf(aid: int) -> bool:
        return aid not in parents_with_children

    # ---- Flow deltas (DRE / DFC) ----
    if basis == "cash" and date_from is not None and date_to is not None:
        flow_deltas = _cash_basis_flow_deltas(
            company_id,
            date_from=date_from, date_to=date_to,
            entity_id=entity_id, include_pending=include_pending,
        )
    else:
        flow_deltas = _accrual_flow_deltas(
            company_id,
            date_from=date_from, date_to=date_to,
            entity_id=entity_id, include_pending=include_pending,
            direction_by_id=direction_by_id,
        )

    # ---- Anchor + post-anchor deltas (Balanço) ----
    # Only compute when there's at least one non-FLOW category in play
    # AND we have a ``date_to`` to anchor the snapshot. Without
    # ``date_to`` (rare; happens when both date params are missing)
    # there's no closing-balance window — fall back to anchor-only.
    closing_deltas: Dict[int, Decimal] = {}
    if date_to is not None:
        closing_deltas = _accrual_post_anchor_deltas(
            company_id,
            date_to=date_to,
            entity_id=entity_id, include_pending=include_pending,
            direction_by_id=direction_by_id,
        )

    cat_buckets: Dict[str, dict] = {}
    for r in rows:
        aid = r["id"]
        eff_cat = (tax_map.get(aid) or {}).get("effective_category")
        if not eff_cat:
            continue

        if eff_cat in FLOW_CATEGORIES:
            contribution = flow_deltas.get(aid, Decimal("0"))
        else:
            # Balanço closing = anchor (at leaf only) + post-anchor flow
            anchor = (
                Decimal(str(r.get("balance") or "0"))
                if is_leaf(aid) else Decimal("0")
            )
            contribution = anchor + closing_deltas.get(aid, Decimal("0"))

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
        if include_accounts:
            bucket["accounts"].append({
                "id": aid,
                "name": r.get("name") or "",
                "amount": str(contribution),
            })

    # ---- Synthetic "Resultado do Exercício (período)" line ----
    # Standard accounting: at year-end a closing JE moves the net DRE
    # result into Patrimônio Líquido. During the period the result
    # conceptually already lives in PL but technically sits in
    # temporary DRE accounts. Without this synthetic line, Balanço
    # can't balance during the period because the cash legs of
    # revenue/expense JEs have hit Ativo / Passivo accounts but no
    # JE has yet credited PL.
    #
    # We compute Lucro Líquido from the FLOW buckets we already
    # populated (no extra DB roundtrip) using the same DRE math the
    # frontend applies, then add it to ``patrimonio_liquido`` — both
    # the bucket total and a synthetic drill-down row tagged
    # ``synthetic=True`` so the frontend can render it without
    # offering a JE drill / wiring edit (id=-1 isn't a real account).
    def _bucket_amount(code: str) -> Decimal:
        return (cat_buckets.get(code) or {}).get("amount") or Decimal("0")

    lucro_liquido = (
        _bucket_amount("receita_bruta") + _bucket_amount("deducao_receita")
        - _bucket_amount("custo") - _bucket_amount("despesa_operacional")
        + _bucket_amount("receita_financeira") - _bucket_amount("despesa_financeira")
        + _bucket_amount("outras_receitas")
        - _bucket_amount("imposto_sobre_lucro")
    )
    if lucro_liquido != 0:
        pl_bucket = cat_buckets.setdefault("patrimonio_liquido", {
            "key": "patrimonio_liquido",
            "label": REPORT_CATEGORY_META.get("patrimonio_liquido", {}).get(
                "label_pt", "Patrimônio Líquido",
            ),
            "amount": Decimal("0"),
            "accounts": [],
        })
        pl_bucket["amount"] += lucro_liquido
        if include_accounts:
            pl_bucket["accounts"].append({
                # Negative id flags this row as synthetic — there's no
                # real Account row behind it. Frontend keys on the
                # ``synthetic`` flag (id is just a unique-key fallback).
                "id": -1,
                "name": "Resultado do Exercício (período)",
                "amount": str(lucro_liquido),
                "synthetic": True,
            })

    from accounting.services.taxonomy_meta import REPORT_CATEGORY_CHOICES
    cat_order = {code: i for i, (code, _) in enumerate(REPORT_CATEGORY_CHOICES)}
    categories = []
    totals_by_key: Dict[str, Decimal] = {}
    for code in sorted(cat_buckets.keys(), key=lambda c: cat_order.get(c, 999)):
        b = cat_buckets[code]
        if include_accounts:
            b["accounts"].sort(key=lambda x: -abs(Decimal(x["amount"])))
            b["account_count"] = len(b["accounts"])
        else:
            # ``account_count`` still useful for the UI even without
            # the accounts list; cheap to derive from the deltas we
            # already walked above.
            b["account_count"] = sum(
                1 for r in rows
                if (tax_map.get(r["id"]) or {}).get("effective_category") == code
            )
            del b["accounts"]
        totals_by_key[code] = b["amount"]
        b["amount"] = str(b["amount"])
        categories.append(b)

    return categories, totals_by_key


def _cashflow_for_window(
    *,
    company_id: int,
    date_from: Optional[_date],
    date_to: Optional[_date],
    entity_id: Optional[int],
    include_pending: bool,
    include_accounts: bool,
) -> Optional[dict]:
    """Wrap ``compute_cashflow_direct`` and re-bucket the per-account
    rows under each category. Returns ``None`` when the window doesn't
    have both bounds (DFC requires a date range).

    ``include_accounts=False`` strips the accounts list from each
    category — used for series sub-periods so a 12-month payload stays
    small.
    """
    if date_from is None or date_to is None:
        return None
    try:
        cashflow_raw = compute_cashflow_direct(
            company_id,
            date_from=date_from, date_to=date_to,
            entity_id=entity_id, include_pending=include_pending,
        )
    except Exception:
        # Defensive: never let DFC failure kill the payload.
        return None

    accs_by_cf_cat: Dict[str, List[dict]] = defaultdict(list)
    if include_accounts:
        for r in cashflow_raw.get("by_account", []):
            accs_by_cf_cat[r["category"]].append({
                "id": r["account_id"],
                "name": r["name"],
                "amount": r["amount"],
            })

    cf_categories = []
    for cat_row in cashflow_raw.get("by_category", []):
        code = cat_row["category"]
        entry = {
            "key": code,
            "label": CASHFLOW_CATEGORY_META.get(code, {}).get(
                "label_pt", code,
            ),
            "section": cat_row["section"],
            "amount": cat_row["amount"],
            "account_count": cat_row["account_count"],
        }
        if include_accounts:
            entry["accounts"] = accs_by_cf_cat.get(code, [])
        cf_categories.append(entry)

    return {
        "by_section": cashflow_raw.get("by_section", {}),
        "by_category": cf_categories,
    }


def _cash_total_snapshot(
    *,
    company_id: int,
    rows: List[dict],
    by_id: Dict[int, dict],
    tax_map: Dict[int, dict],
    parents_with_children: set,
    direction_by_id: Dict[int, int],
) -> Decimal:
    """Current cash position: sum of leaf cash/bank accounts at full
    lifetime accrual. Independent of date / entity scope so the DFC tab
    can render "Saldo atual" without a separate accounts list fetch.
    """
    cash_account_ids: set = set()
    for r in rows:
        aid = r["id"]
        if aid in parents_with_children:
            continue  # leaves only
        tags = (tax_map.get(aid) or {}).get("effective_tags") or []
        if "cash" in tags or "bank_account" in tags:
            cash_account_ids.add(aid)

    if not cash_account_ids:
        return Decimal("0")

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

    total = Decimal("0")
    for aid in cash_account_ids:
        row = by_id.get(aid)
        if not row:
            continue
        anchor = Decimal(str(row.get("balance") or "0"))
        direction = direction_by_id.get(aid) or 1
        delta = lifetime_by_acc.get(aid, Decimal("0")) * direction
        total += anchor + delta
    return total


# ---------------------------------------------------------------------
# Series + compare window helpers
# ---------------------------------------------------------------------


def _series_periods(
    date_from: _date, date_to: _date, granularity: str,
) -> List[dict]:
    """Generate sub-periods using the existing time-dimensions util,
    capped to ``_SERIES_MAX_PERIODS``. Returns dicts shaped for the
    frontend: ``{key, label, date_from, date_to}``."""
    from accounting.utils_time_dimensions import (
        generate_periods,
        format_period_label,
    )
    raw = generate_periods(date_from, date_to, granularity)
    raw = raw[:_SERIES_MAX_PERIODS]
    out = []
    for p in raw:
        out.append({
            "key": p["key"],
            "label": _format_period_label_pt(p["start_date"], granularity),
            "date_from": p["start_date"].isoformat(),
            "date_to": p["end_date"].isoformat(),
        })
    return out


def _format_period_label_pt(d: _date, granularity: str) -> str:
    """Brazilian-style short labels (Jan/25, T1/25, S1/25, 2025) so the
    column headers fit in narrow grid cells."""
    yy = str(d.year)[2:]
    if granularity == "month":
        months = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        return f"{months[d.month-1]}/{yy}"
    if granularity == "quarter":
        q = (d.month - 1) // 3 + 1
        return f"T{q}/{yy}"
    if granularity == "semester":
        s = 1 if d.month <= 6 else 2
        return f"S{s}/{yy}"
    if granularity == "year":
        return str(d.year)
    return d.isoformat()


def _compare_window(
    *,
    date_from: _date, date_to: _date, compare: str,
) -> Optional[Tuple[_date, _date, str]]:
    """Resolve the comparison window and a human label. Returns
    ``None`` if the comparison type is unsupported or dates are missing."""
    if compare not in _SUPPORTED_COMPARE:
        return None
    from accounting.utils_time_dimensions import get_comparison_period
    try:
        cmp_from, cmp_to = get_comparison_period(date_from, date_to, compare)
    except Exception:
        return None
    label = "Período anterior" if compare == "previous_period" else "Mesmo período do ano anterior"
    return cmp_from, cmp_to, label


# ---------------------------------------------------------------------
# Balance diagnostics
# ---------------------------------------------------------------------
#
# Surfaces the *cause* of an unbalanced Balanço so the operator can
# act, rather than just see "diferença de R$ X". From the audit on
# Evolat we learned that the residual after the synthetic
# ``Resultado do Exercício`` line decomposes into three buckets:
#
#   1. Anchor gap — ``Account.balance`` set on Ativo leaves but never
#      on Passivo/PL leaves (opening balances were only recorded on
#      one side). Pure data-entry; no engineering fix.
#   2. Uncategorized leaf accounts with non-zero JE flow — JEs hit
#      these accounts but they have no ``effective_category``, so
#      they're silently dropped from the report. Their counter-legs
#      DO land in a category, creating a one-sided contribution.
#      Fix is one click in the wiring modal.
#   3. Wrong-direction leaves under Passivo / PL — accounts whose
#      ``account_direction`` doesn't match the credit-natural
#      convention. Sign-correction inverts; report total looks zero
#      or negative when it shouldn't. ``(-)`` contra-accounts are an
#      intentional exception and excluded from this list.
#
# We compute these once per main-window invocation and emit them as
# ``balance_diagnostics`` on the payload. The frontend uses them to
# render an actionable panel inline with the imbalance banner.


_PASSIVO_PL_KEYS = frozenset({
    "passivo_circulante", "passivo_nao_circulante", "patrimonio_liquido",
})
_ATIVO_KEYS = frozenset({"ativo_circulante", "ativo_nao_circulante"})


def _suggest_category_for_uncategorized(
    *, name: str, direction: int, tags: List[str],
) -> Optional[str]:
    """Cheap heuristic that picks a likely ``report_category`` for an
    uncategorized leaf. Used only for the operator-facing suggestion;
    the wiring modal still requires the operator to confirm. We err
    toward Ativo Circulante because that's where most uncategorized
    operational leaves land in practice (clearing accounts, suspense
    accounts, in-transit cash).
    """
    nm = (name or "").lower()
    tag_set = {t.lower() for t in (tags or [])}

    # Cash / bank tags are unambiguous.
    if "cash" in tag_set or "bank_account" in tag_set or "cash_equivalent" in tag_set:
        return "ativo_circulante"
    # Common Brazilian patterns by name.
    if "clearing" in nm or "trânsito" in nm or "transito" in nm or "pending" in nm:
        return "ativo_circulante"
    if " a recolher" in nm or " a pagar" in nm or "fornecedores" in nm or "empréstimos" in nm:
        return "passivo_circulante"
    if " a recuperar" in nm or " a receber" in nm:
        return "ativo_circulante"
    if "capital" in nm or "reserva" in nm or "lucros acumulados" in nm or "prejuízos" in nm:
        return "patrimonio_liquido"
    # Fall back to direction alone: debit-natural → ativo_circulante,
    # credit-natural → passivo_circulante. Operator can override.
    if direction == 1:
        return "ativo_circulante"
    if direction == -1:
        return "passivo_circulante"
    return None


def _category_label(code: str) -> str:
    return REPORT_CATEGORY_META.get(code, {}).get("label_pt", code)


def _compute_balance_diagnostics(
    *,
    rows: List[dict],
    by_id: Dict[int, dict],
    direction_by_id: Dict[int, int],
    tax_map: Dict[int, dict],
    parents_with_children: set,
    company_id: int,
    date_from: Optional[_date],
    date_to: Optional[_date],
    entity_id: Optional[int],
    include_pending: bool,
    main_totals: Dict[str, Decimal],
    synthetic_lucro: Decimal,
) -> Optional[dict]:
    """Build the diagnostics payload. Returns ``None`` when there's no
    Balanço imbalance to explain (Ativo == Passivo + PL within 1¢)."""
    total_ativo = sum(
        (main_totals.get(k) or Decimal("0")) for k in _ATIVO_KEYS
    )
    total_pas_pl = sum(
        (main_totals.get(k) or Decimal("0")) for k in _PASSIVO_PL_KEYS
    )
    imbalance = total_ativo - total_pas_pl
    # 1¢ tolerance covers float-aggregation drift; below it we don't
    # bother building the diagnostics block.
    if abs(imbalance) < Decimal("0.01"):
        return None

    def is_leaf(aid: int) -> bool:
        return aid not in parents_with_children

    # ---- 1) Anchor gap (leaf balances on Ativo vs Passivo+PL) ----
    ativo_anchor = Decimal("0")
    pas_pl_anchor = Decimal("0")
    for r in rows:
        aid = r["id"]
        if not is_leaf(aid):
            continue
        eff_cat = (tax_map.get(aid) or {}).get("effective_category")
        if not eff_cat:
            continue
        bal = Decimal(str(r.get("balance") or "0"))
        if eff_cat in _ATIVO_KEYS:
            ativo_anchor += bal
        elif eff_cat in _PASSIVO_PL_KEYS:
            pas_pl_anchor += bal
    anchor_gap = ativo_anchor - pas_pl_anchor

    # ---- 2) Uncategorized leaf accounts with non-zero impact ----
    # Use the same flow window the main report uses so the impact
    # numbers shown to the operator match what they'd see if the
    # account WERE categorized.
    flow_deltas = _accrual_flow_deltas(
        company_id,
        date_from=date_from, date_to=date_to,
        entity_id=entity_id, include_pending=include_pending,
        direction_by_id=direction_by_id,
    )
    uncat_rows: List[dict] = []
    for r in rows:
        aid = r["id"]
        if not is_leaf(aid):
            continue
        eff_cat = (tax_map.get(aid) or {}).get("effective_category")
        if eff_cat:
            continue
        bal = Decimal(str(r.get("balance") or "0"))
        flow = flow_deltas.get(aid, Decimal("0"))
        impact = bal + flow
        if abs(impact) < Decimal("0.01"):
            continue
        eff_tags = (tax_map.get(aid) or {}).get("effective_tags") or []
        suggestion = _suggest_category_for_uncategorized(
            name=r.get("name") or "",
            direction=direction_by_id.get(aid) or 1,
            tags=eff_tags,
        )
        uncat_rows.append({
            "id": aid,
            "name": r.get("name") or "",
            "anchor": str(bal),
            "flow": str(flow),
            "impact": str(impact),
            "suggested_category": suggestion,
            "suggested_label": _category_label(suggestion) if suggestion else None,
        })
    # Largest absolute impact first — drives the "fix this first" UX.
    uncat_rows.sort(key=lambda x: -abs(Decimal(x["impact"])))

    # ---- 3) Wrong-direction Passivo/PL leaves ----
    # Credit-natural categories should have direction=-1. Exception:
    # contra-accounts (name starts with ``(-)``) are intentionally
    # debit-natural, so skip those.
    wrong_dir: List[dict] = []
    for r in rows:
        aid = r["id"]
        if not is_leaf(aid):
            continue
        eff_cat = (tax_map.get(aid) or {}).get("effective_category")
        if eff_cat not in _PASSIVO_PL_KEYS:
            continue
        if (direction_by_id.get(aid) or 1) != 1:
            continue  # already credit-natural, fine
        nm = (r.get("name") or "").lstrip()
        if nm.startswith("(-)"):
            continue  # contra-account, +1 is intentional
        wrong_dir.append({
            "id": aid,
            "name": r.get("name") or "",
            "current_category": eff_cat,
            "current_direction": 1,
            "suggested_direction": -1,
        })

    # ---- 4) Roll-up summary ----
    # Note: we don't enumerate every contribution path because the
    # uncategorized impact and anchor gap can interact non-trivially
    # (an uncategorized account paired with DRE legs reduces the
    # observed gap; paired with Balanço legs widens it). We just
    # report the raw components and the residual; the frontend frames
    # the narrative.
    uncat_total = sum((Decimal(r["impact"]) for r in uncat_rows), Decimal("0"))

    return {
        "total_ativo": str(total_ativo),
        "total_passivo_pl": str(total_pas_pl),
        "synthetic_lucro": str(synthetic_lucro),
        "imbalance": str(imbalance),
        "anchor_gap": {
            "ativo_anchor": str(ativo_anchor),
            "pas_pl_anchor": str(pas_pl_anchor),
            "delta": str(anchor_gap),
        },
        "uncategorized_leaves": uncat_rows,
        "uncategorized_total_impact": str(uncat_total),
        "wrong_direction_accounts": wrong_dir,
    }


# ---------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------


def compute_financial_statements(
    company_id: int,
    *,
    date_from=None,
    date_to=None,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
    basis: str = "accrual",
    series: Optional[str] = None,
    compare: Optional[str] = None,
) -> dict:
    """Pre-aggregated DRE / Balanço / DFC payload for the
    Demonstrativos page.

    Math contract:
        FLOW_CATEGORIES (DRE/DFC):
            contribution(a) = flow_delta(a, date_from, date_to)
        non-FLOW (Balanço):
            contribution(a) = anchor(a) + post_anchor_delta(a, date_to)
                where post_anchor uses ``transaction.date > balance_date
                AND <= date_to`` for posted, ``date <= date_to`` for
                pending. ``date_from`` is intentionally ignored — a
                snapshot has no opening date.

    Optional:
      ``series`` — when ``"month"|"quarter"|"semester"|"year"``, break
      ``[date_from, date_to]`` into sub-periods and compute per-bucket
      totals for each. Each sub-period inherits the same Balanço /
      flow split, so monthly Balanço = closing balance at month-end.
      ``compare`` — when ``"previous_period"|"previous_year"``,
      compute the same payload's totals for the comparison window and
      return them under ``comparison``.
    """
    # Normalize feature toggles. Series + compare are advisory; bad
    # values silently degrade to "off" rather than error so URL shares
    # don't break when a value rolls out of the supported set.
    if series not in _SUPPORTED_SERIES:
        series = None
    if compare not in _SUPPORTED_COMPARE:
        compare = None

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

    parents_with_children: set = set()
    for r in rows:
        if r["parent_id"] is not None:
            parents_with_children.add(r["parent_id"])

    # ---- 2. Main window: full categories + cashflow + drill accounts ----
    categories, _ = _category_buckets_for_window(
        rows=rows, by_id=by_id, direction_by_id=direction_by_id,
        tax_map=tax_map, parents_with_children=parents_with_children,
        company_id=company_id,
        date_from=date_from, date_to=date_to,
        entity_id=entity_id, include_pending=include_pending,
        basis=basis, include_accounts=True,
    )
    cashflow_payload = _cashflow_for_window(
        company_id=company_id,
        date_from=date_from, date_to=date_to,
        entity_id=entity_id, include_pending=include_pending,
        include_accounts=True,
    )

    # ---- 3. Currency (most-common across accounts) ----
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

    # ---- 4. Cash KPI snapshot (independent of date scope) ----
    cash_total = _cash_total_snapshot(
        company_id=company_id,
        rows=rows, by_id=by_id, tax_map=tax_map,
        parents_with_children=parents_with_children,
        direction_by_id=direction_by_id,
    )

    # Build the totals map from the just-computed categories so the
    # diagnostics helper sees the same numbers the frontend will
    # render — including the synthetic Resultado do Exercício that
    # gets folded into ``patrimonio_liquido``.
    main_totals: Dict[str, Decimal] = {}
    synthetic_lucro = Decimal("0")
    for c in categories:
        try:
            main_totals[c["key"]] = Decimal(c["amount"])
        except Exception:
            main_totals[c["key"]] = Decimal("0")
        if c["key"] == "patrimonio_liquido":
            for a in (c.get("accounts") or []):
                if a.get("synthetic"):
                    try:
                        synthetic_lucro = Decimal(a.get("amount") or "0")
                    except Exception:
                        synthetic_lucro = Decimal("0")
                    break

    diagnostics = _compute_balance_diagnostics(
        rows=rows, by_id=by_id, direction_by_id=direction_by_id,
        tax_map=tax_map, parents_with_children=parents_with_children,
        company_id=company_id,
        date_from=date_from, date_to=date_to,
        entity_id=entity_id, include_pending=include_pending,
        main_totals=main_totals, synthetic_lucro=synthetic_lucro,
    )

    payload: dict = {
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
        # Present only when there's an imbalance to explain. Frontend
        # gates the diagnostic panel on this being truthy.
        "balance_diagnostics": diagnostics,
    }

    # ---- 5. Optional series sub-period totals ----
    if series and date_from is not None and date_to is not None:
        sub_periods = _series_periods(date_from, date_to, series)
        series_periods_out: List[dict] = []
        for p in sub_periods:
            sub_from = _date.fromisoformat(p["date_from"])
            sub_to = _date.fromisoformat(p["date_to"])
            cats, totals = _category_buckets_for_window(
                rows=rows, by_id=by_id, direction_by_id=direction_by_id,
                tax_map=tax_map, parents_with_children=parents_with_children,
                company_id=company_id,
                date_from=sub_from, date_to=sub_to,
                entity_id=entity_id, include_pending=include_pending,
                basis=basis, include_accounts=False,
            )
            cf = _cashflow_for_window(
                company_id=company_id,
                date_from=sub_from, date_to=sub_to,
                entity_id=entity_id, include_pending=include_pending,
                include_accounts=False,
            )
            series_periods_out.append({
                "key": p["key"],
                "label": p["label"],
                "date_from": p["date_from"],
                "date_to": p["date_to"],
                "totals": {k: str(v) for k, v in totals.items()},
                "cashflow_totals": (cf or {}).get("by_section") if cf else None,
            })
        payload["series"] = {
            "granularity": series,
            "periods": series_periods_out,
            "truncated": len(sub_periods) >= _SERIES_MAX_PERIODS,
        }

    # ---- 6. Optional comparison window ----
    if compare and date_from is not None and date_to is not None:
        cmp_resolved = _compare_window(
            date_from=date_from, date_to=date_to, compare=compare,
        )
        if cmp_resolved is not None:
            cmp_from, cmp_to, cmp_label = cmp_resolved
            cmp_cats, cmp_totals = _category_buckets_for_window(
                rows=rows, by_id=by_id, direction_by_id=direction_by_id,
                tax_map=tax_map, parents_with_children=parents_with_children,
                company_id=company_id,
                date_from=cmp_from, date_to=cmp_to,
                entity_id=entity_id, include_pending=include_pending,
                basis=basis, include_accounts=False,
            )
            cmp_cf = _cashflow_for_window(
                company_id=company_id,
                date_from=cmp_from, date_to=cmp_to,
                entity_id=entity_id, include_pending=include_pending,
                include_accounts=False,
            )
            payload["comparison"] = {
                "type": compare,
                "label": cmp_label,
                "period": {
                    "date_from": cmp_from.isoformat(),
                    "date_to": cmp_to.isoformat(),
                },
                "totals": {k: str(v) for k, v in cmp_totals.items()},
                "cashflow_totals": (cmp_cf or {}).get("by_section") if cmp_cf else None,
            }

    return payload


def compute_financial_statements_cached(
    company_id: int,
    *,
    date_from=None,
    date_to=None,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
    basis: str = "accrual",
    series: Optional[str] = None,
    compare: Optional[str] = None,
    bypass_cache: bool = False,
) -> dict:
    """Cached wrapper around ``compute_financial_statements``.

    Cache key includes the tenant data version (see
    ``report_cache.data_version``); a write to any
    ``JournalEntry`` / ``Transaction`` / ``Account`` row in the
    tenant moves the version, so the next read rebuilds with
    fresh numbers. ``bypass_cache=True`` short-circuits to a
    direct rebuild for debug / ?nocache=1.

    The cache key now also covers ``series`` and ``compare`` so
    different granularity / comparison choices don't collide.
    """
    key_parts = {
        "df": date_from.isoformat() if date_from else None,
        "dt": date_to.isoformat() if date_to else None,
        "ent": entity_id,
        "ip": bool(include_pending),
        "basis": basis,
        "series": series or None,
        "compare": compare or None,
    }

    def _build():
        return compute_financial_statements(
            company_id,
            date_from=date_from,
            date_to=date_to,
            entity_id=entity_id,
            include_pending=include_pending,
            basis=basis,
            series=series,
            compare=compare,
        )

    return cached_payload(
        "fs:v4", company_id, key_parts, _build, bypass=bypass_cache,
    )
