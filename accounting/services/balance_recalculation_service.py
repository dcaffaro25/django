"""
Balance Recalculation Service

Service for calculating and storing account balance history.
Always calculates three balance types per account/month:
- posted: Only posted transactions
- bank_reconciled: Only bank-reconciled transactions
- all: All transactions
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from calendar import monthrange

from django.db import transaction
from django.db.models import Q, Sum, Min, Max
from django.utils import timezone

from accounting.models import Account, JournalEntry, Currency
from accounting.models_financial_statements import AccountBalanceHistory

log = logging.getLogger(__name__)


class BalanceRecalculationService:
    """
    Service for calculating and storing account balance history.
    """
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
    def recalculate_balances(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        account_ids: Optional[List[int]] = None,
        currency_id: Optional[int] = None,
        calculated_by=None,
    ) -> Dict[str, Any]:
        """
        Recalculate account balances for a given period.
        
        This method ALWAYS calculates ALL THREE balance types:
        - Posted transactions only (balance_type='posted')
        - Bank-reconciled only (balance_type='bank_reconciled')
        - All transactions (balance_type='all')
        
        Existing records are ALWAYS overwritten.
        
        Parameters:
        -----------
        start_date : date
            Start of the period (required). Will use the first day of the month.
        end_date : Optional[date]
            End of the period (optional). If not provided, calculates only for start_date's month.
            Will use the last day of the month.
        account_ids : Optional[List[int]]
            Specific accounts to recalculate. If None, recalculates all accounts.
        currency_id : Optional[int]
            Specific currency to recalculate. If None, recalculates all currencies.
        calculated_by : User
            User who triggered the recalculation
        
        Returns:
        --------
        Dict with statistics about the recalculation
        """
        start_time = timezone.now()
        
        # Normalize dates to month boundaries
        period_start = date(start_date.year, start_date.month, 1)
        if end_date:
            # Get last day of end_date's month
            last_day = monthrange(end_date.year, end_date.month)[1]
            period_end = date(end_date.year, end_date.month, last_day)
        else:
            # Only calculate for start_date's month
            last_day = monthrange(start_date.year, start_date.month)[1]
            period_end = date(start_date.year, start_date.month, last_day)
        
        # Get accounts to process
        accounts_qs = Account.objects.filter(company_id=self.company_id, is_active=True)
        if account_ids:
            accounts_qs = accounts_qs.filter(id__in=account_ids)
        
        # Get currencies to process
        # If currency_id is provided, use only that currency
        # Otherwise, we'll process each account's currency individually
        if currency_id:
            currencies_qs = Currency.objects.filter(id=currency_id)
            currencies = list(currencies_qs)
        else:
            # No specific currency filter - we'll process each account's currency
            currencies = None  # Will be determined per account
        
        accounts = list(accounts_qs)
        
        if currencies:
            currency_count = len(currencies)
        else:
            currency_count = "account-specific"
        
        log.info(
            "Starting balance recalculation: company_id=%s, period=%s to %s, accounts=%d, currencies=%s",
            self.company_id, period_start, period_end, len(accounts), currency_count
        )
        
        # Generate list of months to process
        months_to_process = []
        current = period_start
        while current <= period_end:
            months_to_process.append((current.year, current.month))
            # Move to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        
        records_created = 0
        records_deleted = 0
        errors = []
        currencies_processed_set = set()
        
        # Process each account, currency, month combination
        # Each record stores all three balance types
        # Note: We only calculate balances for the account's currency, filtering JournalEntry by transaction currency
        with transaction.atomic():
            for account in accounts:
                # Determine which currency(ies) to process for this account
                if currency_id:
                    # Specific currency filter provided - only process if account matches
                    if account.currency_id != currency_id:
                        continue
                    account_currencies = [Currency.objects.get(id=currency_id)]
                else:
                    # No currency filter - only process the account's own currency
                    if not account.currency_id:
                        log.warning(f"Account {account.id} has no currency set, skipping")
                        continue
                    account_currencies = [account.currency]
                
                for currency in account_currencies:
                    currencies_processed_set.add(currency.id)
                    
                    for year, month in months_to_process:
                        try:
                            # Calculate all three balance types
                            posted_data = self._calculate_month_balance(
                                account=account,
                                year=year,
                                month=month,
                                currency=currency,
                                balance_type='posted',
                            )
                            
                            bank_reconciled_data = self._calculate_month_balance(
                                account=account,
                                year=year,
                                month=month,
                                currency=currency,
                                balance_type='bank_reconciled',
                            )
                            
                            all_data = self._calculate_month_balance(
                                account=account,
                                year=year,
                                month=month,
                                currency=currency,
                                balance_type='all',
                            )
                            
                            # Use update_or_create to handle race conditions and avoid IntegrityError
                            # This atomically updates existing records or creates new ones
                            # Note: opening and ending balances are not stored, only movements (debits/credits)
                            balance_history, created = AccountBalanceHistory.objects.update_or_create(
                                company_id=self.company_id,
                                account=account,
                                year=year,
                                month=month,
                                currency=currency,
                                defaults={
                                    # Posted movements
                                    'posted_total_debit': posted_data['total_debit'],
                                    'posted_total_credit': posted_data['total_credit'],
                                    # Bank-reconciled movements
                                    'bank_reconciled_total_debit': bank_reconciled_data['total_debit'],
                                    'bank_reconciled_total_credit': bank_reconciled_data['total_credit'],
                                    # All transactions movements
                                    'all_total_debit': all_data['total_debit'],
                                    'all_total_credit': all_data['total_credit'],
                                    'calculated_by': calculated_by,
                                }
                            )
                            
                            if created:
                                records_created += 1
                            else:
                                records_deleted += 1  # Count updates as deletions for statistics
                            
                        except Exception as e:
                            error_msg = (
                                f"Error calculating balance for account={account.id}, "
                                f"year={year}, month={month}, currency={currency.id}: {str(e)}"
                            )
                            log.error(error_msg, exc_info=True)
                            errors.append(error_msg)
        
        duration = (timezone.now() - start_time).total_seconds()
        
        result = {
            'status': 'success',
            'message': 'Recalculation completed',
            'statistics': {
                'period_start': str(period_start),
                'period_end': str(period_end),
                'accounts_processed': len(accounts),
                'currencies_processed': len(currencies_processed_set),
                'months_processed': len(months_to_process),
                'records_created': records_created,
                'records_deleted': records_deleted,
                'duration_seconds': round(duration, 2),
            },
            'errors': errors,
        }
        
        log.info(
            "Balance recalculation completed: created=%d, deleted=%d, duration=%.2fs",
            records_created, records_deleted, duration
        )
        
        return result
    
    def _calculate_month_balance(
        self,
        account: Account,
        year: int,
        month: int,
        currency: Currency,
        balance_type: str = 'all',
    ) -> Dict[str, Decimal]:
        """
        Calculate balance for a specific account and month.
        
        Parameters:
        -----------
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
            - 'posted': Only journal entries where state='posted'
            - 'bank_reconciled': Only journal entries where is_reconciled=True
            - 'all': All journal entries (posted + pending, reconciled + unreconciled)
        
        Returns:
        --------
        Dict with 'opening_balance', 'ending_balance', 'total_debit', 'total_credit'
        """
        # Get month boundaries
        month_start = date(year, month, 1)
        last_day = monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        
        # Get opening balance
        opening_balance = self._get_opening_balance_for_month(
            account=account,
            year=year,
            month=month,
            currency=currency,
            balance_type=balance_type,
        )
        
        # Get journal entries for this month, filtered by currency
        entries = JournalEntry.objects.filter(
            account=account,
            transaction__company_id=self.company_id,
            transaction__currency=currency,
        )
        
        # Apply balance_type filter
        if balance_type == 'posted':
            entries = entries.filter(state='posted')
        elif balance_type == 'bank_reconciled':
            entries = entries.filter(is_reconciled=True)
        elif balance_type == 'all':
            # No filter - include everything
            pass
        else:
            raise ValueError(f"Invalid balance_type: {balance_type}")
        
        # Filter by date range
        entries = entries.filter(
            date__gte=month_start,
            date__lte=month_end
        )
        
        # Aggregate totals
        totals = entries.aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        
        total_debit = totals['total_debit'] or Decimal('0.00')
        total_credit = totals['total_credit'] or Decimal('0.00')
        
        # Calculate change with account direction
        net_movement = total_debit - total_credit
        change = net_movement * account.account_direction
        
        # Calculate ending balance
        ending_balance = opening_balance + change
        
        return {
            'opening_balance': opening_balance,
            'ending_balance': ending_balance,
            'total_debit': total_debit,
            'total_credit': total_credit,
        }
    
    def _get_opening_balance_for_month(
        self,
        account: Account,
        year: int,
        month: int,
        currency: Currency,
        balance_type: str = 'all',
    ) -> Decimal:
        """
        Get the opening balance for a month.
        This is the ending balance of the previous month (same balance_type),
        or account.balance if it's the first month.
        """
        # Try to get previous month's ending balance from history
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1
        
        prev_balance = AccountBalanceHistory.get_balance_for_period(
            account=account,
            year=prev_year,
            month=prev_month,
            currency=currency,
            balance_type=balance_type,
        )
        
        if prev_balance:
            return prev_balance.get_ending_balance(balance_type)
        
        # If no previous month in history, check if we can use account.balance
        if account.balance_date:
            month_start = date(year, month, 1)
            if account.balance_date < month_start:
                # Account balance is before this month, so we can use it
                # But we need to calculate the difference from balance_date to month_start
                # For simplicity, if there's no history, we'll calculate from beginning
                pass
        
        # Calculate from beginning of time (or from account.balance_date if set)
        # Get all journal entries up to (but not including) this month, filtered by currency
        entries = JournalEntry.objects.filter(
            account=account,
            transaction__company_id=self.company_id,
            transaction__currency=currency,
        )
        
        # Apply balance_type filter
        if balance_type == 'posted':
            entries = entries.filter(state='posted')
        elif balance_type == 'bank_reconciled':
            entries = entries.filter(is_reconciled=True)
        elif balance_type == 'all':
            pass
        else:
            raise ValueError(f"Invalid balance_type: {balance_type}")
        
        # Filter by date (before this month)
        month_start = date(year, month, 1)
        entries = entries.filter(date__lt=month_start)
        
        # If account has a balance_date before month_start, use that balance and add entries after it
        if account.balance_date and account.balance_date < month_start:
            entries = entries.filter(date__gt=account.balance_date)
            base_balance = account.balance or Decimal('0.00')
        else:
            base_balance = Decimal('0.00')
        
        # Aggregate totals
        totals = entries.aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        
        total_debit = totals['total_debit'] or Decimal('0.00')
        total_credit = totals['total_credit'] or Decimal('0.00')
        
        # Calculate opening balance
        net_movement = total_debit - total_credit
        change = net_movement * account.account_direction
        opening_balance = base_balance + change
        
        return opening_balance

