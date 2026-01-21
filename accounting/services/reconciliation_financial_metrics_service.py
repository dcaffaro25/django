"""
reconciliation_financial_metrics_service.py

Service for calculating and storing financial metrics for transactions and journal entries
based on their bank reconciliation relationships.

Metrics are calculated from journal entries and aggregated to transaction level.
All metrics are read-only (system calculated only).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set
from django.db import transaction
from django.db.models import Q, Avg, Sum, Count, Max, Min, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models import (
    Transaction,
    JournalEntry,
    BankTransaction,
    Reconciliation,
    Account,
)

log = logging.getLogger(__name__)


class ReconciliationFinancialMetricsService:
    """Service for calculating and storing reconciliation-based financial metrics."""
    
    # Tolerance for "exact" matches (in currency units)
    AMOUNT_TOLERANCE = Decimal('0.01')
    # Tolerance for date matches (in days)
    DATE_TOLERANCE_DAYS = 2
    
    def __init__(self):
        self.stats = {
            'transactions_processed': 0,
            'journal_entries_processed': 0,
            'metrics_calculated': 0,
            'errors': [],
        }
    
    def calculate_journal_entry_metrics(self, journal_entry: JournalEntry) -> Dict[str, Any]:
        """
        Calculate reconciliation metrics for a single journal entry.
        
        Returns a dictionary of calculated metrics:
        - payment_day_delta: Days between transaction date and bank date (if reconciled)
        - journal_entry_date_delta: Days between JE date and bank date
        - amount_discrepancy: Difference between JE effective amount (considering account direction) and bank amount
        - is_exact_match: Whether amounts match exactly (within tolerance)
        - is_date_match: Whether dates match (within tolerance)
        - is_perfect_match: Both amount and date match
        - reconciliation_id: ID of the reconciliation (if any)
        - bank_transaction_id: ID of the matched bank transaction (if any)
        """
        metrics = {
            'payment_day_delta': None,
            'journal_entry_date_delta': None,
            'bank_payment_date_delta': None,  # Only for cash accounts when bank_reconciled
            'amount_discrepancy': None,  # Financial difference in value (2 decimal places)
            'is_exact_match': False,
            'is_date_match': False,
            'is_perfect_match': False,
            'reconciliation_id': None,
            'bank_transaction_id': None,
            'reconciliation_status': None,
        }
        
        # Get reconciliations for this journal entry
        reconciliations = journal_entry.reconciliations.filter(
            status__in=['matched', 'approved']
        ).select_related().prefetch_related('bank_transactions')
        
        if not reconciliations.exists():
            return metrics
        
        # Use the most recent approved reconciliation, or the most recent matched one
        reconciliation = reconciliations.filter(status='approved').first()
        if not reconciliation:
            reconciliation = reconciliations.order_by('-id').first()
        
        if not reconciliation:
            return metrics
        
        metrics['reconciliation_id'] = reconciliation.id
        metrics['reconciliation_status'] = reconciliation.status
        
        # Get related bank transactions
        bank_transactions = reconciliation.bank_transactions.all()
        if not bank_transactions.exists():
            return metrics
        
        # For multiple bank transactions, use weighted average date and sum amounts
        total_bank_amount = sum(bt.amount for bt in bank_transactions)
        # Use effective amount (considering account direction and debits/credits)
        # For accounts with direction=1 (debits increase, like cash), debits are positive
        # For accounts with direction=-1 (credits increase), credits are positive
        je_amount = journal_entry.get_effective_amount()
        
        if je_amount is None or total_bank_amount is None:
            return metrics
        
        # Payment metrics are only calculated for journal entries linked to reconciliations
        # Calculate date deltas (only if reconciled)
        # Weight bank transaction dates by amount for average
        total_weight = Decimal('0')
        weighted_date_sum = Decimal('0')
        earliest_bank_date = None
        latest_bank_date = None
        
        for bt in bank_transactions:
            amount_weight = abs(bt.amount)
            total_weight += amount_weight
            # Convert date to days since epoch for weighted calculation
            days_since_epoch = (bt.date - date(1970, 1, 1)).days
            weighted_date_sum += amount_weight * Decimal(str(days_since_epoch))
            
            if earliest_bank_date is None or bt.date < earliest_bank_date:
                earliest_bank_date = bt.date
            if latest_bank_date is None or bt.date > latest_bank_date:
                latest_bank_date = bt.date
        
        if total_weight > 0:
            avg_bank_date_days = weighted_date_sum / total_weight
            avg_bank_date = date(1970, 1, 1) + timedelta(days=int(avg_bank_date_days))
        else:
            avg_bank_date = earliest_bank_date if earliest_bank_date else None
        
        # Payment metrics - only calculate when reconciled
        if avg_bank_date:
            if journal_entry.transaction and journal_entry.transaction.date:
                payment_delta = (avg_bank_date - journal_entry.transaction.date).days
                metrics['payment_day_delta'] = payment_delta
            
            if journal_entry.date:
                je_date_delta = (avg_bank_date - journal_entry.date).days
                metrics['journal_entry_date_delta'] = je_date_delta
            
            # Bank payment date delta: only for journal entries hitting cash accounts (bank accounts) that are bank_reconciled
            # Compare journal entry date (est payment date) to bank transaction date
            # Only calculate if: 1) journal entry has a date, 2) journal entry is bank_reconciled, 3) journal entry hits a cash account
            if journal_entry.date and journal_entry.is_reconciled:
                # Check if this journal entry hits a cash account (account has bank_account relationship)
                # Reload account to ensure we have bank_account_id
                if journal_entry.account_id:
                    account = journal_entry.account
                    if account and account.bank_account_id:
                        bank_payment_delta = (avg_bank_date - journal_entry.date).days
                        metrics['bank_payment_date_delta'] = bank_payment_delta
        
        # Amount discrepancy (only for reconciled entries)
        # Store only the financial difference in value (2 decimal places), not percentage
        amount_discrepancy = total_bank_amount - je_amount
        metrics['amount_discrepancy'] = amount_discrepancy
        
        # Accuracy flags (only meaningful when reconciled)
        metrics['is_exact_match'] = abs(amount_discrepancy) <= self.AMOUNT_TOLERANCE
        metrics['is_date_match'] = abs(metrics.get('journal_entry_date_delta', 999)) <= self.DATE_TOLERANCE_DAYS if metrics.get('journal_entry_date_delta') is not None else False
        metrics['is_perfect_match'] = metrics['is_exact_match'] and metrics['is_date_match']
        
        # Get primary bank transaction ID (first one, or largest amount)
        if bank_transactions:
            primary_bt = max(bank_transactions, key=lambda bt: abs(bt.amount))
            metrics['bank_transaction_id'] = primary_bt.id
        
        return metrics
    
    def store_journal_entry_metrics(self, journal_entry: JournalEntry, metrics: Dict[str, Any]) -> None:
        """Store calculated metrics to the journal entry model fields."""
        from django.utils import timezone
        
        update_fields = []
        
        # Map metrics dict keys to model field names
        # Note: amount_discrepancy_percentage is not stored - only the value difference (amount_discrepancy)
        field_mapping = {
            'payment_day_delta': 'payment_day_delta',
            'journal_entry_date_delta': 'journal_entry_date_delta',
            'bank_payment_date_delta': 'bank_payment_date_delta',  # Only for cash accounts when bank_reconciled
            'amount_discrepancy': 'amount_discrepancy',  # Financial difference in value (2 decimal places)
            'is_exact_match': 'is_exact_match',
            'is_date_match': 'is_date_match',
            'is_perfect_match': 'is_perfect_match',
        }
        
        for metric_key, field_name in field_mapping.items():
            if metric_key in metrics:
                setattr(journal_entry, field_name, metrics[metric_key])
                update_fields.append(field_name)
        
        # Store account verification metrics
        account_verification = self.verify_account_assignment(journal_entry)
        if 'confidence_score' in account_verification:
            journal_entry.account_confidence_score = account_verification['confidence_score']
            update_fields.append('account_confidence_score')
        if 'historical_matches' in account_verification:
            journal_entry.account_historical_matches = account_verification['historical_matches']
            update_fields.append('account_historical_matches')
        
        # Update calculation timestamp
        journal_entry.metrics_last_calculated_at = timezone.now()
        update_fields.append('metrics_last_calculated_at')
        
        if update_fields:
            journal_entry.save(update_fields=update_fields)
    
    def store_transaction_metrics(self, transaction: Transaction, metrics: Dict[str, Any]) -> None:
        """Store calculated metrics to the transaction model fields."""
        from django.utils import timezone
        
        update_fields = []
        
        # Map metrics dict keys to model field names
        field_mapping = {
            'avg_payment_day_delta': 'avg_payment_day_delta',
            'min_payment_day_delta': 'min_payment_day_delta',
            'max_payment_day_delta': 'max_payment_day_delta',
            'avg_bank_payment_date_delta': 'avg_bank_payment_date_delta',
            'min_bank_payment_date_delta': 'min_bank_payment_date_delta',
            'max_bank_payment_date_delta': 'max_bank_payment_date_delta',
            'total_amount_discrepancy': 'total_amount_discrepancy',
            'avg_amount_discrepancy': 'avg_amount_discrepancy',
            'exact_match_count': 'exact_match_count',
            'perfect_match_count': 'perfect_match_count',
            'reconciliation_rate': 'reconciliation_rate',
            'days_outstanding': 'days_outstanding',
        }
        
        for metric_key, field_name in field_mapping.items():
            if metric_key in metrics:
                setattr(transaction, field_name, metrics[metric_key])
                update_fields.append(field_name)
        
        # Update calculation timestamp
        transaction.metrics_last_calculated_at = timezone.now()
        update_fields.append('metrics_last_calculated_at')
        
        if update_fields:
            transaction.save(update_fields=update_fields)
    
    def calculate_transaction_metrics(self, transaction: Transaction) -> Dict[str, Any]:
        """
        Calculate aggregated reconciliation metrics for a transaction
        by aggregating metrics from its journal entries.
        
        Payment metrics (payment_day_delta, amount_discrepancy, etc.) are only
        aggregated from journal entries that are linked to reconciliations.
        
        Returns aggregated metrics:
        - avg_payment_day_delta: Average payment delay across reconciled JEs only
        - min_payment_day_delta: Minimum payment delay (from reconciled JEs only)
        - max_payment_day_delta: Maximum payment delay (from reconciled JEs only)
        - avg_bank_payment_date_delta: Average bank payment date delta (JE est date vs bank date) for JEs hitting cash accounts
        - min_bank_payment_date_delta: Minimum bank payment date delta for JEs hitting cash accounts
        - max_bank_payment_date_delta: Maximum bank payment date delta for JEs hitting cash accounts
        - total_amount_discrepancy: Sum of discrepancies from reconciled JEs only
        - avg_amount_discrepancy: Average discrepancy (from reconciled JEs only)
        - exact_match_count: Number of reconciled JEs with exact amount matches
        - perfect_match_count: Number of reconciled JEs with perfect matches
        - reconciliation_rate: Percentage of JEs that are reconciled
        - reconciled_je_count: Count of reconciled journal entries
        - total_je_count: Total journal entry count
        """
        metrics = {
            'avg_payment_day_delta': None,
            'min_payment_day_delta': None,
            'max_payment_day_delta': None,
            'avg_bank_payment_date_delta': None,
            'min_bank_payment_date_delta': None,
            'max_bank_payment_date_delta': None,
            'total_amount_discrepancy': Decimal('0'),
            'avg_amount_discrepancy': None,
            'exact_match_count': 0,
            'perfect_match_count': 0,
            'reconciliation_rate': Decimal('0'),
            'reconciled_je_count': 0,
            'total_je_count': 0,
            'days_outstanding': None,
            'first_reconciliation_date': None,
        }
        
        journal_entries = transaction.journal_entries.all().prefetch_related(
            'reconciliations__bank_transactions'
        )
        
        total_je_count = journal_entries.count()
        metrics['total_je_count'] = total_je_count
        
        if total_je_count == 0:
            return metrics
        
        # Collect metrics from journal entries
        # Payment metrics: only from reconciled journal entries
        payment_deltas = []
        bank_payment_date_deltas = []  # Only from journal entries hitting cash accounts
        amount_discrepancies = []
        exact_matches = 0
        perfect_matches = 0
        reconciled_count = 0
        first_reconciliation_date = None
        
        for je in journal_entries:
            je_metrics = self.calculate_journal_entry_metrics(je)
            
            # Only collect payment metrics from reconciled journal entries
            if je_metrics.get('reconciliation_id'):
                reconciled_count += 1
                
                # Collect payment deltas (only for reconciled entries)
                if je_metrics.get('payment_day_delta') is not None:
                    payment_deltas.append(je_metrics['payment_day_delta'])
                
                # Collect bank payment date deltas (only for journal entries hitting cash accounts)
                # This is the delta between JE est payment date and bank transaction date
                if je_metrics.get('bank_payment_date_delta') is not None:
                    bank_payment_date_deltas.append(je_metrics['bank_payment_date_delta'])
                
                # Collect amount discrepancies (only for reconciled entries)
                if je_metrics.get('amount_discrepancy') is not None:
                    amount_discrepancies.append(je_metrics['amount_discrepancy'])
                    metrics['total_amount_discrepancy'] += je_metrics['amount_discrepancy']
                
                # Count matches (only for reconciled entries)
                if je_metrics.get('is_exact_match'):
                    exact_matches += 1
                if je_metrics.get('is_perfect_match'):
                    perfect_matches += 1
                
                # Get reconciliation date
                recon = Reconciliation.objects.filter(id=je_metrics['reconciliation_id']).first()
                if recon:
                    recon_date = recon.updated_at.date() if hasattr(recon, 'updated_at') else recon.created_at.date() if hasattr(recon, 'created_at') else None
                    if recon_date:
                        if first_reconciliation_date is None or recon_date < first_reconciliation_date:
                            first_reconciliation_date = recon_date
        
        # Aggregate payment deltas (only from reconciled entries)
        if payment_deltas:
            metrics['avg_payment_day_delta'] = Decimal(str(sum(payment_deltas) / len(payment_deltas)))
            metrics['min_payment_day_delta'] = min(payment_deltas)
            metrics['max_payment_day_delta'] = max(payment_deltas)
        
        # Aggregate bank payment date deltas (only from journal entries hitting cash accounts)
        if bank_payment_date_deltas:
            metrics['avg_bank_payment_date_delta'] = Decimal(str(sum(bank_payment_date_deltas) / len(bank_payment_date_deltas)))
            metrics['min_bank_payment_date_delta'] = min(bank_payment_date_deltas)
            metrics['max_bank_payment_date_delta'] = max(bank_payment_date_deltas)
        
        # Aggregate amount discrepancies (only from reconciled entries)
        if amount_discrepancies:
            metrics['avg_amount_discrepancy'] = metrics['total_amount_discrepancy'] / Decimal(str(len(amount_discrepancies)))
        
        # Match counts (only from reconciled entries)
        metrics['exact_match_count'] = exact_matches
        metrics['perfect_match_count'] = perfect_matches
        
        # Reconciliation rate
        if total_je_count > 0:
            metrics['reconciliation_rate'] = (Decimal(str(reconciled_count)) / Decimal(str(total_je_count))) * Decimal('100')
        metrics['reconciled_je_count'] = reconciled_count
        
        # Days outstanding (from transaction date to first reconciliation)
        if first_reconciliation_date and transaction.date:
            metrics['days_outstanding'] = (first_reconciliation_date - transaction.date).days
        metrics['first_reconciliation_date'] = first_reconciliation_date
        
        return metrics
    
    def verify_account_assignment(self, journal_entry: JournalEntry) -> Dict[str, Any]:
        """
        Verify account assignment based on historical transactions.
        
        Checks if the account assigned to this journal entry matches
        patterns from historical transactions (same company, entity, exact description).
        
        The query excludes the current journal entry to avoid self-matching.
        Only exact description matches are considered (no date or amount checks).
        
        Returns:
        - confidence_score: How confident we are in the assignment (0-1)
        - historical_matches: Count of historical transactions with same account and description
        - suggested_account_id: Most common account from history (if different)
        - match_reasons: List of reasons for confidence
        """
        result = {
            'confidence_score': Decimal('0'),
            'historical_matches': 0,
            'suggested_account_id': None,
            'match_reasons': [],
        }
        
        if not journal_entry.account_id or not journal_entry.transaction_id:
            return result
        
        tx = journal_entry.transaction
        if not tx:
            return result
        
        # Build base query for historical transactions
        # Same company, same entity, has an account assigned
        # Excludes the current journal entry (id != journal_entry.id) to avoid self-matching
        base_qs = JournalEntry.objects.filter(
            transaction__company=tx.company,
            transaction__entity=tx.entity,
            account__isnull=False,
        ).exclude(id=journal_entry.id)
        
        # Exact description match only
        if tx.description:
            exact_desc_matches = base_qs.filter(
                transaction__description__iexact=tx.description
            ).values('account_id').annotate(
                count=Count('id'),
                last_used=Max('transaction__date')
            ).order_by('-count')[:10]
            
            if exact_desc_matches:
                top_match = exact_desc_matches[0]
                if top_match['account_id'] == journal_entry.account_id:
                    result['historical_matches'] += top_match['count']
                    result['confidence_score'] = Decimal('1.0')  # Full confidence for exact description match
                    result['match_reasons'].append('exact_description_match')
                else:
                    result['suggested_account_id'] = top_match['account_id']
        
        return result
    
    def recalculate_metrics(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        company_id: Optional[int] = None,
        entity_id: Optional[int] = None,
        account_id: Optional[int] = None,
        transaction_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Recalculate metrics for unposted (pending) transactions and journal entries matching the filters.
        
        Also recalculates transaction and journal entry flags:
        - is_balanced, is_reconciled, state, is_posted (for transactions)
        - is_cash, is_reconciled (for journal entries)
        
        Only processes transactions and journal entries with state='pending'.
        Posted transactions and journal entries are excluded from recalculation.
        
        Parameters:
        - start_date: Required start date for filtering
        - end_date: Optional end date (defaults to today if not provided)
        - company_id: Optional company filter
        - entity_id: Optional entity filter
        - account_id: Optional account filter (for journal entries)
        - transaction_ids: Optional list of specific transaction IDs (must be unposted)
        
        Returns statistics about the recalculation.
        """
        from accounting.utils import recalculate_transaction_and_journal_entry_status
        
        if end_date is None:
            end_date = date.today()
        
        # Build transaction query - only unposted transactions
        tx_query = Transaction.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            state='pending',  # Only process unposted transactions
        ).select_related('company', 'entity', 'currency').prefetch_related(
            'journal_entries__account',
            'journal_entries__reconciliations__bank_transactions',
        )
        
        if company_id:
            tx_query = tx_query.filter(company_id=company_id)
        if entity_id:
            tx_query = tx_query.filter(entity_id=entity_id)
        if transaction_ids:
            tx_query = tx_query.filter(id__in=transaction_ids)
        
        # Build journal entry query - only unposted journal entries
        je_query = JournalEntry.objects.filter(
            transaction__date__gte=start_date,
            transaction__date__lte=end_date,
            state='pending',  # Only process unposted journal entries
        ).select_related(
            'transaction', 'account', 'account__bank_account'
        ).prefetch_related(
            'reconciliations__bank_transactions',
        )
        
        if company_id:
            je_query = je_query.filter(company_id=company_id)
        if entity_id:
            je_query = je_query.filter(transaction__entity_id=entity_id)
        if account_id:
            je_query = je_query.filter(account_id=account_id)
        if transaction_ids:
            je_query = je_query.filter(transaction_id__in=transaction_ids)
        
        # Reset stats
        self.stats = {
            'transactions_processed': 0,
            'journal_entries_processed': 0,
            'metrics_calculated': 0,
            'flags_updated': 0,
            'errors': [],
        }
        
        # Get transaction IDs for status recalculation
        tx_ids = list(tx_query.values_list('id', flat=True))
        
        # Process journal entries first (since transaction metrics depend on them)
        with transaction.atomic():
            # First, recalculate transaction and journal entry flags (is_balanced, is_reconciled, etc.)
            if tx_ids:
                try:
                    flag_stats = recalculate_transaction_and_journal_entry_status(
                        transaction_ids=tx_ids,
                        company_id=company_id
                    )
                    self.stats['flags_updated'] = (
                        flag_stats.get('transactions_updated', 0) + 
                        flag_stats.get('journal_entries_updated', 0)
                    )
                except Exception as e:
                    log.error(f"Error recalculating flags: {e}")
                    self.stats['errors'].append(f"Flag recalculation: {str(e)}")
            
            # Then calculate reconciliation financial metrics
            for je in je_query:
                try:
                    je_metrics = self.calculate_journal_entry_metrics(je)
                    self.store_journal_entry_metrics(je, je_metrics)
                    self.stats['journal_entries_processed'] += 1
                    self.stats['metrics_calculated'] += 1
                except Exception as e:
                    log.error(f"Error calculating metrics for journal entry {je.id}: {e}")
                    self.stats['errors'].append(f"JournalEntry {je.id}: {str(e)}")
            
            # Process transactions (aggregate from journal entries)
            for tx in tx_query:
                try:
                    tx_metrics = self.calculate_transaction_metrics(tx)
                    self.store_transaction_metrics(tx, tx_metrics)
                    self.stats['transactions_processed'] += 1
                    self.stats['metrics_calculated'] += 1
                except Exception as e:
                    log.error(f"Error calculating metrics for transaction {tx.id}: {e}")
                    self.stats['errors'].append(f"Transaction {tx.id}: {str(e)}")
        
        return {
            'success': len(self.stats['errors']) == 0,
            'stats': self.stats,
            'filters': {
                'start_date': str(start_date),
                'end_date': str(end_date),
                'company_id': company_id,
                'entity_id': entity_id,
                'account_id': account_id,
                'transaction_ids': transaction_ids,
            },
        }

