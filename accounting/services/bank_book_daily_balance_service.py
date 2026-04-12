"""
Build paired daily bank-statement vs GL (book) balance lines for one BankAccount.

Convention (matches typical statement / GL anchors):
- Bank: anchor is BankAccount.balance as of end of balance_date; include all
  BankTransaction rows with date > balance_date.
- Book: for each leaf Account with bank_account = this bank, anchor is
  Account.balance as of balance_date; include JournalEntry rows whose
  effective date (entry date or transaction date) is > that account's balance_date.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Sum

from accounting.models import Account, BankAccount, BankTransaction, JournalEntry


def _d(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def _je_eff_date(je: JournalEntry) -> date:
    return je.date or je.transaction.date


def _je_signed_for_account(je: JournalEntry) -> Decimal:
    td = je.debit_amount or Decimal("0")
    tc = je.credit_amount or Decimal("0")
    return (td - tc) * je.account.account_direction


def _iter_days(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def _leaf_accounts_for_bank(ba: BankAccount) -> List[Account]:
    linked = list(
        Account.objects.filter(bank_account=ba, company_id=ba.company_id).select_related(
            "currency"
        )
    )
    return [a for a in linked if a.is_leaf()]


def build_bank_book_daily_balance_lines(
    bank_account: BankAccount,
    date_from: date,
    date_to: date,
    *,
    include_pending_book: bool = False,
    max_span_days: int = 800,
) -> Dict[str, Any]:
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if (date_to - date_from).days > max_span_days:
        raise ValueError(f"Date range cannot exceed {max_span_days} days")

    ba = bank_account
    anchor_b = ba.balance_date
    balance_b = _d(ba.balance)

    bank_by_day: Dict[date, Decimal] = {}
    for row in (
        BankTransaction.objects.filter(
            bank_account=ba, date__gt=anchor_b, is_deleted=False
        )
        .values("date")
        .annotate(net=Sum("amount"))
    ):
        bank_by_day[row["date"]] = _d(row["net"])

    bank_opening = balance_b + sum(amt for d, amt in bank_by_day.items() if d < date_from)

    bank_line: List[Dict[str, Any]] = []
    running_b = bank_opening
    for d in _iter_days(date_from, date_to):
        mv = bank_by_day.get(d, Decimal("0"))
        running_b += mv
        bank_line.append(
            {
                "date": d.isoformat(),
                "movement": float(mv),
                "balance": float(running_b),
            }
        )

    states = ["posted", "pending"] if include_pending_book else ["posted"]
    leaf_accounts = _leaf_accounts_for_bank(ba)
    gl_ids = [a.id for a in leaf_accounts]

    book_line: List[Dict[str, Any]]
    book_warning: Optional[str] = None
    currency_mismatch: Optional[str] = None

    if not gl_ids:
        book_warning = "no_leaf_gl_linked_to_bank_account"
        book_opening = Decimal("0")
        book_line = [
            {"date": d.isoformat(), "movement": 0.0, "balance": 0.0}
            for d in _iter_days(date_from, date_to)
        ]
    else:
        if len({a.currency_id for a in leaf_accounts}) > 1:
            currency_mismatch = "linked_gl_accounts_use_different_currencies"

        jes = list(
            JournalEntry.objects.filter(
                account_id__in=gl_ids,
                company_id=ba.company_id,
                state__in=states,
                is_deleted=False,
            ).select_related("transaction", "account")
        )

        book_by_day: Dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        book_opening = sum(_d(a.balance) for a in leaf_accounts)

        for je in jes:
            ed = _je_eff_date(je)
            acc = je.account
            if ed <= acc.balance_date:
                continue
            m = _je_signed_for_account(je)
            if date_from <= ed <= date_to:
                book_by_day[ed] += m
            elif ed < date_from:
                book_opening += m

        book_line = []
        running_g = book_opening
        for d in _iter_days(date_from, date_to):
            mv = book_by_day.get(d, Decimal("0"))
            running_g += mv
            book_line.append(
                {
                    "date": d.isoformat(),
                    "movement": float(mv),
                    "balance": float(running_g),
                }
            )

    return {
        "bank_account_id": ba.id,
        "company_id": ba.company_id,
        "currency_id": ba.currency_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "include_pending_book": include_pending_book,
        "linked_gl_account_ids": gl_ids,
        "bank": {
            "anchor_date": anchor_b.isoformat(),
            "anchor_balance": float(balance_b),
            "opening_balance": float(bank_opening),
            "line": bank_line,
        },
        "book": {
            "opening_balance": float(book_opening),
            "line": book_line,
            "warning": book_warning,
            "currency_mismatch": currency_mismatch,
        },
    }
