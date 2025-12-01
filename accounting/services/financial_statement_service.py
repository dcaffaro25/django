"""
Financial Statement Generation Service

Generates financial statements (Balance Sheet, P&L, Cash Flow, etc.)
from accounting data.
"""

import logging
from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional, Set, Any, Union
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
        
        # Generate lines without saving
        line_templates = template.line_templates.all().order_by('line_number')
        line_values: Dict[int, Decimal] = {}
        lines_data = []
        
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
                    transaction__date__gte=start_date,
                    transaction__date__lte=end_date,
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
                ending_balance = self._calculate_cumulative_ending_balance(
                    account=account,
                    as_of_date=end_date,
                    include_pending=include_pending,
                )
                change = ending_balance
                
                account_detail['opening_balance'] = float(account.balance or Decimal('0.00'))
                account_detail['balance_date'] = str(account.balance_date) if account.balance_date else None
                account_detail['ending_balance'] = float(ending_balance)
                account_detail['value'] = float(ending_balance)
                
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
        """Get accounts that contribute to this line."""
        accounts = Account.objects.filter(company_id=self.company_id)
        
        # Filter by specific account
        if line_template.account:
            # Expand parent account to include all leaf descendants
            return self._expand_to_leaf_accounts([line_template.account])
        
        # Filter by account IDs
        if line_template.account_ids:
            accounts = list(accounts.filter(id__in=line_template.account_ids))
        # Filter by code prefix
        elif line_template.account_code_prefix:
            accounts = list(accounts.filter(
                account_code__startswith=line_template.account_code_prefix
            ))
        # Filter by path contains
        elif line_template.account_path_contains:
            # This requires checking account paths - simplified for now
            matching_accounts = []
            for account in accounts:
                if line_template.account_path_contains in account.get_path():
                    matching_accounts.append(account)
            accounts = matching_accounts
        else:
            accounts = list(accounts)
        
        # Expand all accounts to their leaf descendants
        # This ensures parent accounts are replaced by their leaf children
        return self._expand_to_leaf_accounts(accounts)
    
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
        
        log.debug(
            "Expanding %s accounts to leaf accounts",
            len(accounts)
        )
        
        for account in accounts:
            if account.is_leaf():
                # Leaf account: include directly
                leaf_accounts.append(account)
                log.debug(
                    "Including leaf account %s (id=%s, bank_account_id=%s)",
                    account.name,
                    account.id,
                    account.bank_account_id
                )
            else:
                # Parent account: get all leaf descendants
                leaf_descendants = self._get_leaf_descendants(account)
                leaf_accounts.extend(leaf_descendants)
                log.debug(
                    "Expanded parent account %s (id=%s) to %s leaf accounts: %s",
                    account.name,
                    account.id,
                    len(leaf_descendants),
                    [(acc.name, acc.id, acc.bank_account_id) for acc in leaf_descendants]
                )
        
        # Remove duplicates by ID
        seen_ids = set()
        unique_leaf_accounts = []
        for acc in leaf_accounts:
            if acc.id not in seen_ids:
                seen_ids.add(acc.id)
                unique_leaf_accounts.append(acc)
        
        log.debug(
            "Expanded to %s unique leaf accounts (from %s original accounts)",
            len(unique_leaf_accounts),
            len(accounts)
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
        
        log.debug(
            "Getting leaf descendants for account %s (id=%s), found %s children",
            account.name,
            account.id,
            children.count()
        )
        
        for child in children:
            if child.is_leaf():
                # Leaf: add to list
                leaf_accounts.append(child)
                log.debug(
                    "Added leaf account %s (id=%s) to descendants",
                    child.name,
                    child.id
                )
            else:
                # Parent: recursively get its leaf descendants
                child_leaves = self._get_leaf_descendants(child)
                leaf_accounts.extend(child_leaves)
                log.debug(
                    "Expanded parent account %s (id=%s) to %s leaf descendants",
                    child.name,
                    child.id,
                    len(child_leaves)
                )
        
        log.debug(
            "Account %s (id=%s) has %s total leaf descendants",
            account.name,
            account.id,
            len(leaf_accounts)
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
        total = Decimal('0.00')
        
        for account in accounts:
            if calculation_type == 'balance':
                # Balance: Use last closing balance + transactions after closing date
                balance = self._calculate_account_balance_from_closing(
                    account=account,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
            else:
                # Sum or difference: Calculate from journal entries in period
                balance = self._calculate_account_balance_with_children(
                    account=account,
                    include_pending=include_pending,
                    beginning_date=None,
                    end_date=as_of_date,
                )
                # Apply account direction for sum
                if calculation_type == 'sum':
                    balance = balance * account.account_direction
            
            total += balance
        
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
        if not account.is_leaf():
            # Parent account: sum all children's ending balances
            children = account.get_children().filter(company_id=self.company_id)
            total = Decimal('0.00')
            for child in children:
                total += self._calculate_cumulative_ending_balance(
                    account=child,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
            return total
        
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
                Q(transaction__date__gt=balance_date) &
                Q(transaction__date__lte=as_of_date)
            )
            use_opening_balance = True
        else:
            # as_of_date is BEFORE balance_date (or no balance_date set)
            # Sum ALL entries from the beginning up to as_of_date
            entries = entries.filter(transaction__date__lte=as_of_date)
            use_opening_balance = False
        
        totals = entries.aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        
        total_debit = totals['total_debit'] or Decimal('0.00')
        total_credit = totals['total_credit'] or Decimal('0.00')
        
        # Calculate change with account direction
        change = (total_debit - total_credit) * account.account_direction
        
        # Final balance
        if use_opening_balance:
            ending_balance = opening_balance + change
        else:
            # No opening balance - just the sum of all entries
            ending_balance = change
        
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
        
        return ending_balance
    
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
        if account.is_leaf():
            # Get the last closing balance and date
            closing_balance = account.balance
            closing_date = account.balance_date
            
            # If as_of_date is before or equal to closing_date, return closing balance with direction
            if as_of_date <= closing_date:
                return closing_balance * account.account_direction
            
            # Get transactions after closing date up to as_of_date
            state_filter = Q(state='posted')
            if include_pending:
                state_filter = Q(state__in=['posted', 'pending'])
            
            transactions = JournalEntry.objects.filter(
                account=account,
                transaction__date__gt=closing_date,
                transaction__date__lte=as_of_date,
                transaction__company_id=self.company_id,
            ).filter(state_filter).aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )
            
            total_debit = transactions['total_debit'] or Decimal('0.00')
            total_credit = transactions['total_credit'] or Decimal('0.00')
            
            # Calculate change: (debit - credit) * account_direction
            change = (total_debit - total_credit) * account.account_direction
            
            # Final balance = closing balance (with direction) + change (with direction)
            # Both are normalized by account_direction
            return closing_balance * account.account_direction + change
        else:
            # Parent account: sum all children
            children = account.get_children().filter(company_id=self.company_id)
            
            if not children.exists():
                log.warning(
                    "Parent account %s (id=%s) has no children for company %s",
                    account.name,
                    account.id,
                    self.company_id
                )
                return Decimal('0.00')
            
            total = Decimal('0.00')
            for child in children:
                child_balance = self._calculate_account_balance_from_closing(
                    account=child,
                    as_of_date=as_of_date,
                    include_pending=include_pending,
                )
                total += child_balance
            
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
        if account.is_leaf():
            # Leaf account: calculate directly from journal entries
            return account.calculate_balance(
                include_pending=include_pending,
                beginning_date=beginning_date,
                end_date=end_date,
            ) or Decimal('0.00')
        else:
            # Parent account: sum all children
            # Ensure we only get children from the same company
            children = account.get_children().filter(company_id=self.company_id)
            
            if not children.exists():
                log.warning(
                    "Parent account %s (id=%s) has no children for company %s",
                    account.name,
                    account.id,
                    self.company_id
                )
                return Decimal('0.00')
            
            total = Decimal('0.00')
            for child in children:
                child_balance = self._calculate_account_balance_with_children(
                    account=child,
                    include_pending=include_pending,
                    beginning_date=beginning_date,
                    end_date=end_date,
                )
                total += child_balance
            
            log.debug(
                "Parent account %s (id=%s) balance: %s (from %s children)",
                account.name,
                account.id,
                total,
                children.count()
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
        total = Decimal('0.00')
        
        for account in accounts:
            if account.is_leaf():
                # Leaf account: calculate from journal entries
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
                    # Debit - Credit (no account direction)
                    debit_total = entries.aggregate(
                        total=Sum('debit_amount')
                    )['total'] or Decimal('0.00')
                    credit_total = entries.aggregate(
                        total=Sum('credit_amount')
                    )['total'] or Decimal('0.00')
                    balance = debit_total - credit_total
                elif calculation_type == 'balance':
                    # Balance: Use last closing balance + transactions after closing date
                    balance = self._calculate_account_balance_from_closing(
                        account=account,
                        as_of_date=end_date,
                        include_pending=include_pending,
                    )
                else:
                    # Sum: Period movements with account direction (e.g., cash flow)
                    debit_total = entries.aggregate(
                        total=Sum('debit_amount')
                    )['total'] or Decimal('0.00')
                    credit_total = entries.aggregate(
                        total=Sum('credit_amount')
                    )['total'] or Decimal('0.00')
                    balance = (debit_total - credit_total) * account.account_direction
                
                total += balance
            else:
                # Parent account: sum children's period activity
                children = account.get_children().filter(company_id=self.company_id)
                for child in children:
                    # Recursively calculate child balance for the period
                    child_balance = self._calculate_income_statement_line(
                        accounts=[child],
                        start_date=start_date,
                        end_date=end_date,
                        calculation_type=calculation_type,
                        include_pending=include_pending,
                    )
                    total += child_balance
        
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
                    transaction__date__gte=start_date,
                    transaction__date__lte=end_date,
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
        
        series_data = {}
        
        for line_template in line_templates:
            line_series = []
            
            # Get accounts for this line (for metadata)
            accounts = self._get_accounts_for_line(line_template) if include_metadata else []
            
            for period in periods:
                # Calculate value for this line in this period
                if include_metadata:
                    value, calculation_memory = self._calculate_line_value_with_metadata(
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
                        'calculation_memory': calculation_memory,
                    })
                else:
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
                    'calculation_type': line_template.calculation_type,
                    'account_id': line_template.account_id,
                    'account_ids': line_template.account_ids,
                    'account_code_prefix': line_template.account_code_prefix,
                    'account_path_contains': line_template.account_path_contains,
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
        
        # Generate current period statement
        statement = self.generate_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            status='draft',
            include_pending=include_pending,
        )
        
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
        
        for comp_type in comparison_types:
            try:
                comp_start, comp_end = get_comparison_period(
                    start_date,
                    end_date,
                    comp_type,
                    dimension=dimension
                )
                
                # Generate comparison statement
                comp_statement = self.generate_statement(
                    template=template,
                    start_date=comp_start,
                    end_date=comp_end,
                    status='draft',
                    include_pending=include_pending,
                )
                
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
        """Preview comparisons without saving statements."""
        result = self.generate_with_comparisons(
            template, start_date, end_date, comparison_types, dimension, include_pending
        )
        result['is_preview'] = True
        return result

