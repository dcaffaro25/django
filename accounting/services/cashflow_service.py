"""Direct-method cash flow statement.

For each transaction with at least one bank-side journal entry inside
the requested period, we attribute its book-leg amounts to the matching
``effective_category``. When a transaction has bank legs spanning
multiple periods (settled across the boundary), book legs are
allocated **proportionally** to the in-period bank-leg share -- this
keeps the period total tied to the actual cash that hit the bank in
the window, not to the full accrual.

Date scope per bank leg ("effective cash date" — see
``_annotate_effective_cash_date``):

* JE is **reconciled** → use the linked ``BankTransaction.date``
  (when the cash actually settled at the bank).
* JE is **not reconciled** → use the JE's own ``date`` (the
  bookkeeper's expected/estimated payment date).

This is the only point where DRE-cash and DFC scoping diverges from
``Transaction.date``: accrual uses transaction date, cash uses the
bank-settle-or-estimate date above.

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

from django.db.models import (
    Case,
    DateField,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from accounting.models import Account, BankTransaction, JournalEntry


# ---------------------------------------------------------------------
# Cash-flow section taxonomy (FCO / FCI / FCF)
# ---------------------------------------------------------------------
# Section is derived directly from the prefix of the
# ``cashflow_category`` field on Account (``fco_*`` / ``fci_*`` /
# ``fcf_*``). No mapping table; no derivation from ``report_category``
# or ``tags``.
#
# This is the second iteration of DFC wiring. The first iteration
# (DEFAULT_CATEGORY_TO_SECTION + TAG_TO_SECTION) tried to derive the
# DFC section from ``report_category`` + ``tags``, but BS/PnL category
# and DFC sub-line are genuinely independent decisions: an "Aplicação
# Financeira de Liquidez Imediata" is BS-side ``ativo_circulante`` AND
# DFC-side ``fci_investimentos_financeiros``; deriving one from the
# other forces a wrong default in either report. The new
# ``cashflow_category`` field on Account makes this explicit.

CASHFLOW_SECTIONS: Tuple[str, ...] = (
    "operacional",
    "investimento",
    "financiamento",
)


def cashflow_section_for(cashflow_category: Optional[str]) -> Optional[str]:
    """Resolve the FCO/FCI/FCF section from a ``cashflow_category``
    code. The section is encoded in the prefix (``fco_`` / ``fci_`` /
    ``fcf_``) so this is a constant-time lookup. Returns ``None`` when
    no category is set — the DFC surfaces these in its "Não
    classificadas" tail bucket so they're visible for cleanup."""
    if not cashflow_category:
        return None
    return {
        "fco": "operacional",
        "fci": "investimento",
        "fcf": "financiamento",
    }.get(cashflow_category.split("_", 1)[0])


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


def _annotate_effective_cash_date(je_qs):
    """Annotate ``effective_cash_date`` on a bank-leg JE queryset.

    Cash flow scoping should follow *when the cash actually hit the
    bank*, not when the bookkeeper dated the GL entry. The two diverge
    routinely: an A/P payable JE is dated on the due date, the bank
    settles a few days later. Without this annotation, accrued-but-not-
    settled JEs leak into the period and reconciled JEs that settled
    in the period get pushed out.

    Resolution rule per JE:

    * ``is_reconciled=True`` → use the date of any linked
      ``BankTransaction`` (earliest, picked by ``date`` then ``id``
      for determinism). Falls back to the JE's own ``date`` if the
      reconciliation row exists but no BT is linked (rare data drift).
    * ``is_reconciled=False`` → use the JE's own ``date`` (the
      forward-looking estimated payment date set by the bookkeeper).

    Path: ``JournalEntry → reconciliations (M2M) → bank_transactions
    (M2M) → date``. Multi-BT reconciliations pick the earliest date;
    that's a heuristic, not a perfect answer when one JE settles via
    several payments, but the typical 1:1 case is correct and the
    rest stays bounded.
    """
    bt_date_subq = (
        BankTransaction.objects.filter(
            reconciliations__journal_entries=OuterRef("pk"),
        )
        .order_by("date", "id")
        .values("date")[:1]
    )
    return je_qs.annotate(
        effective_cash_date=Case(
            When(
                is_reconciled=True,
                then=Coalesce(Subquery(bt_date_subq), F("date")),
            ),
            default=F("date"),
            output_field=DateField(),
        )
    )


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

    bank_qs = _annotate_effective_cash_date(bank_qs)

    abs_e = _abs_expr()
    aggs = bank_qs.values("transaction_id").annotate(
        total_abs=Sum(abs_e),
        in_period_abs=Sum(
            abs_e,
            filter=Q(effective_cash_date__gte=date_from)
            & Q(effective_cash_date__lte=date_to),
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

    Returns three resolved values per account: ``effective_category``
    (drives DRE/Balanço), ``effective_tags`` (cross-cutting markers),
    ``effective_cashflow_category`` (drives DFC). All three follow
    the same nearest-tagged-ancestor inheritance rule, with tags
    unioning across ancestors instead of taking the nearest.
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

    def cashflow_category_for(aid: int) -> Optional[str]:
        cur = by_id.get(aid)
        while cur is not None:
            if cur.get("cashflow_category"):
                return cur["cashflow_category"]
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
            "effective_cashflow_category": cashflow_category_for(aid),
        }
        for aid in by_id.keys()
    }


# ---------------------------------------------------------------------
# Public surface 1: DFC direct method
# ---------------------------------------------------------------------


def _distribute_cash_to_book_categories(
    company_id: int,
    date_from,
    date_to,
    *,
    entity_id: Optional[int] = None,
    include_pending: bool = False,
) -> Dict[int, Decimal]:
    """Compute the actual cash that moved per period and distribute
    it across each transaction's book-leg accounts proportionally to
    each book leg's |debit−credit| share.

    Returns ``{book_account_id: cash_amount_signed}``.

    Why this shape: in the Direct Method DFC, the *amount* is the
    cash that hit the bank (so its sign is governed by the bank-leg
    direction, naturally +1 for cash accounts) and the
    *categorisation* is "what did the cash buy / what did it come
    from" — i.e. the opposing book leg's category. The previous
    implementation summed book-leg amounts and applied
    ``account_direction``, which is correct for DRE math but wrong
    for cash flow: an expense payment (DR Despesa | CR Bancos) came
    out **positive** because Despesa is debit-natural with dir=+1,
    even though cash actually went *out*. See the
    ``compute_cashflow_direct`` docstring for the worked example.

    Allocation per transaction:

        cash_in_period = Σ bank_leg (debit − credit) where leg.date
                         ∈ [date_from, date_to]
        per book leg b:
            weight_b = |debit_b − credit_b| / Σ |debit_b' − credit_b'|
                       across all book legs of the same tx
            allocated_b = cash_in_period × weight_b

    Multi-period transactions: only the bank legs that hit in-window
    contribute to ``cash_in_period``, so a transaction settled across
    a period boundary attributes only its in-period cash to book
    categories. This subsumes the old per-tx weight scaling.

    Multi-bank-leg transactions (DR Banco1 + DR Banco2 | CR Receita):
    the two cash legs sum naturally inside ``cash_in_period``.

    Edge case — transaction with no book legs (pure bank-to-bank
    transfer, ``cash_in_period`` already nets to zero): nothing to
    distribute, the tx is skipped.
    """
    bank_qs = JournalEntry.objects.filter(
        account__company_id=company_id,
        account__bank_account__isnull=False,
    ).filter(_state_filter(include_pending))
    if entity_id is not None:
        bank_qs = bank_qs.filter(transaction__entity_id=entity_id)

    bank_qs = _annotate_effective_cash_date(bank_qs)

    # Per-tx bank-leg net in-period. Sign is naturally cash-correct
    # because cash accounts are direction=+1 (debit-natural assets):
    # DR cash → cash in (+), CR cash → cash out (−).
    cash_per_tx_aggs = (
        bank_qs.filter(
            effective_cash_date__gte=date_from,
            effective_cash_date__lte=date_to,
        )
        .values("transaction_id")
        .annotate(net=Sum(_net_expr()))
    )
    cash_per_tx: Dict[int, Decimal] = {}
    for r in cash_per_tx_aggs:
        net = r["net"] or Decimal("0")
        if net != 0:
            cash_per_tx[r["transaction_id"]] = net
    if not cash_per_tx:
        return {}

    # Book legs across the same transaction set, with each leg's
    # ABSOLUTE amount used for proportional weighting. Bank legs
    # excluded so they don't get cash allocated to themselves.
    book_qs = JournalEntry.objects.filter(
        account__company_id=company_id,
        transaction_id__in=list(cash_per_tx.keys()),
        account__bank_account__isnull=True,
    ).filter(_state_filter(include_pending))

    abs_e = _abs_expr()
    book_aggs = book_qs.values("transaction_id", "account_id").annotate(
        abs_amount=Sum(abs_e),
    )
    rows = list(book_aggs)

    total_book_abs_per_tx: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        total_book_abs_per_tx[r["transaction_id"]] += r["abs_amount"] or Decimal("0")

    by_account: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        tx_id = r["transaction_id"]
        cash = cash_per_tx.get(tx_id, Decimal("0"))
        total_abs = total_book_abs_per_tx.get(tx_id, Decimal("0"))
        if total_abs <= 0:
            # No book activity to anchor the categorisation — usually
            # a pure bank-to-bank transfer that already netted to
            # zero in ``cash_per_tx`` and was filtered out. Defensive
            # guard for unusual data.
            continue
        leg_abs = r["abs_amount"] or Decimal("0")
        by_account[r["account_id"]] += cash * (leg_abs / total_abs)
    return dict(by_account)


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

    Sign convention: amounts are real cash flows. Cash in → positive,
    cash out → negative. The sign comes from the bank-leg direction
    (cash accounts are debit-natural, so DR cash = +, CR cash = −).
    The book-leg category just labels the line — it does NOT
    contribute its ``account_direction`` to the sign. This is the
    Direct Method definition: cash flow IS the bank movement,
    classified by what the cash was for.

    Worked example. JE: ``DR Despesa Operacional 500 | CR Bancos
    500`` (paying R$ 500 in cash for an expense). The bank leg is
    ``-500`` (CR cash → cash out). The single book leg is Despesa
    Operacional with weight 1.0. Allocation: ``despesa_operacional
    bucket += -500 × 1.0 = -500``. ✓ (The previous implementation
    came out at +500 because it summed the book leg with
    ``direction=+1``.)
    """
    by_account_unsigned = _distribute_cash_to_book_categories(
        company_id,
        date_from,
        date_to,
        entity_id=entity_id,
        include_pending=include_pending,
    )
    if not by_account_unsigned:
        return _empty_cashflow_response(date_from, date_to, include_pending)

    # Pull the full account chart in one query so we can resolve
    # taxonomy without N+1. ``account_direction`` is intentionally
    # NOT applied here — sign already reflects cash movement.
    rows = list(
        Account.objects.filter(company_id=company_id).values(
            "id", "name", "parent_id",
            "report_category", "tags", "cashflow_category",
            "account_direction",
        )
    )
    tax_map = _walk_taxonomy(rows)
    by_id = {r["id"]: r for r in rows}

    by_account_rows: List[dict] = []
    # Bucket key is (cashflow_category, section) — the DFC tab
    # groups by its own category, not by the BS/PnL ``report_category``.
    by_category_acc: Dict[Tuple[str, str], dict] = defaultdict(
        lambda: {"amount": Decimal("0"), "accounts": 0}
    )
    section_totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for aid, signed in by_account_unsigned.items():
        info = by_id.get(aid)
        if info is None:
            continue
        if signed == 0:
            continue
        tax = tax_map.get(aid, {})
        cf_cat = tax.get("effective_cashflow_category")
        report_cat = tax.get("effective_category") or "<uncategorized>"
        tags = tax.get("effective_tags") or []
        section = cashflow_section_for(cf_cat) or "no_section"
        # Bucket label: prefer the explicit cashflow_category; fall
        # back to ``<no_cashflow_category>`` so unmapped accounts are
        # visible for the operator to fix via the wiring modal.
        bucket_cat = cf_cat or "<no_cashflow_category>"

        by_account_rows.append(
            {
                "account_id": aid,
                "name": info.get("name") or "",
                "category": bucket_cat,
                "report_category": report_cat,
                "tags": tags,
                "section": section,
                "amount": str(signed),
            }
        )
        bucket = by_category_acc[(bucket_cat, section)]
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
