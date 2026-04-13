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


def bank_account_summary(ba: BankAccount) -> Dict[str, Any]:
    """Lightweight bank account row for listings (no daily series)."""
    return {
        "id": ba.id,
        "name": ba.name,
        "entity_id": ba.entity_id,
        "entity_name": getattr(ba.entity, "name", None) if ba.entity_id else None,
        "bank_id": ba.bank_id,
        "bank_name": getattr(ba.bank, "name", None) if ba.bank_id else None,
        "currency_id": ba.currency_id,
        "account_number": ba.account_number,
        "branch_id": ba.branch_id,
        "balance": float(ba.balance or Decimal("0")),
        "balance_date": ba.balance_date.isoformat() if ba.balance_date else None,
    }


def build_aggregate_bank_book_daily_balance(
    bank_accounts: List[BankAccount],
    date_from: date,
    date_to: date,
    *,
    include_pending_book: bool = False,
    max_span_days: int = 800,
) -> Dict[str, Any]:
    """
    Sum bank vs book daily running balances across all given accounts, **grouped by currency**.

    Each currency bucket sums opening balances and per-day movements from every account in that
    currency so the aggregate lines are comparable (same-currency totals only).
    """
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if (date_to - date_from).days > max_span_days:
        raise ValueError(f"Date range cannot exceed {max_span_days} days")

    if not bank_accounts:
        return {
            "by_currency": {},
            "totals": {
                "bank_accounts": 0,
                "currencies": 0,
            },
        }

    by_currency: Dict[int, List[BankAccount]] = defaultdict(list)
    for ba in bank_accounts:
        by_currency[ba.currency_id].append(ba)

    by_currency_out: Dict[str, Any] = {}
    for cur_id, bas in by_currency.items():
        bank_open = Decimal("0")
        book_open = Decimal("0")
        bank_mov_by_day: Dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        book_mov_by_day: Dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        book_warnings: List[Dict[str, Any]] = []
        currency_mismatches: List[Dict[str, Any]] = []

        for ba in bas:
            try:
                payload = build_bank_book_daily_balance_lines(
                    ba,
                    date_from,
                    date_to,
                    include_pending_book=include_pending_book,
                )
            except ValueError:
                continue
            bank_open += _d(payload["bank"]["opening_balance"])
            book_open += _d(payload["book"]["opening_balance"])
            bw = payload["book"].get("warning")
            if bw:
                book_warnings.append({"bank_account_id": ba.id, "warning": bw})
            cm = payload["book"].get("currency_mismatch")
            if cm:
                currency_mismatches.append({"bank_account_id": ba.id, "currency_mismatch": cm})

            for pt in payload["bank"]["line"]:
                d = date.fromisoformat(pt["date"])
                bank_mov_by_day[d] += _d(pt["movement"])
            for pt in payload["book"]["line"]:
                d = date.fromisoformat(pt["date"])
                book_mov_by_day[d] += _d(pt["movement"])

        bank_line: List[Dict[str, Any]] = []
        book_line: List[Dict[str, Any]] = []
        running_b = bank_open
        running_g = book_open
        for d in _iter_days(date_from, date_to):
            mb = bank_mov_by_day.get(d, Decimal("0"))
            mg = book_mov_by_day.get(d, Decimal("0"))
            running_b += mb
            running_g += mg
            d_iso = d.isoformat()
            bank_line.append({"date": d_iso, "movement": float(mb), "balance": float(running_b)})
            book_line.append({"date": d_iso, "movement": float(mg), "balance": float(running_g)})

        diff_line = [
            {
                "date": bank_line[i]["date"],
                "bank_minus_book": float(
                    _d(bank_line[i]["balance"]) - _d(book_line[i]["balance"])
                ),
            }
            for i in range(len(bank_line))
        ]

        by_currency_out[str(cur_id)] = {
            "currency_id": cur_id,
            "bank_accounts_count": len(bas),
            "bank": {
                "opening_balance": float(bank_open),
                "line": bank_line,
            },
            "book": {
                "opening_balance": float(book_open),
                "line": book_line,
                "warnings": book_warnings,
                "currency_mismatches": currency_mismatches,
            },
            "difference": {
                "line": diff_line,
            },
        }

    return {
        "by_currency": by_currency_out,
        "totals": {
            "bank_accounts": len(bank_accounts),
            "currencies": len(by_currency_out),
        },
    }
