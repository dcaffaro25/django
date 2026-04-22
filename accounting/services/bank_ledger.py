"""Balanced double-entry for bank-to-ledger reconciliation adjustments.

Public surface: :func:`create_balanced_adjustment`. Every call produces a
fresh `Transaction` whose debits equal its credits, comprised of:

    * **one auto-created cash leg** — on the CoA account tied to the
      bank's ``BankAccount`` (looked up via :func:`resolve_cash_account`),
    * **N contra legs** supplied by the caller (what the operator picked
      in the drawer).

The cash leg's *effective amount* equals the ``adjustment_target``
(how much the reconciliation still needs to close); its side is derived
from that target + the cash account's ``account_direction``. Contra legs
supply the offsetting debits/credits so the transaction balances.

Two intended call-sites (both in ``BankTransactionViewSet.create_suggestions``):

    **Case 1** — adjustment over an existing match
        The selection already has one or more book entries; the new
        Transaction only needs to carry the *gap*. Pass
        ``adjustment_target = bank.amount - Σ(existing cash-leg effective
        amounts)``. The existing Transaction(s) are **not** mutated — a
        clean hand-off that keeps historical books untouched.

    **Case 2** — orphan bank line
        No existing book; the entire movement needs a fresh Transaction.
        Pass ``adjustment_target = bank.amount``.

The function raises :class:`BankLedgerError` when it can't satisfy the
accounting contract — never silently half-writes. Callers wrap the
whole ``create_suggestions`` body in an atomic block already, so a
raise is a clean rollback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from datetime import date as _date_t, datetime
from typing import Any, Iterable

from django.db import transaction as db_transaction
from django.db.models import Sum, F, DecimalField, IntegerField, Value
from django.db.models.functions import Coalesce

from accounting.models import Account, JournalEntry, Transaction


log = logging.getLogger(__name__)


class BankLedgerError(Exception):
    """Domain error for the balanced-adjustment flow. Callers should
    surface the ``.message`` to the API consumer — the messages are
    written to be operator-readable."""


# ------------------------------------------------------------------ models


@dataclass(frozen=True)
class ContraLeg:
    """One leg the operator specified in the drawer. ``debit_amount``
    XOR ``credit_amount`` must be positive — both null or both set is a
    protocol error."""

    account_id: int
    debit_amount: Decimal | None
    credit_amount: Decimal | None
    description: str = ""
    cost_center_id: int | None = None
    date: _date_t | None = None

    def signed_amount(self) -> Decimal:
        """``(debit - credit)``; not direction-adjusted."""
        d = self.debit_amount or Decimal("0")
        c = self.credit_amount or Decimal("0")
        return d - c


# ---------------------------------------------------------------- helpers


_DECIMAL_0 = Decimal("0")


def _parse_date(value: Any) -> _date_t | None:
    """Accept YYYY-MM-DD strings and already-parsed date objects. Bad
    input returns ``None`` — caller falls back to the transaction date.
    Silently swallowing ParseError here is intentional: a typo in an
    individual row shouldn't fail the whole adjustment."""
    if value is None or value == "":
        return None
    if isinstance(value, _date_t):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _quantize(value: Decimal) -> Decimal:
    """Round to 2 decimal places, matching our money columns. Uses the
    default rounding (ROUND_HALF_EVEN) — the reconciliation engine's
    own sums use the same quantisation path via
    ``get_effective_amount``, so results agree."""
    return (value or _DECIMAL_0).quantize(Decimal("0.01"))


def resolve_cash_account(bank_account_id: int, company_id: int) -> Account:
    """Find the CoA ``Account`` backing this BankAccount.

    Raises :class:`BankLedgerError` when missing or ambiguous — the
    caller must halt; silently picking one of N ambiguous accounts
    would split balances across the wrong ledgers.
    """
    qs = Account.objects.filter(
        company_id=company_id,
        bank_account_id=bank_account_id,
        is_active=True,
    )
    rows = list(qs[:2])
    if not rows:
        raise BankLedgerError(
            f"Nenhuma conta contábil ativa está vinculada à conta bancária "
            f"{bank_account_id} desta empresa. Configure o vínculo antes de "
            f"conciliar."
        )
    if len(rows) > 1:
        raise BankLedgerError(
            f"Mais de uma conta contábil está vinculada à conta bancária "
            f"{bank_account_id} desta empresa. Deixe apenas uma ativa."
        )
    return rows[0]


def sum_existing_cash_leg_effective(
    existing_journal_entries: Iterable[JournalEntry],
) -> Decimal:
    """Σ(``get_effective_amount``) over the cash legs we're reconciling.

    Filtering — only JEs whose account has a ``bank_account`` FK are
    considered "cash legs"; the rest are contra entries that live on
    the same transaction but must not contribute to ``book_sum`` on
    the reconciliation side (see ``JournalEntryViewSet.unmatched``).
    """
    total = _DECIMAL_0
    for je in existing_journal_entries:
        acc = je.account
        if acc is None or acc.bank_account_id is None:
            continue
        eff = je.get_effective_amount()
        if eff is not None:
            total += eff
    return _quantize(total)


def _cash_leg_sides(
    adjustment_target: Decimal, cash_account: Account,
) -> tuple[Decimal | None, Decimal | None]:
    """Return ``(debit_amount, credit_amount)`` for the cash leg.

    We want ``(debit - credit) * direction == adjustment_target``, so::

        raw = adjustment_target / direction      # signed
        if raw > 0: debit = raw, credit = None
        if raw < 0: debit = None, credit = |raw|
        if raw == 0: caller shouldn't invoke us, but zero is legal

    Direction=0 would be a data-config bug; we treat it as direction=1
    rather than raising, matching ``get_effective_amount``'s own
    fallback.
    """
    direction = Decimal(cash_account.account_direction or 1)
    raw = _quantize(adjustment_target / direction if direction else adjustment_target)
    if raw > 0:
        return raw, None
    if raw < 0:
        return None, -raw
    return _DECIMAL_0, None  # zero-amount cash leg — only for a perfectly-covered adjustment


def assert_transaction_balanced(tx: Transaction) -> Decimal:
    """Verify Σdebits == Σcredits on the transaction. Returns the
    signed imbalance (0 when balanced). Raise is the caller's
    decision; we just surface the number so error messages can
    report the exact mismatch."""
    agg = tx.journal_entries.aggregate(
        d=Coalesce(Sum("debit_amount"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))),
        c=Coalesce(Sum("credit_amount"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))),
    )
    return _quantize((agg["d"] or _DECIMAL_0) - (agg["c"] or _DECIMAL_0))


# ------------------------------------------------------------- core writer


@dataclass
class AdjustmentResult:
    transaction: Transaction
    cash_leg: JournalEntry
    contra_legs: list[JournalEntry]


def create_balanced_adjustment(
    *,
    company_id: int,
    bank_account_id: int,
    adjustment_target: Decimal,
    contra_legs: list[ContraLeg],
    transaction_date: _date_t,
    entity_id: int | None = None,
    currency_id: int | None = None,
    description: str = "",
    state: str = "pending",
    notes: str = "",
) -> AdjustmentResult:
    """Create a balanced adjustment Transaction in a single atomic block.

    ``adjustment_target`` is the *signed* amount the cash leg's effective
    value must equal. For Case 2 this is ``bank.amount``; for Case 1
    it's ``bank.amount − Σ(existing cash-leg effective amounts)``.

    Contra legs are what the operator picked in the drawer. Their sum of
    effective amounts must equal ``-adjustment_target`` so the resulting
    transaction balances; we don't auto-compute contra sides here
    because the operator often has a specific sign in mind (e.g.,
    "this is a *credit note*, not an expense"). We validate instead.
    """
    adjustment_target = _quantize(adjustment_target)

    if not contra_legs and adjustment_target != _DECIMAL_0:
        raise BankLedgerError(
            "Nenhum contra-lançamento foi informado — não é possível "
            "fechar o ajuste sem ao menos uma conta de destino."
        )

    cash_account = resolve_cash_account(bank_account_id, company_id)

    # Default entity / currency from the BankAccount when the caller
    # didn't supply them. Every BankAccount row has both as NOT NULL,
    # so this is the most-correct fallback.
    if entity_id is None or currency_id is None:
        from accounting.models import BankAccount
        ba = BankAccount.objects.filter(id=bank_account_id, company_id=company_id).only("entity_id", "currency_id").first()
        if ba is not None:
            if entity_id is None:
                entity_id = ba.entity_id
            if currency_id is None:
                currency_id = ba.currency_id

    # Transaction-balance invariant: Σ debit_amount == Σ credit_amount
    # across ALL legs (cash + contras). We enforce it via raw
    # (debit-credit) sums rather than effective amounts, because
    # ``effective = (d - c) * direction`` mixes in each leg's
    # direction and the raw-sum invariant is what Σd=Σc really means.
    # Accounts with mixed directions (e.g., contra Passivo against
    # cash Ativo) make ``Σ effective`` non-zero but the transaction
    # is still perfectly balanced — the effective-based check was
    # incorrect for those cases.
    contra_raw = _quantize(sum((leg.signed_amount() for leg in contra_legs), _DECIMAL_0))
    cash_dir = Decimal(cash_account.account_direction or 1)
    cash_raw_expected = _quantize(adjustment_target / cash_dir if cash_dir else adjustment_target)
    # For the whole Tx to balance: contra_raw + cash_raw == 0.
    if _quantize(contra_raw + cash_raw_expected) != _DECIMAL_0:
        raise BankLedgerError(
            f"Soma de débitos/créditos dos contra-lançamentos ({contra_raw}) "
            f"não fecha com a perna de caixa ({cash_raw_expected}). "
            f"Esperado {-cash_raw_expected} (Σd − Σc dos contras)."
        )

    with db_transaction.atomic():
        tx = Transaction.objects.create(
            company_id=company_id,
            date=transaction_date,
            entity_id=entity_id,
            description=description or "",
            amount=_quantize(abs(adjustment_target)),
            currency_id=currency_id,
            state=state,
            **({"notes": notes} if notes else {}),
        )

        # ----- cash leg -------------------------------------------------
        cash_debit, cash_credit = _cash_leg_sides(adjustment_target, cash_account)
        cash_leg = JournalEntry.objects.create(
            company_id=company_id,
            transaction=tx,
            account_id=cash_account.id,
            debit_amount=cash_debit,
            credit_amount=cash_credit,
            description=description or "Cash leg (auto)",
            date=transaction_date,
            state=state,
        )

        # ----- contra legs ----------------------------------------------
        contra_objs: list[JournalEntry] = []
        for leg in contra_legs:
            contra_objs.append(
                JournalEntry.objects.create(
                    company_id=company_id,
                    transaction=tx,
                    account_id=leg.account_id,
                    cost_center_id=leg.cost_center_id,
                    debit_amount=_quantize(leg.debit_amount) if leg.debit_amount else None,
                    credit_amount=_quantize(leg.credit_amount) if leg.credit_amount else None,
                    description=leg.description or description or "",
                    date=leg.date or transaction_date,
                    state=state,
                )
            )

        # ----- integrity gate -------------------------------------------
        # Belt + suspenders: the pre-check above guarantees raw
        # contra_raw + cash_raw = 0; this re-queries the Tx to
        # defend against clock-skew / racing writers / a future
        # refactor that slips a bad leg past the pre-check. A raise
        # here rolls back the atomic block cleanly.
        imbalance = assert_transaction_balanced(tx)
        if imbalance != _DECIMAL_0:
            raise BankLedgerError(
                f"Lançamento descompensado ({imbalance}) após criação — "
                f"isto é um bug. Cash ({cash_debit or 0} D / {cash_credit or 0} C), "
                f"contra soma (Σd−Σc) = {contra_raw}."
            )

    return AdjustmentResult(transaction=tx, cash_leg=cash_leg, contra_legs=contra_objs)


# ---------------------------------------------------------------- helpers


def _account_direction(account_id: int, company_id: int) -> int:
    """Cheap lookup — we call this once per contra leg, and contra-leg
    counts are tiny (1-5 in practice)."""
    a = Account.objects.filter(id=account_id, company_id=company_id).only("account_direction").first()
    if a is None:
        raise BankLedgerError(
            f"Conta contábil {account_id} não encontrada nesta empresa."
        )
    return a.account_direction or 1


def contra_legs_from_payload(
    rows: list[dict], *, default_date: _date_t | None = None,
) -> list[ContraLeg]:
    """Translate raw dicts from the API payload into
    :class:`ContraLeg` instances. Ignores rows with no amount or no
    account (they were blank rows in the drawer)."""
    legs: list[ContraLeg] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if not r.get("account_id"):
            continue
        d_raw = r.get("debit_amount")
        c_raw = r.get("credit_amount")
        debit = Decimal(str(d_raw)) if d_raw not in (None, "") else None
        credit = Decimal(str(c_raw)) if c_raw not in (None, "") else None
        if debit is None and credit is None:
            continue
        legs.append(ContraLeg(
            account_id=int(r["account_id"]),
            debit_amount=debit,
            credit_amount=credit,
            description=str(r.get("description") or ""),
            cost_center_id=r.get("cost_center_id"),
            date=_parse_date(r.get("date")) or default_date,
        ))
    return legs


def sum_existing_cash_legs_for_jes(
    je_ids: Iterable[int], company_id: int,
) -> tuple[Decimal, list[JournalEntry]]:
    """Load the cash legs among the selected JEs and their effective
    sum. A "cash leg" is a JE on an account that has ``bank_account``
    set — mirrors the filter in ``JournalEntryViewSet.unmatched``.

    Returns ``(sum_effective, cash_legs)``. Non-cash JEs in ``je_ids``
    are quietly dropped; the caller decides whether that's an error.
    """
    ids = [int(x) for x in je_ids if x is not None]
    if not ids:
        return _DECIMAL_0, []
    jes = list(
        JournalEntry.objects
        .filter(id__in=ids, company_id=company_id, account__bank_account__isnull=False)
        .select_related("account", "transaction")
    )
    return sum_existing_cash_leg_effective(jes), jes
