"""
Balance Sheet Service

Service for generating detailed balance sheets from parent accounts.
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
from accounting.services.income_statement_service import (
    IncomeStatementService,
    calculate_net_movement_from_history,
)

log = logging.getLogger(__name__)


def calculate_ending_balance_from_history(
    account: Account,
    as_of_date: date,
    currency: Currency,
    balance_type: str = 'posted',
    company_id: int = None,
) -> Decimal:
    """
    Calculate ending balance as of a specific date using AccountBalanceHistory.
    
    Ending balance = opening balance (from account or previous month) + 
                     cumulative movements up to as_of_date
    
    Parameters:
    -----------
    account : Account
        The account to calculate balance for
    as_of_date : date
        Date to calculate balance as of (inclusive)
    currency : Currency
        Currency for the calculation
    balance_type : str
        One of: 'posted', 'bank_reconciled', 'all'
    company_id : int
        Company ID for filtering
        
    Returns:
    --------
    Decimal
        Ending balance as of as_of_date
    """
    if company_id is None:
        company_id = account.company_id
    
    # Get account's base balance
    opening_balance = account.balance or Decimal('0.00')
    balance_date = account.balance_date
    
    # Determine months to query (up to as_of_date)
    if balance_date:
        start_month = date(balance_date.year, balance_date.month, 1)
    else:
        # If no balance_date, start from first month with history
        first_history = AccountBalanceHistory.objects.filter(
            company_id=company_id,
            account=account,
            currency=currency,
        ).order_by('year', 'month').first()
        
        if first_history:
            start_month = date(first_history.year, first_history.month, 1)
        else:
            # No history, return account balance
            return opening_balance * account.account_direction
    
    end_month = date(as_of_date.year, as_of_date.month, 1)
    
    # If as_of_date is before balance_date, just return opening balance
    if balance_date and as_of_date < balance_date:
        return opening_balance * account.account_direction
    
    # Generate list of months to query
    months_to_query = []
    current = start_month
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
    
    # Filter by year/month combination
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
    
    # Calculate cumulative movement from balance_date to as_of_date
    # net_movement is (debit - credit) before applying account direction
    net_movement = total_debit - total_credit
    
    # Calculate ending balance: opening + movements with account direction
    # Apply account direction to movement
    movement_with_direction = net_movement * account.account_direction
    ending_balance = opening_balance + movement_with_direction
    
    # Return ending balance (already has direction applied in movement)
    return ending_balance


class BalanceSheetService(IncomeStatementService):
    """
    Service for generating detailed hierarchical balance sheets.
    Inherits from IncomeStatementService to reuse hierarchy building logic.
    """
    
    def generate_balance_sheet(
        self,
        asset_parent_ids: List[int],
        liability_parent_ids: List[int],
        equity_parent_ids: List[int],
        as_of_date: date,
        currency_id: Optional[int] = None,
        balance_type: str = 'posted',
        include_zero_balances: bool = False,
        asset_depth: int = -1,
        liability_depth: int = -1,
        equity_depth: int = -1,
    ) -> Dict[str, Any]:
        """
        Generate a detailed hierarchical balance sheet.
        
        Parameters:
        -----------
        asset_parent_ids : List[int]
            Parent account IDs for assets
        liability_parent_ids : List[int]
            Parent account IDs for liabilities
        equity_parent_ids : List[int]
            Parent account IDs for equity
        as_of_date : date
            Date to calculate balances as of (inclusive)
        currency_id : Optional[int]
            Currency ID (defaults to company's base currency or account currency)
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
        include_zero_balances : bool
            Include accounts with zero balances
        asset_depth : int
            Maximum depth to show for assets (-1 = all levels)
        liability_depth : int
            Maximum depth to show for liabilities (-1 = all levels)
        equity_depth : int
            Maximum depth to show for equity (-1 = all levels)
        
        Returns:
        --------
        Dict[str, Any]
            Balance sheet structure with assets, liabilities, equity, and totals
        """
        # Get currency
        if currency_id:
            currency = Currency.objects.get(id=currency_id)
        else:
            # Try to get from first account, or default
            first_account = Account.objects.filter(
                company_id=self.company_id,
                id__in=asset_parent_ids + liability_parent_ids + equity_parent_ids
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
        asset_accounts = self._get_all_descendants(asset_parent_ids)
        liability_accounts = self._get_all_descendants(liability_parent_ids)
        equity_accounts = self._get_all_descendants(equity_parent_ids)
        
        # Build hierarchical structure for each section with ending balances
        # Add level 0 consolidation wrapper
        assets = self._build_account_hierarchy_balance_sheet_with_consolidation(
            asset_accounts,
            asset_parent_ids,
            as_of_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=asset_depth,
            section_name="Assets",
        )
        
        liabilities = self._build_account_hierarchy_balance_sheet_with_consolidation(
            liability_accounts,
            liability_parent_ids,
            as_of_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=liability_depth,
            section_name="Liabilities",
        )
        
        equity = self._build_account_hierarchy_balance_sheet_with_consolidation(
            equity_accounts,
            equity_parent_ids,
            as_of_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=equity_depth,
            section_name="Equity",
        )
        
        # Calculate totals
        total_assets = self._calculate_total(assets)
        total_liabilities = self._calculate_total(liabilities)
        total_equity = self._calculate_total(equity)
        total_liabilities_and_equity = total_liabilities + total_equity
        
        return {
            'as_of_date': str(as_of_date),
            'currency': {
                'id': currency.id,
                'code': currency.code,
                'name': currency.name,
            },
            'balance_type': balance_type,
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'totals': {
                'total_assets': float(total_assets),
                'total_liabilities': float(total_liabilities),
                'total_equity': float(total_equity),
                'total_liabilities_and_equity': float(total_liabilities_and_equity),
            },
        }
    
    def _build_account_hierarchy_balance_sheet(
        self,
        accounts: List[Account],
        as_of_date: date,
        currency: Currency,
        balance_type: str,
        include_zero_balances: bool,
        max_depth: int = -1,
    ) -> List[Dict[str, Any]]:
        """
        Build hierarchical structure of accounts with ending balances.
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
                balance = calculate_ending_balance_from_history(
                    account=account,
                    as_of_date=as_of_date,
                    currency=currency,
                    balance_type=balance_type,
                    company_id=self.company_id,
                )
                account_balances[account.id] = balance
        
        # Roll up balances from children to parents
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
            filtered_account_ids = {
                acc.id for acc in accounts
                if account_balances.get(acc.id, Decimal('0.00')) != Decimal('0.00')
            }
            
            # Recursively mark parent accounts if any descendant has balance
            sorted_accounts = sorted(accounts, key=lambda a: getattr(a, 'level', 0), reverse=True)
            for account in sorted_accounts:
                if account.id in filtered_account_ids:
                    continue
                if not account.is_leaf():
                    children = [acc for acc in accounts if acc.parent_id == account.id]
                    if any(child.id in filtered_account_ids for child in children):
                        filtered_account_ids.add(account.id)
            
            filtered_account_map = {
                acc.id: acc for acc in accounts
                if acc.id in filtered_account_ids
            }
        else:
            filtered_account_map = account_map
        
        # Build hierarchical structure
        hierarchy = []
        
        # Find root accounts in the filtered set
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
                max_depth=max_depth,
                root_level=getattr(root, 'level', 0),
            )
            if node:
                hierarchy.append(node)
        
        return hierarchy
    
    def _build_account_hierarchy_balance_sheet_with_consolidation(
        self,
        accounts: List[Account],
        parent_ids: List[int],
        as_of_date: date,
        currency: Currency,
        balance_type: str,
        include_zero_balances: bool,
        max_depth: int = -1,
        section_name: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Build hierarchical structure with level 0 consolidation of parent accounts.
        
        Level 0 = Consolidation of all parent accounts
        Level 1 = Individual parent accounts
        Level 2+ = Children of parent accounts
        """
        if not accounts or not parent_ids:
            return []
        
        # Build the base hierarchy
        base_hierarchy = self._build_account_hierarchy_balance_sheet(
            accounts,
            as_of_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=-1,  # Build full hierarchy first
        )
        
        # If max_depth is 0, return only consolidation
        if max_depth == 0:
            total_balance = self._calculate_total(base_hierarchy)
            return [{
                'id': None,
                'account_code': '',
                'name': section_name or 'Total',
                'path': section_name or 'Total',
                'balance': float(total_balance),
                'depth': 0,
                'is_leaf': False,
                'children': None,
            }]
        
        # Calculate total balance for consolidation
        total_balance = self._calculate_total(base_hierarchy)
        
        # Adjust depth for children
        adjusted_max_depth = max_depth - 1 if max_depth > 0 else -1
        
        # Wrap each root account node and apply depth limit
        parent_nodes = []
        for root_node in base_hierarchy:
            if adjusted_max_depth >= 0:
                limited_node = self._limit_node_depth(root_node, adjusted_max_depth, current_depth=0)
                if limited_node:
                    parent_nodes.append(limited_node)
            else:
                parent_nodes.append(root_node)
        
        # Create consolidation node at level 0
        consolidation = {
            'id': None,
            'account_code': '',
            'name': section_name or 'Total',
            'path': section_name or 'Total',
            'balance': float(total_balance),
            'depth': 0,
            'is_leaf': False,
            'children': parent_nodes if parent_nodes else None,
        }
        
        return [consolidation]

