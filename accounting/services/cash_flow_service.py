"""
Cash Flow Service

Service for generating detailed cash flow statements from parent accounts.
Uses AccountBalanceHistory for fast calculations.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.db.models import Q, Sum

from accounting.models import Account, Currency
from accounting.models_financial_statements import AccountBalanceHistory
from accounting.services.income_statement_service import IncomeStatementService
from accounting.services.balance_sheet_service import calculate_ending_balance_from_history

log = logging.getLogger(__name__)


def calculate_cash_flow_change(
    account: Account,
    start_date: date,
    end_date: date,
    currency: Currency,
    balance_type: str = 'posted',
    company_id: int = None,
) -> Decimal:
    """
    Calculate cash flow change (ending balance - opening balance) for a period.
    
    Parameters:
    -----------
    account : Account
        The account to calculate change for
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
        Change in balance (ending - opening)
    """
    if company_id is None:
        company_id = account.company_id
    
    # Calculate opening balance (as of start_date - 1 day, or use start_date if same)
    opening_balance = calculate_ending_balance_from_history(
        account=account,
        as_of_date=start_date,
        currency=currency,
        balance_type=balance_type,
        company_id=company_id,
    )
    
    # Calculate ending balance
    ending_balance = calculate_ending_balance_from_history(
        account=account,
        as_of_date=end_date,
        currency=currency,
        balance_type=balance_type,
        company_id=company_id,
    )
    
    # Calculate change (ending - opening)
    change = ending_balance - opening_balance
    
    return change


class CashFlowService(IncomeStatementService):
    """
    Service for generating detailed hierarchical cash flow statements.
    Inherits from IncomeStatementService to reuse hierarchy building logic.
    """
    
    def generate_cash_flow(
        self,
        operating_parent_ids: List[int],
        investing_parent_ids: List[int],
        financing_parent_ids: List[int],
        start_date: date,
        end_date: date,
        currency_id: Optional[int] = None,
        balance_type: str = 'posted',
        include_zero_balances: bool = False,
        operating_depth: int = -1,
        investing_depth: int = -1,
        financing_depth: int = -1,
    ) -> Dict[str, Any]:
        """
        Generate a detailed hierarchical cash flow statement.
        
        Parameters:
        -----------
        operating_parent_ids : List[int]
            Parent account IDs for operating activities
        investing_parent_ids : List[int]
            Parent account IDs for investing activities
        financing_parent_ids : List[int]
            Parent account IDs for financing activities
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
        operating_depth : int
            Maximum depth to show for operating activities (-1 = all levels)
        investing_depth : int
            Maximum depth to show for investing activities (-1 = all levels)
        financing_depth : int
            Maximum depth to show for financing activities (-1 = all levels)
        
        Returns:
        --------
        Dict[str, Any]
            Cash flow structure with operating, investing, financing, and totals
        """
        # Get currency
        if currency_id:
            currency = Currency.objects.get(id=currency_id)
        else:
            # Try to get from first account, or default
            first_account = Account.objects.filter(
                company_id=self.company_id,
                id__in=operating_parent_ids + investing_parent_ids + financing_parent_ids
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
        operating_accounts = self._get_all_descendants(operating_parent_ids)
        investing_accounts = self._get_all_descendants(investing_parent_ids)
        financing_accounts = self._get_all_descendants(financing_parent_ids)
        
        # Build hierarchical structure for each section with cash flow changes
        operating = self._build_account_hierarchy_cash_flow(
            operating_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=operating_depth,
        )
        
        investing = self._build_account_hierarchy_cash_flow(
            investing_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=investing_depth,
        )
        
        financing = self._build_account_hierarchy_cash_flow(
            financing_accounts,
            start_date,
            end_date,
            currency,
            balance_type,
            include_zero_balances,
            max_depth=financing_depth,
        )
        
        # Calculate totals
        total_operating = self._calculate_total(operating)
        total_investing = self._calculate_total(investing)
        total_financing = self._calculate_total(financing)
        net_cash_flow = total_operating + total_investing + total_financing
        
        return {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'currency': {
                'id': currency.id,
                'code': currency.code,
                'name': currency.name,
            },
            'balance_type': balance_type,
            'operating': operating,
            'investing': investing,
            'financing': financing,
            'totals': {
                'total_operating': float(total_operating),
                'total_investing': float(total_investing),
                'total_financing': float(total_financing),
                'net_cash_flow': float(net_cash_flow),
            },
        }
    
    def _build_account_hierarchy_cash_flow(
        self,
        accounts: List[Account],
        start_date: date,
        end_date: date,
        currency: Currency,
        balance_type: str,
        include_zero_balances: bool,
        max_depth: int = -1,
    ) -> List[Dict[str, Any]]:
        """
        Build hierarchical structure of accounts with cash flow changes.
        Only includes accounts with non-zero changes (unless include_zero_balances=True).
        """
        if not accounts:
            return []
        
        # Create a map of account_id -> account for quick lookup
        account_map = {acc.id: acc for acc in accounts}
        
        # Calculate cash flow changes for all accounts (leaf accounts only)
        account_balances = {}
        for account in accounts:
            # Only calculate for leaf accounts (non-leaf accounts get rolled up)
            if account.is_leaf():
                change = calculate_cash_flow_change(
                    account=account,
                    start_date=start_date,
                    end_date=end_date,
                    currency=currency,
                    balance_type=balance_type,
                    company_id=self.company_id,
                )
                account_balances[account.id] = change
        
        # Roll up changes from children to parents
        sorted_accounts = sorted(accounts, key=lambda a: getattr(a, 'level', 0), reverse=True)
        for account in sorted_accounts:
            if not account.is_leaf():
                # Sum children changes
                children = [acc for acc in accounts if acc.parent_id == account.id]
                change = sum(
                    account_balances.get(child.id, Decimal('0.00'))
                    for child in children
                )
                account_balances[account.id] = change
        
        # Filter out accounts with zero change (unless include_zero_balances=True)
        if not include_zero_balances:
            filtered_account_ids = {
                acc.id for acc in accounts
                if account_balances.get(acc.id, Decimal('0.00')) != Decimal('0.00')
            }
            
            # Recursively mark parent accounts if any descendant has change
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

