"""
Financial Statement Generation Service

Generates financial statements (Balance Sheet, P&L, Cash Flow, etc.)
from accounting data.

Calculation Methods:
- ending_balance: Balance as of end_date (inclusive) - for Balance Sheet
- opening_balance: Balance as of start_date - 1 day - for Cash Flow opening
- net_movement: Sum of (debit - credit) in [start_date, end_date] - for Income Statement
- change_in_balance: ending_balance - opening_balance - for Cash Flow delta
- debit_total: Sum of debits in period
- credit_total: Sum of credits in period
- rollup_children: Sum of child template lines (no GL query)
- formula: Reference other lines with L-tokens
- manual_input: User-provided constant value

Date Boundaries:
- All date ranges are INCLUSIVE on both ends
- opening_balance uses date < start_date (exclusive of start_date)
- ending_balance uses date <= end_date (inclusive)
- net_movement uses date >= start_date AND date <= end_date
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Any, Union, Tuple

from django.db import transaction
from django.db.models import Q, Sum, F, Min, Max

from accounting.models import Account, JournalEntry, Currency
from accounting.models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
    FinancialStatement,
    FinancialStatementLine,
    AccountBalanceHistory,
)
from accounting.services.balance_recalculation_service import BalanceRecalculationService
from accounting.services.formula_evaluator import (
    SafeFormulaEvaluator,
    FormulaError,
    InvalidFormulaError,
    UndefinedLineError,
)

log = logging.getLogger(__name__)

# Singleton formula evaluator
_formula_evaluator = SafeFormulaEvaluator()


class FinancialStatementGenerator:
    """Generates financial statements from templates and accounting data."""
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
    def _ensure_balance_history_for_period(
        self,
        start_date: date,
        end_date: date,
        currency_id: Optional[int] = None,
        account_ids: Optional[List[int]] = None,
        template: Optional[FinancialStatementTemplate] = None,
        generated_by=None,
    ) -> bool:
        """
        Check if balance history exists for the period and automatically
        recalculate missing periods if needed.
        
        Parameters:
        -----------
        start_date : date
            Start of the period
        end_date : date
            End of the period
        currency_id : Optional[int]
            Currency to check (if None, checks all currencies)
        account_ids : Optional[List[int]]
            Specific accounts to check (if None, checks all accounts used in statements)
        generated_by : User
            User triggering the recalculation
        
        Returns:
        --------
        bool
            True if history was recalculated, False if already exists
        """
        from calendar import monthrange
        
        # Generate list of months to check
        months_to_check = []
        current = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)
        
        while current <= end_month:
            months_to_check.append((current.year, current.month))
            # Move to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        
        # Check if history exists for all months
        # We need to check for at least one balance_type ('all' is sufficient)
        # If any month is missing, we'll recalculate the entire period
        
        # Get accounts to check
        if account_ids:
            accounts_qs = Account.objects.filter(
                company_id=self.company_id,
                id__in=account_ids,
                is_active=True
            )
        elif template:
            # Get accounts from template (more efficient)
            line_templates = template.line_templates.all()
            account_ids_from_template = set()
            
            for line_template in line_templates:
                if line_template.account_id:
                    account_ids_from_template.add(line_template.account_id)
                elif line_template.account_ids:
                    account_ids_from_template.update(line_template.account_ids)
                elif line_template.account_code_prefix:
                    # Get accounts with matching prefix
                    prefix_accounts = Account.objects.filter(
                        company_id=self.company_id,
                        account_code__startswith=line_template.account_code_prefix,
                        is_active=True
                    ).values_list('id', flat=True)
                    account_ids_from_template.update(prefix_accounts)
            
            if account_ids_from_template:
                accounts_qs = Account.objects.filter(
                    company_id=self.company_id,
                    id__in=account_ids_from_template,
                    is_active=True
                )
            else:
                # Fallback to all accounts if template has no account references
                accounts_qs = Account.objects.filter(
                    company_id=self.company_id,
                    is_active=True
                )
        else:
            # Check all active accounts
            accounts_qs = Account.objects.filter(
                company_id=self.company_id,
                is_active=True
            )
        
        accounts = list(accounts_qs)
        if not accounts:
            return False
        
        # Get currencies to check
        if currency_id:
            currencies = [Currency.objects.get(id=currency_id)]
        else:
            # Check all currencies used by accounts
            currencies = list(Currency.objects.filter(
                account__company_id=self.company_id,
                account__is_active=True
            ).distinct())
        
        # Check if history exists for all account/month/currency combinations
        missing_periods = []
        for account in accounts:
            for currency in currencies:
                # Only check if account currency matches (or if no currency filter)
                if currency_id and account.currency_id != currency_id:
                    continue
                
                for year, month in months_to_check:
                    # Check if history exists (one record per account/month/currency)
                    exists = AccountBalanceHistory.objects.filter(
                        company_id=self.company_id,
                        account=account,
                        year=year,
                        month=month,
                        currency=currency
                    ).exists()
                    
                    if not exists:
                        missing_periods.append((account.id, currency.id, year, month))
        
        # If no missing periods, return False (no recalculation needed)
        if not missing_periods:
            log.debug(
                "Balance history exists for period %s to %s, no recalculation needed",
                start_date, end_date
            )
            return False
        
        # Recalculate missing periods
        log.info(
            "Balance history missing for %d account/month/currency combinations. "
            "Auto-triggering recalculation for period %s to %s",
            len(missing_periods), start_date, end_date
        )
        
        # Determine which accounts and currencies need recalculation
        accounts_to_recalc = list(set(acc_id for acc_id, _, _, _ in missing_periods))
        currencies_to_recalc = list(set(curr_id for _, curr_id, _, _ in missing_periods))
        
        # Use BalanceRecalculationService to recalculate
        recalculation_service = BalanceRecalculationService(company_id=self.company_id)
        
        result = recalculation_service.recalculate_balances(
            start_date=start_date,
            end_date=end_date,
            account_ids=accounts_to_recalc if len(accounts_to_recalc) < len(accounts) else None,
            currency_id=currency_id,
            calculated_by=generated_by,
        )
        
        log.info(
            "Auto-recalculation completed: created %d records, duration %.2fs",
            result['statistics']['records_created'],
            result['statistics']['duration_seconds']
        )
        
        return True
    
    def generate_statement(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        currency_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        status: str = 'draft',
        generated_by=None,
        notes: Optional[str] = None,
        include_pending: bool = False,
    ) -> FinancialStatement:
        """
        Generate a financial statement from a template.
        
        Parameters
        ----------
        template: FinancialStatementTemplate
            Template defining the statement structure
        start_date: date
            Start of reporting period
        end_date: date
            End of reporting period
        currency_id: Optional[int]
            Currency ID (defaults to company's base currency)
        as_of_date: Optional[date]
            For balance sheet: specific date. For P&L: same as end_date
        status: str
            Statement status (draft, final, archived)
        generated_by: User
            User who generated the statement
        notes: Optional[str]
            Additional notes
        
        Returns
        -------
        FinancialStatement
            Generated statement with lines
        """
        if as_of_date is None:
            as_of_date = end_date
        
        if currency_id is None:
            # Get company's base currency (you may need to adjust this)
            currency = Currency.objects.filter(
                # Add your company currency logic here
            ).first()
            if not currency:
                raise ValueError("No currency specified and no default currency found")
        else:
            currency = Currency.objects.get(id=currency_id)
        
        # Ensure balance history exists for the period (auto-recalculate if missing)
        self._ensure_balance_history_for_period(
            start_date=start_date,
            end_date=end_date,
            currency_id=currency_id,
            account_ids=None,
            template=template,  # Pass template to optimize account checking
            generated_by=generated_by,
        )
        
        # Create statement record
        statement = FinancialStatement.objects.create(
            company_id=self.company_id,
            template=template,
            report_type=template.report_type,
            name=template.name,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            status=status,
            currency=currency,
            generated_by=generated_by,
            notes=notes,
        )
        
        # Generate lines
        line_templates = template.line_templates.all().order_by('line_number')
        line_values: Dict[int, Decimal] = {}  # line_number -> calculated value
        
        log.info(
            "="*80 + "\n"
            "STARTING FINANCIAL STATEMENT GENERATION\n"
            "="*80 + "\n"
            "Template: %s (ID: %s)\n"
            "Report Type: %s\n"
            "Company ID: %s\n"
            "Period: %s to %s\n"
            "As of Date: %s\n"
            "Include Pending: %s\n"
            "Total Line Templates: %s\n"
            "="*80,
            template.name,
            template.id,
            template.report_type,
            self.company_id,
            start_date,
            end_date,
            as_of_date,
            include_pending,
            line_templates.count(),
        )
        
        for line_template in line_templates:
            log.info(
                "\n" + "-"*80 + "\n"
                "PROCESSING LINE %s: %s\n"
                "-"*80 + "\n"
                "Line Type: %s\n"
                "Calculation Type: %s\n"
                "Formula: %s\n"
                "Account ID: %s\n"
                "Account IDs: %s\n"
                "Account Code Prefix: %s\n"
                "Account Path Contains: %s",
                line_template.line_number,
                line_template.label,
                line_template.line_type,
                line_template.calculation_type,
                line_template.formula or 'None',
                line_template.account_id or 'None',
                line_template.account_ids or 'None',
                line_template.account_code_prefix or 'None',
                line_template.account_path_contains or 'None',
            )
            
            value = self._calculate_line_value(
                line_template,
                start_date,
                end_date,
                as_of_date,
                template.report_type,
                line_values,
                include_pending=include_pending,
            )
            line_values[line_template.line_number] = value
            
            log.info(
                "Line %s calculated value: %s",
                line_template.line_number,
                value
            )
            
            # Create line record
            FinancialStatementLine.objects.create(
                statement=statement,
                line_template=line_template,
                line_number=line_template.line_number,
                label=line_template.label,
                line_type=line_template.line_type,
                balance=value,
                indent_level=line_template.indent_level,
                is_bold=line_template.is_bold,
                account_ids=self._get_account_ids_for_line(line_template),
            )
        
        # Calculate and store totals
        self._calculate_totals(statement, line_values, template.report_type)
        
        log.info(
            "Generated %s statement %s for period %s to %s",
            template.report_type,
            statement.id,
            start_date,
            end_date,
        )
        
        return statement
    
    def preview_statement(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        currency_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        include_pending: bool = False,
    ) -> Dict[str, Any]:
        """
        Preview a financial statement without saving to database.
        Returns the same data structure as a generated statement but without DB records.
        
        Parameters
        ----------
        template: FinancialStatementTemplate
            Template defining the statement structure
        start_date: date
            Start of reporting period
        end_date: date
            End of reporting period
        currency_id: Optional[int]
            Currency ID (defaults to company's base currency)
        as_of_date: Optional[date]
            For balance sheet: specific date. For P&L: same as end_date
        include_pending: bool
            Include pending journal entries
        
        Returns
        -------
        Dict[str, Any]
            Statement data with lines (same structure as serializer)
        """
        if as_of_date is None:
            as_of_date = end_date
        
        if currency_id is None:
            currency = Currency.objects.first()
            if not currency:
                raise ValueError("No currency specified and no default currency found")
        else:
            currency = Currency.objects.get(id=currency_id)
        
        # Ensure balance history exists for the period (auto-recalculate if missing)
        self._ensure_balance_history_for_period(
            start_date=start_date,
            end_date=end_date,
            currency_id=currency_id,
            account_ids=None,
            template=template,  # Pass template to optimize account checking
            generated_by=None,  # Preview doesn't have a user
        )
        
        # Generate lines without saving
        line_templates = template.line_templates.all().order_by('line_number')
        line_values: Dict[int, Decimal] = {}
        lines_data = []
        
        log.info(
            "="*80 + "\n"
            "STARTING FINANCIAL STATEMENT PREVIEW\n"
            "="*80 + "\n"
            "Template: %s (ID: %s)\n"
            "Report Type: %s\n"
            "Company ID: %s\n"
            "Period: %s to %s\n"
            "As of Date: %s\n"
            "Include Pending: %s\n"
            "Currency: %s (ID: %s)\n"
            "Total Line Templates: %s\n"
            "="*80,
            template.name,
            template.id,
            template.report_type,
            self.company_id,
            start_date,
            end_date,
            as_of_date,
            include_pending,
            currency.code if currency else 'None',
            currency.id if currency else 'None',
            line_templates.count(),
        )
        
        for line_template in line_templates:
            value = self._calculate_line_value(
                line_template,
                start_date,
                end_date,
                as_of_date,
                template.report_type,
                line_values,
                include_pending=include_pending,
            )
            line_values[line_template.line_number] = value
            
            lines_data.append({
                'line_number': line_template.line_number,
                'label': line_template.label,
                'line_type': line_template.line_type,
                'balance': float(value),
                'debit_amount': 0.0,  # Could calculate if needed
                'credit_amount': 0.0,  # Could calculate if needed
                'indent_level': line_template.indent_level,
                'is_bold': line_template.is_bold,
            })
        
        # Calculate totals
        totals = self._calculate_totals_dict(line_values, template.report_type)
        
        return {
            'template_id': template.id,
            'template_name': template.name,
            'report_type': template.report_type,
            'name': template.name,
            'start_date': start_date,
            'end_date': end_date,
            'as_of_date': as_of_date,
            'currency': {
                'id': currency.id,
                'code': currency.code,
                'symbol': getattr(currency, 'symbol', currency.code),
            },
            'status': 'preview',
            'lines': lines_data,
            **totals,
        }
    
    def _calculate_totals_dict(
        self,
        line_values: Dict[int, Decimal],
        report_type: str,
    ) -> Dict[str, Any]:
        """Calculate totals as dictionary (for preview)."""
        totals = {
            'total_assets': None,
            'total_liabilities': None,
            'total_equity': None,
            'net_income': None,
        }
        
        # Basic implementation - can be enhanced based on template structure
        if report_type == 'income_statement':
            # Calculate net income from lines (simplified)
            totals['net_income'] = float(sum(line_values.values()))
        
        return totals
    
    def _calculate_line_value(
        self,
        line_template: FinancialStatementLineTemplate,
        start_date: date,
        end_date: date,
        as_of_date: date,
        report_type: str,
        line_values: Dict[int, Decimal],
        include_pending: bool = False,
    ) -> Decimal:
        """
        Calculate the value for a single line item.
        
        Uses calculation_method if set, otherwise falls back to legacy calculation_type.
        
        Parameters
        ----------
        line_template : FinancialStatementLineTemplate
            The line template defining the calculation
        start_date : date
            Start of the reporting period (inclusive)
        end_date : date
            End of the reporting period (inclusive)
        as_of_date : date
            Point-in-time date for balance calculations
        report_type : str
            Type of report (balance_sheet, income_statement, cash_flow, etc.)
        line_values : Dict[int, Decimal]
            Previously calculated line values (for formula references)
        include_pending : bool
            Whether to include pending journal entries
            
        Returns
        -------
        Decimal
            Calculated value for the line, with sign_policy applied
        """
        log.debug(
            "Calculating line value for line %s (%s) - Type: %s, Method: %s, Legacy Calc Type: %s",
            line_template.line_number,
            line_template.label,
            line_template.line_type,
            line_template.calculation_method or 'None',
            line_template.calculation_type
        )
        
        # Handle different line types (headers/spacers always return 0)
        if line_template.line_type in ('header', 'spacer'):
            log.debug("Line %s is header/spacer, returning 0.00", line_template.line_number)
            return Decimal('0.00')
        
        # Get effective calculation method (new field or legacy mapping)
        calc_method = line_template.get_effective_calculation_method()
        log.debug("Line %s effective calculation method: %s", line_template.line_number, calc_method)
        
        # Dispatch to appropriate calculation method
        value = self._dispatch_calculation(
            calc_method=calc_method,
            line_template=line_template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            report_type=report_type,
            line_values=line_values,
            include_pending=include_pending,
        )
        
        # Apply sign policy
        value = self._apply_sign_policy(value, line_template.sign_policy)
        
        log.info("Line %s final value: %s", line_template.line_number, value)
        return value
    
    def _dispatch_calculation(
        self,
        calc_method: str,
        line_template: FinancialStatementLineTemplate,
        start_date: date,
        end_date: date,
        as_of_date: date,
        report_type: str,
        line_values: Dict[int, Decimal],
        include_pending: bool,
    ) -> Decimal:
        """
        Dispatch to the appropriate calculation method based on calc_method.
        
        This is the core dispatcher that routes to specific calculation implementations.
        """
        # Formula-based calculation (no accounts needed)
        if calc_method == 'formula':
            if line_template.formula:
                log.info("Line %s uses formula: %s", line_template.line_number, line_template.formula)
                try:
                    result = _formula_evaluator.evaluate(line_template.formula, line_values)
                    log.info("Line %s formula result: %s", line_template.line_number, result)
                    return result
                except FormulaError as e:
                    log.warning("Formula evaluation failed for line %s: %s", line_template.line_number, e)
                    return Decimal('0.00')
            else:
                log.warning("Line %s has formula method but no formula defined", line_template.line_number)
                return Decimal('0.00')
        
        # Rollup children (sum child template lines, no GL query)
        if calc_method == 'rollup_children':
            return self._calc_rollup_children(line_template, line_values)
        
        # Manual input (user-provided constant)
        if calc_method == 'manual_input':
            return line_template.manual_value or Decimal('0.00')
        
        # All other methods require accounts
        accounts = self._get_accounts_for_line(line_template)
        if not accounts:
            log.warning("No accounts found for line %s (%s)", line_template.line_number, line_template.label)
            return Decimal('0.00')
        
        log.info(
            "Line %s will use %s account(s) for %s calculation",
            line_template.line_number,
            len(accounts),
            calc_method
        )
        
        # Stock measures (point-in-time)
        if calc_method == 'ending_balance':
            return self._calc_ending_balance(accounts, as_of_date, include_pending)
        
        if calc_method == 'opening_balance':
            # Opening balance is balance as of day before start_date
            opening_date = start_date - timedelta(days=1)
            return self._calc_ending_balance(accounts, opening_date, include_pending)
        
        # Flow measures (period activity)
        if calc_method == 'net_movement':
            return self._calc_net_movement(accounts, start_date, end_date, include_pending)
        
        if calc_method == 'debit_total':
            return self._calc_debit_total(accounts, start_date, end_date, include_pending)
        
        if calc_method == 'credit_total':
            return self._calc_credit_total(accounts, start_date, end_date, include_pending)
        
        # Delta measures
        if calc_method == 'change_in_balance':
            opening_date = start_date - timedelta(days=1)
            opening = self._calc_ending_balance(accounts, opening_date, include_pending)
            ending = self._calc_ending_balance(accounts, as_of_date, include_pending)
            return ending - opening
        
        # Fallback: use legacy report_type-based calculation
        log.warning(
            "Unknown calculation method '%s' for line %s, falling back to legacy logic",
            calc_method, line_template.line_number
        )
        return self._calculate_legacy(
            accounts, start_date, end_date, as_of_date, 
            report_type, line_template.calculation_type, include_pending
        )
    
    def _apply_sign_policy(self, value: Decimal, sign_policy: str) -> Decimal:
        """
        Apply sign policy to a calculated value.
        
        Parameters
        ----------
        value : Decimal
            The calculated value
        sign_policy : str
            'natural' - return as-is
            'invert' - multiply by -1
            'absolute' - return absolute value
        """
        if sign_policy == 'invert':
            return -value
        elif sign_policy == 'absolute':
            return abs(value)
        else:  # 'natural' or default
            return value
    
    def _calc_rollup_children(
        self,
        line_template: FinancialStatementLineTemplate,
        line_values: Dict[int, Decimal],
    ) -> Decimal:
        """
        Calculate rollup of child template lines.
        
        Sums the values of all child lines (template hierarchy, not account hierarchy).
        This allows for hierarchical statement structures where totals are computed
        from their component lines without querying the GL.
        """
        child_templates = line_template.child_lines.all()
        total = Decimal('0.00')
        
        for child in child_templates:
            child_value = line_values.get(child.line_number, Decimal('0.00'))
            total += child_value
            log.debug(
                "Rollup: Line %s adding child L%s = %s (running total: %s)",
                line_template.line_number, child.line_number, child_value, total
            )
        
        log.info(
            "Line %s rollup_children total: %s (from %s children)",
            line_template.line_number, total, child_templates.count()
        )
        return total
    
    def _calc_ending_balance(
        self,
        accounts: List[Account],
        as_of_date: date,
        include_pending: bool,
    ) -> Decimal:
        """
        Calculate ending balance as of a specific date (inclusive).
        
        This is a STOCK measure - point-in-time balance.
        Used for Balance Sheet items.
        
        Returns sum of all account balances considering:
        - Account's opening balance (if balance_date <= as_of_date)
        - All journal entries up to and including as_of_date
        - Account direction for sign normalization
        """
        total = Decimal('0.00')
        
        for account in accounts:
            balance = self._calculate_cumulative_ending_balance(
                account=account,
                as_of_date=as_of_date,
                include_pending=include_pending,
            )
            total += balance
        
        return total
    
    def _calc_net_movement(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        include_pending: bool,
    ) -> Decimal:
        """
        Calculate net movement (debit - credit) within a period.
        
        This is a FLOW measure - activity within a period.
        Used for Income Statement items.
        
        Date range is inclusive: [start_date, end_date]
        """
        state_filter = Q(state='posted')
        if include_pending:
            state_filter = Q(state__in=['posted', 'pending'])
        
        log.info(
            "Calculating net_movement: %s account(s), period [%s, %s], "
            "include_pending=%s, company_id=%s",
            len(accounts), start_date, end_date, include_pending, self.company_id
        )
        
        total = Decimal('0.00')
        
        for account in accounts:
            entries = JournalEntry.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter)
            
            entry_count = entries.count()
            
            result = entries.aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )
            
            debit = result['total_debit'] or Decimal('0.00')
            credit = result['total_credit'] or Decimal('0.00')
            
            # Apply account direction for proper sign
            net = (debit - credit) * account.account_direction
            total += net
            
            log.info(
                "Account %s (ID: %s, Code: %s): %s entries found, "
                "debit=%s, credit=%s, direction=%s, net=%s",
                account.name,
                account.id,
                account.account_code,
                entry_count,
                debit,
                credit,
                account.account_direction,
                net
            )
            
            # If no entries found, log potential reasons
            if entry_count == 0:
                # Check if entries exist for this account at all
                all_entries_count = JournalEntry.objects.filter(
                    account=account,
                    transaction__company_id=self.company_id,
                ).count()
                
                # Check entries in date range regardless of state
                entries_any_state = JournalEntry.objects.filter(
                    account=account,
                    date__gte=start_date,
                    date__lte=end_date,
                    transaction__company_id=self.company_id,
                ).count()
                
                log.warning(
                    "Account %s (ID: %s): No entries found in period [%s, %s]. "
                    "Total entries for account: %s, Entries in date range (any state): %s",
                    account.name,
                    account.id,
                    start_date,
                    end_date,
                    all_entries_count,
                    entries_any_state,
                )
        
        log.info("Net movement total: %s", total)
        return total
    
    def _calc_debit_total(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        include_pending: bool,
    ) -> Decimal:
        """
        Calculate total debits within a period.
        
        Date range is inclusive: [start_date, end_date]
        """
        state_filter = Q(state='posted')
        if include_pending:
            state_filter = Q(state__in=['posted', 'pending'])
        
        total = Decimal('0.00')
        
        for account in accounts:
            result = JournalEntry.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter).aggregate(total=Sum('debit_amount'))
            
            total += result['total'] or Decimal('0.00')
        
        return total
    
    def _calc_credit_total(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        include_pending: bool,
    ) -> Decimal:
        """
        Calculate total credits within a period.
        
        Date range is inclusive: [start_date, end_date]
        """
        state_filter = Q(state='posted')
        if include_pending:
            state_filter = Q(state__in=['posted', 'pending'])
        
        total = Decimal('0.00')
        
        for account in accounts:
            result = JournalEntry.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter).aggregate(total=Sum('credit_amount'))
            
            total += result['total'] or Decimal('0.00')
        
        return total
    
    def _calculate_legacy(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        as_of_date: date,
        report_type: str,
        calculation_type: str,
        include_pending: bool,
    ) -> Decimal:
        """
        Legacy calculation method for backward compatibility.
        
        This is called when calculation_method is not recognized or not set.
        Routes to the original report_type-based calculation logic.
        """
        if report_type == 'balance_sheet':
            return self._calculate_balance_sheet_line(
                accounts, as_of_date, calculation_type, include_pending
            )
        elif report_type == 'income_statement':
            return self._calculate_income_statement_line(
                accounts, start_date, end_date, calculation_type, include_pending
            )
        elif report_type == 'cash_flow':
            return self._calculate_cash_flow_line(
                accounts, start_date, end_date, calculation_type, include_pending
            )
        else:
            return self._calculate_period_balance(
                accounts, start_date, end_date, calculation_type, include_pending
            )
    
    def _calculate_line_value_with_metadata(
        self,
        line_template: FinancialStatementLineTemplate,
        start_date: date,
        end_date: date,
        as_of_date: date,
        report_type: str,
        line_values: Dict[int, Decimal],
        include_pending: bool = False,
    ) -> tuple[Decimal, Dict[str, Any]]:
        """
        Calculate the value for a single line item with calculation metadata.
        Returns (value, calculation_memory) tuple.
        """
        calculation_memory = {
            'calculation_type': line_template.calculation_type,
            'report_type': report_type,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'as_of_date': str(as_of_date),
            'accounts': [],
        }
        
        # Handle different line types
        if line_template.line_type in ('header', 'spacer'):
            calculation_memory['reason'] = 'Line type is header/spacer'
            return Decimal('0.00'), calculation_memory
        
        # Handle formula-based lines
        if line_template.calculation_type == 'formula' and line_template.formula:
            value = self._evaluate_formula(line_template.formula, line_values)
            calculation_memory['formula'] = line_template.formula
            calculation_memory['line_values_used'] = {k: float(v) for k, v in line_values.items()}
            calculation_memory['result'] = float(value)
            return value, calculation_memory
        
        # Get accounts for this line
        accounts = self._get_accounts_for_line(line_template)
        if not accounts:
            calculation_memory['reason'] = 'No accounts found for this line'
            return Decimal('0.00'), calculation_memory
        
        # Calculate based on report type with metadata
        if report_type == 'cash_flow':
            value, account_details = self._calculate_cash_flow_line_with_metadata(
                accounts,
                start_date,
                end_date,
                line_template.calculation_type,
                include_pending=include_pending,
            )
            calculation_memory['accounts'] = account_details
            calculation_memory['total'] = float(value)
        else:
            # For other report types, use basic calculation
            value = self._calculate_line_value(
                line_template, start_date, end_date, as_of_date,
                report_type, line_values, include_pending
            )
            calculation_memory['accounts'] = [
                {'id': acc.id, 'name': acc.name, 'bank_account_id': acc.bank_account_id}
                for acc in accounts
            ]
            calculation_memory['total'] = float(value)
        
        return value, calculation_memory
    
    def _calculate_cash_flow_line_with_metadata(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        calculation_type: str,
        include_pending: bool = False,
    ) -> tuple[Decimal, List[Dict[str, Any]]]:
        """
        Calculate cash flow line with detailed metadata for each account.
        Returns (total, account_details) tuple.
        """
        # Filter to cash/bank accounts
        cash_accounts = [acc for acc in accounts if acc.bank_account is not None]
        account_details = []
        
        if not cash_accounts:
            account_details.append({
                'reason': 'No cash accounts found (accounts without bank_account_id)',
                'all_accounts': [
                    {'id': acc.id, 'name': acc.name, 'bank_account_id': acc.bank_account_id}
                    for acc in accounts
                ]
            })
            return Decimal('0.00'), account_details
        
        total = Decimal('0.00')
        
        for account in cash_accounts:
            account_detail = {
                'id': account.id,
                'name': account.name,
                'account_code': account.account_code,
                'bank_account_id': account.bank_account_id,
                'account_direction': account.account_direction,
                'calculation_type': calculation_type,
            }
            
            if calculation_type == 'sum':
                state_filter = Q(state='posted')
                if include_pending:
                    state_filter = Q(state__in=['posted', 'pending'])
                
                entries = JournalEntry.objects.filter(
                    account=account,
                    date__gte=start_date,
                    date__lte=end_date,
                    transaction__company_id=self.company_id,
                ).filter(state_filter)
                
                debit_total = entries.aggregate(
                    total=Sum('debit_amount')
                )['total'] or Decimal('0.00')
                credit_total = entries.aggregate(
                    total=Sum('credit_amount')
                )['total'] or Decimal('0.00')
                
                change = (debit_total - credit_total) * account.account_direction
                
                account_detail['debit_total'] = float(debit_total)
                account_detail['credit_total'] = float(credit_total)
                account_detail['account_direction'] = account.account_direction
                account_detail['change'] = float(change)
                account_detail['entry_count'] = entries.count()
                
            elif calculation_type == 'balance':
                # Cumulative ending balance from all journal entries up to end_date
                ending_balance, balance_metadata = self._calculate_cumulative_ending_balance_with_metadata(
                    account=account,
                    as_of_date=end_date,
                    include_pending=include_pending,
                )
                change = ending_balance
                
                account_detail['opening_balance'] = float(account.balance or Decimal('0.00'))
                account_detail['balance_date'] = str(account.balance_date) if account.balance_date else None
                account_detail['ending_balance'] = float(ending_balance)
                account_detail['value'] = float(ending_balance)
                account_detail['balance_calculation'] = balance_metadata
                
            else:
                # Difference or default
                beginning_balance = account.calculate_balance(
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=start_date,
                ) or Decimal('0.00')
                
                ending_balance = account.calculate_balance(
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=end_date,
                ) or Decimal('0.00')
                
                change = ending_balance - beginning_balance
                
                account_detail['beginning_balance'] = float(beginning_balance)
                account_detail['ending_balance'] = float(ending_balance)
                account_detail['change'] = float(change)
            
            total += change
            account_details.append(account_detail)
        
        return total, account_details
    
    def _get_accounts_for_line(
        self,
        line_template: FinancialStatementLineTemplate,
    ) -> List[Account]:
        """
        Get accounts that contribute to this line.
        
        Respects the include_descendants field:
        - If True (default): expands parent accounts to include all leaf descendants
        - If False: returns only the explicitly specified accounts
        """
        include_descendants = getattr(line_template, 'include_descendants', True)
        
        log.debug(
            "Getting accounts for line %s - Account ID: %s, Account IDs: %s, "
            "Code Prefix: %s, Path Contains: %s, Include Descendants: %s",
            line_template.line_number,
            line_template.account_id,
            line_template.account_ids,
            line_template.account_code_prefix,
            line_template.account_path_contains,
            include_descendants,
        )
        
        accounts = Account.objects.filter(company_id=self.company_id)
        initial_count = accounts.count()
        
        # Filter by specific account
        if line_template.account:
            # Warn if other selectors are also set (they will be ignored)
            if line_template.account_path_contains or line_template.account_code_prefix or line_template.account_ids:
                log.warning(
                    "Line %s: Both 'account' and other selectors are set. "
                    "Using only the specific account (ID: %s). Other selectors will be ignored.",
                    line_template.line_number,
                    line_template.account.id,
                )
            
            log.info(
                "Line %s: Using specific account %s (ID: %s, Code: %s, Name: %s, Is Leaf: %s)",
                line_template.line_number,
                line_template.account.id,
                line_template.account.id,
                line_template.account.account_code,
                line_template.account.name,
                line_template.account.is_leaf(),
            )
            
            if include_descendants:
                # Expand parent account to include all leaf descendants
                expanded = self._expand_to_leaf_accounts([line_template.account])
                log.info(
                    "Line %s: Expanded account %s to %s leaf account(s): %s",
                    line_template.line_number,
                    line_template.account.id,
                    len(expanded),
                    [f"{acc.account_code or 'None'} ({acc.name})" for acc in expanded[:5]]
                )
                
                # Check if parent account itself has entries
                # If so, include it in the calculation (common pattern where entries are posted to parent)
                parent_has_entries = JournalEntry.objects.filter(
                    account=line_template.account,
                    transaction__company_id=self.company_id,
                ).exists()
                
                if parent_has_entries:
                    log.warning(
                        "Line %s: Parent account %s has journal entries. "
                        "Including parent account in calculation along with %s leaf accounts.",
                        line_template.line_number,
                        line_template.account.id,
                        len(expanded),
                    )
                    # Include parent account in the list
                    expanded.append(line_template.account)
                elif len(expanded) == 0:
                    log.warning(
                        "Line %s: Account %s expanded to 0 leaf accounts. "
                        "This account may have no children, or all children are inactive.",
                        line_template.line_number,
                        line_template.account.id,
                    )
                    # If no leaf accounts and parent has no entries, return empty list
                    # Otherwise return parent account itself
                    if not parent_has_entries:
                        return []
                    else:
                        return [line_template.account]
                
                return expanded
            else:
                # Return only the specified account (no descendant expansion)
                log.info(
                    "Line %s: Using only specified account (include_descendants=False)",
                    line_template.line_number,
                )
                return [line_template.account]
        
        # Filter by account IDs
        if line_template.account_ids:
            log.info(
                "Line %s: Filtering by account IDs: %s",
                line_template.line_number,
                line_template.account_ids,
            )
            accounts = list(accounts.filter(id__in=line_template.account_ids))
            log.info(
                "Line %s: Found %s account(s) matching IDs",
                line_template.line_number,
                len(accounts),
            )
        # Filter by code prefix
        elif line_template.account_code_prefix:
            log.info(
                "Line %s: Filtering by account code prefix: %s",
                line_template.line_number,
                line_template.account_code_prefix,
            )
            accounts = list(accounts.filter(
                account_code__startswith=line_template.account_code_prefix
            ))
            log.info(
                "Line %s: Found %s account(s) with code prefix %s",
                line_template.line_number,
                len(accounts),
                line_template.account_code_prefix,
            )
        # Filter by path contains
        elif line_template.account_path_contains:
            log.info(
                "Line %s: Filtering by account path contains: %s",
                line_template.line_number,
                line_template.account_path_contains,
            )
            # This requires checking account paths - simplified for now
            matching_accounts = []
            for account in accounts:
                account_path = account.get_path()
                if line_template.account_path_contains in account_path:
                    matching_accounts.append(account)
                    log.debug(
                        "Line %s: Account %s (ID: %s) matches path filter - Path: %s",
                        line_template.line_number,
                        account.name,
                        account.id,
                        account_path,
                    )
            accounts = matching_accounts
            log.info(
                "Line %s: Found %s account(s) matching path filter",
                line_template.line_number,
                len(accounts),
            )
        else:
            log.warning(
                "Line %s: No account filter specified, using all accounts (count: %s)",
                line_template.line_number,
                initial_count,
            )
            accounts = list(accounts)
        
        # Log account details before expansion
        if accounts:
            log.info(
                "Line %s: Accounts before expansion (%s total):",
                line_template.line_number,
                len(accounts),
            )
            for acc in accounts[:10]:  # Log first 10
                log.info(
                    "  - Account ID: %s, Code: %s, Name: %s, Is Leaf: %s, "
                    "Parent: %s, Direction: %s",
                    acc.id,
                    acc.account_code,
                    acc.name,
                    acc.is_leaf(),
                    acc.parent_id if acc.parent else 'None',
                    acc.account_direction,
                )
            if len(accounts) > 10:
                log.info("  ... and %s more account(s)", len(accounts) - 10)
        
        # Expand accounts to leaf descendants if include_descendants is True
        if include_descendants:
            # This ensures parent accounts are replaced by their leaf children
            expanded_accounts = self._expand_to_leaf_accounts(accounts)
            
            log.info(
                "Line %s: Expanded %s account(s) to %s leaf account(s)",
                line_template.line_number,
                len(accounts),
                len(expanded_accounts),
            )
        else:
            # Don't expand - use accounts as specified
            expanded_accounts = accounts
            log.info(
                "Line %s: Using %s account(s) without expansion (include_descendants=False)",
                line_template.line_number,
                len(accounts),
            )
        
        return expanded_accounts
    
    def _expand_to_leaf_accounts(self, accounts: List[Account]) -> List[Account]:
        """
        Expand accounts to include all leaf descendants.
        If an account is a leaf, it's included as-is.
        If an account is a parent, it's replaced by all its leaf descendants.
        
        Parameters
        ----------
        accounts: List[Account]
            List of accounts (may include parents and children)
        
        Returns
        -------
        List[Account]
            List of only leaf accounts (all parents expanded)
        """
        leaf_accounts = []
        
        log.info(
            "Expanding %s account(s) to leaf accounts",
            len(accounts)
        )
        
        for idx, account in enumerate(accounts, 1):
            log.info(
                "[%s/%s] Processing account: ID=%s, Code=%s, Name=%s, Is Leaf=%s, "
                "Parent ID=%s, Level=%s, Direction=%s",
                idx,
                len(accounts),
                account.id,
                account.account_code,
                account.name,
                account.is_leaf(),
                account.parent_id if account.parent else 'None',
                account.level if hasattr(account, 'level') else 'N/A',
                account.account_direction,
            )
            
            if account.is_leaf():
                # Leaf account: include directly
                leaf_accounts.append(account)
                log.info(
                    "  ✓ Leaf account included: %s (ID: %s, Code: %s, Bank Account ID: %s)",
                    account.name,
                    account.id,
                    account.account_code,
                    account.bank_account_id or 'None',
                )
            else:
                # Parent account: get all leaf descendants
                log.info(
                    "  → Parent account detected, expanding to leaf descendants..."
                )
                leaf_descendants = self._get_leaf_descendants(account)
                leaf_accounts.extend(leaf_descendants)
                log.info(
                    "  ✓ Expanded parent account %s (ID: %s) to %s leaf account(s)",
                    account.name,
                    account.id,
                    len(leaf_descendants),
                )
                if leaf_descendants:
                    log.info("  Leaf descendants:")
                    for desc in leaf_descendants:
                        log.info(
                            "    - %s (ID: %s, Code: %s, Bank Account ID: %s, Direction: %s)",
                            desc.name,
                            desc.id,
                            desc.account_code,
                            desc.bank_account_id or 'None',
                            desc.account_direction,
                        )
                else:
                    log.warning(
                        "  ⚠ Parent account %s (ID: %s) has no leaf descendants!",
                        account.name,
                        account.id,
                    )
        
        # Remove duplicates by ID
        seen_ids = set()
        unique_leaf_accounts = []
        duplicates = []
        for acc in leaf_accounts:
            if acc.id not in seen_ids:
                seen_ids.add(acc.id)
                unique_leaf_accounts.append(acc)
            else:
                duplicates.append(acc.id)
        
        if duplicates:
            log.warning(
                "Found %s duplicate account(s) in expansion (IDs: %s)",
                len(duplicates),
                duplicates[:10],  # Show first 10
            )
        
        log.info(
            "Expansion complete: %s original account(s) → %s unique leaf account(s)",
            len(accounts),
            len(unique_leaf_accounts),
        )
        
        return unique_leaf_accounts
    
    def _get_leaf_descendants(self, account: Account) -> List[Account]:
        """
        Get all leaf descendants of an account (recursively).
        
        Parameters
        ----------
        account: Account
            Parent account
        
        Returns
        -------
        List[Account]
            All leaf accounts that are descendants of this account
        """
        leaf_accounts = []
        
        # Get direct children from same company
        children = account.get_children().filter(company_id=self.company_id)
        children_list = list(children)
        
        log.debug(
            "Getting leaf descendants for account %s (ID: %s, Code: %s), "
            "found %s direct child(ren)",
            account.name,
            account.id,
            account.account_code,
            len(children_list),
        )
        
        if not children_list:
            log.warning(
                "Account %s (ID: %s) has no children for company %s",
                account.name,
                account.id,
                self.company_id,
            )
            return leaf_accounts
        
        for idx, child in enumerate(children_list, 1):
            log.debug(
                "  [%s/%s] Processing child: %s (ID: %s, Code: %s, Is Leaf: %s)",
                idx,
                len(children_list),
                child.name,
                child.id,
                child.account_code,
                child.is_leaf(),
            )
            
            if child.is_leaf():
                # Leaf: add to list
                leaf_accounts.append(child)
                log.debug(
                    "    ✓ Added leaf account %s (ID: %s) to descendants",
                    child.name,
                    child.id,
                )
            else:
                # Parent: recursively get its leaf descendants
                log.debug(
                    "    → Child is also a parent, recursing into %s (ID: %s)...",
                    child.name,
                    child.id,
                )
                child_leaves = self._get_leaf_descendants(child)
                leaf_accounts.extend(child_leaves)
                log.debug(
                    "    ✓ Expanded parent account %s (ID: %s) to %s leaf descendant(s)",
                    child.name,
                    child.id,
                    len(child_leaves),
                )
        
        log.debug(
            "Account %s (ID: %s) has %s total leaf descendant(s)",
            account.name,
            account.id,
            len(leaf_accounts),
        )
        
        return leaf_accounts
    
    def _deduplicate_account_hierarchy(self, accounts: List[Account]) -> List[Account]:
        """
        Remove accounts that are descendants of other accounts in the list.
        This prevents double-counting since parent accounts already include their children.
        
        Parameters
        ----------
        accounts: List[Account]
            List of accounts (may include parents and children)
        
        Returns
        -------
        List[Account]
            Deduplicated list (only top-level accounts in the hierarchy)
        """
        if not accounts:
            return []
        
        # Build a set of all account IDs for quick lookup
        account_ids = {acc.id for acc in accounts}
        result = []
        
        for account in accounts:
            # Check if this account is a descendant of any other account in the list
            is_descendant = False
            
            # Get all ancestors of this account (excluding self)
            try:
                ancestors = account.get_ancestors(include_self=False)
                ancestor_ids = {anc.id for anc in ancestors}
                
                # If any ancestor is in our account list, this account is a descendant
                if ancestor_ids & account_ids:
                    is_descendant = True
            except Exception:
                # Fallback: check parent chain manually
                current = account.parent
                while current:
                    if current.id in account_ids:
                        is_descendant = True
                        break
                    current = current.parent
            
            # Only include accounts that are not descendants of others in the list
            if not is_descendant:
                result.append(account)
        
        return result
    
    def _get_account_ids_for_line(
        self,
        line_template: FinancialStatementLineTemplate,
    ) -> List[int]:
        """Get account IDs for this line (for metadata)."""
        accounts = self._get_accounts_for_line(line_template)
        return [acc.id for acc in accounts]
    
    def _calculate_balance_sheet_line(
        self,
        accounts: List[Account],
        as_of_date: date,
        calculation_type: str,
        include_pending: bool = False,
    ) -> Decimal:
        """Calculate balance sheet line (as of specific date)."""
        log.info(
            "Calculating balance sheet line for %s account(s) as of %s "
            "(calculation_type: %s, include_pending: %s)",
            len(accounts),
            as_of_date,
            calculation_type,
            include_pending,
        )
        
        total = Decimal('0.00')
        
        for idx, account in enumerate(accounts, 1):
            log.info(
                "[%s/%s] Processing account: %s (ID: %s, Code: %s, Direction: %s)",
                idx,
                len(accounts),
                account.name,
                account.id,
                account.account_code,
                account.account_direction,
            )
            
            if calculation_type == 'balance':
                # Balance: Use last closing balance + transactions after closing date
                log.debug(
                    "  Using 'balance' calculation type for account %s (ID: %s)",
                    account.name,
                    account.id,
                )
                balance = self._calculate_account_balance_from_closing(
                    account=account,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
                log.info(
                    "  Account %s (ID: %s) balance from closing: %s",
                    account.name,
                    account.id,
                    balance,
                )
            else:
                # Sum or difference: Calculate from journal entries in period
                log.debug(
                    "  Using '%s' calculation type for account %s (ID: %s)",
                    calculation_type,
                    account.name,
                    account.id,
                )
                balance = self._calculate_account_balance_with_children(
                    account=account,
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=as_of_date,
                )
                log.info(
                    "  Account %s (ID: %s) balance with children: %s",
                    account.name,
                    account.id,
                    balance,
                )
                # Apply account direction for sum
                if calculation_type == 'sum':
                    balance_before_direction = balance
                    balance = balance * account.account_direction
                    log.info(
                        "  Applied account direction %s: %s × %s = %s",
                        account.account_direction,
                        balance_before_direction,
                        account.account_direction,
                        balance,
                    )
            
            total_before = total
            total += balance
            log.info(
                "  Running total: %s + %s = %s",
                total_before,
                balance,
                total,
            )
        
        log.info(
            "Balance sheet line total: %s (from %s account(s))",
            total,
            len(accounts),
        )
        
        return total
    
    def _calculate_cumulative_ending_balance(
        self,
        account: Account,
        as_of_date: date,
        include_pending: bool = False,
    ) -> Decimal:
        """
        Calculate cumulative ending balance by summing all journal entries up to as_of_date.
        
        This method:
        1. If as_of_date >= balance_date: Uses opening balance + entries from balance_date to as_of_date
        2. If as_of_date < balance_date: Sums ALL entries up to as_of_date (ignores opening balance)
        
        This handles cases where balance_date is set to a future date relative to the period being calculated.
        """
        balance, _ = self._calculate_cumulative_ending_balance_with_metadata(
            account=account,
            as_of_date=as_of_date,
            include_pending=include_pending,
        )
        return balance
    
    def _get_balance_from_history(
        self,
        account: Account,
        as_of_date: date,
        balance_type: str = 'all',
        currency: Optional[Currency] = None,
    ) -> Optional[Decimal]:
        """
        Get balance from AccountBalanceHistory if available.
        
        Parameters:
        -----------
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
            Determines which balance type to retrieve from history
        
        Returns:
        --------
        Ending balance from the history table for the month containing as_of_date.
        Returns None if history doesn't exist for that period.
        """
        if currency is None:
            currency = account.currency
        
        year = as_of_date.year
        month = as_of_date.month
        
        try:
            history = AccountBalanceHistory.objects.get(
                account=account,
                year=year,
                month=month,
                currency=currency,
                company_id=self.company_id
            )
            return history.get_ending_balance(balance_type)
        except AccountBalanceHistory.DoesNotExist:
            return None
    
    def _calculate_cumulative_ending_balance_with_metadata(
        self,
        account: Account,
        as_of_date: date,
        include_pending: bool = False,
        balance_type: str = 'all',
    ) -> Tuple[Decimal, Dict[str, Any]]:
        """
        Calculate cumulative ending balance with detailed metadata for debugging.
        
        Parameters:
        -----------
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
            Determines which balance type to use from history or calculate on-the-fly
        
        Returns:
            Tuple of (ending_balance, metadata_dict)
        """
        # Try to get from history first (only for leaf accounts)
        if account.is_leaf():
            balance_from_history = self._get_balance_from_history(
                account=account,
                as_of_date=as_of_date,
                balance_type=balance_type,
            )
            
            if balance_from_history is not None:
                # Use pre-calculated balance
                metadata = {
                    'source': 'balance_history',
                    'from_history': True,
                    'balance_type': balance_type,
                    'as_of_date': str(as_of_date),
                    'is_parent': False,
                }
                return balance_from_history, metadata
        
        if not account.is_leaf():
            # Parent account: sum all children's ending balances
            children = account.get_children().filter(company_id=self.company_id)
            total = Decimal('0.00')
            children_details = []
            
            for child in children:
                child_balance, child_metadata = self._calculate_cumulative_ending_balance_with_metadata(
                    account=child,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
                total += child_balance
                children_details.append({
                    'account_id': child.id,
                    'account_name': child.name,
                    'account_code': child.account_code,
                    'balance_contribution': float(child_balance),
                    'details': child_metadata,
                })
            
            metadata = {
                'is_parent': True,
                'children_count': len(children_details),
                'children': children_details,
                'total_from_children': float(total),
            }
            return total, metadata
        
        # Leaf account: calculate from journal entries
        opening_balance = account.balance or Decimal('0.00')
        balance_date = account.balance_date
        
        # Build state filter
        state_filter = Q(state='posted')
        if include_pending:
            state_filter = Q(state__in=['posted', 'pending'])
        
        # Determine calculation approach based on as_of_date vs balance_date
        entries = JournalEntry.objects.filter(
            account=account,
            transaction__company_id=self.company_id,
        ).filter(state_filter)
        
        if balance_date and as_of_date >= balance_date:
            # Normal case: as_of_date is after balance_date
            # Use opening balance + entries from balance_date to as_of_date
            entries = entries.filter(
                Q(date__gt=balance_date) &
                Q(date__lte=as_of_date)
            )
            use_opening_balance = True
            calculation_mode = 'from_balance_date'
        else:
            # as_of_date is BEFORE balance_date (or no balance_date set)
            # Sum ALL entries from the beginning up to as_of_date
            entries = entries.filter(date__lte=as_of_date)
            use_opening_balance = False
            calculation_mode = 'from_beginning'
        
        # Get entry count before aggregation
        entry_count = entries.count()
        
        # Get date range of entries for debugging
        date_range = entries.aggregate(
            min_date=Min('date'),
            max_date=Max('date')
        )
        
        totals = entries.aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        
        total_debit = totals['total_debit'] or Decimal('0.00')
        total_credit = totals['total_credit'] or Decimal('0.00')
        
        # Calculate change with account direction
        net_movement = total_debit - total_credit
        change = net_movement * account.account_direction
        
        # Final balance
        if use_opening_balance:
            ending_balance = opening_balance + change
        else:
            # No opening balance - just the sum of all entries
            ending_balance = change
        
        metadata = {
            'is_parent': False,
            'calculation_mode': calculation_mode,
            'as_of_date': str(as_of_date),
            'account_balance_date': str(balance_date) if balance_date else None,
            'used_opening_balance': use_opening_balance,
            'stored_opening_balance': float(opening_balance),
            'entry_count': entry_count,
            'entries_date_range': {
                'min_date': str(date_range['min_date']) if date_range['min_date'] else None,
                'max_date': str(date_range['max_date']) if date_range['max_date'] else None,
            },
            'total_debit': float(total_debit),
            'total_credit': float(total_credit),
            'net_movement': float(net_movement),
            'account_direction': account.account_direction,
            'adjusted_change': float(change),
            'ending_balance': float(ending_balance),
            'calculation_explanation': (
                f"{'Opening balance (' + str(float(opening_balance)) + ') + ' if use_opening_balance else ''}"
                f"Net movement ({float(net_movement)}) × direction ({account.account_direction}) = "
                f"{'(' + str(float(opening_balance)) + ' + ' + str(float(change)) + ') = ' if use_opening_balance else ''}"
                f"{float(ending_balance)}"
            ),
        }
        
        log.debug(
            "Cumulative ending balance for %s (id=%s) as of %s: "
            "balance_date=%s, use_opening=%s, opening=%s, debit=%s, credit=%s, direction=%s, change=%s, ending=%s",
            account.name,
            account.id,
            as_of_date,
            balance_date,
            use_opening_balance,
            opening_balance if use_opening_balance else 'N/A',
            total_debit,
            total_credit,
            account.account_direction,
            change,
            ending_balance
        )
        
        return ending_balance, metadata
    
    def _calculate_account_balance_from_closing(
        self,
        account: Account,
        as_of_date: date,
        include_pending: bool = False,
    ) -> Decimal:
        """
        Calculate account balance using last closing balance + transactions after closing date.
        This is used for 'balance' calculation_type.
        
        The closing balance (account.balance) is the validated balance as of account.balance_date.
        We add all transactions after that date up to as_of_date, applying account_direction.
        """
        log.debug(
            "Calculating balance from closing for account %s (ID: %s, Code: %s, Is Leaf: %s) "
            "as of %s (include_pending: %s)",
            account.name,
            account.id,
            account.account_code,
            account.is_leaf(),
            as_of_date,
            include_pending,
        )
        
        if account.is_leaf():
            # Get the last closing balance and date
            closing_balance = account.balance or Decimal('0.00')
            closing_date = account.balance_date
            
            log.debug(
                "  Leaf account %s (ID: %s) - Closing balance: %s, Closing date: %s",
                account.name,
                account.id,
                closing_balance,
                closing_date or 'None',
            )
            
            # If as_of_date is before or equal to closing_date, return closing balance with direction
            if closing_date and as_of_date <= closing_date:
                result = closing_balance * account.account_direction
                log.info(
                    "  Account %s (ID: %s) - As of date %s <= closing date %s, "
                    "returning closing balance %s × direction %s = %s",
                    account.name,
                    account.id,
                    as_of_date,
                    closing_date,
                    closing_balance,
                    account.account_direction,
                    result,
                )
                return result
            
            # Get transactions after closing date up to as_of_date
            state_filter = Q(state='posted')
            if include_pending:
                state_filter = Q(state__in=['posted', 'pending'])
            
            entries = JournalEntry.objects.filter(
                account=account,
                date__gt=closing_date if closing_date else date.min,
                date__lte=as_of_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter)
            
            entry_count = entries.count()
            log.debug(
                "  Found %s journal entry/entries after closing date %s up to %s",
                entry_count,
                closing_date or 'beginning',
                as_of_date,
            )
            
            transactions = entries.aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )
            
            total_debit = transactions['total_debit'] or Decimal('0.00')
            total_credit = transactions['total_credit'] or Decimal('0.00')
            
            # Calculate change: (debit - credit) * account_direction
            net_movement = total_debit - total_credit
            change = net_movement * account.account_direction
            
            # Final balance = closing balance (with direction) + change (with direction)
            # Both are normalized by account_direction
            closing_with_direction = closing_balance * account.account_direction
            result = closing_with_direction + change
            
            log.info(
                "  Account %s (ID: %s) - Closing: %s, Debit: %s, Credit: %s, "
                "Net Movement: %s, Direction: %s, Change: %s, Final: %s",
                account.name,
                account.id,
                closing_balance,
                total_debit,
                total_credit,
                net_movement,
                account.account_direction,
                change,
                result,
            )
            
            return result
        else:
            # Parent account: sum all children
            log.info(
                "  Account %s (ID: %s) is a parent account, summing children balances",
                account.name,
                account.id,
            )
            children = account.get_children().filter(company_id=self.company_id)
            children_list = list(children)
            
            if not children_list:
                log.warning(
                    "  ⚠ Parent account %s (ID: %s) has no children for company %s, returning 0.00",
                    account.name,
                    account.id,
                    self.company_id,
                )
                return Decimal('0.00')
            
            log.info(
                "  Found %s child(ren) for parent account %s (ID: %s)",
                len(children_list),
                account.name,
                account.id,
            )
            
            total = Decimal('0.00')
            for idx, child in enumerate(children_list, 1):
                log.debug(
                    "    [%s/%s] Calculating balance from closing for child: %s (ID: %s)",
                    idx,
                    len(children_list),
                    child.name,
                    child.id,
                )
                child_balance = self._calculate_account_balance_from_closing(
                    account=child,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
                total_before = total
                total += child_balance
                log.info(
                    "    Child %s (ID: %s) balance: %s | Running total: %s + %s = %s",
                    child.name,
                    child.id,
                    child_balance,
                    total_before,
                    child_balance,
                    total,
                )
            
            log.info(
                "  Parent account %s (ID: %s) total balance from closing: %s",
                account.name,
                account.id,
                total,
            )
            
            return total
    
    def _calculate_account_balance_with_children(
        self,
        account: Account,
        include_pending: bool,
        beginning_date: Optional[date],
        end_date: Optional[date],
    ) -> Decimal:
        """
        Calculate account balance, ensuring children are properly included for parent accounts.
        
        This method ensures that when calculating a parent account balance, it properly
        sums all children accounts that belong to the same company.
        """
        log.debug(
            "Calculating balance for account %s (ID: %s, Code: %s, Is Leaf: %s) "
            "from %s to %s (include_pending: %s)",
            account.name,
            account.id,
            account.account_code,
            account.is_leaf(),
            beginning_date or 'beginning',
            end_date or 'end',
            include_pending,
        )
        
        if account.is_leaf():
            # Leaf account: calculate directly from journal entries
            log.debug(
                "  Account %s (ID: %s) is a leaf account, calculating directly from journal entries",
                account.name,
                account.id,
            )
            balance = account.calculate_balance(
                include_pending=include_pending,
                beginning_date=beginning_date,
                end_date=end_date,
            ) or Decimal('0.00')
            log.info(
                "  Leaf account %s (ID: %s) balance: %s",
                account.name,
                account.id,
                balance,
            )
            return balance
        else:
            # Parent account: sum all children
            # Ensure we only get children from the same company
            children = account.get_children().filter(company_id=self.company_id)
            children_list = list(children)
            
            log.info(
                "  Account %s (ID: %s) is a parent account with %s child(ren)",
                account.name,
                account.id,
                len(children_list),
            )
            
            if not children_list:
                log.warning(
                    "  ⚠ Parent account %s (ID: %s) has no children for company %s, returning 0.00",
                    account.name,
                    account.id,
                    self.company_id,
                )
                return Decimal('0.00')
            
            total = Decimal('0.00')
            for idx, child in enumerate(children_list, 1):
                log.debug(
                    "    [%s/%s] Calculating balance for child: %s (ID: %s, Code: %s)",
                    idx,
                    len(children_list),
                    child.name,
                    child.id,
                    child.account_code,
                )
                child_balance = self._calculate_account_balance_with_children(
                    account=child,
                    include_pending=include_pending,
                    beginning_date=beginning_date,
                    end_date=end_date,
                )
                total_before = total
                total += child_balance
                log.info(
                    "    Child %s (ID: %s) balance: %s | Running total: %s + %s = %s",
                    child.name,
                    child.id,
                    child_balance,
                    total_before,
                    child_balance,
                    total,
                )
            
            log.info(
                "  Parent account %s (ID: %s) total balance: %s (from %s child(ren))",
                account.name,
                account.id,
                total,
                len(children_list),
            )
            
            return total
    
    def _calculate_income_statement_line(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        calculation_type: str,
        include_pending: bool = False,
    ) -> Decimal:
        """Calculate income statement line (period activity)."""
        log.info(
            "Calculating income statement line for %s account(s) "
            "from %s to %s (calculation_type: %s, include_pending: %s)",
            len(accounts),
            start_date,
            end_date,
            calculation_type,
            include_pending,
        )
        
        total = Decimal('0.00')
        
        for idx, account in enumerate(accounts, 1):
            log.info(
                "[%s/%s] Processing account: %s (ID: %s, Code: %s, Is Leaf: %s, Direction: %s)",
                idx,
                len(accounts),
                account.name,
                account.id,
                account.account_code,
                account.is_leaf(),
                account.account_direction,
            )
            
            if account.is_leaf():
                # Leaf account: calculate from journal entries
                log.debug(
                    "  Account %s (ID: %s) is a leaf account, calculating from journal entries",
                    account.name,
                    account.id,
                )
                
                if include_pending:
                    state_filter = Q(state__in=['posted', 'pending'])
                else:
                    state_filter = Q(state='posted')
                
                entries = JournalEntry.objects.filter(
                    account=account,
                    date__gte=start_date,
                    date__lte=end_date,
                    transaction__company_id=self.company_id,
                ).filter(state_filter)
                
                entry_count = entries.count()
                log.debug(
                    "  Found %s journal entry/entries for account %s (ID: %s) in period",
                    entry_count,
                    account.name,
                    account.id,
                )
                
                if calculation_type == 'difference':
                    # Debit - Credit (no account direction)
                    log.debug("  Using 'difference' calculation (debit - credit, no direction)")
                    debit_total = entries.aggregate(
                        total=Sum('debit_amount')
                    )['total'] or Decimal('0.00')
                    credit_total = entries.aggregate(
                        total=Sum('credit_amount')
                    )['total'] or Decimal('0.00')
                    balance = debit_total - credit_total
                    log.info(
                        "  Account %s (ID: %s) - Debit: %s, Credit: %s, Difference: %s",
                        account.name,
                        account.id,
                        debit_total,
                        credit_total,
                        balance,
                    )
                elif calculation_type == 'balance':
                    # Balance: Use last closing balance + transactions after closing date
                    log.debug("  Using 'balance' calculation (from closing balance)")
                    balance = self._calculate_account_balance_from_closing(
                        account=account,
                        as_of_date=end_date,
                        include_pending=include_pending,
                    )
                    log.info(
                        "  Account %s (ID: %s) balance from closing: %s",
                        account.name,
                        account.id,
                        balance,
                    )
                else:
                    # Sum: Period movements with account direction (e.g., cash flow)
                    log.debug(
                        "  Using 'sum' calculation (debit - credit) × direction %s",
                        account.account_direction,
                    )
                    debit_total = entries.aggregate(
                        total=Sum('debit_amount')
                    )['total'] or Decimal('0.00')
                    credit_total = entries.aggregate(
                        total=Sum('credit_amount')
                    )['total'] or Decimal('0.00')
                    net_movement = debit_total - credit_total
                    balance = net_movement * account.account_direction
                    log.info(
                        "  Account %s (ID: %s) - Debit: %s, Credit: %s, Net: %s, "
                        "Direction: %s, Final: %s",
                        account.name,
                        account.id,
                        debit_total,
                        credit_total,
                        net_movement,
                        account.account_direction,
                        balance,
                    )
                
                total_before = total
                total += balance
                log.info(
                    "  Running total: %s + %s = %s",
                    total_before,
                    balance,
                    total,
                )
            else:
                # Parent account: sum children's period activity
                log.info(
                    "  Account %s (ID: %s) is a parent account, summing children",
                    account.name,
                    account.id,
                )
                children = account.get_children().filter(company_id=self.company_id)
                children_list = list(children)
                log.info(
                    "  Found %s child(ren) for parent account %s (ID: %s)",
                    len(children_list),
                    account.name,
                    account.id,
                )
                
                for child_idx, child in enumerate(children_list, 1):
                    log.debug(
                        "    [%s/%s] Recursively calculating child: %s (ID: %s)",
                        child_idx,
                        len(children_list),
                        child.name,
                        child.id,
                    )
                    # Recursively calculate child balance for the period
                    child_balance = self._calculate_income_statement_line(
                        accounts=[child],
                        start_date=start_date,
                        end_date=end_date,
                        calculation_type=calculation_type,
                        include_pending=include_pending,
                    )
                    total_before = total
                    total += child_balance
                    log.info(
                        "    Child %s (ID: %s) balance: %s | Running total: %s + %s = %s",
                        child.name,
                        child.id,
                        child_balance,
                        total_before,
                        child_balance,
                        total,
                    )
        
        log.info(
            "Income statement line total: %s (from %s account(s))",
            total,
            len(accounts),
        )
        
        return total
    
    def _calculate_cash_flow_line(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        calculation_type: str,
        include_pending: bool = False,
    ) -> Decimal:
        """Calculate cash flow line (cash accounts only)."""
        # Accounts should already be expanded to leaf accounts by _get_accounts_for_line
        # Filter to cash/bank accounts (only leaf accounts with bank_account)
        cash_accounts = [acc for acc in accounts if acc.bank_account is not None]
        
        log.debug(
            "Cash flow calculation: %s accounts provided, %s have bank_account",
            len(accounts),
            len(cash_accounts)
        )
        
        if not cash_accounts:
            log.warning(
                "No cash accounts found in %s accounts for cash flow calculation",
                len(accounts)
            )
            return Decimal('0.00')
        
        # Calculate period change in cash
        total = Decimal('0.00')
        for account in cash_accounts:
            log.debug(
                "Calculating cash flow for account %s (id=%s, bank_account_id=%s)",
                account.name,
                account.id,
                account.bank_account_id
            )
            
            if calculation_type == 'sum':
                # Sum: Period movements with account direction (inflows - outflows)
                state_filter = Q(state='posted')
                if include_pending:
                    state_filter = Q(state__in=['posted', 'pending'])
                
                entries = JournalEntry.objects.filter(
                    account=account,
                    date__gte=start_date,
                    date__lte=end_date,
                    transaction__company_id=self.company_id,
                ).filter(state_filter)
                
                debit_total = entries.aggregate(
                    total=Sum('debit_amount')
                )['total'] or Decimal('0.00')
                credit_total = entries.aggregate(
                    total=Sum('credit_amount')
                )['total'] or Decimal('0.00')
                
                # Apply account direction for cash flow (inflows - outflows)
                change = (debit_total - credit_total) * account.account_direction
            elif calculation_type == 'balance':
                # Balance: Cumulative ending balance from all journal entries up to end_date
                # Sums opening balance + all entries to get the final balance for that period
                change = self._calculate_cumulative_ending_balance(
                    account=account,
                    as_of_date=end_date,
                    include_pending=include_pending,
                )
            else:
                # Difference or default: Calculate period change
                beginning_balance = account.calculate_balance(
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=start_date,
                ) or Decimal('0.00')
                
                ending_balance = account.calculate_balance(
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=end_date,
                ) or Decimal('0.00')
                
                change = ending_balance - beginning_balance
            
            total += change
            
            log.debug(
                "Account %s: change=%s (calculation_type=%s)",
                account.name,
                change,
                calculation_type
            )
        
        log.debug("Total cash flow change: %s", total)
        return total
    
    def _calculate_period_balance(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        calculation_type: str,
        include_pending: bool = False,
    ) -> Decimal:
        """Calculate period balance (generic)."""
        return self._calculate_income_statement_line(
            accounts,
            start_date,
            end_date,
            calculation_type,
            include_pending=include_pending,
        )
    
    def _evaluate_formula(
        self,
        formula: str,
        line_values: Dict[int, Decimal],
    ) -> Decimal:
        """
        Evaluate a formula referencing other line numbers.
        
        Uses the safe formula evaluator (no eval()).
        
        Parameters
        ----------
        formula : str
            Formula string with L-tokens (e.g., "L1 + L2 - L3")
        line_values : Dict[int, Decimal]
            Dictionary mapping line numbers to their calculated values
            
        Returns
        -------
        Decimal
            Result of the formula evaluation
        """
        try:
            return _formula_evaluator.evaluate(formula, line_values)
        except FormulaError as e:
            log.warning("Formula evaluation failed: %s - %s", formula, e)
            return Decimal('0.00')
    
    def _calculate_totals(
        self,
        statement: FinancialStatement,
        line_values: Dict[int, Decimal],
        report_type: str,
    ) -> None:
        """Calculate and store statement totals."""
        if report_type == 'balance_sheet':
            # Find asset, liability, and equity totals
            # This depends on your template structure
            # For now, we'll calculate from lines
            statement.total_assets = Decimal('0.00')
            statement.total_liabilities = Decimal('0.00')
            statement.total_equity = Decimal('0.00')
            
            # You would identify which lines are assets/liabilities/equity
            # based on your template structure
            statement.save(update_fields=[
                'total_assets',
                'total_liabilities',
                'total_equity',
            ])
        
        elif report_type == 'income_statement':
            # Find revenue and expense totals, calculate net income
            statement.net_income = Decimal('0.00')
            # Calculate from lines
            statement.save(update_fields=['net_income'])
    
    def generate_time_series(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        dimension: Optional[Union[str, List[str]]] = 'month',
        line_numbers: Optional[List[int]] = None,
        include_pending: bool = False,
        include_metadata: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a time series for specific lines grouped by time dimension.
        
        Parameters
        ----------
        template: FinancialStatementTemplate
            Template to use
        start_date: date
            Start of the period
        end_date: date
            End of the period
        dimension: Union[str, List[str]]
            Time dimension(s) ('day', 'week', 'month', 'quarter', 'semester', 'year')
            Can be a single dimension string or a list of dimensions
        line_numbers: Optional[List[int]]
            Specific line numbers to include. If None, includes all lines.
        include_pending: bool
            Include pending journal entries
        include_metadata: bool
            Include calculation memory and metadata for debugging
        
        Returns
        -------
        Dict[str, Any]
            Time series data with periods and values.
            If multiple dimensions, returns dict with dimension as key.
            If single dimension, returns the data directly.
        """
        from accounting.utils_time_dimensions import generate_periods
        
        # Handle multiple dimensions
        dimensions = dimension if isinstance(dimension, list) else [dimension]
        
        if len(dimensions) > 1:
            # Multiple dimensions: return dict with dimension as key
            result = {
                'template_id': template.id,
                'template_name': template.name,
                'report_type': template.report_type,
                'dimensions': dimensions,
                'start_date': start_date,
                'end_date': end_date,
                'data': {}
            }
            
            for dim in dimensions:
                result['data'][dim] = self._generate_single_dimension_time_series(
                    template, start_date, end_date, dim, line_numbers, include_pending, include_metadata
                )
            
            return result
        else:
            # Single dimension: return current structure
            return self._generate_single_dimension_time_series(
                template, start_date, end_date, dimensions[0], line_numbers, include_pending, include_metadata
            )
    
    def _generate_single_dimension_time_series(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        dimension: str,
        line_numbers: Optional[List[int]],
        include_pending: bool,
        include_metadata: bool = False,
    ) -> Dict[str, Any]:
        """Generate time series for a single dimension."""
        from accounting.utils_time_dimensions import generate_periods
        
        periods = generate_periods(start_date, end_date, dimension)
        line_templates = template.line_templates.all().order_by('line_number')
        
        if line_numbers:
            line_templates = line_templates.filter(line_number__in=line_numbers)
        
        log.info(
            "="*80 + "\n"
            "STARTING TIME SERIES GENERATION\n"
            "="*80 + "\n"
            "Template: %s (ID: %s)\n"
            "Report Type: %s\n"
            "Company ID: %s\n"
            "Period: %s to %s\n"
            "Dimension: %s\n"
            "Include Pending: %s\n"
            "Include Metadata: %s\n"
            "Line Numbers Filter: %s\n"
            "Total Periods: %s\n"
            "Total Line Templates: %s\n"
            "="*80,
            template.name,
            template.id,
            template.report_type,
            self.company_id,
            start_date,
            end_date,
            dimension,
            include_pending,
            include_metadata,
            line_numbers or 'All',
            len(periods),
            line_templates.count(),
        )
        
        series_data = {}
        
        # Pre-compute period line values for formula support
        # Each period needs its own set of line values computed sequentially
        period_line_values: Dict[str, Dict[int, Decimal]] = {}
        for period in periods:
            period_line_values[period['key']] = {}
        
        # Process all lines for all periods, computing sequentially per period
        for line_template in line_templates:
            log.info(
                "\n" + "-"*80 + "\n"
                "PROCESSING LINE %s: %s FOR TIME SERIES\n"
                "-"*80,
                line_template.line_number,
                line_template.label,
            )
            
            line_series = []
            
            # Get accounts for this line (for metadata)
            accounts = self._get_accounts_for_line(line_template) if include_metadata else []
            
            log.info(
                "Line %s: Processing %s period(s)",
                line_template.line_number,
                len(periods),
            )
            
            for period_idx, period in enumerate(periods, 1):
                period_key = period['key']
                log.debug(
                    "  [%s/%s] Calculating line %s for period %s (%s to %s)",
                    period_idx,
                    len(periods),
                    line_template.line_number,
                    period_key,
                    period['start_date'],
                    period['end_date'],
                )
                
                # Get the accumulated line values for this period
                # (previous lines in this period have already been computed)
                current_period_line_values = period_line_values[period_key]
                
                # Calculate value for this line in this period
                if include_metadata:
                    value, calculation_memory = self._calculate_line_value_with_metadata(
                        line_template,
                        period['start_date'],
                        period['end_date'],
                        period['end_date'],  # as_of_date
                        template.report_type,
                        current_period_line_values,  # Pass accumulated values for this period
                        include_pending=include_pending,
                    )
                    
                    line_series.append({
                        'period_key': period_key,
                        'period_label': period['label'],
                        'start_date': period['start_date'],
                        'end_date': period['end_date'],
                        'value': float(value),
                        'calculation_memory': calculation_memory,
                    })
                else:
                    value = self._calculate_line_value(
                        line_template,
                        period['start_date'],
                        period['end_date'],
                        period['end_date'],  # as_of_date
                        template.report_type,
                        current_period_line_values,  # Pass accumulated values for this period
                        include_pending=include_pending,
                    )
                    
                    line_series.append({
                        'period_key': period_key,
                        'period_label': period['label'],
                        'start_date': period['start_date'],
                        'end_date': period['end_date'],
                        'value': float(value),
                    })
                
                # Store the computed value for this period so subsequent lines can reference it
                period_line_values[period_key][line_template.line_number] = value
            
            line_data = {
                'line_number': line_template.line_number,
                'label': line_template.label,
                'line_type': line_template.line_type,
                'indent_level': line_template.indent_level,
                'is_bold': line_template.is_bold,
                'data': line_series,
            }
            
            # Add line metadata if requested
            if include_metadata:
                line_data['metadata'] = {
                    'calculation_method': line_template.get_effective_calculation_method(),
                    'calculation_type': line_template.calculation_type,  # Deprecated
                    'sign_policy': line_template.sign_policy,
                    'account_id': line_template.account_id,
                    'account_ids': line_template.account_ids,
                    'account_code_prefix': line_template.account_code_prefix,
                    'account_path_contains': line_template.account_path_contains,
                    'include_descendants': line_template.include_descendants,
                    'formula': line_template.formula,
                    'resolved_accounts': [
                        {
                            'id': acc.id,
                            'name': acc.name,
                            'account_code': acc.account_code,
                            'bank_account_id': acc.bank_account_id,
                            'account_direction': acc.account_direction,
                            'is_leaf': acc.is_leaf(),
                        }
                        for acc in accounts
                    ],
                }
            
            series_data[line_template.line_number] = line_data
        
        return {
            'template_id': template.id,
            'template_name': template.name,
            'report_type': template.report_type,
            'dimension': dimension,
            'start_date': start_date,
            'end_date': end_date,
            'lines': list(series_data.values()),
        }
    
    def preview_time_series(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        dimension: Optional[Union[str, List[str]]] = 'month',
        line_numbers: Optional[List[int]] = None,
        include_pending: bool = False,
        include_metadata: bool = False,
    ) -> Dict[str, Any]:
        """Preview time series without saving (same as generate_time_series but marked as preview)."""
        result = self.generate_time_series(
            template, start_date, end_date, dimension, line_numbers, include_pending, include_metadata
        )
        if isinstance(dimension, list) or (isinstance(result, dict) and 'data' in result):
            result['is_preview'] = True
        else:
            result['is_preview'] = True
        return result
    
    def _calculate_statement_data(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
        include_pending: bool = False,
        currency_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate statement data WITHOUT persisting to database.
        
        This is the core calculation logic that can be used for both
        preview and generation. Returns a dictionary with all computed values.
        
        Note: This method ensures balance history is persisted even though
        the statement itself is not saved. This ensures future queries are faster.
        
        Parameters
        ----------
        template : FinancialStatementTemplate
            Template defining the statement structure
        start_date : date
            Start of reporting period
        end_date : date
            End of reporting period
        as_of_date : Optional[date]
            For balance sheet: specific date. If None, defaults to end_date
        include_pending : bool
            Whether to include pending journal entries
        currency_id : Optional[int]
            Currency ID for balance history calculation
            
        Returns
        -------
        Dict[str, Any]
            Statement data with 'lines', 'line_values', and metadata
        """
        if as_of_date is None:
            as_of_date = end_date
        
        # Ensure balance history exists for the period (auto-recalculate if missing)
        # This persists the calculated balances even for previews/comparisons
        self._ensure_balance_history_for_period(
            start_date=start_date,
            end_date=end_date,
            currency_id=currency_id,
            account_ids=None,
            template=template,
            generated_by=None,  # No user for internal calculations
        )
        
        line_templates = template.line_templates.all().order_by('line_number')
        line_values: Dict[int, Decimal] = {}
        lines_data = []
        
        log.debug(
            "Calculating statement data (no persist): template=%s, period=%s to %s, as_of=%s",
            template.id, start_date, end_date, as_of_date
        )
        
        for line_template in line_templates:
            value = self._calculate_line_value(
                line_template,
                start_date,
                end_date,
                as_of_date,
                template.report_type,
                line_values,
                include_pending=include_pending,
            )
            line_values[line_template.line_number] = value
            
            lines_data.append({
                'line_number': line_template.line_number,
                'label': line_template.label,
                'line_type': line_template.line_type,
                'balance': value,
                'indent_level': line_template.indent_level,
                'is_bold': line_template.is_bold,
                'account_ids': self._get_account_ids_for_line(line_template),
                'calculation_method': line_template.get_effective_calculation_method(),
                'formula': line_template.formula if line_template.get_effective_calculation_method() == 'formula' else None,
            })
        
        return {
            'template_id': template.id,
            'template_name': template.name,
            'report_type': template.report_type,
            'start_date': start_date,
            'end_date': end_date,
            'as_of_date': as_of_date,
            'lines': lines_data,
            'line_values': line_values,  # Raw values for formula references
        }
    
    def generate_with_comparisons(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        comparison_types: List[str],
        dimension: Optional[str] = None,
        include_pending: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate financial statement with comparisons.
        
        Parameters
        ----------
        template: FinancialStatementTemplate
            Template to use
        start_date: date
            Start of current period
        end_date: date
            End of current period
        comparison_types: List[str]
            List of comparison types:
            - 'previous_period'
            - 'previous_year'
            - 'ytd_previous_year'
            - 'last_12_months'
            - 'same_period_last_year'
        dimension: Optional[str]
            Time dimension to break down current period ('month', 'quarter', etc.)
            If provided, breaks down current period by dimension and compares each sub-period
        include_pending: bool
            Include pending journal entries
        
        Returns
        -------
        Dict[str, Any]
            Statement data with comparisons.
            If dimension is provided, returns breakdown by dimension periods.
        """
        from accounting.utils_time_dimensions import (
            get_comparison_period,
            calculate_period_comparison,
            generate_periods,
        )
        
        # If dimension is provided, break down current period by dimension
        if dimension:
            periods = generate_periods(start_date, end_date, dimension)
            result = {
                'template_id': template.id,
                'template_name': template.name,
                'report_type': template.report_type,
                'dimension': dimension,
                'start_date': start_date,
                'end_date': end_date,
                'periods': []
            }
            
            for period in periods:
                period_data = self._generate_comparison_for_period(
                    template, period['start_date'], period['end_date'],
                    comparison_types, include_pending, dimension=dimension
                )
                period_data['period_key'] = period['key']
                period_data['period_label'] = period['label']
                result['periods'].append(period_data)
            
            return result
        else:
            # Original behavior: single period comparison
            return self._generate_comparison_for_period(
                template, start_date, end_date, comparison_types, include_pending, dimension=None
            )
    
    def _generate_comparison_for_period(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        comparison_types: List[str],
        include_pending: bool,
        dimension: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate comparison for a single period."""
        from accounting.utils_time_dimensions import (
            get_comparison_period,
            calculate_period_comparison,
        )
        
        log.info(
            "="*80 + "\n"
            "STARTING COMPARISON GENERATION\n"
            "="*80 + "\n"
            "Template: %s (ID: %s)\n"
            "Report Type: %s\n"
            "Company ID: %s\n"
            "Current Period: %s to %s\n"
            "Comparison Types: %s\n"
            "Dimension: %s\n"
            "Include Pending: %s\n"
            "="*80,
            template.name,
            template.id,
            template.report_type,
            self.company_id,
            start_date,
            end_date,
            comparison_types,
            dimension or 'None',
            include_pending,
        )
        
        # Generate current period statement
        log.info("Generating current period statement...")
        statement = self.generate_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            status='draft',
            include_pending=include_pending,
        )
        
        log.info("Current period statement generated (ID: %s)", statement.id)
        
        # Get current line values and calculation metadata
        current_lines = {}
        current_line_metadata = {}
        for line in statement.lines.all():
            current_lines[line.line_number] = line.balance
            # Get calculation metadata for this line
            line_template = line.line_template
            if line_template:
                current_line_metadata[line.line_number] = {
                    'account_ids': line.account_ids or [],
                    'calculation_type': line_template.calculation_type,
                    'formula': line_template.formula if line_template.calculation_type == 'formula' else None,
                    'account_code_prefix': line_template.account_code_prefix,
                    'account_path_contains': line_template.account_path_contains,
                }
            else:
                current_line_metadata[line.line_number] = {
                    'account_ids': line.account_ids or [],
                    'calculation_type': 'unknown',
                    'formula': None,
                    'account_code_prefix': None,
                    'account_path_contains': None,
                }
        
        # Generate comparisons
        comparisons = {}
        
        log.info("Generating %s comparison(s)...", len(comparison_types))
        
        for comp_idx, comp_type in enumerate(comparison_types, 1):
            log.info(
                "\n" + "-"*80 + "\n"
                "PROCESSING COMPARISON %s/%s: %s\n"
                "-"*80,
                comp_idx,
                len(comparison_types),
                comp_type,
            )
            
            try:
                comp_start, comp_end = get_comparison_period(
                    start_date,
                    end_date,
                    comp_type,
                    dimension=dimension
                )
                
                log.info(
                    "Comparison period for %s: %s to %s",
                    comp_type,
                    comp_start,
                    comp_end,
                )
                
                # Generate comparison statement
                log.info("Generating comparison statement...")
                comp_statement = self.generate_statement(
                    template=template,
                    start_date=comp_start,
                    end_date=comp_end,
                    status='draft',
                    include_pending=include_pending,
                )
                
                log.info("Comparison statement generated (ID: %s)", comp_statement.id)
                
                # Get comparison line values and metadata
                comp_lines = {}
                comp_line_metadata = {}
                for line in comp_statement.lines.all():
                    comp_lines[line.line_number] = line.balance
                    line_template = line.line_template
                    if line_template:
                        comp_line_metadata[line.line_number] = {
                            'account_ids': line.account_ids or [],
                            'calculation_type': line_template.calculation_type,
                            'formula': line_template.formula if line_template.calculation_type == 'formula' else None,
                        }
                    else:
                        comp_line_metadata[line.line_number] = {
                            'account_ids': line.account_ids or [],
                            'calculation_type': 'unknown',
                            'formula': None,
                        }
                
                # Calculate comparison metrics
                line_comparisons = {}
                for line_num in current_lines:
                    current_val = current_lines.get(line_num, Decimal('0.00'))
                    comp_val = comp_lines.get(line_num, Decimal('0.00'))
                    
                    comparison_result = calculate_period_comparison(
                        current_val,
                        comp_val,
                        comp_type
                    )
                    
                    # Add calculation memory
                    comparison_result['calculation_memory'] = {
                        'current_period': {
                            'start_date': str(start_date),
                            'end_date': str(end_date),
                            'value': float(current_val),
                            'metadata': current_line_metadata.get(line_num, {}),
                        },
                        'comparison_period': {
                            'start_date': str(comp_start),
                            'end_date': str(comp_end),
                            'value': float(comp_val),
                            'metadata': comp_line_metadata.get(line_num, {}),
                        },
                        'comparison_type': comp_type,
                        'dimension': dimension,
                        'include_pending': include_pending,
                    }
                    
                    line_comparisons[line_num] = comparison_result
                
                comparisons[comp_type] = {
                    'start_date': comp_start,
                    'end_date': comp_end,
                    'lines': line_comparisons,
                    'calculation_memory': {
                        'dimension': dimension,
                        'comparison_type': comp_type,
                        'current_period': {
                            'start_date': str(start_date),
                            'end_date': str(end_date),
                        },
                        'comparison_period': {
                            'start_date': str(comp_start),
                            'end_date': str(comp_end),
                        },
                        'include_pending': include_pending,
                    },
                }
                
            except Exception as e:
                log.warning(f"Failed to generate comparison {comp_type}: {e}")
                comparisons[comp_type] = {
                    'error': str(e)
                }
        
        # Build statement lines with calculation metadata
        statement_lines = []
        for line in statement.lines.all():
            line_data = {
                'line_number': line.line_number,
                'label': line.label,
                'balance': float(line.balance),
                'indent_level': line.indent_level,
                'is_bold': line.is_bold,
            }
            
            # Add calculation memory for statement lines
            line_template = line.line_template
            if line_template:
                line_data['calculation_memory'] = {
                    'account_ids': line.account_ids or [],
                    'calculation_type': line_template.calculation_type,
                    'formula': line_template.formula if line_template.calculation_type == 'formula' else None,
                    'account_code_prefix': line_template.account_code_prefix,
                    'account_path_contains': line_template.account_path_contains,
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'include_pending': include_pending,
                }
            else:
                line_data['calculation_memory'] = {
                    'account_ids': line.account_ids or [],
                    'calculation_type': 'unknown',
                    'formula': None,
                    'account_code_prefix': None,
                    'account_path_contains': None,
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'include_pending': include_pending,
                }
            
            statement_lines.append(line_data)
        
        return {
            'statement': {
                'id': statement.id,
                'name': statement.name,
                'start_date': statement.start_date,
                'end_date': statement.end_date,
                'lines': statement_lines,
            },
            'comparisons': comparisons,
        }
    
    def preview_with_comparisons(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        comparison_types: List[str],
        dimension: Optional[str] = None,
        include_pending: bool = False,
    ) -> Dict[str, Any]:
        """
        Preview comparisons WITHOUT saving any statements to the database.
        
        Unlike generate_with_comparisons, this method:
        - Does NOT create FinancialStatement records
        - Does NOT create FinancialStatementLine records
        - Uses _calculate_statement_data for computation
        
        Parameters
        ----------
        template : FinancialStatementTemplate
            Template to use
        start_date : date
            Start of current period
        end_date : date
            End of current period
        comparison_types : List[str]
            List of comparison types
        dimension : Optional[str]
            Time dimension to break down current period
        include_pending : bool
            Include pending journal entries
            
        Returns
        -------
        Dict[str, Any]
            Comparison data (no DB records created)
        """
        from accounting.utils_time_dimensions import (
            get_comparison_period,
            calculate_period_comparison,
            generate_periods,
        )
        
        log.info(
            "Preview comparison (no persist): template=%s, period=%s to %s, types=%s",
            template.id, start_date, end_date, comparison_types
        )
        
        # If dimension is provided, break down current period by dimension
        if dimension:
            periods = generate_periods(start_date, end_date, dimension)
            result = {
                'template_id': template.id,
                'template_name': template.name,
                'report_type': template.report_type,
                'dimension': dimension,
                'start_date': start_date,
                'end_date': end_date,
                'is_preview': True,
                'periods': []
            }
            
            for period in periods:
                period_data = self._preview_comparison_for_period(
                    template, period['start_date'], period['end_date'],
                    comparison_types, include_pending, dimension=dimension
                )
                period_data['period_key'] = period['key']
                period_data['period_label'] = period['label']
                result['periods'].append(period_data)
            
            return result
        else:
            # Single period comparison
            result = self._preview_comparison_for_period(
                template, start_date, end_date, comparison_types, include_pending, dimension=None
            )
            result['is_preview'] = True
            return result
    
    def _preview_comparison_for_period(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        comparison_types: List[str],
        include_pending: bool,
        dimension: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Preview comparison for a single period WITHOUT persisting.
        
        Uses _calculate_statement_data instead of generate_statement.
        """
        from accounting.utils_time_dimensions import (
            get_comparison_period,
            calculate_period_comparison,
        )
        
        # Get currency from template or use default
        # For balance history, we'll calculate for all currencies used by accounts
        currency_id = None  # None means all currencies
        
        # Calculate current period data (no DB save)
        current_data = self._calculate_statement_data(
            template=template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=end_date,
            include_pending=include_pending,
            currency_id=currency_id,
        )
        
        # Build current line values dict
        current_lines = {
            line['line_number']: line['balance']
            for line in current_data['lines']
        }
        
        # Generate comparisons
        comparisons = {}
        
        for comp_type in comparison_types:
            try:
                comp_start, comp_end = get_comparison_period(
                    start_date, end_date, comp_type, dimension=dimension
                )
                
                # Calculate comparison period data (no DB save)
                comp_data = self._calculate_statement_data(
                    template=template,
                    start_date=comp_start,
                    end_date=comp_end,
                    as_of_date=comp_end,
                    include_pending=include_pending,
                    currency_id=currency_id,
                )
                
                comp_lines = {
                    line['line_number']: line['balance']
                    for line in comp_data['lines']
                }
                
                # Calculate comparison metrics
                line_comparisons = {}
                for line_num, current_val in current_lines.items():
                    comp_val = comp_lines.get(line_num, Decimal('0.00'))
                    
                    comparison_result = calculate_period_comparison(
                        current_val, comp_val, comp_type
                    )
                    line_comparisons[line_num] = comparison_result
                
                comparisons[comp_type] = {
                    'start_date': comp_start,
                    'end_date': comp_end,
                    'lines': line_comparisons,
                }
                
            except Exception as e:
                log.warning("Failed to generate preview comparison %s: %s", comp_type, e)
                comparisons[comp_type] = {'error': str(e)}
        
        # Build statement data for response
        statement_lines = []
        for line in current_data['lines']:
            statement_lines.append({
                'line_number': line['line_number'],
                'label': line['label'],
                'balance': float(line['balance']),
                'indent_level': line['indent_level'],
                'is_bold': line['is_bold'],
            })
        
        return {
            'statement': {
                'name': template.name,
                'start_date': start_date,
                'end_date': end_date,
                'lines': statement_lines,
            },
            'comparisons': comparisons,
        }
    
    def diagnose_line_calculation(
        self,
        line_template: FinancialStatementLineTemplate,
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Diagnostic method to debug why a line is returning zero.
        
        Returns detailed information about:
        - Account selection
        - Journal entries found
        - Calculation results
        - Potential issues
        """
        if as_of_date is None:
            as_of_date = end_date
        
        diagnosis = {
            'line_template': {
                'id': line_template.id,
                'line_number': line_template.line_number,
                'label': line_template.label,
                'calculation_method': line_template.get_effective_calculation_method(),
                'account_id': line_template.account_id,
                'account_ids': line_template.account_ids,
                'account_code_prefix': line_template.account_code_prefix,
                'account_path_contains': line_template.account_path_contains,
                'include_descendants': getattr(line_template, 'include_descendants', True),
            },
            'date_range': {
                'start_date': str(start_date),
                'end_date': str(end_date),
                'as_of_date': str(as_of_date),
            },
            'company_id': self.company_id,
            'accounts_selected': [],
            'journal_entries': [],
            'calculation_result': None,
            'issues': [],
        }
        
        # Get accounts
        accounts = self._get_accounts_for_line(line_template)
        diagnosis['accounts_selected'] = [
            {
                'id': acc.id,
                'code': acc.account_code,
                'name': acc.name,
                'is_leaf': acc.is_leaf(),
                'account_direction': acc.account_direction,
                'parent_id': acc.parent_id,
            }
            for acc in accounts
        ]
        
        if not accounts:
            diagnosis['issues'].append('No accounts found for this line')
            return diagnosis
        
        # Check journal entries for each account
        for account in accounts:
            # All entries for this account
            all_entries = JournalEntry.objects.filter(
                account=account,
                transaction__company_id=self.company_id,
            )
            
            # Entries in date range (any state)
            entries_in_range = JournalEntry.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
                transaction__company_id=self.company_id,
            )
            
            # Posted entries in date range
            posted_entries = entries_in_range.filter(state='posted')
            
            # Pending entries in date range
            pending_entries = entries_in_range.filter(state='pending')
            
            account_info = {
                'account_id': account.id,
                'account_code': account.account_code,
                'account_name': account.name,
                'total_entries_all_time': all_entries.count(),
                'entries_in_date_range': entries_in_range.count(),
                'posted_entries_in_range': posted_entries.count(),
                'pending_entries_in_range': pending_entries.count(),
                'sample_entries': [],
            }
            
            # Get sample entries
            sample = entries_in_range[:5]
            for entry in sample:
                account_info['sample_entries'].append({
                    'id': entry.id,
                    'date': str(entry.date),
                    'state': entry.state,
                    'debit_amount': float(entry.debit_amount) if entry.debit_amount else 0,
                    'credit_amount': float(entry.credit_amount) if entry.credit_amount else 0,
                    'transaction_id': entry.transaction_id,
                })
            
            diagnosis['journal_entries'].append(account_info)
            
            # Check for issues
            if all_entries.count() == 0:
                diagnosis['issues'].append(
                    f"Account {account.account_code} ({account.name}) has no journal entries at all"
                )
            elif entries_in_range.count() == 0:
                # Check if entries exist outside date range
                earliest = all_entries.order_by('date').first()
                latest = all_entries.order_by('-date').first()
                if earliest and latest:
                    diagnosis['issues'].append(
                        f"Account {account.account_code} has entries but none in range [%s, %s]. "
                        "Entries exist from %s to %s" % (
                            start_date, end_date, earliest.date, latest.date
                        )
                    )
            elif posted_entries.count() == 0 and pending_entries.count() > 0:
                diagnosis['issues'].append(
                    f"Account {account.account_code} has {pending_entries.count()} pending entries "
                    "but no posted entries. Set include_pending=True to include them."
                )
        
        # Calculate the actual value
        calc_method = line_template.get_effective_calculation_method()
        if calc_method == 'net_movement':
            diagnosis['calculation_result'] = float(self._calc_net_movement(
                accounts, start_date, end_date, include_pending=False
            ))
        elif calc_method == 'ending_balance':
            diagnosis['calculation_result'] = float(self._calc_ending_balance(
                accounts, as_of_date, include_pending=False
            ))
        elif calc_method == 'opening_balance':
            opening_date = start_date - timedelta(days=1)
            diagnosis['calculation_result'] = float(self._calc_ending_balance(
                accounts, opening_date, include_pending=False
            ))
        else:
            diagnosis['calculation_result'] = 'Not calculated (method: %s)' % calc_method
        
        # Check if parent account has entries (common issue)
        if line_template.account and not line_template.account.is_leaf():
            parent_entries_all = JournalEntry.objects.filter(
                account=line_template.account,
                transaction__company_id=self.company_id,
            )
            parent_entries_range = parent_entries_all.filter(
                date__gte=start_date,
                date__lte=end_date,
            )
            
            if parent_entries_all.count() > 0:
                diagnosis['parent_account_entries'] = {
                    'account_id': line_template.account.id,
                    'account_name': line_template.account.name,
                    'total_entries': parent_entries_all.count(),
                    'entries_in_range': parent_entries_range.count(),
                }
                diagnosis['issues'].append(
                    f"⚠️  PARENT ACCOUNT '{line_template.account.name}' (ID: {line_template.account.id}) "
                    f"has {parent_entries_all.count()} entries ({parent_entries_range.count()} in date range). "
                    "Entries may be linked to parent account instead of leaf accounts! "
                    "Journal entries should be linked to leaf accounts, not parent accounts."
                )
        
        return diagnosis

