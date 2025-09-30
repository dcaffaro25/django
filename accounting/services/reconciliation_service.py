from datetime import timedelta
from decimal import Decimal
from bisect import bisect_left, bisect_right
from itertools import product, combinations
from collections import defaultdict, Counter
from django.db import transaction
import logging

from accounting.models import BankTransaction, JournalEntry, Account, Reconciliation
from accounting.services.bank_structs import (
    ensure_pending_bank_structs,
    ensure_gl_account_for_bank,
)

log = logging.getLogger("recon")


class ReconciliationService:
    """
    Service layer for reconciliation logic.
    """

    # ---------- small helpers ----------
    @staticmethod
    def _dbg(tag, **k):
        parts = " ".join(f"{kk}={vv}" for kk, vv in k.items())
        log.debug("[%s] %s", tag, parts)

    @staticmethod
    def _info(tag, **k):
        parts = " ".join(f"{kk}={vv}" for kk, vv in k.items())
        log.info("[%s] %s", tag, parts)

    @staticmethod
    def _warn(tag, **k):
        parts = " ".join(f"{kk}={vv}" for kk, vv in k.items())
        log.warning("[%s] %s", tag, parts)

    # ---------- public orchestrator ----------
    @staticmethod
    def match_many_to_many_with_set2(data, tenant_id=None, *, auto_match_100=False):
        """
        Orchestrates reconciliation matching strategies.
        Returns dict with suggestions.
        """
        amount_tolerance = Decimal(str(data.get("amount_tolerance", "0")))
        date_tolerance_days = int(data.get("date_tolerance_days", 2))
        max_group_size = int(data.get("max_group_size", 1))
        strategy = (data.get("strategy") or "exact 1-to-1").lower()
        min_conf = float(data.get("min_confidence", 0))
        rule_id = data.get("rule_id")  # NEW LOG

        ReconciliationService._info(  # NEW LOG
            "run_start",
            rule_id=rule_id,
            strategy=strategy,
            amount_tolerance=amount_tolerance,
            date_tolerance_days=date_tolerance_days,
            max_group_size=max_group_size,
            min_conf=min_conf,
        )

        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])

        # ---------- candidates ----------
        candidate_bank = BankTransaction.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        if bank_ids:
            candidate_bank = candidate_bank.filter(id__in=bank_ids)

        candidate_book = JournalEntry.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        if book_ids:
            candidate_book = candidate_book.filter(transaction_id__in=book_ids)

        candidate_book = candidate_book.filter(account__bank_account__isnull=False)

        # NEW LOG: basic counts + date ranges + zero-effective stats
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

        bank_min, bank_max, book_min, book_max = _qs_stats(candidate_bank, candidate_book)

        ReconciliationService._info(
            "candidates_qs",
            bank_qs_count=candidate_bank.count(),
            book_qs_count=candidate_book.count(),
            bank_date_min=bank_min,
            bank_date_max=bank_max,
            book_date_min=book_min,
            book_date_max=book_max,
        )

        candidate_bank = list(candidate_bank)
        candidate_book = list(candidate_book)

        # NEW LOG: distribution and zero amounts in book lines
        zero_eff = 0
        nonzero_eff = 0
        for e in candidate_book:
            amt = e.get_effective_amount()
            if amt is None or Decimal(str(amt)) == 0:
                zero_eff += 1
            else:
                nonzero_eff += 1
        ReconciliationService._info(
            "book_effective_amount_stats", zeros=zero_eff, nonzeros=nonzero_eff
        )

        exact_matches = []
        fuzzy_matches = []
        group_matches = []

        if strategy in ["exact 1-to-1", "exact", "optimized"]:
            exact_matches, candidate_bank, candidate_book = ReconciliationService.get_exact_matches(
                candidate_bank, candidate_book, date_tolerance_days  # pass tol for logging
            )
            ReconciliationService._info(
                "exact_done", exact=len(exact_matches), bank_left=len(candidate_bank), book_left=len(candidate_book)
            )

        if strategy in ["fuzzy", "optimized"]:
            fuzzy_matches = ReconciliationService.get_fuzzy_matches(
                candidate_bank, candidate_book, amount_tolerance, date_tolerance_days
            )
            ReconciliationService._info("fuzzy_done", fuzzy=len(fuzzy_matches))

        if strategy in ["many-to-many", "optimized"] and max_group_size > 1:
            group_matches = ReconciliationService.get_group_matches(
                candidate_bank, candidate_book, amount_tolerance, date_tolerance_days, max_group_size
            )
            ReconciliationService._info("group_done", groups=len(group_matches))

        combined = [
            s for s in (exact_matches + fuzzy_matches + group_matches)
            if float(s.get("confidence_score", 0)) >= min_conf
        ]
        ReconciliationService._info("combined", total=len(combined))

        # NEW LOG: tail summary (helps see where things died)
        ReconciliationService._info(
            "summary",
            rule_id=rule_id,
            exact=len(exact_matches),
            fuzzy=len(fuzzy_matches),
            groups=len(group_matches),
            kept_after_min_conf=len(combined),
        )

        auto_info = {"enabled": bool(auto_match_100), "applied": 0, "skipped": 0, "details": []}
        if auto_match_100:
            auto_info = ReconciliationService._apply_auto_matches_100(combined, tenant_id)
            ReconciliationService._info("auto100", applied=auto_info["applied"], skipped=auto_info["skipped"])

        ReconciliationService._info("run_end", rule_id=rule_id)
        return {"suggestions": combined, "auto_match": auto_info}

    # ------------------------------------------------------------------
    # Strategy helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_exact_matches(banks, books, date_tolerance_for_info=2):
        ReconciliationService._info("exact_start", banks=len(banks), books=len(books))
        exact_matches = []
        matched_bank_ids = set()
        matched_book_transaction_ids = set()

        bank_account_linked_accounts = set(
            Account.objects.filter(bank_account__isnull=False).values_list("id", flat=True)
        )
        ReconciliationService._info("exact_accounts", linked_accounts=len(bank_account_linked_accounts))

        # group book lines per transaction for transaction-level sums
        book_transactions = defaultdict(list)
        for entry in books:
            if entry.account_id in bank_account_linked_accounts:
                book_transactions[entry.transaction.id].append(entry)

        # NEW LOG: show a few transaction-level sums so we know what exists
        preview = 0
        for txn_id, entries in book_transactions.items():
            t_sum = sum((e.debit_amount or Decimal("0")) - (e.credit_amount or Decimal("0")) for e in entries)
            if preview < 5:
                ReconciliationService._dbg(
                    "exact_txn_preview", txn_id=txn_id, n_lines=len(entries), txn_sum=t_sum
                )
                preview += 1

        # iterate
        near_reasons = Counter()  # NEW LOG
        for bank_tx in banks:
            for transaction_id, entries in book_transactions.items():
                if transaction_id in matched_book_transaction_ids:
                    continue

                transaction_amount = sum(
                    (e.debit_amount or Decimal("0")) - (e.credit_amount or Decimal("0"))
                    for e in entries
                )
                same_day = (entries[0].transaction.date == bank_tx.date)
                same_sign = ((transaction_amount > 0 and bank_tx.amount > 0) or
                             (transaction_amount < 0 and bank_tx.amount < 0))
                amt_match = (abs(transaction_amount) == abs(bank_tx.amount))

                if not (amt_match and same_day and same_sign):
                    # richer diagnostics
                    if amt_match and not same_day:
                        d = abs((entries[0].transaction.date - bank_tx.date).days)
                        near_reasons["same_day_false"] += 1
                        ReconciliationService._dbg(
                            "exact_reject_same_day",
                            bank_id=bank_tx.id,
                            txn_id=transaction_id,
                            bank_date=bank_tx.date,
                            book_date=entries[0].transaction.date,
                            date_diff_days=d,
                            would_pass_fuzzy=(d <= date_tolerance_for_info),
                        )
                    elif amt_match and not same_sign:
                        near_reasons["same_sign_false"] += 1
                        ReconciliationService._dbg(
                            "exact_reject_sign",
                            bank_id=bank_tx.id,
                            txn_id=transaction_id,
                            bank_amt=bank_tx.amount,
                            txn_amt=transaction_amount,
                        )
                    elif not amt_match:
                        delta = abs(abs(transaction_amount) - abs(bank_tx.amount))
                        near_reasons["amount_mismatch"] += 1
                        if delta <= Decimal("0.10"):
                            ReconciliationService._dbg(
                                "exact_near_amt",
                                bank_id=bank_tx.id, txn_id=transaction_id,
                                bank_amt=str(bank_tx.amount), book_amt=str(transaction_amount),
                            )
                    continue

                matched_bank_ids.add(bank_tx.id)
                matched_book_transaction_ids.add(transaction_id)
                exact_matches.append(
                    ReconciliationService.format_suggestion_output(
                        "1-to-1 Exact", [bank_tx], [entries[0]], confidence_score=1.0
                    )
                )
                break

        if near_reasons:
            ReconciliationService._info("exact_reject_counters", **near_reasons)

        ReconciliationService._info(
            "exact_end",
            exact=len(exact_matches),
            bank_left=sum(1 for tx in banks if tx.id not in matched_bank_ids),
            book_left=sum(1 for e in books if e.transaction.id not in matched_book_transaction_ids),
        )

        remaining_bank = [tx for tx in banks if tx.id not in matched_bank_ids]
        remaining_book = [entry for entry in books if entry.transaction.id not in matched_book_transaction_ids]
        return exact_matches, remaining_bank, remaining_book

    @staticmethod
    def get_fuzzy_matches(banks, books, amount_tolerance, date_tolerance):
        ReconciliationService._info(
            "fuzzy_start",
            banks=len(banks), books=len(books),
            amount_tol=str(amount_tolerance), date_tol=date_tolerance
        )
        fuzzy_matches = []
        best_for_bank_line = {}  # closest single line
        best_for_bank_txn = {}   # NEW LOG: closest transaction-level sum

        # Precompute transaction-level sums (same grouping rule as exact)
        bank_linked = set(Account.objects.filter(bank_account__isnull=False).values_list("id", flat=True))
        by_txn = defaultdict(list)
        for e in books:
            if e.account_id in bank_linked:
                by_txn[e.transaction_id].append(e)
        txn_sum = {}
        txn_date = {}
        for tid, entries in by_txn.items():
            s = sum((e.debit_amount or Decimal("0")) - (e.credit_amount or Decimal("0")) for e in entries)
            txn_sum[tid] = s
            # pick a representative date (transaction.date if present, else first line date)
            txn_date[tid] = entries[0].transaction.date if entries[0].transaction else (entries[0].date)

        # reason counters
        skip = Counter()

        for bank_tx in banks:
            # scan line-level
            for book_tx in books:
                bank_amt = bank_tx.amount
                book_amt = book_tx.get_effective_amount()

                if bank_amt is None or book_amt is None:
                    skip["amt_none"] += 1
                    continue

                book_date = book_tx.date or (book_tx.transaction.date if book_tx.transaction else None)
                if book_date is None or bank_tx.date is None:
                    skip["date_none"] += 1
                    continue

                amount_diff = abs(bank_amt - book_amt)
                date_diff = abs((bank_tx.date - book_date).days)

                # track closest line even if out of tol
                key = bank_tx.id
                prev = best_for_bank_line.get(key)
                score_tuple = (amount_diff, date_diff)
                if prev is None or score_tuple < prev[0]:
                    best_for_bank_line[key] = (score_tuple, {
                        "bank_id": bank_tx.id, "book_line_id": book_tx.id,
                        "bank_amt": str(bank_amt), "book_amt": str(book_amt),
                        "amount_diff": str(amount_diff), "date_diff": date_diff,
                        "bank_date": bank_tx.date, "book_date": book_date,
                    })

                if amount_diff > amount_tolerance:
                    skip["amt_outside_tol"] += 1
                    continue
                if date_diff > date_tolerance:
                    skip["date_outside_tol"] += 1
                    continue

                confidence = ReconciliationService.calculate_confidence(
                    amount_diff, date_diff, amount_tolerance, date_tolerance
                )
                fuzzy_matches.append(
                    ReconciliationService.format_suggestion_output(
                        "1-to-1 fuzzy", [bank_tx], [book_tx], confidence
                    )
                )

            # NEW LOG: check closest transaction-level combination for visibility
            # (We don't use it to match here—just to SEE if the right txn sum exists in range.)
            best_txn = None
            for tid, s in txn_sum.items():
                d = txn_date.get(tid)
                if d is None:
                    continue
                a_diff = abs(bank_tx.amount - s)
                dt_diff = abs((bank_tx.date - d).days) if bank_tx.date and d else 1_000_000
                tup = (a_diff, dt_diff)
                if best_txn is None or tup < best_txn[0]:
                    best_txn = (tup, {"txn_id": tid, "sum": s, "t_date": d, "a_diff": a_diff, "dt_diff": dt_diff})
            if best_txn:
                best_for_bank_txn[bank_tx.id] = best_txn[1]

        # Emit short digests (top ~20) — line-level
        for _, info in list(best_for_bank_line.values())[:20]:
            ReconciliationService._dbg("closest_line",
                bank_id=info["bank_id"], book_line_id=info["book_line_id"],
                bank_amt=info["bank_amt"], book_amt=info["book_amt"],
                amount_diff=info["amount_diff"], date_diff=info["date_diff"],
                bank_date=info["bank_date"], book_date=info["book_date"]
            )

        # Emit short digests (top ~20) — transaction-level **visibility**
        for bank_id, info in list(best_for_bank_txn.items())[:20]:
            ReconciliationService._dbg("closest_txn_sum",
                bank_id=bank_id, txn_id=info["txn_id"], txn_sum=str(info["sum"]),
                amount_diff=str(info["a_diff"]), date_diff=info["dt_diff"],
                txn_date=info["t_date"]
            )

        if skip:
            ReconciliationService._info("fuzzy_skip_counters", **skip)

        ReconciliationService._info("fuzzy_end", fuzzy=len(fuzzy_matches))
        fuzzy_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
        return fuzzy_matches

    @staticmethod
    def get_group_matches(banks, books, amount_tolerance, date_tolerance, max_group_size=2,
                          matcher=None, description_threshold=0.5, min_confidence_improvement=0.01):
        ReconciliationService._info(
            "group_start",
            banks=len(banks), books=len(books),
            amount_tol=str(amount_tolerance), date_tol=date_tolerance,
            max_group_size=max_group_size
        )
        group_matches = []
        seen_matches = set()
        counters = Counter()  # NEW LOG

        banks = sorted(banks, key=lambda x: x.date)
        books = sorted(books, key=lambda x: x.date)

        bank_dates = [tx.date for tx in banks]
        book_dates = [tx.date for tx in books]

        for bank_tx in banks:
            start_date = bank_tx.date - timedelta(days=date_tolerance)
            end_date = bank_tx.date + timedelta(days=date_tolerance)

            bank_start = bisect_left(bank_dates, start_date)
            bank_end = bisect_right(bank_dates, end_date)
            bank_group = banks[bank_start:bank_end]

            book_start = bisect_left(book_dates, start_date)
            book_end = bisect_right(book_dates, end_date)
            book_group = books[book_start:book_end]

            for i in range(1, min(len(bank_group), max_group_size) + 1):
                for bank_combo in combinations(bank_group, i):
                    sum_bank = sum(tx.amount for tx in bank_combo)

                    for j in range(1, min(len(book_group), max_group_size) + 1):
                        for book_combo in combinations(book_group, j):
                            book_amounts = [e.get_effective_amount() for e in book_combo if e.get_effective_amount() is not None]
                            if not book_amounts:
                                counters["empty_book_amounts"] += 1
                                continue
                            sum_book = sum(book_amounts)
                            amount_diff = abs(sum_bank - sum_book)
                            if round(amount_diff, 6) > amount_tolerance:
                                counters["amount_outside_tol"] += 1
                                # near misses for visibility
                                if amount_diff <= (amount_tolerance * 3 if amount_tolerance else Decimal("0.10")):
                                    ReconciliationService._dbg("group_amt_miss",
                                        bank_ids=[tx.id for tx in bank_combo],
                                        book_ids=[e.id for e in book_combo],
                                        sum_bank=str(sum_bank), sum_book=str(sum_book),
                                        amount_diff=str(amount_diff)
                                    )
                                continue

                            dates = [tx.date for tx in bank_combo] + [e.date for e in book_combo]
                            span = (max(dates) - min(dates)).days
                            if span > date_tolerance:
                                counters["date_span_outside_tol"] += 1
                                ReconciliationService._dbg("group_date_miss",
                                    bank_ids=[tx.id for tx in bank_combo],
                                    book_ids=[e.id for e in book_combo],
                                    span_days=span, date_tol=date_tolerance
                                )
                                continue

                            avg_date_diff = sum(
                                abs((tx.date - e.date).days) for tx in bank_combo for e in book_combo
                            ) / (len(bank_combo) * len(book_combo))

                            confidence = ReconciliationService.calculate_confidence(
                                amount_diff, avg_date_diff, amount_tolerance, date_tolerance
                            )

                            bank_ids = tuple(sorted(tx.id for tx in bank_combo))
                            book_ids = tuple(sorted(e.id for e in book_combo))
                            match_key = (bank_ids, book_ids)
                            if match_key in seen_matches:
                                counters["dup_seen"] += 1
                                continue
                            seen_matches.add(match_key)

                            group_matches.append(
                                ReconciliationService.format_suggestion_output(
                                    "many-to-many", bank_combo, book_combo, confidence
                                )
                            )

        if counters:
            ReconciliationService._info("group_skip_counters", **counters)

        ReconciliationService._info("group_end", groups=len(group_matches))
        group_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
        return group_matches

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_confidence(amount_diff, date_diff, amount_tol, date_tol):
        if amount_tol == 0:
            amount_tol = 0.01
        if date_tol == 0:
            date_tol = 1
        amount_score = max(0, 1 - float(amount_diff) / float(amount_tol))
        date_score = max(0, 1 - float(date_diff) / float(date_tol))
        return round(0.7 * amount_score + 0.3 * date_score, 2)

    @staticmethod
    def format_suggestion_output2(match_type, bank_combo, book_combo, confidence_score):
        sum_bank = sum(tx.amount for tx in bank_combo)
        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
        diff = abs(sum_bank - sum_book)

        return {
            "match_type": match_type,
            "N bank": len(bank_combo),
            "N book": len(book_combo),
            "bank_ids": [tx.id for tx in bank_combo],
            "journal_entries_ids": [entry.id for entry in book_combo],
            "sum_bank": float(sum_bank),
            "sum_book": float(sum_book),
            "difference": float(diff),
            "confidence_score": float(confidence_score),
        }

    @staticmethod
    def format_suggestion_output(match_type, bank_combo, book_combo, confidence_score):
        sum_bank = sum(tx.amount for tx in bank_combo)
        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
        diff = abs(sum_bank - sum_book)

        date_diffs = [
            abs((tx.date - entry.date).days)
            for tx in bank_combo
            for entry in book_combo
        ]
        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0

        bank_lines = []
        for tx in bank_combo:
            bank_lines.append(f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}")
        bank_summary = "\n".join(bank_lines)

        journal_lines = []
        for entry in book_combo:
            account_code = entry.account.account_code if entry.account else "N/A"
            account_name = entry.account.name if entry.account else "N/A"
            direction = "DEBIT" if entry.debit_amount else "CREDIT"
            journal_lines.append(
                f"ID: {entry.transaction.id}, Date: {entry.date}, JE: {direction} {entry.get_effective_amount()} - "
                f"({account_code}) {account_name}, Desc: {entry.transaction.description}"
            )
        journal_summary = "\n".join(journal_lines)

        return {
            "match_type": match_type,
            "N bank": len(bank_combo),
            "N book": len(book_combo),
            "bank_transaction_details": [{
                "id": tx.id,
                "date": tx.date.isoformat() if tx.date else None,
                "amount": float(tx.amount) if tx.amount is not None else None,
                "description": tx.description,
                "tx_hash": tx.tx_hash,
                "bank_account": {
                    "id": tx.bank_account.id,
                    "name": tx.bank_account.name
                } if tx.bank_account else None,
                "entity": tx.entity.id if tx.entity else None,
                "currency": tx.currency.id
            } for tx in bank_combo],

            "journal_entry_details": [{
                "id": entry.id,
                "date": entry.date.isoformat() if entry.date else None,
                "amount": float(entry.get_effective_amount()) if entry.get_effective_amount() is not None else None,
                "description": entry.transaction.description,
                "account": {
                    "id": entry.account.id,
                    "account_code": entry.account.account_code,
                    "name": entry.account.name
                } if entry.account else None,
                "transaction": {
                    "id": entry.transaction.id,
                    "entity": {
                        "id": entry.transaction.entity.id,
                        "name": entry.transaction.entity.name
                    } if entry.transaction.entity else None,
                    "description": entry.transaction.description,
                    "date": entry.transaction.date.isoformat() if entry.transaction.date else None
                } if entry.transaction else None
            } for entry in book_combo],
            "bank_transaction_summary": bank_summary,
            "journal_entries_summary": journal_summary,
            "bank_ids": [tx.id for tx in bank_combo],
            "journal_entries_ids": [entry.id for entry in book_combo],
            "sum_bank": float(sum_bank),
            "sum_book": float(sum_book),
            "difference": float(diff),
            "avg_date_diff": avg_date_diff,
            "confidence_score": float(confidence_score)
        }
