"""
Income Statement Service

Service for generating detailed income statements from parent accounts.
Uses AccountBalanceHistory for fast calculations.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from calendar import monthrange

from django.db.models import Q, Sum
from django.db import models

from accounting.models import Account, Currency
from accounting.models_financial_statements import AccountBalanceHistory

log = logging.getLogger(__name__)


def calculate_net_movement_from_history(
    account: Account,
    start_date: date,
    end_date: date,
    currency: Currency,
    balance_type: str = 'posted',
    company_id: int = None,
) -> Decimal:
    """
    Calculate net movement (debit - credit) * account_direction for a period
    using AccountBalanceHistory.
    
    Parameters:
    -----------
    account : Account
        The account to calculate movement for
    start_date : date
        Start of the period
    end_date : date
        End of the period
    currency : Currency
        Currency for the calculation
    balance_type : str
        One of: 'posted', 'bank_reconciled', 'all'
    company_id : int
        Company ID for filtering
        
    Returns:
    --------
    Decimal
        Net movement (debit - credit) * account_direction
    """
    if company_id is None:
        company_id = account.company_id
    
    # Generate list of months to query
    months_to_query = []
    current = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    
    while current <= end_month:
        months_to_query.append((current.year, current.month))
        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    
    # Query balance history for all months in the period
    history_qs = AccountBalanceHistory.objects.filter(
        company_id=company_id,
        account=account,
        currency=currency,
        year__in=[y for y, m in months_to_query],
        month__in=[m for y, m in months_to_query],
    )
    
    # Filter by year/month combination to only get the months we need
    month_filters = Q()
    for year, month in months_to_query:
        month_filters |= Q(year=year, month=month)
    history_qs = history_qs.filter(month_filters)
    
    # Aggregate totals based on balance_type
    if balance_type == 'posted':
        debit_field = 'posted_total_debit'
        credit_field = 'posted_total_credit'
    elif balance_type == 'bank_reconciled':
        debit_field = 'bank_reconciled_total_debit'
        credit_field = 'bank_reconciled_total_credit'
    elif balance_type == 'all':
        debit_field = 'all_total_debit'
        credit_field = 'all_total_credit'
    else:
        raise ValueError(f"Invalid balance_type: {balance_type}")
    
    totals = history_qs.aggregate(
        total_debit=Sum(debit_field),
        total_credit=Sum(credit_field)
    )
    
    total_debit = totals['total_debit'] or Decimal('0.00')
    total_credit = totals['total_credit'] or Decimal('0.00')
    
    # Calculate net movement with account direction
    net_movement = total_debit - total_credit
    balance = net_movement * account.account_direction
    
    return balance


class IncomeStatementService:
    """
    Service for generating detailed hierarchical income statements.
    """
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
    def generate_income_statement(
        self,
        revenue_parent_ids: List[int],
        cost_parent_ids: List[int],
        expense_parent_ids: List[int],
        start_date: date,
        end_date: date,
        currency_id: Optional[int] = None,
        balance_type: str = 'posted',
        include_zero_balances: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a detailed hierarchical income statement.
        
        Parameters:
        -----------
        revenue_parent_ids : List[int]
            Parent account IDs for revenues
        cost_parent_ids : List[int]
            Parent account IDs for costs (COGS)
        expense_parent_ids : List[int]
            Parent account IDs for expenses
        start_date : date
            Start of the reporting period
        end_date : date
            End of the reporting period
        currency_id : Optional[int]
            Currency ID (defaults to company's base currency or account currency)
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
        include_zero_balances : bool
            Include accounts with zero balances
        
        Returns:
        --------
        Dict[str, Any]
            Income statement structure with revenues, costs, expenses, and totals
        """
        # Get currency
        if currency_id:
            currency = Currency.objects.get(id=currency_id)
        else:
            # Try to get from first account, or default
            first_account = Account.objects.filter(
                company_id=self.company_id,
                id__in=revenue_parent_ids + cost_parent_ids + expense_parent_ids
            ).first()
            if first_account:
                currency = first_account.currency
            else:
                # Get company's first currency as fallback
                currency = Currency.objects.filter(
                    account__company_id=self.company_id
                ).distinct().first()
                if not currency:
                    raise ValueError("No currency found")
        
        # Get all descendant accounts for each parent
        revenue_accounts = self._get_all_descendants(revenue_parent_ids)
        cost_accounts = self._get_all_descendants(cost_parent_ids)
        expense_accounts = self._get_all_descendants(expense_parent_ids)
        
        # Build hierarchical structure for each section
        revenues = self._build_account_hierarchy(
            revenue_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
        )
        
        costs = self._build_account_hierarchy(
            cost_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
        )
        
        expenses = self._build_account_hierarchy(
            expense_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
        )
        
        # Calculate totals
        total_revenue = self._calculate_total(revenues)
        total_costs = self._calculate_total(costs)
        total_expenses = self._calculate_total(expenses)
        gross_profit = total_revenue - total_costs
        net_income = gross_profit - total_expenses
        
        return {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'currency': {
                'id': currency.id,
                'code': currency.code,
                'name': currency.name,
            },
            'balance_type': balance_type,
            'revenues': revenues,
            'costs': costs,
            'expenses': expenses,
            'totals': {
                'total_revenue': float(total_revenue),
                'total_costs': float(total_costs),
                'gross_profit': float(gross_profit),
                'total_expenses': float(total_expenses),
                'net_income': float(net_income),
            },
        }
    
    def _get_all_descendants(self, parent_ids: List[int]) -> List[Account]:
        """
        Get all descendant accounts (including the parents themselves).
        Uses MPTT for efficient queries.
        """
        if not parent_ids:
            return []
        
        all_account_ids = set(parent_ids)
        
        # Get all descendants using MPTT
        parent_accounts = Account.objects.filter(
            company_id=self.company_id,
            id__in=parent_ids,
            is_active=True
        )
        
        for parent in parent_accounts:
            # Get all descendants using MPTT methods
            descendants = parent.get_descendants(include_self=True).filter(
                company_id=self.company_id,
                is_active=True
            )
            all_account_ids.update(descendants.values_list('id', flat=True))
        
        # Return accounts ordered by tree
        accounts = Account.objects.filter(
            company_id=self.company_id,
            id__in=all_account_ids,
            is_active=True
        ).select_related('currency', 'parent').order_by('tree_id', 'lft')
        
        return list(accounts)
    
    def _build_account_hierarchy(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        currency: Currency,
        balance_type: str,
        include_zero_balances: bool,
    ) -> List[Dict[str, Any]]:
        """
        Build hierarchical structure of accounts with balances.
        Only includes accounts with non-zero balances (unless include_zero_balances=True).
        """
        if not accounts:
            return []
        
        # Create a map of account_id -> account for quick lookup
        account_map = {acc.id: acc for acc in accounts}
        
        # Calculate balances for all accounts (leaf accounts only)
        account_balances = {}
        for account in accounts:
            # Only calculate for leaf accounts (non-leaf accounts get rolled up)
            if account.is_leaf():
                balance = calculate_net_movement_from_history(
                    account=account,
                    start_date=start_date,
                    end_date=end_date,
                    currency=currency,
                    balance_type=balance_type,
                    company_id=self.company_id,
                )
                account_balances[account.id] = balance
        
        # Roll up balances from children to parents
        # Sort accounts by level (depth) in descending order to process leaves first
        sorted_accounts = sorted(accounts, key=lambda a: getattr(a, 'level', 0), reverse=True)
        for account in sorted_accounts:
            if not account.is_leaf():
                # Sum children balances
                children = [acc for acc in accounts if acc.parent_id == account.id]
                balance = sum(
                    account_balances.get(child.id, Decimal('0.00'))
                    for child in children
                )
                account_balances[account.id] = balance
        
        # Filter out accounts with zero balance (unless include_zero_balances=True)
        if not include_zero_balances:
            # First, mark all accounts with non-zero balance
            filtered_account_ids = {
                acc.id for acc in accounts
                if account_balances.get(acc.id, Decimal('0.00')) != Decimal('0.00')
            }
            
            # Then, recursively mark parent accounts if any descendant has balance
            # Process accounts from deepest to shallowest (leaves to root)
            sorted_accounts = sorted(accounts, key=lambda a: getattr(a, 'level', 0), reverse=True)
            for account in sorted_accounts:
                if account.id in filtered_account_ids:
                    continue
                if not account.is_leaf():
                    # Check if any direct child has a balance or is in filtered set
                    children = [acc for acc in accounts if acc.parent_id == account.id]
                    if any(child.id in filtered_account_ids for child in children):
                        filtered_account_ids.add(account.id)
            
            # Build filtered account map
            filtered_account_map = {
                acc.id: acc for acc in accounts
                if acc.id in filtered_account_ids
            }
        else:
            filtered_account_map = account_map
        
        # Build hierarchical structure
        hierarchy = []
        
        # Find root accounts in the filtered set (no parent or parent not in the filtered set)
        root_accounts = [
            acc for acc in accounts
            if acc.id in filtered_account_map and
            (acc.parent_id is None or acc.parent_id not in filtered_account_map)
        ]
        
        for root in root_accounts:
            node = self._build_account_node(
                root,
                filtered_account_map,
                account_balances,
                accounts,
                0,  # depth level
            )
            if node:
                hierarchy.append(node)
        
        return hierarchy
    
    def _build_account_node(
        self,
        account: Account,
        account_map: Dict[int, Account],
        account_balances: Dict[int, Decimal],
        all_accounts: List[Account],
        depth: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a single account node with its children.
        """
        balance = account_balances.get(account.id, Decimal('0.00'))
        
        # Find children that are in the filtered account_map
        children = [
            acc for acc in all_accounts
            if acc.parent_id == account.id and acc.id in account_map
        ]
        
        children_nodes = []
        for child in children:
            child_node = self._build_account_node(
                child,
                account_map,
                account_balances,
                all_accounts,
                depth + 1,
            )
            if child_node:
                children_nodes.append(child_node)
        
        # Only return node if it has balance or has children with balance
        if balance == Decimal('0.00') and not children_nodes:
            return None
        
        return {
            'id': account.id,
            'account_code': account.account_code or '',
            'name': account.name,
            'path': account.get_path(),
            'balance': float(balance),
            'depth': depth,
            'is_leaf': account.is_leaf(),
            'children': children_nodes if children_nodes else None,
        }
    
    def _calculate_total(self, hierarchy: List[Dict[str, Any]]) -> Decimal:
        """
        Calculate total from hierarchical structure.
        """
        total = Decimal('0.00')
        
        for node in hierarchy:
            total += Decimal(str(node['balance']))
            if node.get('children'):
                total += self._calculate_total(node['children'])
        
        return total

