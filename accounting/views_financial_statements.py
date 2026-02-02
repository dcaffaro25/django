"""
Views for Financial Statement generation and management.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Q
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import logging

from multitenancy.mixins import ScopedQuerysetMixin
from multitenancy.utils import resolve_tenant
from .models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatement,
    FinancialStatementComparison,
    AccountBalanceHistory,
)
from .serializers_financial_statements import (
    FinancialStatementTemplateSerializer,
    FinancialStatementSerializer,
    FinancialStatementComparisonSerializer,
    GenerateStatementRequestSerializer,
    TimeSeriesRequestSerializer,
    ComparisonRequestSerializer,
    TemplateSuggestionRequestSerializer,
    TemplateSuggestionResponseSerializer,
    BalanceHistoryRecalculateSerializer,
    AccountBalanceHistorySerializer,
)
from .services.financial_statement_service import FinancialStatementGenerator
from .services.template_suggestion_service import TemplateSuggestionService
from .services.balance_recalculation_service import BalanceRecalculationService
from .services.income_statement_service import IncomeStatementService
from .services.balance_sheet_service import BalanceSheetService
from .services.cash_flow_service import CashFlowService
from .services.detailed_statement_excel import build_detailed_statement_excel_base64
from .models import Currency, Account, JournalEntry

log = logging.getLogger(__name__)


def _get_report_scope_account_ids(company_id, *parent_id_lists):
    """
    Get all account IDs in the report scope (all descendants of the given parent IDs).
    Use this for journal entries so we include entries for all report accounts,
    including those filtered out (zero balance, depth limit) from the displayed report.
    """
    all_parent_ids = []
    for lst in parent_id_lists:
        all_parent_ids.extend(lst or [])
    if not all_parent_ids:
        return set()
    parent_accounts = Account.objects.filter(
        company_id=company_id,
        id__in=all_parent_ids,
        is_active=True,
    )
    account_ids = set()
    for parent in parent_accounts:
        descendants = parent.get_descendants(include_self=True).filter(
            company_id=company_id,
            is_active=True,
        )
        account_ids.update(descendants.values_list('id', flat=True))
    return account_ids


def _collect_account_ids_from_report(report, report_type):
    """Recursively collect all account IDs from report tree nodes (id is not None)."""
    section_keys = {
        'income_statement': ['revenues', 'costs', 'expenses'],
        'balance_sheet': ['assets', 'liabilities', 'equity'],
        'cash_flow': ['operating', 'investing', 'financing'],
    }
    keys = section_keys.get(report_type, [])
    ids = set()

    def walk(nodes):
        for node in (nodes or []):
            if node.get('id') is not None:
                ids.add(node['id'])
            walk(node.get('children') or [])

    for key in keys:
        walk(report.get(key) or [])
    return ids


def _build_account_section_fallback_map(company_id, *parent_id_lists_with_sections):
    """
    Map account_id -> section label for ALL accounts in report scope.
    Used as fallback when an account is in scope but not in the displayed report (filtered out).
    parent_id_lists_with_sections: list of (parent_id_list, section_label) tuples.
    """
    parent_to_section = {}
    all_parent_ids = []
    for parent_ids, section_label in parent_id_lists_with_sections:
        for pid in (parent_ids or []):
            parent_to_section[pid] = section_label
            all_parent_ids.append(pid)
    if not all_parent_ids:
        return {}
    scope_ids = _get_report_scope_account_ids(company_id, *[p for p, _ in parent_id_lists_with_sections])
    if not scope_ids:
        return {}
    account_to_section = {}
    accounts = Account.objects.filter(id__in=scope_ids)
    for acc in accounts:
        for ancestor in acc.get_ancestors(include_self=True):
            if ancestor.id in parent_to_section:
                account_to_section[acc.id] = parent_to_section[ancestor.id]
                break
    return account_to_section


def _build_account_report_lines_map(report, report_type):
    """
    Build a mapping account_id -> list of report line descriptions (section > path/name)
    so we can show where each journal entry was considered in the financial report.
    """
    section_config = {
        'income_statement': [
            ('revenues', 'Revenue'),
            ('costs', 'Cost of Goods Sold'),
            ('expenses', 'Expenses'),
        ],
        'balance_sheet': [
            ('assets', 'Assets'),
            ('liabilities', 'Liabilities'),
            ('equity', 'Equity'),
        ],
        'cash_flow': [
            ('operating', 'Operating Activities'),
            ('investing', 'Investing Activities'),
            ('financing', 'Financing Activities'),
        ],
    }
    config = section_config.get(report_type, [])
    account_to_lines = {}  # account_id -> list of "Section > Path" strings

    def walk(nodes, section_label):
        for node in (nodes or []):
            acc_id = node.get('id')
            if acc_id is not None:
                path = (node.get('path') or '').strip()
                name = (node.get('name') or '').strip()
                label = path if path else (name or str(acc_id))
                place = f"{section_label} > {label}" if label else section_label
                account_to_lines.setdefault(acc_id, []).append(place)
            walk(node.get('children') or [], section_label)

    for key, section_label in config:
        walk(report.get(key) or [], section_label)

    return account_to_lines


def _months_in_range(start_date, end_date):
    """Yield (year, month) from start_date through end_date (inclusive by month)."""
    from calendar import monthrange
    y, m = start_date.year, start_date.month
    end_y, end_m = end_date.year, end_date.month
    while (y, m) <= (end_y, end_m):
        yield (y, m)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def _fetch_raw_balance_history(company_id, account_ids, currency_id, balance_type,
                               start_date=None, end_date=None, as_of_date=None):
    """
    Fetch AccountBalanceHistory rows for the given accounts, currency, and period.
    For income/cash: use start_date and end_date. For balance sheet: use as_of_date (all months up to that date).
    Returns list of dicts with all history fields plus debit_used, credit_used, net_movement_used.
    """
    if not account_ids:
        return []
    account_ids = list(account_ids)
    if as_of_date is not None:
        # Balance sheet: all months up to and including as_of_date
        month_filters = Q(year__lt=as_of_date.year) | (
            Q(year=as_of_date.year) & Q(month__lte=as_of_date.month)
        )
    elif start_date is not None and end_date is not None:
        month_list = list(_months_in_range(start_date, end_date))
        if not month_list:
            return []
        month_filters = Q()
        for y, m in month_list:
            month_filters |= Q(year=y, month=m)
    else:
        return []
    qs = AccountBalanceHistory.objects.filter(
        company_id=company_id,
        account_id__in=account_ids,
        currency_id=currency_id,
    ).filter(month_filters).select_related('account', 'currency').order_by('account_id', 'year', 'month')

    if balance_type == 'posted':
        debit_attr, credit_attr = 'posted_total_debit', 'posted_total_credit'
    elif balance_type == 'bank_reconciled':
        debit_attr, credit_attr = 'bank_reconciled_total_debit', 'bank_reconciled_total_credit'
    else:
        debit_attr, credit_attr = 'all_total_debit', 'all_total_credit'

    rows = []
    for rec in qs:
        debit = getattr(rec, debit_attr) or Decimal('0')
        credit = getattr(rec, credit_attr) or Decimal('0')
        direction = rec.account.account_direction if rec.account else 1
        net_movement = (debit - credit) * direction
        row = {
            'account_id': rec.account_id,
            'account_code': rec.account.account_code if rec.account else '',
            'account_name': rec.account.name if rec.account else '',
            'year': rec.year,
            'month': rec.month,
            'currency_id': rec.currency_id,
            'posted_total_debit': float(rec.posted_total_debit) if rec.posted_total_debit is not None else 0,
            'posted_total_credit': float(rec.posted_total_credit) if rec.posted_total_credit is not None else 0,
            'bank_reconciled_total_debit': float(rec.bank_reconciled_total_debit) if rec.bank_reconciled_total_debit is not None else 0,
            'bank_reconciled_total_credit': float(rec.bank_reconciled_total_credit) if rec.bank_reconciled_total_credit is not None else 0,
            'all_total_debit': float(rec.all_total_debit) if rec.all_total_debit is not None else 0,
            'all_total_credit': float(rec.all_total_credit) if rec.all_total_credit is not None else 0,
            'balance_type_used': balance_type,
            'debit_used': float(debit),
            'credit_used': float(credit),
            'net_movement_used': float(net_movement),
        }
        rows.append(row)
    return rows


def _fetch_journal_entries_for_report(company_id, account_ids, currency_id, balance_type,
                                       start_date=None, end_date=None, as_of_date=None):
    """
    Fetch JournalEntry rows that contributed to the report (same accounts, currency, period, balance_type).
    For income/cash: entries with date in [start_date, end_date]. For balance sheet: date <= as_of_date.
    Returns list of dicts with id, transaction_id, date, description, account_id, account_code, account_name,
    debit_amount, credit_amount, state, is_reconciled, transaction_date.
    """
    if not account_ids:
        return []
    account_ids = list(account_ids)
    qs = JournalEntry.objects.filter(
        account_id__in=account_ids,
        transaction__company_id=company_id,
        transaction__currency_id=currency_id,
    ).select_related('account', 'transaction').order_by('date', 'id')
    if balance_type == 'posted':
        qs = qs.filter(state='posted')
    elif balance_type == 'bank_reconciled':
        qs = qs.filter(is_reconciled=True)
    # else 'all': no state filter
    if as_of_date is not None:
        qs = qs.filter(date__lte=as_of_date)
    elif start_date is not None and end_date is not None:
        qs = qs.filter(date__gte=start_date, date__lte=end_date)
    else:
        return []
    rows = []
    for je in qs:
        tx = je.transaction
        rows.append({
            'journal_entry_id': je.id,
            'transaction_id': tx.id if tx else None,
            'date': str(je.date) if je.date else (str(tx.date) if tx else None),
            'transaction_date': str(tx.date) if tx else None,
            'description': je.description or (tx.description if tx else ''),
            'transaction_description': tx.description if tx else '',
            'account_id': je.account_id,
            'account_code': je.account.account_code if je.account else '',
            'account_name': je.account.name if je.account else '',
            'debit_amount': float(je.debit_amount) if je.debit_amount is not None else None,
            'credit_amount': float(je.credit_amount) if je.credit_amount is not None else None,
            'state': je.state,
            'is_reconciled': je.is_reconciled,
        })
    return rows


def _build_excel_for_quick_statement(statement, template=None):
    """
    Build the same comprehensive Excel (calculation memory, raw data, journal entries,
    hierarchy with JEs, pivot-friendly) for a template-based quick statement.
    Uses the template name as section label (row denominations from template), not
    Revenue/Costs/Expenses from the detailed endpoint.
    Returns (excel_base64_string, filename) or (None, None) if no currency/accounts.
    """
    company_id = statement.company_id
    currency_id = statement.currency_id
    if currency_id is None:
        return None, None
    template = template or getattr(statement, 'template', None)
    template_section_label = template.name if template else 'Statement Lines'
    # Collect all account IDs from statement lines
    lines = list(statement.lines.all().order_by('line_number'))
    all_account_ids = set()
    for line in lines:
        ids = line.account_ids if isinstance(line.account_ids, list) else []
        all_account_ids.update(ids or [])
    # Expand to include all descendants (same as detailed_* endpoints) so we include JEs from child accounts
    if all_account_ids:
        all_account_ids = _get_report_scope_account_ids(company_id, list(all_account_ids))
    if not all_account_ids:
        # Fallback: include all company accounts (e.g. when template lines are formula/rollup only)
        all_account_ids = set(
            Account.objects.filter(company_id=company_id, is_active=True).values_list('id', flat=True)
        )
    balance_type = 'posted'
    start_date = statement.start_date
    end_date = statement.end_date
    as_of_date = getattr(statement, 'as_of_date', None) or end_date
    report_type = statement.report_type or 'income_statement'
    # Fetch raw history and journal entries for those accounts
    if report_type == 'balance_sheet':
        raw_history = _fetch_raw_balance_history(
            company_id=company_id,
            account_ids=all_account_ids,
            currency_id=currency_id,
            balance_type=balance_type,
            as_of_date=as_of_date,
        )
        journal_entries = _fetch_journal_entries_for_report(
            company_id=company_id,
            account_ids=all_account_ids,
            currency_id=currency_id,
            balance_type=balance_type,
            as_of_date=as_of_date,
        )
    else:
        raw_history = _fetch_raw_balance_history(
            company_id=company_id,
            account_ids=all_account_ids,
            currency_id=currency_id,
            balance_type=balance_type,
            start_date=start_date,
            end_date=end_date,
        )
        journal_entries = _fetch_journal_entries_for_report(
            company_id=company_id,
            account_ids=all_account_ids,
            currency_id=currency_id,
            balance_type=balance_type,
            start_date=start_date,
            end_date=end_date,
        )
    # Build account -> report line labels from statement lines (use template name, not Revenue/Costs/Expenses)
    account_report_lines = {}
    for line in lines:
        ids = line.account_ids if isinstance(line.account_ids, list) else []
        label = f"{template_section_label} > {line.label}"
        for acc_id in ids or []:
            account_report_lines.setdefault(acc_id, []).append(label)
    for je in journal_entries:
        je['report_lines'] = '; '.join(account_report_lines.get(je.get('account_id'), []))
    # Build report dict compatible with build_detailed_statement_excel
    currency = statement.currency
    currency_dict = {
        'id': currency.id,
        'code': getattr(currency, 'code', ''),
        'name': getattr(currency, 'name', ''),
    }
    # One node per (line, account_id) so every JE matches a report row in the hierarchy sheet
    line_nodes = []
    for line in lines:
        ids = line.account_ids if isinstance(line.account_ids, list) else []
        balance_val = float(line.balance) if line.balance is not None else None
        if ids:
            for acc_id in ids:
                line_nodes.append({
                    'id': acc_id,
                    'account_code': '',
                    'name': line.label,
                    'path': line.label,
                    'balance': balance_val,
                    'is_leaf': True,
                    'children': None,
                })
        else:
            line_nodes.append({
                'id': None,
                'account_code': '',
                'name': line.label,
                'path': line.label,
                'balance': balance_val,
                'is_leaf': True,
                'children': None,
            })
    section_name = template_section_label
    section_balance = sum(
        (float(line.balance) if line.balance is not None else 0) for line in lines
    )
    if report_type == 'balance_sheet':
        report = {
            'as_of_date': str(as_of_date),
            'currency': currency_dict,
            'balance_type': balance_type,
            'assets': [{
                'id': None,
                'account_code': '',
                'name': section_name,
                'path': section_name,
                'balance': section_balance,
                'is_leaf': False,
                'children': line_nodes,
            }],
            'liabilities': [],
            'equity': [],
            'totals': {
                'total_assets': float(statement.total_assets) if statement.total_assets is not None else None,
                'total_liabilities': float(statement.total_liabilities) if statement.total_liabilities is not None else None,
                'total_equity': float(statement.total_equity) if statement.total_equity is not None else None,
                'total_liabilities_and_equity': None,
            },
        }
        if statement.total_liabilities is not None and statement.total_equity is not None:
            report['totals']['total_liabilities_and_equity'] = (
                float(statement.total_liabilities) + float(statement.total_equity)
            )
        filename = f"quick_balance_sheet_{as_of_date}.xlsx"
    else:
        report = {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'currency': currency_dict,
            'balance_type': balance_type,
            'revenues': [],
            'costs': [],
            'expenses': [{
                'id': None,
                'account_code': '',
                'name': section_name,
                'path': section_name,
                'balance': section_balance,
                'is_leaf': False,
                'children': line_nodes,
            }],
            'totals': {
                'total_revenue': None,
                'total_costs': None,
                'gross_profit': None,
                'total_expenses': section_balance,
                'net_income': float(statement.net_income) if statement.net_income is not None else None,
            },
        }
        filename = f"quick_income_statement_{start_date}_{end_date}.xlsx"
    request_params = {
        'template_id': statement.template_id,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'as_of_date': str(as_of_date),
        'report_type': report_type,
    }
    # Same line structure as markdown (Line | Label | Balance) plus debug: indent_level, is_bold, account_ids
    template_lines = [
        {
            'line_number': getattr(l, 'line_number', None),
            'indent_level': getattr(l, 'indent_level', 0) or 0,
            'label': getattr(l, 'label', '') or '',
            'is_bold': getattr(l, 'is_bold', False),
            'balance': float(l.balance) if getattr(l, 'balance', None) is not None else None,
            'account_ids': (getattr(l, 'account_ids', None) or []) if isinstance(getattr(l, 'account_ids', None), list) else [],
        }
        for l in lines
    ]
    excel_b64 = build_detailed_statement_excel_base64(
        report=report,
        report_type=report_type,
        request_params=request_params,
        raw_history_rows=raw_history,
        balance_type=balance_type,
        journal_entry_rows=journal_entries,
        template_section_label=template_section_label,
        template_lines=template_lines,
    )
    return excel_b64, filename


def _build_excel_for_comparison_result(company_id, result, template, generator, is_preview, include_pending=False):
    """
    Build the same comprehensive Excel for a with_comparisons result.
    - If not preview and result has statement.id: load FinancialStatement and use _build_excel_for_quick_statement.
    - If preview or no id: use _calculate_statement_data to get lines with account_ids, build mock statement, then _build_excel_for_quick_statement.
    Returns (excel_base64_string, filename) or (None, None).
    """
    # When dimension is used, result has 'periods'; use first period's statement for Excel
    if 'periods' in result and result['periods']:
        period_data = result['periods'][0]
        statement_data = period_data.get('statement', {})
        start_date = statement_data.get('start_date')
        end_date = statement_data.get('end_date')
    else:
        statement_data = result.get('statement', {})
        start_date = statement_data.get('start_date')
        end_date = statement_data.get('end_date')

    if not start_date or not end_date:
        return None, None
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    as_of_date = end_date

    # Persisted statement (generate_with_comparisons, no dimension)
    statement_id = statement_data.get('id')
    if not is_preview and statement_id:
        try:
            statement = FinancialStatement.objects.get(id=statement_id, company_id=company_id)
            return _build_excel_for_quick_statement(statement)
        except FinancialStatement.DoesNotExist:
            pass

    # Preview or dimension: build from _calculate_statement_data
    try:
        current_data = generator._calculate_statement_data(
            template=template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            include_pending=result.get('include_pending', include_pending),
            currency_id=None,
        )
    except Exception:
        return None, None

    lines_data = current_data.get('lines') or []
    if not lines_data:
        return None, None

    # Collect account IDs from lines for currency resolution
    account_ids_from_lines = set()
    for l in lines_data:
        ids = l.get('account_ids') or []
        if isinstance(ids, list):
            account_ids_from_lines.update(ids)

    # Get currency from report accounts (matches transaction currency for journal entries)
    # Fallback to any company account currency if no accounts in scope
    currency = None
    if account_ids_from_lines:
        from django.db.models import Count
        currency_id = (
            Account.objects.filter(
                id__in=account_ids_from_lines,
                company_id=company_id,
            )
            .values('currency_id')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')
            .values_list('currency_id', flat=True)
            .first()
        )
        if currency_id:
            currency = Currency.objects.filter(id=currency_id).first()
    if not currency:
        currency = Currency.objects.filter(
            account__company_id=company_id
        ).distinct().first()
    if not currency:
        return None, None

    # Mock line objects compatible with _build_excel_for_quick_statement
    class MockLine:
        __slots__ = ('line_number', 'label', 'balance', 'indent_level', 'is_bold', 'account_ids')
        def __init__(self, ln, label, balance, indent_level, is_bold, account_ids):
            self.line_number = ln
            self.label = label
            self.balance = balance
            self.indent_level = indent_level or 0
            self.is_bold = is_bold or False
            self.account_ids = account_ids if isinstance(account_ids, list) else []

    class MockLinesManager:
        def __init__(self, lines_list):
            self._lines = sorted(lines_list, key=lambda l: getattr(l, 'line_number', 0))
        def all(self):
            return self
        def order_by(self, _):
            return self._lines

    mock_lines = [
        MockLine(
            ln=l.get('line_number', 0),
            label=l.get('label', ''),
            balance=l.get('balance'),
            indent_level=l.get('indent_level', 0),
            is_bold=l.get('is_bold', False),
            account_ids=l.get('account_ids', []),
        )
        for l in lines_data
    ]

    class MockStatement:
        pass
    mock = MockStatement()
    mock.company_id = company_id
    mock.currency_id = currency.id
    mock.currency = currency
    mock.start_date = start_date
    mock.end_date = end_date
    mock.as_of_date = as_of_date
    mock.report_type = template.report_type or 'income_statement'
    mock.template_id = template.id
    mock.lines = MockLinesManager(mock_lines)
    mock.total_assets = None
    mock.total_liabilities = None
    mock.total_equity = None
    mock.net_income = None

    return _build_excel_for_quick_statement(mock, template=template)


class FinancialStatementTemplateViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing financial statement templates.
    """
    
    queryset = FinancialStatementTemplate.objects.all()
    serializer_class = FinancialStatementTemplateSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        report_type = self.request.query_params.get('report_type')
        if report_type:
            qs = qs.filter(report_type=report_type)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None, tenant_id=None):
        """Set this template as the default for its report type."""
        template = self.get_object()
        
        # Unset other defaults for this report type
        FinancialStatementTemplate.objects.filter(
            company=template.company,
            report_type=template.report_type,
            is_default=True,
        ).exclude(id=template.id).update(is_default=False)
        
        # Set this as default
        template.is_default = True
        template.save()
        
        return Response({'status': 'default set'})
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None, tenant_id=None):
        """Duplicate a template with all its line templates."""
        original = self.get_object()
        
        # Create new template
        new_template = FinancialStatementTemplate.objects.create(
            company=original.company,
            name=f"{original.name} (Copy)",
            report_type=original.report_type,
            description=original.description,
            is_active=original.is_active,
            is_default=False,
            show_zero_balances=original.show_zero_balances,
            show_account_codes=original.show_account_codes,
            show_percentages=original.show_percentages,
            group_by_cost_center=original.group_by_cost_center,
        )
        
        # Duplicate line templates
        for line_template in original.line_templates.all():
            line_template.pk = None
            line_template.template = new_template
            line_template.save()
        
        serializer = self.get_serializer(new_template)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def suggest_templates(self, request, tenant_id=None):
        """
        Use AI to suggest/generate Income Statement, Balance Sheet, and Cash Flow templates.
        
        This endpoint:
        1. Reads the company's chart of accounts
        2. Reads existing financial statement templates
        3. Sends context to an external AI (OpenAI/Anthropic)
        4. Receives structured JSON with template suggestions
        5. Validates and applies the suggestions to the database
        
        POST /api/<tenant>/api/financial-statement-templates/suggest_templates/
        {
            "user_preferences": "I want revenue broken down to 3 levels, OPEX to 1 level",
            "apply_changes": true,
            "ai_provider": "openai",
            "ai_model": "gpt-4o"
        }
        
        Response:
        {
            "status": "success",
            "applied_changes": true,
            "templates_created": 3,
            "templates_updated": 0,
            "lines_created": 75,
            "lines_updated": 0,
            "validation_warnings": [],
            "ai_raw_response": { ... }
        }
        """
        # Validate request
        serializer = TemplateSuggestionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Get company from tenant
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        try:
            # Initialize service
            service = TemplateSuggestionService(
                company_id=company_id,
                user_preferences=data.get('user_preferences', ''),
                ai_provider=data.get('ai_provider', 'openai'),
                ai_model=data.get('ai_model'),
            )
            
            # Generate suggestions
            result = service.generate_suggestions(
                apply_changes=data.get('apply_changes', True),
            )
            
            # Determine response status code
            if result.get('status') == 'success':
                http_status = status.HTTP_200_OK
            elif result.get('status') == 'partial':
                http_status = status.HTTP_207_MULTI_STATUS
            else:
                http_status = status.HTTP_400_BAD_REQUEST
            
            # Serialize and return response
            response_serializer = TemplateSuggestionResponseSerializer(data=result)
            if response_serializer.is_valid():
                return Response(response_serializer.data, status=http_status)
            else:
                return Response(result, status=http_status)
        
        except ValueError as e:
            return Response(
                {'error': str(e), 'status': 'error'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.exception("Error in suggest_templates: %s", e)
            return Response(
                {'error': str(e), 'status': 'error', 'error_type': 'internal_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FinancialStatementViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    ViewSet for generating and viewing financial statements.
    """
    
    queryset = FinancialStatement.objects.all()
    serializer_class = FinancialStatementSerializer
    
    def _get_company_currency(self, company_id):
        """
        Get currency for a company.
        Tries to get currency from company's accounts, falls back to first available currency.
        
        Parameters
        ----------
        company_id: int
            Company ID
            
        Returns
        -------
        Currency or None
            Currency instance or None if no currency found
        """
        # Try to get currency from company's accounts
        account = Account.objects.filter(company_id=company_id).select_related('currency').first()
        if account and account.currency:
            return account.currency
        
        # Fallback to first available currency (Currency is global)
        return Currency.objects.first()
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            qs = qs.filter(report_type=report_type)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            qs = qs.filter(end_date__gte=start_date)
        if end_date:
            qs = qs.filter(start_date__lte=end_date)
        
        return qs.order_by('-end_date', '-generated_at')
    
    @action(detail=False, methods=['post'])
    def generate(self, request, tenant_id=None):
        """
        Generate a new financial statement.
        
        POST /api/financial-statements/generate/
        {
            "template_id": 1,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "as_of_date": "2025-12-31",  // optional
            "currency_id": 1,  // optional
            "status": "draft",  // optional
            "notes": "...",  // optional
            "persist": true  // optional, defaults to true. Set to false for preview mode.
        }
        """
        serializer = GenerateStatementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        template = FinancialStatementTemplate.objects.get(
            id=data['template_id'],
            company_id=company_id,
        )
        
        generator = FinancialStatementGenerator(company_id=company_id)
        
        # Check if persist=False (preview mode)
        persist = data.get('persist', True)
        
        if not persist:
            # Preview mode: use preview_statement (no DB save)
            preview_data = generator.preview_statement(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                as_of_date=data.get('as_of_date'),
                currency_id=data.get('currency_id'),
                include_pending=data.get('include_pending', False),
            )
            
            # Get currency for formatting
            currency = self._get_company_currency(company_id)
            
            format_param = request.query_params.get('format', 'json')
            if format_param == 'markdown':
                return Response(
                    self._format_preview_as_markdown(preview_data, currency),
                    content_type='text/markdown',
                    status=status.HTTP_200_OK
                )
            elif format_param == 'html':
                return Response(
                    self._format_preview_as_html(preview_data, currency),
                    content_type='text/html',
                    status=status.HTTP_200_OK
                )
            else:
                preview_data['formatted'] = {
                    'markdown': self._format_preview_as_markdown(preview_data, currency),
                    'html': self._format_preview_as_html(preview_data, currency),
                }
                return Response(preview_data, status=status.HTTP_200_OK)
        
        # Normal mode: persist to database
        statement = generator.generate_statement(
            template=template,
            start_date=data['start_date'],
            end_date=data['end_date'],
            as_of_date=data.get('as_of_date'),
            currency_id=data.get('currency_id'),
            status=data.get('status', 'draft'),
            generated_by=request.user,
            notes=data.get('notes'),
            include_pending=data.get('include_pending', False),
        )
        
        # Return JSON with additional format options
        response_serializer = self.get_serializer(statement)
        response_data = response_serializer.data
        
        # Add formatted versions
        format_param = request.query_params.get('format', 'json')
        if format_param == 'markdown':
            return Response(
                self._format_as_markdown(statement),
                content_type='text/markdown',
                status=status.HTTP_201_CREATED
            )
        elif format_param == 'html':
            return Response(
                self._format_as_html(statement),
                content_type='text/html',
                status=status.HTTP_201_CREATED
            )
        else:
            # Default JSON, but include formatted versions in response
            response_data['formatted'] = {
                'markdown': self._format_as_markdown(statement),
                'html': self._format_as_html(statement),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def finalize(self, request, pk=None, tenant_id=None):
        """Mark a statement as final."""
        statement = self.get_object()
        statement.status = 'final'
        statement.save()
        return Response({'status': 'finalized'})
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None, tenant_id=None):
        """Archive a statement."""
        statement = self.get_object()
        statement.status = 'archived'
        statement.save()
        return Response({'status': 'archived'})
    
    @action(detail=True, methods=['get'])
    def export_pdf(self, request, pk=None, tenant_id=None):
        """Export statement as PDF (placeholder - implement PDF generation)."""
        statement = self.get_object()
        # TODO: Implement PDF generation
        return Response({'message': 'PDF export not yet implemented'})
    
    @action(detail=True, methods=['get'])
    def export_markdown(self, request, pk=None, tenant_id=None):
        """Export statement as Markdown."""
        statement = self.get_object()
        markdown_content = self._format_as_markdown(statement)
        
        from django.http import HttpResponse
        response = HttpResponse(
            markdown_content,
            content_type='text/markdown; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="{statement.name}.md"'
        return response
    
    @action(detail=True, methods=['get'])
    def export_html(self, request, pk=None, tenant_id=None):
        """Export statement as HTML."""
        statement = self.get_object()
        html_content = self._format_as_html(statement)
        
        from django.http import HttpResponse
        response = HttpResponse(
            html_content,
            content_type='text/html; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="{statement.name}.html"'
        return response
    
    def _format_as_markdown(self, statement):
        """Format financial statement as Markdown."""
        lines = []
        
        # Header
        lines.append(f"# {statement.name}")
        lines.append("")
        lines.append(f"**Report Type:** {statement.get_report_type_display()}")
        lines.append(f"**Period:** {statement.start_date} to {statement.end_date}")
        if statement.as_of_date and statement.as_of_date != statement.end_date:
            lines.append(f"**As of Date:** {statement.as_of_date}")
        lines.append(f"**Currency:** {statement.currency.code}")
        lines.append(f"**Status:** {statement.status}")
        if statement.notes:
            lines.append(f"**Notes:** {statement.notes}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Add HTML style block for no-wrap (works in markdown renderers that support HTML)
        lines.append("<style>")
        lines.append("table { white-space: nowrap; }")
        lines.append("th, td { white-space: nowrap; }")
        lines.append("</style>")
        lines.append("")
        
        # Table header
        lines.append("| Line | Label | Debit | Credit | Balance |")
        lines.append("|------|-------|-------|--------|---------|")
        
        # Lines
        for line in statement.lines.all().order_by('line_number'):
            indent = "&nbsp;" * (4 * line.indent_level)
            label = f"{indent}{line.label}"
            
            # Format amounts
            debit = self._format_amount(line.debit_amount, statement.currency)
            credit = self._format_amount(line.credit_amount, statement.currency)
            balance = self._format_amount(line.balance, statement.currency)
            
            # Handle line types
            if line.line_type == 'header':
                lines.append("")
                lines.append(f"### {line.label}")
                lines.append("")
                continue
            elif line.line_type == 'spacer':
                lines.append("")
                continue
            
            # If bold, make entire row bold (label and all data)
            if line.is_bold:
                row = f"| **{line.line_number}** | **{label}** | **{debit}** | **{credit}** | **{balance}** |"
            else:
                row = f"| {line.line_number} | {label} | {debit} | {credit} | {balance} |"
            
            lines.append(row)
        
        # Totals
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Totals")
        lines.append("")
        
        if statement.total_assets is not None:
            lines.append(f"**Total Assets:** {self._format_amount(statement.total_assets, statement.currency)}")
        if statement.total_liabilities is not None:
            lines.append(f"**Total Liabilities:** {self._format_amount(statement.total_liabilities, statement.currency)}")
        if statement.total_equity is not None:
            lines.append(f"**Total Equity:** {self._format_amount(statement.total_equity, statement.currency)}")
        if statement.net_income is not None:
            lines.append(f"**Net Income:** {self._format_amount(statement.net_income, statement.currency)}")
        
        # Footer
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"*Generated on {statement.generated_at.strftime('%Y-%m-%d %H:%M:%S')}*")
        if statement.generated_by:
            lines.append(f"*Generated by: {statement.generated_by.get_full_name() or statement.generated_by.username}*")
        
        return "\n".join(lines)
    
    def _format_as_html(self, statement):
        """Format financial statement as HTML."""
        lines = []
        
        # HTML header
        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='en'>")
        lines.append("<head>")
        lines.append("    <meta charset='UTF-8'>")
        lines.append("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
        lines.append(f"    <title>{statement.name}</title>")
        lines.append("    <style>")
        lines.append("        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }")
        lines.append("        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }")
        lines.append("        h2 { color: #34495e; margin-top: 30px; }")
        lines.append("        h3 { color: #7f8c8d; margin-top: 20px; }")
        lines.append("        table { width: 100%; border-collapse: collapse; margin: 20px 0; }")
        lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; white-space: nowrap; }")
        lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; white-space: nowrap; }")
        lines.append("        tr:hover { background-color: #f5f5f5; }")
        lines.append("        .header-row { background-color: #ecf0f1; font-weight: bold; }")
        lines.append("        .total-row { background-color: #e8f5e9; font-weight: bold; }")
        lines.append("        .amount { text-align: right; font-family: Arial, sans-serif; }")
        lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
        lines.append("        .negative { color: #e74c3c; }")
        lines.append("        /* Font sizes based on indent level */")
        lines.append("        .font-level-0 { font-size: 1em; }")
        lines.append("        .font-level-1 { font-size: 0.95em; }")
        lines.append("        .font-level-2 { font-size: 0.9em; }")
        lines.append("        .font-level-3 { font-size: 0.85em; }")
        lines.append("        .font-level-4 { font-size: 0.8em; }")
        lines.append("        /* Collapsible rows */")
        lines.append("        .collapsible-row { cursor: pointer; }")
        lines.append("        .collapsible-row:hover { background-color: #e3f2fd !important; }")
        lines.append("        .collapsible-content { display: none; }")
        lines.append("        .collapsible-content.expanded { display: table-row; }")
        lines.append("        .toggle-icon { display: inline-block; width: 12px; margin-right: 5px; }")
        lines.append("        .toggle-icon::before { content: '▶'; }")
        lines.append("        .toggle-icon.expanded::before { content: '▼'; }")
        lines.append("    </style>")
        lines.append("    </style>")
        lines.append("    <script>")
        lines.append("        function toggleRow(rowId) {")
        lines.append("            const rows = document.querySelectorAll('[data-parent=\"' + rowId + '\"]');")
        lines.append("            const icon = document.getElementById('icon-' + rowId);")
        lines.append("            let isExpanded = icon && icon.classList.contains('expanded');")
        lines.append("            rows.forEach(function(row) {")
        lines.append("                if (isExpanded) {")
        lines.append("                    row.style.display = 'none';")
        lines.append("                } else {")
        lines.append("                    row.style.display = '';")
        lines.append("                }")
        lines.append("            });")
        lines.append("            if (icon) {")
        lines.append("                icon.classList.toggle('expanded');")
        lines.append("            }")
        lines.append("        }")
        lines.append("    </script>")
        lines.append("</head>")
        lines.append("    </style>")
        lines.append("</head>")
        lines.append("<body>")
        
        # Title
        lines.append(f"    <h1>{statement.name}</h1>")
        
        # Metadata
        lines.append("    <div class='metadata'>")
        lines.append(f"        <p><strong>Report Type:</strong> {statement.get_report_type_display()}</p>")
        lines.append(f"        <p><strong>Period:</strong> {statement.start_date} to {statement.end_date}</p>")
        if statement.as_of_date and statement.as_of_date != statement.end_date:
            lines.append(f"        <p><strong>As of Date:</strong> {statement.as_of_date}</p>")
        lines.append(f"        <p><strong>Currency:</strong> {statement.currency.code}</p>")
        lines.append(f"        <p><strong>Status:</strong> {statement.status}</p>")
        if statement.notes:
            lines.append(f"        <p><strong>Notes:</strong> {statement.notes}</p>")
        lines.append("    </div>")
        
        # Table
        lines.append("    <table>")
        lines.append("        <thead>")
        lines.append("            <tr>")
        lines.append("                <th>Line</th>")
        lines.append("                <th>Label</th>")
        lines.append("                <th class='amount'>Debit</th>")
        lines.append("                <th class='amount'>Credit</th>")
        lines.append("                <th class='amount'>Balance</th>")
        lines.append("            </tr>")
        lines.append("        </thead>")
        lines.append("        <tbody>")
        
        # Lines
        for line in statement.lines.all().order_by('line_number'):
            if line.line_type == 'header':
                lines.append("        </tbody>")
                lines.append("    </table>")
                lines.append(f"    <h3>{line.label}</h3>")
                lines.append("    <table>")
                lines.append("        <thead>")
                lines.append("            <tr>")
                lines.append("                <th>Line</th>")
                lines.append("                <th>Label</th>")
                lines.append("                <th class='amount'>Debit</th>")
                lines.append("                <th class='amount'>Credit</th>")
                lines.append("                <th class='amount'>Balance</th>")
                lines.append("            </tr>")
                lines.append("        </thead>")
                lines.append("        <tbody>")
                continue
            elif line.line_type == 'spacer':
                lines.append("            <tr><td colspan='5'>&nbsp;</td></tr>")
                continue
            
            # Determine row class
            row_class = ""
            if line.line_type == 'header':
                row_class = "header-row"
            elif line.line_type in ('total', 'subtotal'):
                row_class = "total-row"
            
            # Indent style and font size - only apply to label column
            indent_level = line.indent_level
            indent_style = f"padding-left: {indent_level * 20}px;" if indent_level > 0 else ""
            font_class = f"font-level-{min(indent_level, 4)}"
            indent_attr = f" style='{indent_style}'" if indent_style else ""
            
            # Check if this row has children (for collapsible functionality)
            has_children = False
            parent_row_id = None
            if indent_level < 4:  # Only make rows with potential children collapsible
                # Check if next line has higher indent
                all_lines = list(statement.lines.all().order_by('line_number'))
                current_idx = next((i for i, l in enumerate(all_lines) if l.line_number == line.line_number), -1)
                if current_idx >= 0 and current_idx < len(all_lines) - 1:
                    next_line = all_lines[current_idx + 1]
                    has_children = next_line.indent_level > indent_level
                
                # Find parent row ID if this is a child
                if indent_level > 0:
                    for i in range(current_idx - 1, -1, -1):
                        if all_lines[i].indent_level < indent_level:
                            parent_row_id = f"row-{all_lines[i].line_number}"
                            break
            
            # Format amounts
            debit = self._format_amount(line.debit_amount, statement.currency, html=True)
            credit = self._format_amount(line.credit_amount, statement.currency, html=True)
            balance = self._format_amount(line.balance, statement.currency, html=True)
            
            # If bold, make entire row bold (all cells)
            if line.is_bold:
                label = f"<strong>{line.label}</strong>"
                line_num = f"<strong>{line.line_number}</strong>"
                debit = f"<strong>{debit}</strong>"
                credit = f"<strong>{credit}</strong>"
                balance = f"<strong>{balance}</strong>"
            else:
                label = line.label
                line_num = str(line.line_number)
            
            # Add toggle icon if row has children
            toggle_icon = ""
            row_id = f"row-{line.line_number}"
            onclick_attr = ""
            if has_children:
                toggle_icon = f"<span id='icon-{row_id}' class='toggle-icon'></span>"
                row_class += " collapsible-row"
                onclick_attr = f" onclick=\"toggleRow('{row_id}')\""
            
            # Add data-parent attribute if this is a child row
            data_parent_attr = f" data-parent='{parent_row_id}'" if parent_row_id else ""
            
            lines.append(f"            <tr class='{row_class}'{onclick_attr}{data_parent_attr}>")
            lines.append(f"                <td>{line_num}</td>")
            lines.append(f"                <td class='{font_class}'{indent_attr}>{toggle_icon}{label}</td>")
            lines.append(f"                <td class='amount'>{debit}</td>")
            lines.append(f"                <td class='amount'>{credit}</td>")
            lines.append(f"                <td class='amount'>{balance}</td>")
            lines.append("            </tr>")
        
        lines.append("        </tbody>")
        lines.append("    </table>")
        
        # Totals section
        if any([statement.total_assets, statement.total_liabilities, statement.total_equity, statement.net_income]):
            lines.append("    <h2>Totals</h2>")
            lines.append("    <table>")
            lines.append("        <tbody>")
            
            if statement.total_assets is not None:
                amount = self._format_amount(statement.total_assets, statement.currency, html=True)
                lines.append(f"            <tr class='total-row'><td colspan='4'><strong>Total Assets</strong></td><td class='amount'>{amount}</td></tr>")
            if statement.total_liabilities is not None:
                amount = self._format_amount(statement.total_liabilities, statement.currency, html=True)
                lines.append(f"            <tr class='total-row'><td colspan='4'><strong>Total Liabilities</strong></td><td class='amount'>{amount}</td></tr>")
            if statement.total_equity is not None:
                amount = self._format_amount(statement.total_equity, statement.currency, html=True)
                lines.append(f"            <tr class='total-row'><td colspan='4'><strong>Total Equity</strong></td><td class='amount'>{amount}</td></tr>")
            if statement.net_income is not None:
                amount = self._format_amount(statement.net_income, statement.currency, html=True)
                lines.append(f"            <tr class='total-row'><td colspan='4'><strong>Net Income</strong></td><td class='amount'>{amount}</td></tr>")
            
            lines.append("        </tbody>")
            lines.append("    </table>")
        
        # Footer
        lines.append("    <div class='metadata'>")
        lines.append(f"        <p><em>Generated on {statement.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</em></p>")
        if statement.generated_by:
            lines.append(f"        <p><em>Generated by: {statement.generated_by.get_full_name() or statement.generated_by.username}</em></p>")
        lines.append("    </div>")
        
        lines.append("</body>")
        lines.append("</html>")
        
        return "\n".join(lines)
    
    def _format_amount(self, amount, currency, html=False):
        """Format amount with currency symbol."""
        if amount is None:
            return "-" if not html else "&mdash;"
        
        from decimal import Decimal
        if isinstance(amount, Decimal):
            amount = float(amount)
        
        # Handle negative
        is_negative = amount < 0
        abs_amount = abs(amount)
        
        # Format with 2 decimal places
        formatted = f"{abs_amount:,.2f}"
        
        # Add currency symbol
        symbol = currency.symbol if hasattr(currency, 'symbol') and currency.symbol else currency.code
        formatted = f"{symbol} {formatted}"
        
        # Handle negative (parentheses)
        if is_negative:
            formatted = f"({formatted})"
            if html:
                formatted = f"<span class='negative'>{formatted}</span>"
        
        return formatted
    
    def _format_preview_as_markdown(self, preview_data, currency):
        """Format preview data as Markdown."""
        lines = []
        lines.append(f"# {preview_data['name']} (Preview)")
        lines.append("")
        lines.append(f"**Report Type:** {preview_data['report_type']}")
        lines.append(f"**Period:** {preview_data['start_date']} to {preview_data['end_date']}")
        if currency:
            lines.append(f"**Currency:** {currency.code}")
        lines.append("**Status:** Preview (not saved)")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("| Line | Label | Balance |")
        lines.append("|------|-------|---------|")
        for line_data in preview_data.get('lines', []):
            indent = "&nbsp;" * (4 * line_data.get('indent_level', 0))
            label = f"{indent}{line_data['label']}"
            balance = self._format_amount(Decimal(str(line_data.get('balance', 0))), currency) if currency else "0.00"
            if line_data.get('is_bold', False):
                row = f"| **{line_data['line_number']}** | **{label}** | **{balance}** |"
            else:
                row = f"| {line_data['line_number']} | {label} | {balance} |"
            lines.append(row)
        lines.append("")
        lines.append("*This is a preview. No data has been saved.*")
        return "\n".join(lines)
    
    def _format_preview_as_html(self, preview_data, currency):
        """Format preview data as HTML."""
        class MockLine:
            def __init__(self, data):
                self.line_number = data.get('line_number', 0)
                self.label = data.get('label', '')
                self.line_type = data.get('line_type', 'account')
                self.debit_amount = Decimal(str(data.get('debit_amount', 0)))
                self.credit_amount = Decimal(str(data.get('credit_amount', 0)))
                self.balance = Decimal(str(data.get('balance', 0)))
                self.indent_level = data.get('indent_level', 0)
                self.is_bold = data.get('is_bold', False)
        
        class MockStatement:
            def __init__(self, data):
                self.name = data.get('name', 'Financial Statement')
                self.report_type = data.get('report_type', '')
                self.start_date = data.get('start_date')
                self.end_date = data.get('end_date')
                self.as_of_date = data.get('as_of_date')
                self.status = 'preview'
                self.notes = None
                self.currency = currency
                self.total_assets = data.get('total_assets')
                self.total_liabilities = data.get('total_liabilities')
                self.total_equity = data.get('total_equity')
                self.net_income = data.get('net_income')
                self.generated_at = timezone.now()
                self.generated_by = None
                self._lines_list = [MockLine(line) for line in data.get('lines', [])]
            
            def get_report_type_display(self):
                return self.report_type.replace('_', ' ').title()
        
        class LinesManager:
            def __init__(self, lines_list):
                self._lines_list = lines_list
            def all(self):
                return self._lines_list
            def order_by(self, *args):
                return self._lines_list
        
        mock_statement = MockStatement(preview_data)
        mock_statement.lines = LinesManager(mock_statement._lines_list)
        html = self._format_as_html(mock_statement)
        html = html.replace(f"<h1>{preview_data['name']}</h1>", f"<h1>{preview_data['name']} <span style='color: #f39c12;'>(Preview)</span></h1>")
        return html
    
    def _format_time_series_as_markdown(self, series_data, currency):
        """Format time series data as Markdown. Handles both single and multiple dimensions."""
        lines = []
        
        # Check if multiple dimensions
        if 'data' in series_data and 'dimensions' in series_data:
            # Multiple dimensions
            lines.append(f"# {series_data['template_name']}")
            lines.append("")
            lines.append(f"**Report Type:** {series_data['report_type']}")
            lines.append(f"**Period:** {series_data['start_date']} to {series_data['end_date']}")
            lines.append(f"**Dimensions:** {', '.join(series_data['dimensions'])}")
            if currency:
                lines.append(f"**Currency:** {currency.code}")
            lines.append("")
            lines.append("---")
            lines.append("")
            
            # Format each dimension
            for dimension in series_data['dimensions']:
                dim_data = series_data['data'][dimension]
                lines.append(f"## {dimension.title()} Dimension")
                lines.append("")
                # _format_single_dimension_markdown returns a string, split it into lines
                dim_markdown = self._format_single_dimension_markdown(dim_data, currency)
                # Skip the header since we already have it above
                dim_lines = dim_markdown.split('\n')
                # Skip first few header lines and add the rest
                skip_header = True
                for dim_line in dim_lines:
                    if skip_header and (dim_line.startswith('#') or dim_line.startswith('**') or dim_line == ''):
                        continue
                    if dim_line.startswith('---'):
                        skip_header = False
                        continue
                    if not skip_header:
                        lines.append(dim_line)
                lines.append("")
                lines.append("---")
                lines.append("")
            
            return "\n".join(lines)
        else:
            # Single dimension
            return self._format_single_dimension_markdown(series_data, currency)
    
    def _format_single_dimension_markdown(self, series_data, currency):
        """Format a single dimension time series as Markdown."""
        lines = []
        
        # Header
        lines.append(f"# {series_data['template_name']}")
        lines.append("")
        lines.append(f"**Report Type:** {series_data['report_type']}")
        lines.append(f"**Period:** {series_data['start_date']} to {series_data['end_date']}")
        lines.append(f"**Dimension:** {series_data['dimension']}")
        if currency:
            lines.append(f"**Currency:** {currency.code}")
        if series_data.get('is_preview'):
            lines.append("**Status:** Preview (not saved)")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Get all periods from first line (assuming all lines have same periods)
        if not series_data.get('lines'):
            lines.append("*No data available*")
            return lines
        
        first_line = series_data['lines'][0]
        periods = first_line['data']
        
        # Build table header
        header = "| Line | Label |"
        separator = "|------|-------|"
        for period in periods:
            header += f" {period['period_label']} |"
            separator += " " + "-" * len(period['period_label']) + " |"
        lines.append(header)
        lines.append(separator)
        
        # Add each line
        for line_info in series_data['lines']:
            if line_info['line_type'] in ('header', 'spacer'):
                continue
            
            indent = "&nbsp;" * (4 * line_info.get('indent_level', 0))
            label = f"{indent}{line_info['label']}"
            
            # Build row - if bold, make entire row bold
            is_bold = line_info.get('is_bold', False)
            if is_bold:
                row = f"| **{line_info['line_number']}** | **{label}** |"
            else:
                row = f"| {line_info['line_number']} | {label} |"
            
            # Add values for each period
            for period in periods:
                # Find matching period value
                period_value = next(
                    (p['value'] for p in line_info['data'] if p['period_key'] == period['period_key']),
                    0.0
                )
                formatted_value = self._format_amount(Decimal(str(period_value)), currency) if currency else str(period_value)
                
                # If bold, make value bold too
                if is_bold:
                    formatted_value = f"**{formatted_value}**"
                
                row += f" {formatted_value} |"
            
            lines.append(row)
        
        # Footer
        lines.append("")
        lines.append("---")
        
        return "\n".join(lines)
    
    def _format_time_series_as_html(self, series_data, currency):
        """Format time series data as HTML. Handles both single and multiple dimensions."""
        # Check if multiple dimensions
        if 'data' in series_data and 'dimensions' in series_data:
            # Multiple dimensions - create sections for each
            lines = []
            lines.append("<!DOCTYPE html>")
            lines.append("<html lang='en'>")
            lines.append("<head>")
            lines.append("    <meta charset='UTF-8'>")
            lines.append("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
            lines.append(f"    <title>{series_data['template_name']}</title>")
            lines.append("    <style>")
            lines.append("        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }")
            lines.append("        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }")
            lines.append("        h2 { color: #34495e; margin-top: 30px; border-bottom: 2px solid #95a5a6; padding-bottom: 5px; }")
            lines.append("        table { width: 100%; border-collapse: collapse; margin: 20px 0; }")
            lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; }")
            lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; }")
            lines.append("        tr:hover { background-color: #f5f5f5; }")
            lines.append("        .amount { text-align: right; font-family: Arial, sans-serif; }")
            lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
            lines.append("        .negative { color: #e74c3c; }")
            lines.append("        .dimension-section { margin-top: 40px; page-break-inside: avoid; }")
            lines.append("        /* Font sizes based on indent level */")
            lines.append("        .font-level-0 { font-size: 1em; }")
            lines.append("        .font-level-1 { font-size: 0.95em; }")
            lines.append("        .font-level-2 { font-size: 0.9em; }")
            lines.append("        .font-level-3 { font-size: 0.85em; }")
            lines.append("        .font-level-4 { font-size: 0.8em; }")
            lines.append("    </style>")
            lines.append("</head>")
            lines.append("<body>")
            lines.append(f"    <h1>{series_data['template_name']}</h1>")
            lines.append("    <div class='metadata'>")
            lines.append(f"        <p><strong>Report Type:</strong> {series_data['report_type']}</p>")
            lines.append(f"        <p><strong>Period:</strong> {series_data['start_date']} to {series_data['end_date']}</p>")
            lines.append(f"        <p><strong>Dimensions:</strong> {', '.join(series_data['dimensions'])}</p>")
            if currency:
                lines.append(f"        <p><strong>Currency:</strong> {currency.code}</p>")
            lines.append("    </div>")
            
            # Format each dimension
            for dimension in series_data['dimensions']:
                dim_data = series_data['data'][dimension]
                lines.append(f"    <div class='dimension-section'>")
                lines.append(f"        <h2>{dimension.title()} Dimension</h2>")
                dim_html = self._format_single_dimension_html(dim_data, currency, include_header=False)
                # Extract table content from dim_html
                dim_lines = dim_html.split('\n')
                in_table = False
                for dim_line in dim_lines:
                    if '<table>' in dim_line:
                        in_table = True
                    if in_table:
                        lines.append(f"        {dim_line}")
                    if '</table>' in dim_line:
                        in_table = False
                lines.append("    </div>")
            
            lines.append("</body>")
            lines.append("</html>")
            return "\n".join(lines)
        else:
            # Single dimension
            return self._format_single_dimension_html(series_data, currency, include_header=True)
    
    def _format_single_dimension_html(self, series_data, currency, include_header=True):
        """Format a single dimension time series as HTML."""
        lines = []
        
        if include_header:
            # HTML header
            lines.append("<!DOCTYPE html>")
            lines.append("<html lang='en'>")
            lines.append("<head>")
            lines.append("    <meta charset='UTF-8'>")
            lines.append("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
            lines.append(f"    <title>{series_data['template_name']}</title>")
            lines.append("    <style>")
            lines.append("        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }")
            lines.append("        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }")
            lines.append("        table { width: 100%; border-collapse: collapse; margin: 20px 0; }")
            lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; }")
            lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; }")
            lines.append("        tr:hover { background-color: #f5f5f5; }")
            lines.append("        .amount { text-align: right; font-family: Arial, sans-serif; }")
            lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
            lines.append("        .negative { color: #e74c3c; }")
            lines.append("        /* Font sizes based on indent level */")
            lines.append("        .font-level-0 { font-size: 1em; }")
            lines.append("        .font-level-1 { font-size: 0.95em; }")
            lines.append("        .font-level-2 { font-size: 0.9em; }")
            lines.append("        .font-level-3 { font-size: 0.85em; }")
            lines.append("        .font-level-4 { font-size: 0.8em; }")
            lines.append("    </style>")
            lines.append("</head>")
            lines.append("<body>")
            
            # Title
            lines.append(f"    <h1>{series_data['template_name']}</h1>")
            
            # Metadata
            lines.append("    <div class='metadata'>")
            lines.append(f"        <p><strong>Report Type:</strong> {series_data['report_type']}</p>")
            lines.append(f"        <p><strong>Period:</strong> {series_data['start_date']} to {series_data['end_date']}</p>")
            lines.append(f"        <p><strong>Dimension:</strong> {series_data['dimension']}</p>")
            if currency:
                lines.append(f"        <p><strong>Currency:</strong> {currency.code}</p>")
            if series_data.get('is_preview'):
                lines.append("        <p><strong>Status:</strong> <span style='color: #f39c12;'>Preview (not saved)</span></p>")
            lines.append("    </div>")
        
        # Table
        if not series_data['lines']:
            lines.append("    <p><em>No data available</em></p>")
        else:
            first_line = series_data['lines'][0]
            periods = first_line['data']
            
            lines.append("    <table>")
            lines.append("        <thead>")
            lines.append("            <tr>")
            lines.append("                <th>Line</th>")
            lines.append("                <th>Label</th>")
            for period in periods:
                lines.append(f"                <th class='amount'>{period['period_label']}</th>")
            lines.append("            </tr>")
            lines.append("        </thead>")
            lines.append("        <tbody>")
            
            # Add each line
            for line_info in series_data['lines']:
                if line_info['line_type'] in ('header', 'spacer'):
                    continue
                
                # Indent style and font size - only apply to label column
                indent_level = line_info.get('indent_level', 0)
                indent_style = f"padding-left: {indent_level * 20}px;" if indent_level > 0 else ""
                font_class = f"font-level-{min(indent_level, 4)}"
                indent_attr = f" style='{indent_style}'" if indent_style else ""
                
                label = line_info['label']
                line_num = str(line_info['line_number'])
                
                # If bold, wrap all cells in <strong>
                is_bold = line_info.get('is_bold', False)
                if is_bold:
                    label = f"<strong>{label}</strong>"
                    line_num = f"<strong>{line_num}</strong>"
                
                lines.append("            <tr>")
                lines.append(f"                <td>{line_num}</td>")
                lines.append(f"                <td class='{font_class}'{indent_attr}>{label}</td>")
                
                # Add values for each period
                for period in periods:
                    # Find matching period value
                    period_value = next(
                        (p['value'] for p in line_info['data'] if p['period_key'] == period['period_key']),
                        0.0
                    )
                    formatted_value = self._format_amount(Decimal(str(period_value)), currency, html=True) if currency else str(period_value)
                    
                    # If bold, make value bold too
                    if is_bold:
                        formatted_value = f"<strong>{formatted_value}</strong>"
                    
                    lines.append(f"                <td class='amount'>{formatted_value}</td>")
                
                lines.append("            </tr>")
            
            lines.append("        </tbody>")
            lines.append("    </table>")
        
        # Footer
        lines.append("</body>")
        lines.append("</html>")
        
        return "\n".join(lines)
    
    def _format_comparisons_as_markdown(self, comparison_data, currency):
        """Format comparison data as Markdown."""
        lines = []
        
        # Check if dimension breakdown (multiple periods)
        if 'periods' in comparison_data:
            # Multiple periods with dimension
            lines.append(f"# {comparison_data.get('template_name', 'Financial Statement')} - Comparisons")
            lines.append("")
            lines.append(f"**Report Type:** {comparison_data.get('report_type', '')}")
            lines.append(f"**Period:** {comparison_data['start_date']} to {comparison_data['end_date']}")
            lines.append(f"**Dimension:** {comparison_data.get('dimension', '')}")
            if currency:
                lines.append(f"**Currency:** {currency.code}")
            if comparison_data.get('is_preview'):
                lines.append("**Status:** Preview (not saved)")
            lines.append("")
            lines.append("---")
            lines.append("")
            
            # Format each period
            for period_data in comparison_data['periods']:
                lines.append(f"## {period_data.get('period_label', 'Period')}")
                lines.append("")
                period_md = self._format_single_comparison_markdown(period_data, currency)
                # Skip header from period_md
                period_lines = period_md.split('\n')
                skip_header = True
                for p_line in period_lines:
                    if skip_header and (p_line.startswith('#') or p_line.startswith('**') or p_line == '' or p_line.startswith('---')):
                        continue
                    if p_line.startswith('## Current Period'):
                        skip_header = False
                    if not skip_header:
                        lines.append(p_line)
                lines.append("")
                lines.append("---")
                lines.append("")
            
            return "\n".join(lines)
        else:
            # Single period comparison
            return self._format_single_comparison_markdown(comparison_data, currency)
    
    def _format_single_comparison_markdown(self, comparison_data, currency):
        """Format a single comparison as Markdown - all comparisons in one table."""
        lines = []
        
        statement = comparison_data.get('statement', {})
        comparisons = comparison_data.get('comparisons', {})
        
        # Header
        lines.append(f"# {statement.get('name', 'Financial Statement')} - Comparisons")
        lines.append("")
        lines.append(f"**Period:** {statement.get('start_date')} to {statement.get('end_date')}")
        if currency:
            lines.append(f"**Currency:** {currency.code}")
        if comparison_data.get('is_preview'):
            lines.append("**Status:** Preview (not saved)")
        lines.append("")
        
        # Build comparison period info
        comp_periods = []
        valid_comparisons = {}
        for comp_type, comp_data in comparisons.items():
            if 'error' in comp_data:
                continue
            comp_periods.append(f"**{comp_type.replace('_', ' ').title()}:** {comp_data.get('start_date')} to {comp_data.get('end_date')}")
            valid_comparisons[comp_type] = comp_data
        
        if comp_periods:
            lines.append(" | ".join(comp_periods))
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # Build table header - single table with all comparisons
        header_cols = ["Line", "Label"]
        header_cols.append("Current Period")
        
        for comp_type, comp_data in valid_comparisons.items():
            comp_label = comp_type.replace('_', ' ').title()
            header_cols.extend([f"{comp_label}", f"Change", f"% Change"])
        
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")
        
        # Build rows
        for line in statement.get('lines', []):
            row_cols = []
            
            # Line number
            row_cols.append(str(line['line_number']))
            
            # Label with indentation
            indent = "&nbsp;" * (4 * line.get('indent_level', 0))
            label = f"{indent}{line['label']}"
            if line.get('is_bold', False):
                label = f"**{label}**"
            row_cols.append(label)
            
            # Current period value
            current_val = Decimal(str(line['balance']))
            current_fmt = self._format_amount(current_val, currency) if currency else str(current_val)
            if line.get('is_bold', False):
                current_fmt = f"**{current_fmt}**"
            row_cols.append(current_fmt)
            
            # Each comparison
            for comp_type, comp_data in valid_comparisons.items():
                comp_lines = comp_data.get('lines', {})
                line_num = line['line_number']  # Use integer key
                comp_info = comp_lines.get(line_num, {})
                
                # Comparison value
                comp_val = Decimal(str(comp_info.get('comparison_value', 0)))
                comp_fmt = self._format_amount(comp_val, currency) if currency else str(comp_val)
                if line.get('is_bold', False):
                    comp_fmt = f"**{comp_fmt}**"
                row_cols.append(comp_fmt)
                
                # Change
                abs_change = comp_info.get('absolute_change', 0)
                if abs_change is None:
                    change_fmt = "-"
                else:
                    change_fmt = self._format_amount(Decimal(str(abs_change)), currency) if currency else str(abs_change)
                if line.get('is_bold', False):
                    change_fmt = f"**{change_fmt}**"
                row_cols.append(change_fmt)
                
                # Percentage change
                pct_change = comp_info.get('percentage_change')
                if pct_change is None:
                    pct_fmt = "-"
                else:
                    pct_fmt = f"{float(pct_change):.2f}%"
                if line.get('is_bold', False):
                    pct_fmt = f"**{pct_fmt}**"
                row_cols.append(pct_fmt)
            
            lines.append("| " + " | ".join(row_cols) + " |")
        
        lines.append("")
        
        # Add error messages if any
        for comp_type, comp_data in comparisons.items():
            if 'error' in comp_data:
                lines.append(f"**{comp_type.replace('_', ' ').title()}:** *Error: {comp_data['error']}*")
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_comparisons_as_html(self, comparison_data, currency):
        """Format comparison data as HTML."""
        # Check if dimension breakdown
        if 'periods' in comparison_data:
            # Multiple periods
            lines = []
            lines.append("<!DOCTYPE html>")
            lines.append("<html lang='en'>")
            lines.append("<head>")
            lines.append("    <meta charset='UTF-8'>")
            lines.append("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
            lines.append(f"    <title>{comparison_data.get('template_name', 'Comparisons')}</title>")
            lines.append("    <style>")
            lines.append("        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }")
            lines.append("        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }")
            lines.append("        h2 { color: #34495e; margin-top: 30px; border-bottom: 2px solid #95a5a6; padding-bottom: 5px; }")
            lines.append("        table { width: 100%; border-collapse: collapse; margin: 20px 0; }")
            lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; }")
            lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; }")
            lines.append("        tr:hover { background-color: #f5f5f5; }")
            lines.append("        .amount { text-align: right; font-family: Arial, sans-serif; }")
            lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
            lines.append("        .negative { color: #e74c3c; }")
            lines.append("        .positive { color: #27ae60; }")
            lines.append("        .dimension-section { margin-top: 40px; page-break-inside: avoid; }")
            lines.append("    </style>")
            lines.append("</head>")
            lines.append("<body>")
            lines.append(f"    <h1>{comparison_data.get('template_name', 'Comparisons')}</h1>")
            lines.append("    <div class='metadata'>")
            lines.append(f"        <p><strong>Report Type:</strong> {comparison_data.get('report_type', '')}</p>")
            lines.append(f"        <p><strong>Period:</strong> {comparison_data['start_date']} to {comparison_data['end_date']}</p>")
            lines.append(f"        <p><strong>Dimension:</strong> {comparison_data.get('dimension', '')}</p>")
            if currency:
                lines.append(f"        <p><strong>Currency:</strong> {currency.code}</p>")
            lines.append("    </div>")
            
            for period_data in comparison_data['periods']:
                lines.append(f"    <div class='dimension-section'>")
                lines.append(f"        <h2>{period_data.get('period_label', 'Period')}</h2>")
                period_html = self._format_single_comparison_html(period_data, currency, include_header=False)
                # Extract content from period_html
                period_lines = period_html.split('\n')
                for p_line in period_lines:
                    if '<body>' in p_line or '</body>' in p_line or '</html>' in p_line or '<!DOCTYPE' in p_line or '<html' in p_line or '<head>' in p_line or '</head>' in p_line:
                        continue
                    if '<h1>' in p_line:
                        continue
                    lines.append(f"        {p_line}")
                lines.append("    </div>")
            
            lines.append("</body>")
            lines.append("</html>")
            return "\n".join(lines)
        else:
            # Single period
            return self._format_single_comparison_html(comparison_data, currency, include_header=True)
    
    def _format_single_comparison_html(self, comparison_data, currency, include_header=True):
        """Format a single comparison as HTML - all comparisons in one table."""
        lines = []
        
        statement = comparison_data.get('statement', {})
        comparisons = comparison_data.get('comparisons', {})
        
        if include_header:
            lines.append("<!DOCTYPE html>")
            lines.append("<html lang='en'>")
            lines.append("<head>")
            lines.append("    <meta charset='UTF-8'>")
            lines.append("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
            lines.append(f"    <title>{statement.get('name', 'Comparisons')}</title>")
            lines.append("    <style>")
            lines.append("        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }")
            lines.append("        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }")
            lines.append("        h2 { color: #34495e; margin-top: 30px; border-bottom: 2px solid #95a5a6; padding-bottom: 5px; }")
            lines.append("        table { width: 100%; border-collapse: collapse; margin: 20px 0; }")
            lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; }")
            lines.append("        th.amount { text-align: right; }")
            lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; }")
            lines.append("        tr:hover { background-color: #f5f5f5; }")
            lines.append("        .amount { text-align: right; font-family: Arial, sans-serif; }")
            lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
            lines.append("        .negative { color: #e74c3c; }")
            lines.append("        .positive { color: #27ae60; }")
            lines.append("        .font-level-0 { font-size: 1em; }")
            lines.append("        .font-level-1 { font-size: 0.95em; }")
            lines.append("        .font-level-2 { font-size: 0.9em; }")
            lines.append("        .font-level-3 { font-size: 0.85em; }")
            lines.append("        .font-level-4 { font-size: 0.8em; }")
            lines.append("    </style>")
            lines.append("</head>")
            lines.append("<body>")
            lines.append(f"    <h1>{statement.get('name', 'Financial Statement')} - Comparisons</h1>")
            lines.append("    <div class='metadata'>")
            lines.append(f"        <p><strong>Period:</strong> {statement.get('start_date')} to {statement.get('end_date')}</p>")
            if currency:
                lines.append(f"        <p><strong>Currency:</strong> {currency.code}</p>")
            if comparison_data.get('is_preview'):
                lines.append("        <p><strong>Status:</strong> <span style='color: #f39c12;'>Preview (not saved)</span></p>")
            
            # Add comparison period info
            comp_periods = []
            for comp_type, comp_data in comparisons.items():
                if 'error' not in comp_data:
                    comp_periods.append(f"<strong>{comp_type.replace('_', ' ').title()}:</strong> {comp_data.get('start_date')} to {comp_data.get('end_date')}")
            if comp_periods:
                lines.append("        <p>" + " | ".join(comp_periods) + "</p>")
            
            lines.append("    </div>")
        
        # Build single table with all comparisons
        valid_comparisons = {k: v for k, v in comparisons.items() if 'error' not in v}
        
        if valid_comparisons:
            lines.append("    <table>")
            lines.append("        <thead>")
            lines.append("            <tr>")
            lines.append("                <th>Line</th>")
            lines.append("                <th>Label</th>")
            lines.append("                <th class='amount'>Current Period</th>")
            
            for comp_type, comp_data in valid_comparisons.items():
                comp_label = comp_type.replace('_', ' ').title()
                lines.append(f"                <th class='amount' colspan='3'>{comp_label}</th>")
            
            lines.append("            </tr>")
            lines.append("            <tr>")
            lines.append("                <th></th>")
            lines.append("                <th></th>")
            lines.append("                <th class='amount'></th>")
            
            for comp_type, comp_data in valid_comparisons.items():
                lines.append("                <th class='amount'>Amount</th>")
                lines.append("                <th class='amount'>Change</th>")
                lines.append("                <th class='amount'>% Change</th>")
            
            lines.append("            </tr>")
            lines.append("        </thead>")
            lines.append("        <tbody>")
            
            for line in statement.get('lines', []):
                indent_level = line.get('indent_level', 0)
                is_bold = line.get('is_bold', False)
                indent_style = f"padding-left: {indent_level * 20}px;" if indent_level > 0 else ""
                font_class = f"font-level-{min(indent_level, 4)}"
                bold_style = "font-weight: bold;" if is_bold else ""
                style_attr = f" style='{indent_style}{bold_style}'" if (indent_style or bold_style) else ""
                
                lines.append("            <tr>")
                lines.append(f"                <td>{line['line_number']}</td>")
                lines.append(f"                <td class='{font_class}'{style_attr}>{line['label']}</td>")
                
                # Current period value
                current_val = Decimal(str(line['balance']))
                current_fmt = self._format_amount(current_val, currency, html=True) if currency else str(current_val)
                if is_bold:
                    current_fmt = f"<strong>{current_fmt}</strong>"
                lines.append(f"                <td class='amount'>{current_fmt}</td>")
                
                # Each comparison
                for comp_type, comp_data in valid_comparisons.items():
                    comp_lines = comp_data.get('lines', {})
                    line_num = line['line_number']  # Use integer key
                    comp_info = comp_lines.get(line_num, {})
                    
                    # Comparison value
                    comp_val = Decimal(str(comp_info.get('comparison_value', 0)))
                    comp_fmt = self._format_amount(comp_val, currency, html=True) if currency else str(comp_val)
                    if is_bold:
                        comp_fmt = f"<strong>{comp_fmt}</strong>"
                    lines.append(f"                <td class='amount'>{comp_fmt}</td>")
                    
                    # Change
                    abs_change = comp_info.get('absolute_change', 0)
                    if abs_change is None:
                        change_fmt = "-"
                        change_class = ""
                    else:
                        abs_change_decimal = Decimal(str(abs_change))
                        change_fmt = self._format_amount(abs_change_decimal, currency, html=True) if currency else str(abs_change)
                        change_class = "positive" if abs_change_decimal >= 0 else "negative"
                        if is_bold:
                            change_fmt = f"<strong>{change_fmt}</strong>"
                    lines.append(f"                <td class='amount {change_class}'>{change_fmt}</td>")
                    
                    # Percentage change
                    pct_change = comp_info.get('percentage_change')
                    if pct_change is None:
                        pct_fmt = "-"
                        pct_class = ""
                    else:
                        pct_fmt = f"{float(pct_change):.2f}%"
                        pct_class = "positive" if pct_change >= 0 else "negative"
                        if is_bold:
                            pct_fmt = f"<strong>{pct_fmt}</strong>"
                    lines.append(f"                <td class='amount {pct_class}'>{pct_fmt}</td>")
                
                lines.append("            </tr>")
            
            lines.append("        </tbody>")
            lines.append("    </table>")
        
        # Add error messages if any
        for comp_type, comp_data in comparisons.items():
            if 'error' in comp_data:
                lines.append(f"    <p><strong>{comp_type.replace('_', ' ').title()}:</strong> <em>Error: {comp_data['error']}</em></p>")
        
        if include_header:
            lines.append("</body>")
            lines.append("</html>")
        
        return "\n".join(lines)
    
    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None, tenant_id=None):
        """Export statement as Excel."""
        statement = self.get_object()
        
        import pandas as pd
        from openpyxl import Workbook
        from openpyxl.utils.dataframe import dataframe_to_rows
        from django.http import HttpResponse
        
        # Build DataFrame
        lines_data = []
        for line in statement.lines.all():
            lines_data.append({
                'Line': line.line_number,
                'Label': '  ' * line.indent_level + line.label,
                'Debit': line.debit_amount,
                'Credit': line.credit_amount,
                'Balance': line.balance,
            })
        
        df = pd.DataFrame(lines_data)
        
        # Create Excel response
        wb = Workbook()
        ws = wb.active
        ws.title = statement.name
        
        # Add header
        ws.append(['Financial Statement'])
        ws.append([statement.name])
        ws.append([f"Period: {statement.start_date} to {statement.end_date}"])
        ws.append([])
        
        # Add data
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
        
        # Add totals
        ws.append([])
        if statement.total_assets:
            ws.append(['Total Assets', '', '', statement.total_assets])
        if statement.total_liabilities:
            ws.append(['Total Liabilities', '', '', statement.total_liabilities])
        if statement.total_equity:
            ws.append(['Total Equity', '', '', statement.total_equity])
        if statement.net_income:
            ws.append(['Net Income', '', '', statement.net_income])
        
        # Create response
        from io import BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{statement.name}.xlsx"'
        return response
    
    @action(detail=False, methods=['get'])
    def quick_balance_sheet(self, request, tenant_id=None):
        """Quick balance sheet for current period."""
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        # Get default balance sheet template
        template = FinancialStatementTemplate.objects.filter(
            company_id=company_id,
            report_type='balance_sheet',
            is_default=True,
            is_active=True,
        ).first()
        
        if not template:
            return Response(
                {'error': 'No default balance sheet template found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Use current year
        today = date.today()
        start_date = date(today.year, 1, 1)
        end_date = today
        
        generator = FinancialStatementGenerator(company_id=company_id)
        statement = generator.generate_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=end_date,
            status='draft',
            generated_by=request.user,
        )
        
        serializer = self.get_serializer(statement)
        data = dict(serializer.data)
        # Attach same comprehensive Excel (calculation memory, raw data, JEs, hierarchy, pivot-friendly)
        excel_b64, excel_filename = _build_excel_for_quick_statement(statement)
        if excel_b64 and excel_filename:
            data['excel_base64'] = excel_b64
            data['excel_filename'] = excel_filename
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def time_series(self, request, tenant_id=None):
        """
        Generate time series data for financial statement lines.
        
        POST /api/financial-statements/time_series/?include_metadata=true
        {
            "template_id": 1,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "dimension": "month",  // day, week, month, quarter, semester, year
            "line_numbers": [1, 2, 3],  // optional, specific lines
            "include_pending": false
        }
        
        Query Parameters:
        - preview=true: Returns preview without saving
        - include_metadata=true: Includes calculation memory and metadata for debugging
          (accounts used, calculation type, debit/credit breakdowns, etc.)
        """
        serializer = TimeSeriesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Get company from tenant
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        try:
            template = FinancialStatementTemplate.objects.get(
                id=data['template_id'],
                company_id=company_id,
            )
        except FinancialStatementTemplate.DoesNotExist:
            return Response(
                {'error': 'Template not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if preview mode
        is_preview = request.query_params.get('preview', 'false').lower() == 'true'
        
        # Check if calculation metadata should be included (for debugging)
        include_metadata = request.query_params.get('include_metadata', 'false').lower() == 'true'
        
        # Get dimension(s) - support both single string and list
        dimension = data.get('dimension', 'month')
        # If dimensions list is provided, use it; otherwise use single dimension
        if 'dimensions' in data and data.get('dimensions'):
            dimension = data['dimensions']
        
        # Generate time series
        generator = FinancialStatementGenerator(company_id=company_id)
        if is_preview:
            series_data = generator.preview_time_series(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                dimension=dimension,
                line_numbers=data.get('line_numbers'),
                include_pending=data.get('include_pending', False),
                include_metadata=include_metadata,
            )
        else:
            series_data = generator.generate_time_series(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                dimension=dimension,
                line_numbers=data.get('line_numbers'),
                include_pending=data.get('include_pending', False),
                include_metadata=include_metadata,
            )
        
        # Get currency for formatting
        currency = self._get_company_currency(company_id)
        
        # Return formatted versions based on format parameter
        format_param = request.query_params.get('format', 'json')
        if format_param == 'markdown':
            return Response(
                self._format_time_series_as_markdown(series_data, currency),
                content_type='text/markdown',
                status=status.HTTP_200_OK
            )
        elif format_param == 'html':
            return Response(
                self._format_time_series_as_html(series_data, currency),
                content_type='text/html',
                status=status.HTTP_200_OK
            )
        else:
            # Default JSON, but include formatted versions in response
            series_data['formatted'] = {
                'markdown': self._format_time_series_as_markdown(series_data, currency),
                'html': self._format_time_series_as_html(series_data, currency),
            }
            return Response(series_data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def with_comparisons(self, request, tenant_id=None):
        """
        Generate financial statement with period comparisons.
        
        POST /api/financial-statements/with_comparisons/
        POST /api/financial-statements/with_comparisons/?preview=true  // Preview mode (no DB save)
        
        {
            "template_id": 1,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "comparison_types": ["previous_period", "previous_year"],
            "dimension": "month",  // optional: break down current period by dimension (month, quarter, etc.)
            "include_pending": false
        }
        """
        serializer = ComparisonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Get company from tenant
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        try:
            template = FinancialStatementTemplate.objects.get(
                id=data['template_id'],
                company_id=company_id,
            )
        except FinancialStatementTemplate.DoesNotExist:
            return Response(
                {'error': 'Template not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if preview mode
        is_preview = request.query_params.get('preview', 'false').lower() == 'true'
        
        # Generate with comparisons
        generator = FinancialStatementGenerator(company_id=company_id)
        if is_preview:
            result = generator.preview_with_comparisons(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                comparison_types=data.get('comparison_types', ['previous_period', 'previous_year']),
                dimension=data.get('dimension'),
                include_pending=data.get('include_pending', False),
            )
        else:
            result = generator.generate_with_comparisons(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                comparison_types=data.get('comparison_types', ['previous_period', 'previous_year']),
                dimension=data.get('dimension'),
                include_pending=data.get('include_pending', False),
            )
        
        # Get currency for formatting
        currency = self._get_company_currency(company_id)
        
        # Return formatted versions based on format parameter
        format_param = request.query_params.get('format', 'json')
        if format_param == 'markdown':
            return Response(
                self._format_comparisons_as_markdown(result, currency),
                content_type='text/markdown',
                status=status.HTTP_200_OK
            )
        elif format_param == 'html':
            return Response(
                self._format_comparisons_as_html(result, currency),
                content_type='text/html',
                status=status.HTTP_200_OK
            )
        else:
            # Default JSON, but include formatted versions in response
            result['formatted'] = {
                'markdown': self._format_comparisons_as_markdown(result, currency),
                'html': self._format_comparisons_as_html(result, currency),
            }
            # Attach same comprehensive Excel (calculation memory, raw data, JEs, hierarchy, pivot-friendly)
            excel_b64, excel_filename = _build_excel_for_comparison_result(
                company_id, result, template, generator, is_preview,
                include_pending=data.get('include_pending', False),
            )
            if excel_b64 and excel_filename:
                result['excel_base64'] = excel_b64
                result['excel_filename'] = excel_filename
            return Response(result, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def quick_income_statement(self, request, tenant_id=None):
        """Quick income statement for current period."""
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        # Get default income statement template
        template = FinancialStatementTemplate.objects.filter(
            company_id=company_id,
            report_type='income_statement',
            is_default=True,
            is_active=True,
        ).first()
        
        if not template:
            return Response(
                {'error': 'No default income statement template found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Use current year
        today = date.today()
        start_date = date(today.year, 1, 1)
        end_date = today
        
        generator = FinancialStatementGenerator(company_id=company_id)
        statement = generator.generate_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            status='draft',
            generated_by=request.user,
        )
        
        serializer = self.get_serializer(statement)
        data = dict(serializer.data)
        # Attach same comprehensive Excel (calculation memory, raw data, JEs, hierarchy, pivot-friendly)
        excel_b64, excel_filename = _build_excel_for_quick_statement(statement)
        if excel_b64 and excel_filename:
            data['excel_base64'] = excel_b64
            data['excel_filename'] = excel_filename
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def detailed_income_statement(self, request, tenant_id=None):
        """
        Generate detailed hierarchical income statement from parent accounts.
        
        POST /api/financial-statements/detailed_income_statement/
        {
            "revenue_parent_ids": [1, 2],
            "cost_parent_ids": [3, 4],
            "expense_parent_ids": [5, 6],
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "currency_id": 1,  // optional
            "balance_type": "posted",  // optional: "posted", "bank_reconciled", or "all"
            "include_zero_balances": false,  // optional: include accounts with zero balance
            "revenue_depth": -1,  // optional: max depth for revenues (-1 = all, 0 = parent only, 1 = parent+1 level)
            "cost_depth": -1,  // optional: max depth for costs
            "expense_depth": -1  // optional: max depth for expenses
        }
        """
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        # Validate required fields
        revenue_parent_ids = request.data.get('revenue_parent_ids', [])
        cost_parent_ids = request.data.get('cost_parent_ids', [])
        expense_parent_ids = request.data.get('expense_parent_ids', [])
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        
        if not revenue_parent_ids and not cost_parent_ids and not expense_parent_ids:
            return Response(
                {'error': 'At least one parent account ID list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'start_date and end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start_date > end_date:
            return Response(
                {'error': 'start_date must be before or equal to end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get optional parameters
        currency_id = request.data.get('currency_id')
        balance_type = request.data.get('balance_type', 'posted')
        include_zero_balances = request.data.get('include_zero_balances', False)
        
        # Get depth parameters (-1 means show all levels)
        revenue_depth = request.data.get('revenue_depth', -1)
        cost_depth = request.data.get('cost_depth', -1)
        expense_depth = request.data.get('expense_depth', -1)
        
        # Validate depth parameters
        try:
            revenue_depth = int(revenue_depth) if revenue_depth is not None else -1
            cost_depth = int(cost_depth) if cost_depth is not None else -1
            expense_depth = int(expense_depth) if expense_depth is not None else -1
        except (ValueError, TypeError):
            return Response(
                {'error': 'Depth parameters must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if balance_type not in ['posted', 'bank_reconciled', 'all']:
            return Response(
                {'error': 'balance_type must be one of: posted, bank_reconciled, all'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Generate income statement
            service = IncomeStatementService(company_id=company_id)
            income_statement = service.generate_income_statement(
                revenue_parent_ids=revenue_parent_ids,
                cost_parent_ids=cost_parent_ids,
                expense_parent_ids=expense_parent_ids,
                start_date=start_date,
                end_date=end_date,
                currency_id=currency_id,
                balance_type=balance_type,
                include_zero_balances=include_zero_balances,
                revenue_depth=revenue_depth,
                cost_depth=cost_depth,
                expense_depth=expense_depth,
            )
            # Build Excel with calculation memory, raw data, and journal entries; attach base64 for Retool download
            # Use full report scope (all descendants) for journal entries so we include entries from
            # all accounts (revenue, costs, expenses), including those filtered out by zero balance or depth
            report_scope_account_ids = _get_report_scope_account_ids(
                company_id, revenue_parent_ids, cost_parent_ids, expense_parent_ids
            )
            currency_id_report = (income_statement.get('currency') or {}).get('id')
            if currency_id_report is not None:
                raw_history = _fetch_raw_balance_history(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                journal_entries = _fetch_journal_entries_for_report(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                account_report_lines = _build_account_report_lines_map(income_statement, 'income_statement')
                account_section_fallback = _build_account_section_fallback_map(
                    company_id,
                    (revenue_parent_ids, 'Revenue'),
                    (cost_parent_ids, 'Cost of Goods Sold'),
                    (expense_parent_ids, 'Expenses'),
                )
                for je in journal_entries:
                    lines = account_report_lines.get(je.get('account_id'), [])
                    if not lines and je.get('account_id') in account_section_fallback:
                        lines = [account_section_fallback[je['account_id']]]
                    je['report_lines'] = '; '.join(lines)
                excel_b64 = build_detailed_statement_excel_base64(
                    report=income_statement,
                    report_type='income_statement',
                    request_params=dict(request.data),
                    raw_history_rows=raw_history,
                    balance_type=balance_type,
                    journal_entry_rows=journal_entries,
                )
                income_statement['excel_base64'] = excel_b64
                income_statement['excel_filename'] = (
                    f"detailed_income_statement_{start_date}_{end_date}.xlsx"
                )
            return Response(income_statement, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log.exception("Error generating detailed income statement")
            return Response(
                {'error': f'Error generating income statement: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def detailed_balance_sheet(self, request, tenant_id=None):
        """
        Generate detailed hierarchical balance sheet from parent accounts.
        
        POST /api/financial-statements/detailed_balance_sheet/
        {
            "asset_parent_ids": [1, 2],
            "liability_parent_ids": [3, 4],
            "equity_parent_ids": [5, 6],
            "as_of_date": "2025-12-31",
            "currency_id": 1,  // optional
            "balance_type": "posted",  // optional: "posted", "bank_reconciled", or "all"
            "include_zero_balances": false,  // optional
            "asset_depth": -1,  // optional: max depth for assets (-1 = all)
            "liability_depth": -1,  // optional: max depth for liabilities
            "equity_depth": -1  // optional: max depth for equity
        }
        """
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        # Validate required fields
        asset_parent_ids = request.data.get('asset_parent_ids', [])
        liability_parent_ids = request.data.get('liability_parent_ids', [])
        equity_parent_ids = request.data.get('equity_parent_ids', [])
        as_of_date_str = request.data.get('as_of_date')
        
        if not asset_parent_ids and not liability_parent_ids and not equity_parent_ids:
            return Response(
                {'error': 'At least one parent account ID list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not as_of_date_str:
            return Response(
                {'error': 'as_of_date is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            as_of_date = date.fromisoformat(as_of_date_str)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get optional parameters
        currency_id = request.data.get('currency_id')
        balance_type = request.data.get('balance_type', 'posted')
        include_zero_balances = request.data.get('include_zero_balances', False)
        
        # Get depth parameters (-1 means show all levels)
        asset_depth = request.data.get('asset_depth', -1)
        liability_depth = request.data.get('liability_depth', -1)
        equity_depth = request.data.get('equity_depth', -1)
        
        # Validate depth parameters
        try:
            asset_depth = int(asset_depth) if asset_depth is not None else -1
            liability_depth = int(liability_depth) if liability_depth is not None else -1
            equity_depth = int(equity_depth) if equity_depth is not None else -1
        except (ValueError, TypeError):
            return Response(
                {'error': 'Depth parameters must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if balance_type not in ['posted', 'bank_reconciled', 'all']:
            return Response(
                {'error': 'balance_type must be one of: posted, bank_reconciled, all'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Generate balance sheet
            service = BalanceSheetService(company_id=company_id)
            balance_sheet = service.generate_balance_sheet(
                asset_parent_ids=asset_parent_ids,
                liability_parent_ids=liability_parent_ids,
                equity_parent_ids=equity_parent_ids,
                as_of_date=as_of_date,
                currency_id=currency_id,
                balance_type=balance_type,
                include_zero_balances=include_zero_balances,
                asset_depth=asset_depth,
                liability_depth=liability_depth,
                equity_depth=equity_depth,
            )
            # Build Excel with calculation memory, raw data, and journal entries; attach base64 for Retool download
            # Use full report scope so we include journal entries from all accounts (assets, liabilities, equity)
            report_scope_account_ids = _get_report_scope_account_ids(
                company_id, asset_parent_ids, liability_parent_ids, equity_parent_ids
            )
            currency_id_report = (balance_sheet.get('currency') or {}).get('id')
            if currency_id_report is not None:
                raw_history = _fetch_raw_balance_history(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    as_of_date=as_of_date,
                )
                journal_entries = _fetch_journal_entries_for_report(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    as_of_date=as_of_date,
                )
                account_report_lines = _build_account_report_lines_map(balance_sheet, 'balance_sheet')
                account_section_fallback = _build_account_section_fallback_map(
                    company_id,
                    (asset_parent_ids, 'Assets'),
                    (liability_parent_ids, 'Liabilities'),
                    (equity_parent_ids, 'Equity'),
                )
                for je in journal_entries:
                    lines = account_report_lines.get(je.get('account_id'), [])
                    if not lines and je.get('account_id') in account_section_fallback:
                        lines = [account_section_fallback[je['account_id']]]
                    je['report_lines'] = '; '.join(lines)
                excel_b64 = build_detailed_statement_excel_base64(
                    report=balance_sheet,
                    report_type='balance_sheet',
                    request_params=dict(request.data),
                    raw_history_rows=raw_history,
                    balance_type=balance_type,
                    journal_entry_rows=journal_entries,
                )
                balance_sheet['excel_base64'] = excel_b64
                balance_sheet['excel_filename'] = f"detailed_balance_sheet_{as_of_date}.xlsx"
            return Response(balance_sheet, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log.exception("Error generating detailed balance sheet")
            return Response(
                {'error': f'Error generating balance sheet: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def detailed_cash_flow(self, request, tenant_id=None):
        """
        Generate detailed hierarchical cash flow statement from parent accounts.
        
        POST /api/financial-statements/detailed_cash_flow/
        {
            "operating_parent_ids": [1, 2],
            "investing_parent_ids": [3, 4],
            "financing_parent_ids": [5, 6],
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "currency_id": 1,  // optional
            "balance_type": "posted",  // optional: "posted", "bank_reconciled", or "all"
            "include_zero_balances": false,  // optional
            "operating_depth": -1,  // optional: max depth for operating (-1 = all)
            "investing_depth": -1,  // optional: max depth for investing
            "financing_depth": -1  // optional: max depth for financing
        }
        """
        # Get company from tenant (set by middleware)
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        # Validate required fields
        operating_parent_ids = request.data.get('operating_parent_ids', [])
        investing_parent_ids = request.data.get('investing_parent_ids', [])
        financing_parent_ids = request.data.get('financing_parent_ids', [])
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        
        if not operating_parent_ids and not investing_parent_ids and not financing_parent_ids:
            return Response(
                {'error': 'At least one parent account ID list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'start_date and end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start_date > end_date:
            return Response(
                {'error': 'start_date must be before or equal to end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get optional parameters
        currency_id = request.data.get('currency_id')
        balance_type = request.data.get('balance_type', 'posted')
        include_zero_balances = request.data.get('include_zero_balances', False)
        
        # Get depth parameters (-1 means show all levels)
        operating_depth = request.data.get('operating_depth', -1)
        investing_depth = request.data.get('investing_depth', -1)
        financing_depth = request.data.get('financing_depth', -1)
        
        # Validate depth parameters
        try:
            operating_depth = int(operating_depth) if operating_depth is not None else -1
            investing_depth = int(investing_depth) if investing_depth is not None else -1
            financing_depth = int(financing_depth) if financing_depth is not None else -1
        except (ValueError, TypeError):
            return Response(
                {'error': 'Depth parameters must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if balance_type not in ['posted', 'bank_reconciled', 'all']:
            return Response(
                {'error': 'balance_type must be one of: posted, bank_reconciled, all'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Generate cash flow
            service = CashFlowService(company_id=company_id)
            cash_flow = service.generate_cash_flow(
                operating_parent_ids=operating_parent_ids,
                investing_parent_ids=investing_parent_ids,
                financing_parent_ids=financing_parent_ids,
                start_date=start_date,
                end_date=end_date,
                currency_id=currency_id,
                balance_type=balance_type,
                include_zero_balances=include_zero_balances,
                operating_depth=operating_depth,
                investing_depth=investing_depth,
                financing_depth=financing_depth,
            )
            # Build Excel with calculation memory, raw data, and journal entries; attach base64 for Retool download
            # Use full report scope so we include journal entries from all accounts (operating, investing, financing)
            report_scope_account_ids = _get_report_scope_account_ids(
                company_id, operating_parent_ids, investing_parent_ids, financing_parent_ids
            )
            currency_id_report = (cash_flow.get('currency') or {}).get('id')
            if currency_id_report is not None:
                raw_history = _fetch_raw_balance_history(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                journal_entries = _fetch_journal_entries_for_report(
                    company_id=company_id,
                    account_ids=report_scope_account_ids,
                    currency_id=currency_id_report,
                    balance_type=balance_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                account_report_lines = _build_account_report_lines_map(cash_flow, 'cash_flow')
                account_section_fallback = _build_account_section_fallback_map(
                    company_id,
                    (operating_parent_ids, 'Operating Activities'),
                    (investing_parent_ids, 'Investing Activities'),
                    (financing_parent_ids, 'Financing Activities'),
                )
                for je in journal_entries:
                    lines = account_report_lines.get(je.get('account_id'), [])
                    if not lines and je.get('account_id') in account_section_fallback:
                        lines = [account_section_fallback[je['account_id']]]
                    je['report_lines'] = '; '.join(lines)
                excel_b64 = build_detailed_statement_excel_base64(
                    report=cash_flow,
                    report_type='cash_flow',
                    request_params=dict(request.data),
                    raw_history_rows=raw_history,
                    balance_type=balance_type,
                    journal_entry_rows=journal_entries,
                )
                cash_flow['excel_base64'] = excel_b64
                cash_flow['excel_filename'] = (
                    f"detailed_cash_flow_{start_date}_{end_date}.xlsx"
                )
            return Response(cash_flow, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log.exception("Error generating detailed cash flow")
            return Response(
                {'error': f'Error generating cash flow: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def preview(self, request, tenant_id=None):
        """
        Preview a financial statement without saving to database.
        
        POST /api/financial-statements/preview/
        {
            "template_id": 1,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "as_of_date": "2025-12-31",  // optional
            "currency_id": 1,  // optional
            "include_pending": false
        }
        """
        serializer = GenerateStatementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Get company from tenant
        company = getattr(request, 'tenant', None)
        if not company or company == 'all':
            return Response(
                {'error': 'Company/tenant not found in request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        company_id = company.id if hasattr(company, 'id') else company
        
        try:
            template = FinancialStatementTemplate.objects.get(
                id=data['template_id'],
                company_id=company_id,
            )
        except FinancialStatementTemplate.DoesNotExist:
            return Response(
                {'error': 'Template not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Generate preview (without saving)
        generator = FinancialStatementGenerator(company_id=company_id)
        preview_data = generator.preview_statement(
            template=template,
            start_date=data['start_date'],
            end_date=data['end_date'],
            as_of_date=data.get('as_of_date'),
            currency_id=data.get('currency_id'),
            include_pending=data.get('include_pending', False),
        )
        
        # Return formatted versions based on format parameter
        format_param = request.query_params.get('format', 'json')
        currency = Currency.objects.get(id=preview_data['currency']['id']) if preview_data.get('currency') else None
        
        if format_param == 'markdown':
            return Response(
                self._format_preview_as_markdown(preview_data, currency),
                content_type='text/markdown',
                status=status.HTTP_200_OK
            )
        elif format_param == 'html':
            return Response(
                self._format_preview_as_html(preview_data, currency),
                content_type='text/html',
                status=status.HTTP_200_OK
            )
        else:
            # Default JSON, but include formatted versions
            preview_data['formatted'] = {
                'markdown': self._format_preview_as_markdown(preview_data, currency),
                'html': self._format_preview_as_html(preview_data, currency),
            }
            return Response(preview_data, status=status.HTTP_200_OK)
    

class FinancialStatementComparisonViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    ViewSet for comparing financial statements.
    """
    
    queryset = FinancialStatementComparison.objects.all()
    serializer_class = FinancialStatementComparisonSerializer
    
    @action(detail=True, methods=['get'])
    def comparison_data(self, request, pk=None, tenant_id=None):
        """Get detailed comparison data between two statements."""
        comparison = self.get_object()
        
        base_lines = {
            line.line_number: line.balance
            for line in comparison.base_statement.lines.all()
        }
        comp_lines = {
            line.line_number: line.balance
            for line in comparison.comparison_statement.lines.all()
        }
        
        # Build comparison
        comparison_data = []
        all_line_numbers = set(base_lines.keys()) | set(comp_lines.keys())
        
        for line_num in sorted(all_line_numbers):
            base_value = base_lines.get(line_num, Decimal('0.00'))
            comp_value = comp_lines.get(line_num, Decimal('0.00'))
            difference = comp_value - base_value
            percent_change = (
                (difference / base_value * 100) if base_value != 0 else Decimal('0.00')
            )
            
            comparison_data.append({
                'line_number': line_num,
                'base_value': str(base_value),
                'comparison_value': str(comp_value),
                'difference': str(difference),
                'percent_change': str(percent_change),
            })
        
        return Response({
            'comparison': comparison_data,
            'base_statement': FinancialStatementSerializer(comparison.base_statement).data,
            'comparison_statement': FinancialStatementSerializer(comparison.comparison_statement).data,
        })


class BalanceHistoryRecalculateView(APIView):
    """
    Endpoint to trigger recalculation of account balances for a period.
    
    POST /api/accounting/balance-history/recalculate/
    
    Always calculates all three balance types (posted, bank_reconciled, all)
    and always overwrites existing records.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        serializer = BalanceHistoryRecalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get company from request (multitenancy)
        tenant = resolve_tenant(request)
        if not tenant or tenant == 'all':
            return Response(
                {'error': 'Company/tenant must be specified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get company_id from tenant
        from multitenancy.models import Company
        try:
            company = Company.objects.get(subdomain=tenant)
            company_id = company.id
        except Company.DoesNotExist:
            return Response(
                {'error': 'Company not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        service = BalanceRecalculationService(company_id=company_id)
        
        result = service.recalculate_balances(
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data.get('end_date'),
            account_ids=serializer.validated_data.get('account_ids'),
            currency_id=serializer.validated_data.get('currency_id'),
            calculated_by=request.user,
        )
        
        return Response(result, status=status.HTTP_200_OK)


class BalanceHistoryViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing account balance history.
    
    GET /api/accounting/balance-history/
    """
    
    queryset = AccountBalanceHistory.objects.all()
    serializer_class = AccountBalanceHistorySerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        # Filter by account
        account_id = self.request.query_params.get('account_id')
        if account_id:
            qs = qs.filter(account_id=account_id)
        
        # Filter by year/month
        year = self.request.query_params.get('year')
        if year:
            qs = qs.filter(year=year)
        
        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(month=month)
        
        # Filter by currency
        currency_id = self.request.query_params.get('currency_id')
        if currency_id:
            qs = qs.filter(currency_id=currency_id)
        
        return qs.order_by('year', 'month', 'account')

