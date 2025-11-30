"""
Financial Statement Generation Service

Generates financial statements (Balance Sheet, P&L, Cash Flow, etc.)
from accounting data.
"""

import logging
from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional, Set, Any
from django.db.models import Q, Sum, F
from django.db import transaction

from accounting.models import Account, JournalEntry, Currency
from accounting.models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
    FinancialStatement,
    FinancialStatementLine,
)

log = logging.getLogger(__name__)


class FinancialStatementGenerator:
    """Generates financial statements from templates and accounting data."""
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
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
        """Calculate the value for a single line item."""
        
        # Handle different line types
        if line_template.line_type in ('header', 'spacer'):
            return Decimal('0.00')
        
        # Handle formula-based lines
        if line_template.calculation_type == 'formula' and line_template.formula:
            return self._evaluate_formula(line_template.formula, line_values)
        
        # Get accounts for this line
        accounts = self._get_accounts_for_line(line_template)
        if not accounts:
            return Decimal('0.00')
        
        # Calculate based on report type
        if report_type == 'balance_sheet':
            # Balance sheet: use balance as of date
            return self._calculate_balance_sheet_line(
                accounts,
                as_of_date,
                line_template.calculation_type,
                include_pending=include_pending,
            )
        elif report_type == 'income_statement':
            # Income statement: use period activity
            return self._calculate_income_statement_line(
                accounts,
                start_date,
                end_date,
                line_template.calculation_type,
                include_pending=include_pending,
            )
        elif report_type == 'cash_flow':
            # Cash flow: specific logic
            return self._calculate_cash_flow_line(
                accounts,
                start_date,
                end_date,
                line_template.calculation_type,
                include_pending=include_pending,
            )
        else:
            # Default: period activity
            return self._calculate_period_balance(
                accounts,
                start_date,
                end_date,
                line_template.calculation_type,
                include_pending=include_pending,
            )
    
    def _get_accounts_for_line(
        self,
        line_template: FinancialStatementLineTemplate,
    ) -> List[Account]:
        """Get accounts that contribute to this line."""
        accounts = Account.objects.filter(company_id=self.company_id)
        
        # Filter by specific account
        if line_template.account:
            return [line_template.account]
        
        # Filter by account IDs
        if line_template.account_ids:
            return list(accounts.filter(id__in=line_template.account_ids))
        
        # Filter by code prefix
        if line_template.account_code_prefix:
            accounts = accounts.filter(
                account_code__startswith=line_template.account_code_prefix
            )
        
        # Filter by path contains
        if line_template.account_path_contains:
            # This requires checking account paths - simplified for now
            matching_accounts = []
            for account in accounts:
                if line_template.account_path_contains in account.get_path():
                    matching_accounts.append(account)
            return matching_accounts
        
        return list(accounts)
    
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
        total = Decimal('0.00')
        
        for account in accounts:
            # Get balance as of date
            balance = account.calculate_balance(
                include_pending=include_pending,
                beginning_date=None,
                end_date=as_of_date,
            ) or Decimal('0.00')
            
            # Apply account direction
            if calculation_type == 'balance':
                balance = balance * account.account_direction
            
            total += balance
        
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
        total = Decimal('0.00')
        
        for account in accounts:
            # Get period activity
            if include_pending:
                state_filter = Q(state__in=['posted', 'pending'])
            else:
                state_filter = Q(state='posted')
            
            entries = JournalEntry.objects.filter(
                account=account,
                transaction__date__gte=start_date,
                transaction__date__lte=end_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter)
            
            if calculation_type == 'difference':
                # Debit - Credit
                debit_total = entries.aggregate(
                    total=Sum('debit_amount')
                )['total'] or Decimal('0.00')
                credit_total = entries.aggregate(
                    total=Sum('credit_amount')
                )['total'] or Decimal('0.00')
                balance = debit_total - credit_total
            elif calculation_type == 'balance':
                # Apply account direction
                debit_total = entries.aggregate(
                    total=Sum('debit_amount')
                )['total'] or Decimal('0.00')
                credit_total = entries.aggregate(
                    total=Sum('credit_amount')
                )['total'] or Decimal('0.00')
                balance = (debit_total - credit_total) * account.account_direction
            else:
                # Sum
                balance = entries.aggregate(
                    total=Sum(F('debit_amount') - F('credit_amount'))
                )['total'] or Decimal('0.00')
            
            total += balance
        
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
        # Filter to cash/bank accounts
        cash_accounts = [acc for acc in accounts if acc.bank_account is not None]
        
        if not cash_accounts:
            return Decimal('0.00')
        
        # Calculate period change in cash
        total = Decimal('0.00')
        for account in cash_accounts:
            # Get beginning balance
            beginning_balance = account.calculate_balance(
                include_pending=include_pending,
                end_date=start_date,
            ) or Decimal('0.00')
            
            # Get ending balance
            ending_balance = account.calculate_balance(
                include_pending=include_pending,
                end_date=end_date,
            ) or Decimal('0.00')
            
            # Change = ending - beginning
            change = ending_balance - beginning_balance
            total += change
        
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
        """Evaluate a formula referencing other line numbers."""
        # Simple formula evaluator: "L1 + L2 - L3"
        # Replace L{number} with actual values
        result = formula
        for line_num, value in line_values.items():
            result = result.replace(f'L{line_num}', str(value))
        
        # Evaluate (simple - in production, use a proper expression evaluator)
        try:
            return Decimal(str(eval(result)))
        except Exception as e:
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
        dimension: str = 'month',
        line_numbers: Optional[List[int]] = None,
        include_pending: bool = False,
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
        dimension: str
            Time dimension ('day', 'week', 'month', 'quarter', 'semester', 'year')
        line_numbers: Optional[List[int]]
            Specific line numbers to include. If None, includes all lines.
        include_pending: bool
            Include pending journal entries
        
        Returns
        -------
        Dict[str, Any]
            Time series data with periods and values
        """
        from accounting.utils_time_dimensions import generate_periods
        
        periods = generate_periods(start_date, end_date, dimension)
        line_templates = template.line_templates.all().order_by('line_number')
        
        if line_numbers:
            line_templates = line_templates.filter(line_number__in=line_numbers)
        
        series_data = {}
        
        for line_template in line_templates:
            line_series = []
            
            for period in periods:
                # Calculate value for this line in this period
                value = self._calculate_line_value(
                    line_template,
                    period['start_date'],
                    period['end_date'],
                    period['end_date'],  # as_of_date
                    template.report_type,
                    {},  # line_values not used for time series
                    include_pending=include_pending,
                )
                
                line_series.append({
                    'period_key': period['key'],
                    'period_label': period['label'],
                    'start_date': period['start_date'],
                    'end_date': period['end_date'],
                    'value': float(value),
                })
            
            series_data[line_template.line_number] = {
                'line_number': line_template.line_number,
                'label': line_template.label,
                'line_type': line_template.line_type,
                'data': line_series,
            }
        
        return {
            'template_id': template.id,
            'template_name': template.name,
            'report_type': template.report_type,
            'dimension': dimension,
            'start_date': start_date,
            'end_date': end_date,
            'lines': list(series_data.values()),
        }
    
    def generate_with_comparisons(
        self,
        template: FinancialStatementTemplate,
        start_date: date,
        end_date: date,
        comparison_types: List[str],
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
        include_pending: bool
            Include pending journal entries
        
        Returns
        -------
        Dict[str, Any]
            Statement data with comparisons
        """
        from accounting.utils_time_dimensions import (
            get_comparison_period,
            calculate_period_comparison,
        )
        
        # Generate current period statement
        statement = self.generate_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            status='draft',
            include_pending=include_pending,
        )
        
        # Get current line values
        current_lines = {}
        for line in statement.lines.all():
            current_lines[line.line_number] = line.balance
        
        # Generate comparisons
        comparisons = {}
        
        for comp_type in comparison_types:
            try:
                comp_start, comp_end = get_comparison_period(
                    start_date,
                    end_date,
                    comp_type
                )
                
                # Generate comparison statement
                comp_statement = self.generate_statement(
                    template=template,
                    start_date=comp_start,
                    end_date=comp_end,
                    status='draft',
                    include_pending=include_pending,
                )
                
                # Calculate comparisons for each line
                comp_lines = {}
                for line in comp_statement.lines.all():
                    comp_lines[line.line_number] = line.balance
                
                # Calculate comparison metrics
                line_comparisons = {}
                for line_num in current_lines:
                    current_val = current_lines.get(line_num, Decimal('0.00'))
                    comp_val = comp_lines.get(line_num, Decimal('0.00'))
                    
                    line_comparisons[line_num] = calculate_period_comparison(
                        current_val,
                        comp_val,
                        comp_type
                    )
                
                comparisons[comp_type] = {
                    'start_date': comp_start,
                    'end_date': comp_end,
                    'lines': line_comparisons,
                }
                
                # Optionally keep comparison statements for audit trail
                # For now, we keep them but mark as draft
                # You can delete them if needed: comp_statement.delete()
                
            except Exception as e:
                log.warning(f"Failed to generate comparison {comp_type}: {e}")
                comparisons[comp_type] = {
                    'error': str(e)
                }
        
        return {
            'statement': {
                'id': statement.id,
                'name': statement.name,
                'start_date': statement.start_date,
                'end_date': statement.end_date,
                'lines': [
                    {
                        'line_number': line.line_number,
                        'label': line.label,
                        'balance': float(line.balance),
                    }
                    for line in statement.lines.all()
                ],
            },
            'comparisons': comparisons,
        }

