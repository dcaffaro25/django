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
)
from .services.financial_statement_service import FinancialStatementGenerator


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
            if line.is_bold:
                label = f"**{label}**"
            
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
            
            lines.append(f"| {line.line_number} | {label} | {debit} | {credit} | {balance} |")
        
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
        lines.append("        .indent-1 { padding-left: 20px; }")
        lines.append("        .indent-2 { padding-left: 40px; }")
        lines.append("        .indent-3 { padding-left: 60px; }")
        lines.append("        .amount { text-align: right; font-family: 'Courier New', monospace; }")
        lines.append("        .metadata { color: #7f8c8d; font-size: 0.9em; margin-top: 30px; }")
        lines.append("        .negative { color: #e74c3c; }")
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
            
            # Indent class
            indent_class = f"indent-{line.indent_level}" if line.indent_level > 0 else ""
            
            # Format amounts
            debit = self._format_amount(line.debit_amount, statement.currency, html=True)
            credit = self._format_amount(line.credit_amount, statement.currency, html=True)
            balance = self._format_amount(line.balance, statement.currency, html=True)
            
            # Bold label if needed
            label = line.label
            if line.is_bold:
                label = f"<strong>{label}</strong>"
            
            lines.append(f"            <tr class='{row_class}'>")
            lines.append(f"                <td>{line.line_number}</td>")
            lines.append(f"                <td class='{indent_class}'>{label}</td>")
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

