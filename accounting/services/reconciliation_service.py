"""
Reconciliation service for bank and journal entries.

This module provides a robust implementation of the reconciliation logic,
addressing issues observed in earlier versions.  Notable improvements include:

- Quantized comparisons: amounts are rounded to two decimal places using
  Decimal quantization to avoid floating-point artefacts.
- Date tolerance: exact matches consider dates equal within a configurable
  number of days rather than only the same calendar day.
- Effective amounts: journal entries are matched using get_effective_amount()
  to account for debit/credit direction rather than raw debit minus credit.
- Strategy configuration: matching behaviour is driven by parameters
  (strategy, amount tolerance, date tolerance, max group size, etc.)
  obtained from ReconciliationConfig or the supplied data dictionary.
- Fuzzy and group matching: fuzzy matching considers small differences in
  amounts/dates with confidence scoring, while group matching handles
  many‑to‑many relationships within tolerance windows.
- Auto‑matching: suggestions with confidence_score == 1.0 can be persisted
  automatically using the Reconciliation model.
- Celery‑safe: all database writes are wrapped in transactions and locked
  appropriately to avoid race conditions.

To use this service in your Celery task, import ReconciliationService below and
call match_many_to_many() with the request data and tenant_id.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from bisect import bisect_left, bisect_right
from itertools import combinations
from collections import defaultdict, Counter
from typing import List, Dict, Iterable, Tuple, Optional

from django.apps import apps
from django.db import transaction
from django.db.models import Sum, Q
import logging
import os

from accounting.models import (
    BankTransaction,
    JournalEntry,
    Account,
    Reconciliation,
)

log = logging.getLogger("recon")


def _q2(x: Decimal | None) -> Decimal:
    """
    Quantize a Decimal to two decimal places with normal rounding.
    Returns Decimal("0.00") if x is None.
    """
    if x is None:
        return Decimal("0.00")
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_exact_match(
    bank_amount: Decimal, txn_amount: Decimal, book_date, bank_date, date_tol_days: int
) -> bool:
    """
    Return True if the absolute values match exactly (to cents) and the dates
    differ by no more than date_tol_days.  The sign is ignored because bank
    outflows often have opposite sign to book entries.
    """
    return (
        abs(_q2(bank_amount)) == abs(_q2(txn_amount))
        and book_date
        and bank_date
        and abs((bank_date - book_date).days) <= date_tol_days
    )


@dataclass
class MatchConfig:
    """
    Configuration parameters for reconciliation matching.  Values may come from
    ReconciliationConfig or a raw payload.
    """
    strategy: str
    amount_tolerance: Decimal
    date_tolerance_days: int
    max_group_size: int
    min_confidence: float
    max_suggestions: int
    log_all: bool

    @classmethod
    def from_data(cls, data: Dict[str, object]) -> "MatchConfig":
        strategy = (data.get("strategy") or "exact 1-to-1").lower()
        amount_tolerance = Decimal(str(data.get("amount_tolerance", "0")))
        date_tol = int(data.get("date_tolerance_days", 2))
        max_gsize = int(data.get("max_group_size", 1))
        min_conf = float(data.get("min_confidence", 0))
        max_sug = int(data.get("max_suggestions", 10000))
        log_all = bool(data.get("log_all") or os.getenv("RECON_LOG_ALL") == "1")
        return cls(
            strategy=strategy,
            amount_tolerance=amount_tolerance,
            date_tolerance_days=date_tol,
            max_group_size=max_gsize,
            min_confidence=min_conf,
            max_suggestions=max_sug,
            log_all=log_all,
        )


class ReconciliationService:
    """
    Service layer for reconciliation logic.  Provides methods to match
    bank transactions and journal entries using exact, fuzzy, or group
    matching strategies, with configuration-driven behaviour.
    """

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    @staticmethod
    def match_many_to_many(data: Dict[str, object], tenant_id: Optional[str] = None,
                           *, auto_match_100: bool = False) -> Dict[str, object]:
        """
        Orchestrates reconciliation matching strategies.  Returns a dict with
        suggestions and auto_match results.
        """
        cfg = MatchConfig.from_data(data)

        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])

        # Build candidate bank and journal entry lists
        bank_qs = BankTransaction.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        if bank_ids:
            bank_qs = bank_qs.filter(id__in=bank_ids)

        book_qs = JournalEntry.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        if book_ids:
            book_qs = book_qs.filter(transaction_id__in=book_ids)

        # Only consider journal entries that belong to a bank account account
        book_qs = book_qs.filter(account__bank_account__isnull=False)

        candidate_bank = list(bank_qs)
        candidate_book = list(book_qs)

        # Stats about candidate ranges
        def _qs_stats(bank_qs, book_qs):
            try:
                bank_min = bank_qs.order_by("date").values_list("date", flat=True).first()
                bank_max = bank_qs.order_by("-date").values_list("date", flat=True).first()
            except Exception:
                bank_min = bank_max = None
            try:
                book_min = book_qs.order_by("date").values_list("date", flat=True).first()
                book_max = book_qs.order_by("-date").values_list("date", flat=True).first()
            except Exception:
                book_min = book_max = None
            return bank_min, bank_max, book_min, book_max

        bank_min, bank_max, book_min, book_max = _qs_stats(bank_qs, book_qs)
        log.info(
            "[recon] candidates_qs bank_qs_count=%d book_qs_count=%d "
            "bank_date_min=%s bank_date_max=%s book_date_min=%s book_date_max=%s",
            len(candidate_bank), len(candidate_book),
            bank_min, bank_max, book_min, book_max
        )

        # Matching strategies
        exact_matches = []
        fuzzy_matches = []
        group_matches = []

        # Exact
        if cfg.strategy in ("exact 1-to-1", "exact", "optimized"):
            exact_matches, candidate_bank, candidate_book = ReconciliationService.get_exact_matches(
                candidate_bank, candidate_book, cfg.date_tolerance_days, log_all=cfg.log_all
            )
            log.info("[recon] exact_done exact=%d bank_left=%d book_left=%d",
                     len(exact_matches), len(candidate_bank), len(candidate_book))

        # Fuzzy
        if cfg.strategy in ("fuzzy", "optimized"):
            fuzzy_matches = ReconciliationService.get_fuzzy_matches(
                candidate_bank, candidate_book,
                cfg.amount_tolerance, cfg.date_tolerance_days, log_all=cfg.log_all
            )
            log.info("[recon] fuzzy_done fuzzy=%d", len(fuzzy_matches))

        # Group
        if cfg.strategy in ("many-to-many", "optimized") and cfg.max_group_size > 1:
            group_matches = ReconciliationService.get_group_matches(
                candidate_bank, candidate_book,
                cfg.amount_tolerance, cfg.date_tolerance_days,
                cfg.max_group_size, log_all=cfg.log_all
            )
            log.info("[recon] group_done groups=%d", len(group_matches))

        # Combine and filter by min confidence
        combined = [s for s in (exact_matches + fuzzy_matches + group_matches)
                    if float(s.get("confidence_score", 0)) >= cfg.min_confidence]

        # Sort by descending confidence
        combined.sort(key=lambda x: (-x["confidence_score"], x["difference"]))

        # Cap suggestions
        combined = combined[:cfg.max_suggestions]

        # Optionally auto-match perfect matches
        auto_info = {"enabled": bool(auto_match_100), "applied": 0, "skipped": 0, "details": []}
        if auto_match_100:
            auto_info = ReconciliationService._apply_auto_matches_100(combined, tenant_id)
            log.info("[recon] auto100 applied=%d skipped=%d",
                     auto_info["applied"], auto_info["skipped"])

        return {"suggestions": combined, "auto_match": auto_info}

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_exact_matches(banks: Iterable[BankTransaction], books: Iterable[JournalEntry],
                          date_tolerance_days: int, *, log_all: bool = False
                          ) -> Tuple[List[dict], List[BankTransaction], List[JournalEntry]]:
        """
        Attempt to match bank transactions and journal entries at a transaction level.
        A match occurs when the absolute amounts (quantized to two decimals) are exactly equal
        and the dates differ by no more than date_tolerance_days.
        Returns a tuple: matched_suggestions, remaining_banks, remaining_books.
        """
        exact_matches = []
        matched_bank_ids = set()
        matched_book_txn_ids = set()

        # Only consider journal entries whose account is linked to a bank account
        linked_account_ids = set(
            Account.objects.filter(bank_account__isnull=False).values_list("id", flat=True)
        )

        # Group journal entries by transaction_id (one transaction may have multiple lines)
        book_groups: Dict[int, List[JournalEntry]] = defaultdict(list)
        for entry in books:
            if entry.account_id in linked_account_ids:
                book_groups[entry.transaction_id].append(entry)

        # Evaluate each bank transaction against grouped book entries
        for bank_tx in banks:
            for txn_id, entries in book_groups.items():
                if txn_id in matched_book_txn_ids:
                    continue

                # Sum effective amounts for the transaction and pick representative date
                txn_sum = sum(
                    (e.get_effective_amount() or Decimal("0"))
                    for e in entries
                )
                book_date = entries[0].date or (
                    entries[0].transaction.date if entries[0].transaction else None
                )

                if _is_exact_match(bank_tx.amount, txn_sum, book_date, bank_tx.date, date_tolerance_days):
                    # Found a match
                    matched_bank_ids.add(bank_tx.id)
                    matched_book_txn_ids.add(txn_id)
                    exact_matches.append(
                        ReconciliationService.format_suggestion_output(
                            "1-to-1 Exact", [bank_tx], [entries[0]], confidence_score=1.0
                        )
                    )
                    break  # move to next bank_tx

                # Debug logging for mismatches
                if log_all:
                    amt_match = abs(_q2(bank_tx.amount)) == abs(_q2(txn_sum))
                    date_diff = (book_date and bank_tx.date
                                 and abs((bank_tx.date - book_date).days))
                    log.debug(
                        "[exact_try] bank_id=%s txn_id=%s bank_amt=%.2f txn_amt=%.2f "
                        "amt_match=%s date_diff=%s",
                        bank_tx.id, txn_id,
                        float(bank_tx.amount), float(txn_sum),
                        amt_match, date_diff
                    )

        # Build lists of remaining candidates
        remaining_banks = [tx for tx in banks if tx.id not in matched_bank_ids]
        remaining_books = [
            entry for entry in books if entry.transaction_id not in matched_book_txn_ids
        ]

        return exact_matches, remaining_banks, remaining_books

    @staticmethod
    def get_fuzzy_matches(banks: Iterable[BankTransaction], books: Iterable[JournalEntry],
                          amount_tolerance: Decimal, date_tolerance: int, *,
                          log_all: bool = False) -> List[dict]:
        """
        Match individual bank and journal entries when absolute amount differences and
        date differences are within tolerances.  A confidence score is computed from
        amount_diff and date_diff.  Returns sorted fuzzy suggestions.
        """
        fuzzy_matches: List[dict] = []

        for bank_tx in banks:
            for book_tx in books:
                bank_amt = _q2(bank_tx.amount)
                book_amt = _q2(book_tx.get_effective_amount())
                amount_diff = abs(bank_amt - book_amt)
                book_date = book_tx.date or (
                    book_tx.transaction.date if book_tx.transaction else None
                )
                if book_date is None or bank_tx.date is None:
                    continue
                date_diff = abs((bank_tx.date - book_date).days)

                if amount_diff <= amount_tolerance and date_diff <= date_tolerance:
                    conf = ReconciliationService.calculate_confidence(
                        amount_diff, date_diff, amount_tolerance, date_tolerance
                    )
                    fuzzy_matches.append(
                        ReconciliationService.format_suggestion_output(
                            "1-to-1 fuzzy", [bank_tx], [book_tx], conf
                        )
                    )

                if log_all:
                    log.debug(
                        "[fuzzy_try] bank_id=%s book_id=%s bank_amt=%.2f book_amt=%.2f "
                        "amount_diff=%.2f date_diff=%s",
                        bank_tx.id, book_tx.id,
                        float(bank_amt), float(book_amt),
                        float(amount_diff), date_diff
                    )

        # sort by confidence descending
        fuzzy_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
        return fuzzy_matches

    @staticmethod
    def get_group_matches(
        banks: Iterable[BankTransaction],
        books: Iterable[JournalEntry],
        amount_tolerance: Decimal,
        date_tolerance: int,
        max_group_size: int,
        *,
        log_all: bool = False
    ) -> List[dict]:
        """
        Many-to-many matching: for each bank transaction, build windows of bank/entry
        candidates within date tolerance, then evaluate all combinations up to max_group_size.
        A group match is valid when the absolute differences between summed bank and book
        amounts are within the tolerance and the date span is within tolerance.
        """
        group_matches: List[dict] = []
        seen_keys = set()

        sorted_banks = sorted(banks, key=lambda x: x.date)
        sorted_books = sorted(books, key=lambda x: x.date)

        bank_dates = [tx.date for tx in sorted_banks]
        book_dates = [ent.date for ent in sorted_books]

        for bank_tx in sorted_banks:
            start = bank_tx.date - timedelta(days=date_tolerance)
            end = bank_tx.date + timedelta(days=date_tolerance)

            # Build sliding windows
            b_start = bisect_left(bank_dates, start)
            b_end = bisect_right(bank_dates, end)
            bank_window = sorted_banks[b_start:b_end]

            bk_start = bisect_left(book_dates, start)
            bk_end = bisect_right(book_dates, end)
            book_window = sorted_books[bk_start:bk_end]

            # iterate combinations
            for i in range(1, min(len(bank_window), max_group_size) + 1):
                for bank_combo in combinations(bank_window, i):
                    sum_bank = sum(_q2(tx.amount) for tx in bank_combo)

                    for j in range(1, min(len(book_window), max_group_size) + 1):
                        for book_combo in combinations(book_window, j):
                            book_values = [e.get_effective_amount() for e in book_combo
                                           if e.get_effective_amount() is not None]
                            if not book_values:
                                continue
                            sum_book = sum(_q2(v) for v in book_values)
                            amount_diff = abs(sum_bank - sum_book)
                            if amount_diff > amount_tolerance:
                                continue

                            all_dates = [tx.date for tx in bank_combo] + [ent.date for ent in book_combo]
                            span = (max(all_dates) - min(all_dates)).days
                            if span > date_tolerance:
                                continue

                            # compute average date difference across cross-products
                            date_diffs = [
                                abs((b.date - e.date).days)
                                for b in bank_combo for e in book_combo
                            ]
                            avg_date_diff = sum(date_diffs) / len(date_diffs)
                            conf = ReconciliationService.calculate_confidence(
                                amount_diff, avg_date_diff, amount_tolerance, date_tolerance
                            )

                            key = (tuple(sorted(tx.id for tx in bank_combo)),
                                   tuple(sorted(ent.id for ent in book_combo)))
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)

                            group_matches.append(
                                ReconciliationService.format_suggestion_output(
                                    "many-to-many", list(bank_combo), list(book_combo), conf
                                )
                            )

        group_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
        return group_matches

    # ------------------------------------------------------------------
    # Auto-match persistence
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def _apply_auto_matches_100(suggestions: List[dict], tenant_id: Optional[str] = None,
                                *, status_value: str = "matched") -> dict:
        """
        Persist suggestions with confidence_score == 1.0 into Reconciliation records.
        This method is greedy and ensures no overlap between applied suggestions.
        """
        applied = 0
        skipped = 0
        details = []
        used_banks: set[int] = set()
        used_books: set[int] = set()
        reasons = Counter()

        for idx, s in enumerate(suggestions):
            if float(s.get("confidence_score", 0)) != 1.0:
                continue  # only auto-match perfect matches

            bank_ids = [int(b) for b in s.get("bank_ids", [])]
            book_ids = [int(j) for j in s.get("journal_entries_ids", [])]
            if not bank_ids or not book_ids:
                skipped += 1
                reasons["empty_ids"] += 1
                details.append({"reason": "empty_ids", "suggestion": s})
                continue
            if any(b in used_banks for b in bank_ids) or any(j in used_books for j in book_ids):
                skipped += 1
                reasons["overlap_in_batch"] += 1
                details.append({"reason": "overlap_in_batch", "suggestion": s})
                continue

            sp = transaction.savepoint()
            try:
                # check for existing matches in DB
                if BankTransaction.objects.filter(
                    id__in=bank_ids, reconciliations__status__in=["matched", "approved"]
                ).exists():
                    skipped += 1
                    reasons["already_matched_bank"] += 1
                    transaction.savepoint_commit(sp)
                    continue
                if JournalEntry.objects.filter(
                    id__in=book_ids, reconciliations__status__in=["matched", "approved"]
                ).exists():
                    skipped += 1
                    reasons["already_matched_book"] += 1
                    transaction.savepoint_commit(sp)
                    continue

                # lock rows
                bank_objs = list(BankTransaction.objects.select_for_update().filter(id__in=bank_ids))
                book_objs = list(JournalEntry.objects.select_for_update().filter(id__in=book_ids))

                # infer company; skip if ambiguous
                company_ids = {b.company_id for b in bank_objs if b.company_id} | \
                              {j.company_id for j in book_objs if j.company_id}
                if len(company_ids) != 1:
                    skipped += 1
                    reasons["company_unresolved"] += 1
                    transaction.savepoint_commit(sp)
                    continue
                company_id = next(iter(company_ids))

                # create Reconciliation
                recon = Reconciliation.objects.create(
                    status=status_value,
                    company_id=company_id,
                    notes="auto_match_100",
                )
                recon.bank_transactions.add(*bank_objs)
                recon.journal_entries.add(*book_objs)
                applied += 1
                used_banks.update(bank_ids)
                used_books.update(book_ids)
                details.append({
                    "reconciliation_id": recon.id,
                    "company_id": company_id,
                    "bank_ids": bank_ids,
                    "journal_entries_ids": book_ids,
                })
                transaction.savepoint_commit(sp)

            except Exception as exc:
                transaction.savepoint_rollback(sp)
                skipped += 1
                reasons["exception"] += 1
                details.append({"reason": "exception", "error": str(exc), "suggestion": s})

        return {
            "enabled": True,
            "applied": applied,
            "skipped": skipped,
            "reasons": dict(reasons),
            "details": details,
        }

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_confidence(amount_diff: Decimal | float,
                             date_diff: float, amount_tol: Decimal,
                             date_tol: int) -> float:
        """
        Compute a confidence score in [0,1] based on normalized differences.
        Weighted 70% on amount and 30% on date.
        """
        amt_tol = float(amount_tol or Decimal("0.01"))
        dt_tol = float(date_tol or 1)
        amt_score = max(0.0, 1 - float(amount_diff) / amt_tol)
        dt_score = max(0.0, 1 - float(date_diff) / dt_tol)
        return round(0.7 * amt_score + 0.3 * dt_score, 2)

    @staticmethod
    def format_suggestion_output(match_type: str,
                                 bank_combo: List[BankTransaction],
                                 book_combo: List[JournalEntry],
                                 confidence_score: float) -> dict:
        """
        Produce a suggestion dict summarizing a match.
        """
        sum_bank = sum(tx.amount for tx in bank_combo)
        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
        diff = abs(sum_bank - sum_book)
        date_diffs = [
            abs((tx.date - entry.date).days)
            for tx in bank_combo for entry in book_combo
        ]
        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0

        return {
            "match_type": match_type,
            "N bank": len(bank_combo),
            "N book": len(book_combo),
            "bank_ids": [tx.id for tx in bank_combo],
            "journal_entries_ids": [entry.id for entry in book_combo],
            "sum_bank": float(sum_bank),
            "sum_book": float(sum_book),
            "difference": float(diff),
            "avg_date_diff": avg_date_diff,
            "confidence_score": float(confidence_score),
            "bank_transaction_details": [
                {
                    "id": tx.id,
                    "date": tx.date.isoformat() if tx.date else None,
                    "amount": float(tx.amount) if tx.amount is not None else None,
                    "description": tx.description,
                    "tx_hash": tx.tx_hash,
                    "bank_account": {
                        "id": tx.bank_account.id,
                        "name": tx.bank_account.name,
                    } if tx.bank_account else None,
                    "entity": tx.entity.id if tx.entity else None,
                    "currency": tx.currency.id,
                }
                for tx in bank_combo
            ],
            "journal_entry_details": [
                {
                    "id": entry.id,
                    "date": entry.date.isoformat() if entry.date else None,
                    "amount": float(entry.get_effective_amount()) if entry.get_effective_amount() is not None else None,
                    "description": entry.transaction.description,
                    "account": {
                        "id": entry.account.id,
                        "account_code": entry.account.account_code,
                        "name": entry.account.name,
                    } if entry.account else None,
                    "transaction": {
                        "id": entry.transaction.id,
                        "entity": {
                            "id": entry.transaction.entity.id,
                            "name": entry.transaction.entity.name,
                        } if entry.transaction.entity else None,
                        "description": entry.transaction.description,
                        "date": entry.transaction.date.isoformat() if entry.transaction.date else None,
                    } if entry.transaction else None,
                }
                for entry in book_combo
            ],
        }
