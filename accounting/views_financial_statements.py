"""
Views for Financial Statement generation and management.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from multitenancy.mixins import ScopedQuerysetMixin
from multitenancy.utils import resolve_tenant
from .models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatement,
    FinancialStatementComparison,
)
from .serializers_financial_statements import (
    FinancialStatementTemplateSerializer,
    FinancialStatementSerializer,
    FinancialStatementComparisonSerializer,
    GenerateStatementRequestSerializer,
    TimeSeriesRequestSerializer,
    ComparisonRequestSerializer,
)
from .services.financial_statement_service import FinancialStatementGenerator
from .models import Currency, Account


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
            "notes": "..."  // optional
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
        
        # Generate statement
        generator = FinancialStatementGenerator(company_id=company_id)
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
        
        # Table header
        lines.append("| Line | Label | Debit | Credit | Balance |")
        lines.append("|------|-------|-------|--------|---------|")
        
        # Lines
        for line in statement.lines.all().order_by('line_number'):
            indent = "  " * line.indent_level
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
        lines.append("        th { background-color: #3498db; color: white; padding: 12px; text-align: left; }")
        lines.append("        td { padding: 10px; border-bottom: 1px solid #ddd; }")
        lines.append("        tr:hover { background-color: #f5f5f5; }")
        lines.append("        .header-row { background-color: #ecf0f1; font-weight: bold; }")
        lines.append("        .total-row { background-color: #e8f5e9; font-weight: bold; }")
        lines.append("        .amount { text-align: right; font-family: 'Courier New', monospace; }")
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
            indent = "  " * line_data.get('indent_level', 0)
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
            
            indent = "  " * line_info.get('indent_level', 0)
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
            lines.append("        .amount { text-align: right; font-family: 'Courier New', monospace; }")
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
            lines.append("        .amount { text-align: right; font-family: 'Courier New', monospace; }")
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
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def time_series(self, request, tenant_id=None):
        """
        Generate time series data for financial statement lines.
        
        POST /api/financial-statements/time_series/
        {
            "template_id": 1,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "dimension": "month",  // day, week, month, quarter, semester, year
            "line_numbers": [1, 2, 3],  // optional, specific lines
            "include_pending": false
        }
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
            )
        else:
            series_data = generator.generate_time_series(
                template=template,
                start_date=data['start_date'],
                end_date=data['end_date'],
                dimension=dimension,
                line_numbers=data.get('line_numbers'),
                include_pending=data.get('include_pending', False),
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
        return Response(serializer.data)
    
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

