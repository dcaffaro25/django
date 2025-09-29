from datetime import timedelta
from decimal import Decimal
from bisect import bisect_left, bisect_right
from itertools import product, combinations
from collections import defaultdict
from django.db import transaction

from accounting.models import BankTransaction, JournalEntry, Account, Reconciliation
from accounting.services.bank_structs import (
    ensure_pending_bank_structs,
    ensure_gl_account_for_bank,
)

class ReconciliationService:
    """
    Service layer for reconciliation logic.
    """

    @staticmethod
    def match_many_to_many_with_set2(data, tenant_id=None, *, auto_match_100=False):
        """
        Orchestrates reconciliation matching strategies.
        Returns dict with suggestions.
        """
        amount_tolerance = Decimal(str(data.get("amount_tolerance", "0")))
        date_tolerance_days = int(data.get("date_tolerance_days", 2))
        #max_suggestions = int(data.get("max_suggestions", 5))
        max_group_size = int(data.get("max_group_size", 1))
        strategy = data.get("strategy", "Exact 1-to-1")

        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])

        candidate_bank = BankTransaction.objects.exclude(
            reconciliations__status__in=['matched', 'approved']
        )
        if bank_ids:
            candidate_bank = candidate_bank.filter(id__in=bank_ids)

        candidate_book = JournalEntry.objects.exclude(
            reconciliations__status__in=['matched', 'approved']
        )
        if book_ids:
            candidate_book = candidate_book.filter(transaction_id__in=book_ids)

        candidate_book = candidate_book.filter(account__bank_account__isnull=False)

        candidate_bank = list(candidate_bank)
        candidate_book = list(candidate_book)

        exact_matches = []
        fuzzy_matches = []
        group_matches = []

        if strategy in ["exact 1-to-1", "optimized"]:
            exact_matches, candidate_bank, candidate_book = ReconciliationService.get_exact_matches(
                candidate_bank, candidate_book
            )
        if strategy in ["fuzzy", "optimized"]:
            fuzzy_matches = ReconciliationService.get_fuzzy_matches(
                candidate_bank, candidate_book, amount_tolerance, date_tolerance_days
            )
        if strategy in ["many-to-many", "optimized"] and max_group_size>1 :
            group_matches = ReconciliationService.get_group_matches(
                candidate_bank, candidate_book, amount_tolerance, date_tolerance_days, max_group_size
            )

        #combined = (exact_matches + fuzzy_matches + group_matches)#[:max_suggestions]
        
        min_conf = float(data.get("min_confidence", 0))
        combined = [s for s in (exact_matches + fuzzy_matches + group_matches)
                    if float(s.get("confidence_score", 0)) >= min_conf]
        
        auto_info = {"enabled": bool(auto_match_100), "applied": 0, "skipped": 0, "details": []}
        if auto_match_100:
            auto_info = ReconciliationService._apply_auto_matches_100(combined, tenant_id)

        return {"suggestions": combined, "auto_match": auto_info}
    
    @staticmethod
    @transaction.atomic
    def _apply_auto_matches_100(suggestions, tenant_id=None, *, status_value="matched"):
        """
        Persist suggestions with confidence_score == 1.0 using the group-style
        Reconciliation model (M2M to bank/journal).
    
        - Greedy & non-overlapping within this pass (no bank/journal id reused).
        - Skip if any involved objs already matched/approved.
        - Infer company_id from involved objs; skip if mixed/unresolved.
        - Per-suggestion savepoint so one failure doesn't abort the batch.
        """
        applied, skipped = 0, 0
        details = []
        used_bank, used_book = set(), set()
    
        for s in suggestions:
            # only perfect matches
            if float(s.get("confidence_score", 0)) != 1.0:
                continue
    
            # gather ids (flat or from details)
            bank_ids = s.get("bank_ids") or []
            book_ids = s.get("journal_entries_ids") or []
            if not bank_ids and s.get("bank_transaction_details"):
                bank_ids = [x.get("id") for x in s["bank_transaction_details"]]
            if not book_ids and s.get("journal_entry_details"):
                book_ids = [x.get("id") for x in s["journal_entry_details"]]
    
            bank_ids = list({int(b) for b in (bank_ids or []) if b is not None})
            book_ids = list({int(j) for j in (book_ids or []) if j is not None})
    
            if not bank_ids or not book_ids:
                skipped += 1
                details.append({"reason": "empty_ids", "suggestion": s})
                continue
    
            # intra-batch overlap?
            if any(b in used_bank for b in bank_ids) or any(j in used_book for j in book_ids):
                skipped += 1
                details.append({"reason": "overlap_in_batch", "suggestion": s})
                continue
    
            # per-suggestion savepoint
            sp = transaction.savepoint()
            try:
                # quick conflict check WITHOUT locks (avoids FOR UPDATE oddities)
                if BankTransaction.objects.filter(
                    id__in=bank_ids, reconciliations__status__in=['matched', 'approved']
                ).exists() or JournalEntry.objects.filter(
                    id__in=book_ids, reconciliations__status__in=['matched', 'approved']
                ).exists():
                    skipped += 1
                    details.append({"reason": "already_matched_in_db", "suggestion": s})
                    transaction.savepoint_commit(sp)
                    continue
    
                # lock the rows we will attach (no DISTINCT)
                bank_objs = list(BankTransaction.objects.select_for_update().filter(id__in=bank_ids))
                book_objs = list(JournalEntry.objects.select_for_update().filter(id__in=book_ids))
    
                # infer single company (collect in Python; no DISTINCT in SQL)
                company_set = {b.company_id for b in bank_objs if b.company_id is not None} | \
                              {j.company_id for j in book_objs if j.company_id is not None}
    
                if not company_set:
                    skipped += 1
                    details.append({"reason": "company_unresolved", "suggestion": s})
                    transaction.savepoint_commit(sp)
                    continue
                if len(company_set) > 1:
                    skipped += 1
                    details.append({"reason": "mixed_company", "companies": list(company_set), "suggestion": s})
                    transaction.savepoint_commit(sp)
                    continue
    
                company_id = next(iter(company_set))
    
                # create reconciliation and attach M2Ms
                recon = Reconciliation.objects.create(
                    status=status_value,
                    notes="auto_match_100",
                    company_id=company_id,
                )
                # attach locked objs
                recon.bank_transactions.add(*bank_objs)
                recon.journal_entries.add(*book_objs)
    
                applied += 1
                used_bank.update(bank_ids)
                used_book.update(book_ids)
                details.append({
                    "reconciliation_id": recon.id,
                    "company_id": company_id,
                    "bank_ids": bank_ids,
                    "journal_entries_ids": book_ids
                })
    
                transaction.savepoint_commit(sp)
    
            except Exception as e:
                transaction.savepoint_rollback(sp)
                skipped += 1
                details.append({"reason": "exception", "error": str(e), "suggestion": s})
    
        return {"enabled": True, "applied": applied, "skipped": skipped, "details": details}
    # ------------------------------------------------------------------
    # Strategy helpers
    # ------------------------------------------------------------------
    
    @staticmethod
    def get_exact_matches(banks, books):
        exact_matches = []
        matched_bank_ids = set()
        matched_book_transaction_ids = set()

        bank_account_linked_accounts = set(
            Account.objects.filter(bank_account__isnull=False).values_list('id', flat=True)
        )

        book_transactions = defaultdict(list)
        for entry in books:
            if entry.account_id in bank_account_linked_accounts:
                book_transactions[entry.transaction.id].append(entry)

        for bank_tx in banks:
            for transaction_id, entries in book_transactions.items():
                if transaction_id in matched_book_transaction_ids:
                    continue

                transaction_amount = sum(
                    (e.debit_amount or Decimal('0')) - (e.credit_amount or Decimal('0'))
                    for e in entries
                )

                if abs(transaction_amount) == abs(bank_tx.amount) and entries[0].transaction.date == bank_tx.date:
                    if (transaction_amount > 0 and bank_tx.amount > 0) or (transaction_amount < 0 and bank_tx.amount < 0):
                        matched_bank_ids.add(bank_tx.id)
                        matched_book_transaction_ids.add(transaction_id)

                        exact_matches.append(
                            ReconciliationService.format_suggestion_output(
                                "1-to-1 Exact",
                                [bank_tx],
                                [entries[0]],
                                confidence_score=1.0,
                            )
                        )
                        break

        remaining_bank = [tx for tx in banks if tx.id not in matched_bank_ids]
        remaining_book = [entry for entry in books if entry.transaction.id not in matched_book_transaction_ids]

        return exact_matches, remaining_bank, remaining_book

    @staticmethod
    def get_fuzzy_matches(banks, books, amount_tolerance, date_tolerance):
        fuzzy_matches = []
    
        for bank_tx, book_tx in product(banks, books):
            amount_diff = abs(bank_tx.amount - book_tx.get_effective_amount())
    
            # ✅ compare against JournalEntry.date (fallback to Transaction.date)
            book_date = book_tx.date or (book_tx.transaction.date if book_tx.transaction else None)
            if book_date is None or bank_tx.date is None:
                continue  # or decide a default behavior
    
            date_diff = abs((bank_tx.date - book_date).days)
    
            if amount_diff <= amount_tolerance and date_diff <= date_tolerance:
                confidence = ReconciliationService.calculate_confidence(
                    amount_diff, date_diff, amount_tolerance, date_tolerance
                )
                fuzzy_matches.append(
                    ReconciliationService.format_suggestion_output(
                        "1-to-1 fuzzy", [bank_tx], [book_tx], confidence
                    )
                )
    
        fuzzy_matches.sort(key=lambda x: x['confidence_score'], reverse=True)
        return fuzzy_matches

    @staticmethod
    def get_group_matches(banks, books, amount_tolerance, date_tolerance, max_group_size=2,
                          matcher=None, description_threshold=0.5, min_confidence_improvement=0.01):
        group_matches = []
        seen_matches = set()
        atomic_matches = {}

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
                            book_amounts = [
                                e.get_effective_amount() for e in book_combo
                                if e.get_effective_amount() is not None
                            ]
                            if not book_amounts:
                                continue
                            sum_book = sum(book_amounts)
                            amount_diff = abs(sum_bank - sum_book)
                            if round(amount_diff, 6) > amount_tolerance:
                                continue

                            dates = [tx.date for tx in bank_combo] + [e.date for e in book_combo]
                            if (max(dates) - min(dates)).days > date_tolerance:
                                continue

                            avg_date_diff = sum(
                                abs((tx.date - e.date).days)
                                for tx in bank_combo for e in book_combo
                            ) / (len(bank_combo) * len(book_combo))

                            confidence = ReconciliationService.calculate_confidence(
                                amount_diff, avg_date_diff, amount_tolerance, date_tolerance
                            )

                            bank_ids = tuple(sorted(tx.id for tx in bank_combo))
                            book_ids = tuple(sorted(e.id for e in book_combo))
                            match_key = (bank_ids, book_ids)

                            if match_key in seen_matches:
                                continue
                            seen_matches.add(match_key)

                            group_matches.append(
                                ReconciliationService.format_suggestion_output(
                                    "many-to-many", bank_combo, book_combo, confidence
                                )
                            )

        group_matches.sort(key=lambda x: x['confidence_score'], reverse=True)
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
    
        # Média das diferenças de datas entre os pares
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
        #bank_summary = f"{[ID: tx.id, Date: tx.date, Amount: tx.amount, Desc: tx.description for tx in bank_combo]}"
        #journal_summary = f"IDs: {[entry.id for entry in book_combo]}, Total: {sum_book:.2f}"
        
        #bank_summary = f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}"
        
        journal_lines = []
        for entry in book_combo:
            account_code = entry.account.account_code if entry.account else 'N/A'
            account_name = entry.account.name if entry.account else 'N/A'
            direction = 'DEBIT' if entry.debit_amount else 'CREDIT'
            journal_lines.append(f"ID: {entry.transaction.id}, Date: {entry.date}, JE: {direction} {entry.get_effective_amount()} - ({account_code}) {account_name}, Desc: {entry.transaction.description}")
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
            
            "journal_entry_details":[{
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
    