"""
Excel export for detailed financial statements (income statement, balance sheet, cash flow).

Produces a comprehensive workbook with:
- Report summary and detail (flattened hierarchy)
- Calculation memory (parameters, formulas, section breakdown)
- Raw data (AccountBalanceHistory rows used in calculations)
"""

import io
import base64
from datetime import date
from decimal import Decimal
from typing import Dict, List, Any, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter


def _flatten_report_tree(nodes: List[Dict], depth: int = 0) -> List[Dict]:
    """Flatten hierarchical report nodes into rows with depth, code, name, path, balance."""
    rows = []
    for node in nodes or []:
        rows.append({
            'depth': depth,
            'id': node.get('id'),
            'account_code': node.get('account_code') or '',
            'name': node.get('name') or '',
            'path': node.get('path') or '',
            'balance': node.get('balance'),
            'is_leaf': node.get('is_leaf', False),
        })
        if node.get('children'):
            rows.extend(_flatten_report_tree(node['children'], depth + 1))
    return rows


def _collect_calculation_memory_income(report: Dict, request_params: Dict, balance_type: str) -> List[Dict]:
    """Build calculation memory rows for income statement."""
    rows = []
    totals = report.get('totals') or {}
    # Formulas
    rows.append({'section': 'Formulas', 'description': 'Total Revenue = sum of all Revenue section line items', 'value': totals.get('total_revenue')})
    rows.append({'section': 'Formulas', 'description': 'Total Costs (COGS) = sum of all Cost of Goods Sold section line items', 'value': totals.get('total_costs')})
    rows.append({'section': 'Formulas', 'description': 'Gross Profit = Total Revenue - Total Costs', 'value': totals.get('gross_profit')})
    rows.append({'section': 'Formulas', 'description': 'Total Expenses = sum of all Expenses section line items', 'value': totals.get('total_expenses')})
    rows.append({'section': 'Formulas', 'description': 'Net Income = Gross Profit - Total Expenses', 'value': totals.get('net_income')})
    rows.append({'section': 'Parameters', 'description': 'Balance type used for movements', 'value': balance_type})
    rows.append({'section': 'Parameters', 'description': 'Period', 'value': f"{report.get('start_date')} to {report.get('end_date')}"})
    rows.append({'section': 'Parameters', 'description': 'Currency', 'value': (report.get('currency') or {}).get('code') or report.get('currency')})
    return rows


def _collect_calculation_memory_balance_sheet(report: Dict, request_params: Dict, balance_type: str) -> List[Dict]:
    """Build calculation memory rows for balance sheet."""
    rows = []
    totals = report.get('totals') or {}
    rows.append({'section': 'Formulas', 'description': 'Total Assets = sum of all Assets section line items', 'value': totals.get('total_assets')})
    rows.append({'section': 'Formulas', 'description': 'Total Liabilities = sum of all Liabilities section line items', 'value': totals.get('total_liabilities')})
    rows.append({'section': 'Formulas', 'description': 'Total Equity = sum of all Equity section line items', 'value': totals.get('total_equity')})
    rows.append({'section': 'Formulas', 'description': 'Total Liabilities and Equity = Total Liabilities + Total Equity', 'value': totals.get('total_liabilities_and_equity')})
    rows.append({'section': 'Formulas', 'description': 'Check: Total Assets = Total Liabilities and Equity', 'value': 'OK' if abs((totals.get('total_assets') or 0) - (totals.get('total_liabilities_and_equity') or 0)) < 0.01 else 'Mismatch'})
    rows.append({'section': 'Parameters', 'description': 'Balance type used', 'value': balance_type})
    rows.append({'section': 'Parameters', 'description': 'As of date', 'value': report.get('as_of_date')})
    rows.append({'section': 'Parameters', 'description': 'Currency', 'value': (report.get('currency') or {}).get('code') or report.get('currency')})
    return rows


def _collect_calculation_memory_cash_flow(report: Dict, request_params: Dict, balance_type: str) -> List[Dict]:
    """Build calculation memory rows for cash flow."""
    rows = []
    totals = report.get('totals') or {}
    rows.append({'section': 'Formulas', 'description': 'Total Operating = sum of Operating Activities section', 'value': totals.get('total_operating')})
    rows.append({'section': 'Formulas', 'description': 'Total Investing = sum of Investing Activities section', 'value': totals.get('total_investing')})
    rows.append({'section': 'Formulas', 'description': 'Total Financing = sum of Financing Activities section', 'value': totals.get('total_financing')})
    rows.append({'section': 'Formulas', 'description': 'Net Cash Flow = Total Operating + Total Investing + Total Financing', 'value': totals.get('net_cash_flow')})
    rows.append({'section': 'Parameters', 'description': 'Balance type used', 'value': balance_type})
    rows.append({'section': 'Parameters', 'description': 'Period', 'value': f"{report.get('start_date')} to {report.get('end_date')}"})
    rows.append({'section': 'Parameters', 'description': 'Currency', 'value': (report.get('currency') or {}).get('code') if report.get('currency') else report.get('currency')})
    return rows


def _style_header(ws, row_num: int, num_cols: int):
    """Apply header style to a row."""
    thin = Side(style='thin')
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='DDDDDD', end_color='DDDDDD', fill_type='solid')
        cell.border = Border(top=thin, left=thin, right=thin, bottom=thin)
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)


def _section_headers_income() -> List[tuple]:
    """Section name and key for income statement."""
    return [
        ('Revenue', 'revenues'),
        ('Cost of Goods Sold', 'costs'),
        ('Expenses', 'expenses'),
    ]


def _section_headers_balance_sheet() -> List[tuple]:
    return [
        ('Assets', 'assets'),
        ('Liabilities', 'liabilities'),
        ('Equity', 'equity'),
    ]


def _section_headers_cash_flow() -> List[tuple]:
    return [
        ('Operating Activities', 'operating'),
        ('Investing Activities', 'investing'),
        ('Financing Activities', 'financing'),
    ]


def build_detailed_statement_excel(
    report: Dict[str, Any],
    report_type: str,
    request_params: Dict[str, Any],
    raw_history_rows: List[Dict[str, Any]],
    balance_type: str = 'posted',
) -> bytes:
    """
    Build an Excel workbook for a detailed financial statement.

    report_type: 'income_statement' | 'balance_sheet' | 'cash_flow'
    request_params: the POST body (parent_ids, dates, balance_type, etc.)
    raw_history_rows: list of dicts with keys account_id, account_code, account_name, year, month,
                     posted_total_debit, posted_total_credit, bank_reconciled_*, all_*,
                     balance_type_used, net_movement_used (or ending_balance_used for balance sheet)
    """
    wb = Workbook()
    wb.remove(wb.active)

    # ----- Sheet 1: Report Summary -----
    ws_summary = wb.create_sheet('Report Summary', 0)
    if report_type == 'income_statement':
        section_headers = _section_headers_income()
        total_keys = ['total_revenue', 'total_costs', 'gross_profit', 'total_expenses', 'net_income']
    elif report_type == 'balance_sheet':
        section_headers = _section_headers_balance_sheet()
        total_keys = ['total_assets', 'total_liabilities', 'total_equity', 'total_liabilities_and_equity']
    else:
        section_headers = _section_headers_cash_flow()
        total_keys = ['total_operating', 'total_investing', 'total_financing', 'net_cash_flow']

    totals = report.get('totals') or {}
    row = 1
    ws_summary.cell(row=row, column=1, value='Section')
    ws_summary.cell(row=row, column=2, value='Total')
    _style_header(ws_summary, row, 2)
    row += 1
    for label, key in section_headers:
        ws_summary.cell(row=row, column=1, value=label)
        section_nodes = report.get(key) or []
        section_total = _sum_tree(section_nodes)
        ws_summary.cell(row=row, column=2, value=float(section_total) if section_total is not None else None)
        row += 1
    ws_summary.cell(row=row, column=1, value='Totals')
    _style_header(ws_summary, row, 2)
    row += 1
    for k in total_keys:
        ws_summary.cell(row=row, column=1, value=k.replace('_', ' ').title())
        ws_summary.cell(row=row, column=2, value=totals.get(k))
        row += 1
    ws_summary.column_dimensions['A'].width = 35
    ws_summary.column_dimensions['B'].width = 18

    # ----- Sheet 2: Report Detail (flattened hierarchy) -----
    ws_detail = wb.create_sheet('Report Detail', 1)
    ws_detail.cell(row=1, column=1, value='Section')
    ws_detail.cell(row=1, column=2, value='Depth')
    ws_detail.cell(row=1, column=3, value='Account ID')
    ws_detail.cell(row=1, column=4, value='Account Code')
    ws_detail.cell(row=1, column=5, value='Name')
    ws_detail.cell(row=1, column=6, value='Path')
    ws_detail.cell(row=1, column=7, value='Balance')
    ws_detail.cell(row=1, column=8, value='Is Leaf')
    _style_header(ws_detail, 1, 8)
    row = 2
    for section_label, key in section_headers:
        nodes = report.get(key) or []
        flat = _flatten_report_tree(nodes)
        for r in flat:
            ws_detail.cell(row=row, column=1, value=section_label)
            ws_detail.cell(row=row, column=2, value=r['depth'])
            ws_detail.cell(row=row, column=3, value=r.get('id'))
            ws_detail.cell(row=row, column=4, value=r.get('account_code'))
            ws_detail.cell(row=row, column=5, value=r.get('name'))
            ws_detail.cell(row=row, column=6, value=r.get('path'))
            ws_detail.cell(row=row, column=7, value=r.get('balance'))
            ws_detail.cell(row=row, column=8, value=r.get('is_leaf'))
            row += 1
    for c in range(1, 9):
        ws_detail.column_dimensions[get_column_letter(c)].width = 18 if c in (5, 6) else 14

    # ----- Sheet 3: Calculation Memory -----
    ws_calc = wb.create_sheet('Calculation Memory', 2)
    if report_type == 'income_statement':
        calc_rows = _collect_calculation_memory_income(report, request_params, balance_type)
    elif report_type == 'balance_sheet':
        calc_rows = _collect_calculation_memory_balance_sheet(report, request_params, balance_type)
    else:
        calc_rows = _collect_calculation_memory_cash_flow(report, request_params, balance_type)
    ws_calc.cell(row=1, column=1, value='Section')
    ws_calc.cell(row=1, column=2, value='Description')
    ws_calc.cell(row=1, column=3, value='Value')
    _style_header(ws_calc, 1, 3)
    for i, r in enumerate(calc_rows, start=2):
        ws_calc.cell(row=i, column=1, value=r.get('section'))
        ws_calc.cell(row=i, column=2, value=r.get('description'))
        val = r.get('value')
        if isinstance(val, (Decimal, float)):
            ws_calc.cell(row=i, column=3, value=float(val))
        else:
            ws_calc.cell(row=i, column=3, value=str(val) if val is not None else '')
    ws_calc.column_dimensions['A'].width = 18
    ws_calc.column_dimensions['B'].width = 55
    ws_calc.column_dimensions['C'].width = 22

    # ----- Sheet 4: Request Parameters -----
    ws_params = wb.create_sheet('Request Parameters', 3)
    ws_params.cell(row=1, column=1, value='Parameter')
    ws_params.cell(row=1, column=2, value='Value')
    _style_header(ws_params, 1, 2)
    row = 2
    for k, v in sorted(request_params.items()):
        ws_params.cell(row=row, column=1, value=k)
        if isinstance(v, (list, tuple)):
            ws_params.cell(row=row, column=2, value=', '.join(str(x) for x in v))
        else:
            ws_params.cell(row=row, column=2, value=str(v) if v is not None else '')
        row += 1
    ws_params.column_dimensions['A'].width = 28
    ws_params.column_dimensions['B'].width = 50

    # ----- Sheet 5: Raw Data - Balance History -----
    ws_raw = wb.create_sheet('Raw Data - Balance History', 4)
    if raw_history_rows:
        headers = list(raw_history_rows[0].keys())
        for col, h in enumerate(headers, 1):
            ws_raw.cell(row=1, column=col, value=h)
        _style_header(ws_raw, 1, len(headers))
        for r_idx, row_data in enumerate(raw_history_rows, start=2):
            for c_idx, h in enumerate(headers, 1):
                val = row_data.get(h)
                if isinstance(val, Decimal):
                    val = float(val)
                ws_raw.cell(row=r_idx, column=c_idx, value=val)
        for c in range(1, len(headers) + 1):
            ws_raw.column_dimensions[get_column_letter(c)].width = 14
    else:
        ws_raw.cell(row=1, column=1, value='No raw balance history rows (leaf accounts may have no history in period).')
    ws_raw.column_dimensions['A'].width = 50

    # ----- Sheet 6: Leaf Account Summary (per-account totals from raw data) -----
    ws_leaf = wb.create_sheet('Leaf Account Summary', 5)
    if raw_history_rows:
        def _dec(x):
            return Decimal(str(x)) if x is not None else Decimal('0')
        # Aggregate by account: sum debit, credit, net_movement (use balance_type columns or _used fields)
        by_account: Dict[Any, Dict] = {}
        for r in raw_history_rows:
            acc_id = r.get('account_id')
            key = (acc_id, r.get('account_code'), r.get('account_name'))
            if key not in by_account:
                by_account[key] = {
                    'account_id': acc_id,
                    'account_code': r.get('account_code'),
                    'account_name': r.get('account_name'),
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0'),
                    'net_movement': Decimal('0'),
                    'months_count': 0,
                }
            debit = r.get('debit_used') or r.get('posted_total_debit')
            credit = r.get('credit_used') or r.get('posted_total_credit')
            net = r.get('net_movement_used') or r.get('net_movement')
            by_account[key]['total_debit'] += _dec(debit)
            by_account[key]['total_credit'] += _dec(credit)
            by_account[key]['net_movement'] += _dec(net)
            by_account[key]['months_count'] += 1
        leaf_headers = ['Account ID', 'Account Code', 'Account Name', 'Total Debit', 'Total Credit', 'Net Movement', 'Months']
        for col, h in enumerate(leaf_headers, 1):
            ws_leaf.cell(row=1, column=col, value=h)
        _style_header(ws_leaf, 1, len(leaf_headers))
        for r_idx, (_, data) in enumerate(sorted(by_account.items(), key=lambda x: (str(x[1].get('account_code') or ''))), start=2):
            ws_leaf.cell(row=r_idx, column=1, value=data.get('account_id'))
            ws_leaf.cell(row=r_idx, column=2, value=data.get('account_code'))
            ws_leaf.cell(row=r_idx, column=3, value=data.get('account_name'))
            ws_leaf.cell(row=r_idx, column=4, value=float(data['total_debit']))
            ws_leaf.cell(row=r_idx, column=5, value=float(data['total_credit']))
            ws_leaf.cell(row=r_idx, column=6, value=float(data['net_movement']))
            ws_leaf.cell(row=r_idx, column=7, value=data['months_count'])
        for c in range(1, 8):
            ws_leaf.column_dimensions[get_column_letter(c)].width = 16
    else:
        ws_leaf.cell(row=1, column=1, value='No leaf account data (no raw history in period).')

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _sum_tree(nodes: List[Dict]) -> Optional[float]:
    """Recursively sum balance of tree nodes."""
    total = None
    for node in nodes or []:
        b = node.get('balance')
        if b is not None:
            total = (total or 0) + float(b)
        if node.get('children'):
            child_sum = _sum_tree(node['children'])
            if child_sum is not None:
                total = (total or 0) + child_sum
    return total


def build_detailed_statement_excel_base64(
    report: Dict[str, Any],
    report_type: str,
    request_params: Dict[str, Any],
    raw_history_rows: List[Dict[str, Any]],
    balance_type: str = 'posted',
) -> str:
    """Same as build_detailed_statement_excel but returns base64-encoded string."""
    data = build_detailed_statement_excel(
        report=report,
        report_type=report_type,
        request_params=request_params,
        raw_history_rows=raw_history_rows,
        balance_type=balance_type,
    )
    return base64.b64encode(data).decode('ascii')
