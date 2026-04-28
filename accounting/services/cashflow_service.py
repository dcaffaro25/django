"""Direct-method cash flow statement.

For each transaction with at least one bank-side journal entry inside
the requested period, we attribute its book-leg amounts to the matching
``effective_category``. When a transaction has bank legs spanning
multiple periods (settled across the boundary), book legs are
allocated **proportionally** to the in-period bank-leg share -- this
keeps the period total tied to the actual cash that hit the bank in
the window, not to the full accrual.

The same machinery powers two surfaces:

* ``compute_cashflow_direct`` -- the DFC tab (FCO / FCI / FCF
  breakdown by ``effective_category``).
* ``compute_cash_basis_book_deltas`` -- the DRE "cash basis" toggle
  (per-account ``own_*_delta`` rebuilt with the bank-leg-date
  scope instead of ``transaction.date``).

Why a service file instead of fattening ``views.py``: this logic
straddles JE aggregation, taxonomy resolution, and per-transaction
weighting. Keeping it isolated makes it unit-testable and lets the
view layer stay thin.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from accounting.models import Account, JournalEntry


# ---------------------------------------------------------------------
# Cash-flow section taxonomy (FCO / FCI / FCF)
# ---------------------------------------------------------------------
# The DRE / Balanço use ``report_category``. The DFC uses a *derived*
# section computed from category + tags. We don't add a model field
# (yet) -- the mapping below is the source of truth and ships with
# the closed enum. When the operator's chart adds new categories the
# default below stays sane (uncategorized tags fall through to
# ``no_section`` and surface in the DFC tail bucket so they're
# visible for cleanup).

DEFAULT_CATEGORY_TO_SECTION: Dict[str, str] = {
    # Operating: revenue, cost, opex, working capital
    "receita_bruta": "operacional",
    "deducao_receita": "operacional",
    "custo": "operacional",
    "despesa_operacional": "operacional",
    "receita_financeira": "operacional",
    "outras_receitas": "operacional",
    "imposto_sobre_lucro": "operacional",
    "ativo_circulante": "operacional",
    "passivo_circulante": "operacional",
    # Financing: long-term debt, equity, financial expense (interest
    # is FCF in IFRS Option B; we follow that here -- can be flipped
    # via a tag override on the specific accounts).
    "despesa_financeira": "financiamento",
    "passivo_nao_circulante": "financiamento",
    "patrimonio_liquido": "financiamento",
    # Investing: long-term assets
    "ativo_nao_circulante": "investimento",
}

# Tag overrides win over the category default. Mostly relevant for
# accounts that classify oddly under their parent (a debt under
# ``passivo_circulante`` is FCF, not FCO; a fixed_asset leaf under a
# misc parent should still be FCI).
TAG_TO_SECTION: Dict[str, str] = {
    "debt": "financiamento",
    "fixed_asset": "investimento",
    "intangible_asset": "investimento",
    "jcp": "financiamento",
    "dividends": "financiamento",
}

CASHFLOW_SECTIONS: Tuple[str, ...] = (
    "operacional",
    "investimento",
    "financiamento",
)


def cashflow_section_for(
    category: Optional[str], tags: Optional[Iterable[str]]
) -> Optional[str]:
    """Resolve the FCO/FCI/FCF section for an account.

    Tag override wins if any matching tag is set; otherwise fall back
    to the category default. Returns ``None`` (=> ``no_section``) when
    nothing matches -- the operator hasn't categorised the account.
    """
    if tags:
        for t in tags:
            if t in TAG_TO_SECTION:
                return TAG_TO_SECTION[t]
    if category and category in DEFAULT_CATEGORY_TO_SECTION:
        return DEFAULT_CATEGORY_TO_SECTION[category]
    return None


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

def _zero_decimal() -> Value:
    return Value(
        Decimal("0"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _net_expr() -> F:
    """``debit - credit`` (NULL-safe). Positive = debit-direction
    movement before account_direction multiplier."""
    z = _zero_decimal()
    return Coalesce(F("debit_amount"), z) - Coalesce(F("credit_amount"), z)


def _abs_expr() -> F:
    """Absolute amount for weight denominators. Since ``debit_amount``
    and ``credit_amount`` are mutually exclusive (one is always NULL/0),
    their NULL-safe sum equals ``|debit - credit|``."""
    z = _zero_decimal()
    return Coalesce(F("debit_amount"), z) + Coalesce(F("credit_amount"), z)


def _state_filter(include_pending: bool) -> Q:
    """Which transaction states count.

    Default is ``posted`` only (matches the rest of the report stack).
    ``include_pending=True`` also folds pending JEs in -- needed for
    tenants like Evolat where the ledger is mostly pending.
    """
    states = ["posted", "pending"] if include_pending else ["posted"]
    return Q(transaction__state__in=states)


def _compute_transaction_weights(
    company_id: int,
    date_from,
    date_to,
    *,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
) -> Dict[int, Decimal]:
    """For every transaction with bank-side JE volume, compute

        weight = sum(|bank_je| where date in [date_from, date_to])
                 / sum(|bank_je|)

    Returns ``{transaction_id: weight}`` only for transactions where
    weight > 0 (some bank cash actually hit in-period). Transactions
    fully settled outside the window are dropped here.
    """
    if date_from is None or date_to is None:
        return {}

    bank_qs = JournalEntry.objects.filter(
        account__company_id=company_id,
        account__bank_account__isnull=False,
    ).filter(_state_filter(include_pending))

    if entity_id is not None:
        bank_qs = bank_qs.filter(transaction__entity_id=entity_id)

    abs_e = _abs_expr()
    aggs = bank_qs.values("transaction_id").annotate(
        total_abs=Sum(abs_e),
        in_period_abs=Sum(
            abs_e,
            filter=Q(date__gte=date_from) & Q(date__lte=date_to),
        ),
    )

    weights: Dict[int, Decimal] = {}
    for r in aggs:
        in_period = r["in_period_abs"] or Decimal("0")
        if in_period <= 0:
            continue
        total = r["total_abs"] or Decimal("0")
        if total <= 0:
            continue
        # ``in_period / total`` lives in [0, 1]. Numerically it can
        # land slightly above 1 if we ever count a bank leg twice
        # (we don't, but clamp defensively to keep downstream math
        # well-behaved).
        w = in_period / total
        if w > 1:
            w = Decimal("1")
        weights[r["transaction_id"]] = w
    return weights


def _aggregate_book_legs_with_weights(
    company_id: int,
    weights: Dict[int, Decimal],
    *,
    include_pending: bool = False,
) -> Dict[int, Decimal]:
    """Sum book-leg ``net = debit - credit`` per account, applying the
    per-transaction weight from ``weights``.

    Bank-side JEs (``account__bank_account__isnull=False``) are
    excluded -- they're the cash leg itself; including them would
    double-count when summed alongside book legs in the same
    transaction.
    """
    if not weights:
        return {}

    book_qs = JournalEntry.objects.filter(
        account__company_id=company_id,
        transaction_id__in=list(weights.keys()),
        account__bank_account__isnull=True,
    ).filter(_state_filter(include_pending))

    aggs = book_qs.values("transaction_id", "account_id").annotate(
        net=Sum(_net_expr())
    )

    by_account: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in aggs:
        w = weights.get(r["transaction_id"], Decimal("0"))
        if w == 0:
            continue
        net = r["net"] or Decimal("0")
        by_account[r["account_id"]] += net * w
    return by_account


def _walk_taxonomy(rows: List[dict]) -> Dict[int, dict]:
    """Cheap MPTT walk that mirrors ``_build_account_taxonomy_map`` in
    ``views.py``. We do it locally to keep the service self-contained
    (the view-layer helper is private and not all callers go through
    that code path).
    """
    by_id = {r["id"]: r for r in rows}

    def category_for(aid: int) -> Optional[str]:
        cur = by_id.get(aid)
        while cur is not None:
            if cur.get("report_category"):
                return cur["report_category"]
            pid = cur.get("parent_id")
            cur = by_id.get(pid) if pid is not None else None
        return None

    def tags_for(aid: int) -> List[str]:
        seen: set[str] = set()
        cur = by_id.get(aid)
        while cur is not None:
            for t in cur.get("tags") or []:
                seen.add(t)
            pid = cur.get("parent_id")
            cur = by_id.get(pid) if pid is not None else None
        return sorted(seen)

    return {
        aid: {
            "effective_category": category_for(aid),
            "effective_tags": tags_for(aid),
        }
        for aid in by_id.keys()
    }


# ---------------------------------------------------------------------
# Public surface 1: DFC direct method
# ---------------------------------------------------------------------

def compute_cashflow_direct(
    company_id: int,
    date_from,
    date_to,
    *,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
) -> dict:
    """Aggregate cash flow by category for ``[date_from, date_to]``.

    Returns a dict shaped for the frontend tab:

        {
          "date_from": "2025-01-01", "date_to": "2025-12-31",
          "include_pending": True,
          "by_category": [
            {"category": "receita_bruta",
             "section": "operacional",
             "amount": "12345.67",
             "account_count": 3},
            ...
          ],
          "by_section": {
            "operacional":  "..", "investimento": "..",
            "financiamento": "..", "no_section": "..",
            "net_change_in_cash": ".."
          },
          "by_account": [
            {"account_id": 17, "name": "Receita de Servicos",
             "category": "receita_bruta", "section": "operacional",
             "amount": "9876.54", "tags": ["service_revenue"]},
            ...
          ],
        }

    Amounts are signed-by-account_direction, so revenue → positive
    (cash in), expense → negative (cash out), matching the DRE
    convention used elsewhere on the frontend.
    """
    weights = _compute_transaction_weights(
        company_id,
        date_from,
        date_to,
        entity_id=entity_id,
        include_pending=include_pending,
    )
    if not weights:
        return _empty_cashflow_response(date_from, date_to, include_pending)

    by_account_unsigned = _aggregate_book_legs_with_weights(
        company_id, weights, include_pending=include_pending
    )
    if not by_account_unsigned:
        return _empty_cashflow_response(date_from, date_to, include_pending)

    # Pull the full account chart in one query so we can resolve
    # taxonomy + apply ``account_direction`` without N+1.
    rows = list(
        Account.objects.filter(company_id=company_id).values(
            "id", "name", "parent_id", "report_category", "tags",
            "account_direction",
        )
    )
    tax_map = _walk_taxonomy(rows)
    by_id = {r["id"]: r for r in rows}

    by_account_rows: List[dict] = []
    by_category_acc: Dict[Tuple[str, str], dict] = defaultdict(
        lambda: {"amount": Decimal("0"), "accounts": 0}
    )
    section_totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for aid, raw_amount in by_account_unsigned.items():
        info = by_id.get(aid)
        if info is None:
            continue
        direction = info.get("account_direction") or 1
        signed = raw_amount * direction
        if signed == 0:
            continue
        tax = tax_map.get(aid, {})
        cat = tax.get("effective_category") or "<uncategorized>"
        tags = tax.get("effective_tags") or []
        section = cashflow_section_for(cat, tags) or "no_section"

        by_account_rows.append(
            {
                "account_id": aid,
                "name": info.get("name") or "",
                "category": cat,
                "tags": tags,
                "section": section,
                "amount": str(signed),
            }
        )
        bucket = by_category_acc[(cat, section)]
        bucket["amount"] += signed
        bucket["accounts"] += 1
        section_totals[section] += signed

    by_category = [
        {
            "category": cat,
            "section": section,
            "amount": str(info["amount"]),
            "account_count": info["accounts"],
        }
        for (cat, section), info in by_category_acc.items()
    ]
    # Sort by section (FCO/FCI/FCF/no_section), then by absolute amount
    # descending so the largest movers in each section show first.
    section_order = {s: i for i, s in enumerate([*CASHFLOW_SECTIONS, "no_section"])}
    by_category.sort(
        key=lambda r: (
            section_order.get(r["section"], 99),
            -abs(Decimal(r["amount"])),
        )
    )
    by_account_rows.sort(
        key=lambda r: (
            section_order.get(r["section"], 99),
            -abs(Decimal(r["amount"])),
        )
    )

    net = sum(section_totals.values(), Decimal("0"))

    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "include_pending": include_pending,
        "entity_id": entity_id,
        "by_category": by_category,
        "by_section": {
            "operacional": str(section_totals.get("operacional", Decimal("0"))),
            "investimento": str(section_totals.get("investimento", Decimal("0"))),
            "financiamento": str(section_totals.get("financiamento", Decimal("0"))),
            "no_section": str(section_totals.get("no_section", Decimal("0"))),
            "net_change_in_cash": str(net),
        },
        "by_account": by_account_rows,
    }


def _empty_cashflow_response(date_from, date_to, include_pending: bool) -> dict:
    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "include_pending": include_pending,
        "entity_id": None,
        "by_category": [],
        "by_section": {
            "operacional": "0",
            "investimento": "0",
            "financiamento": "0",
            "no_section": "0",
            "net_change_in_cash": "0",
        },
        "by_account": [],
    }


# ---------------------------------------------------------------------
# Public surface 2: DRE cash basis (per-account own_delta override)
# ---------------------------------------------------------------------

def compute_cash_basis_book_deltas(
    company_id: int,
    date_from,
    date_to,
    *,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
) -> Dict[int, Dict[str, str]]:
    """Build a ``{account_id: {own_posted_delta, own_pending_delta,
    own_unreconciled_delta}}`` map under the **cash basis** scope.

    "Cash basis" means: a book-leg amount counts in the period iff its
    transaction has bank-side cash hitting in that period. Multi-period
    transactions are weighted (see ``_compute_transaction_weights``).

    Returned shape mirrors the ``account_delta_map`` the
    ``AccountSerializer`` already consumes via
    ``get_serializer_context`` -- so the only thing the view needs to
    do when ``basis=cash`` is swap ``account_delta_map`` for the dict
    we return here. Direction sign-correction is applied (matching the
    accrual code path), so values are drop-in compatible.

    ``own_unreconciled_delta`` stays at ``"0"``: the cash basis lens
    is about *when cash hit the bank*, not whether the JE has been
    reconciled. Surfacing unreconciled-net here would conflate the
    two ideas.
    """
    posted_weights = _compute_transaction_weights(
        company_id,
        date_from,
        date_to,
        entity_id=entity_id,
        include_pending=False,
    )
    posted_by_account = _aggregate_book_legs_with_weights(
        company_id, posted_weights, include_pending=False
    )

    if include_pending:
        # Compute weights again with pending folded in, then SUBTRACT
        # the posted contribution so ``own_pending_delta`` carries the
        # pending-only slice. This keeps the legacy splits the
        # frontend math relies on (some callers add posted+pending,
        # others use posted only).
        full_weights = _compute_transaction_weights(
            company_id,
            date_from,
            date_to,
            entity_id=entity_id,
            include_pending=True,
        )
        full_by_account = _aggregate_book_legs_with_weights(
            company_id, full_weights, include_pending=True
        )
        pending_by_account = {
            aid: full_by_account.get(aid, Decimal("0"))
            - posted_by_account.get(aid, Decimal("0"))
            for aid in (full_by_account.keys() | posted_by_account.keys())
        }
    else:
        pending_by_account = {}

    # Apply ``account_direction`` so the values are sign-correct (same
    # convention the accrual path uses).
    direction_by_id = dict(
        Account.objects.filter(company_id=company_id).values_list(
            "id", "account_direction"
        )
    )

    delta_map: Dict[int, Dict[str, str]] = {}
    all_aids = set(posted_by_account.keys()) | set(pending_by_account.keys())
    for aid in all_aids:
        d = direction_by_id.get(aid) or 1
        posted = (posted_by_account.get(aid) or Decimal("0")) * d
        pending = (pending_by_account.get(aid) or Decimal("0")) * d
        delta_map[aid] = {
            "own_posted_delta": str(posted),
            "own_pending_delta": str(pending),
            "own_unreconciled_delta": "0",
        }
    return delta_map
