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
    def set_default(self, request, pk=None):
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
    def duplicate(self, request, pk=None):
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
    def generate(self, request):
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
        template = FinancialStatementTemplate.objects.get(
            id=data['template_id'],
            company_id=request.user.company_id,
        )
        
        # Get company ID
        company_id = request.user.company_id
        
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
        )
        
        response_serializer = self.get_serializer(statement)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def finalize(self, request, pk=None):
        """Mark a statement as final."""
        statement = self.get_object()
        statement.status = 'final'
        statement.save()
        return Response({'status': 'finalized'})
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a statement."""
        statement = self.get_object()
        statement.status = 'archived'
        statement.save()
        return Response({'status': 'archived'})
    
    @action(detail=True, methods=['get'])
    def export_pdf(self, request, pk=None):
        """Export statement as PDF (placeholder - implement PDF generation)."""
        statement = self.get_object()
        # TODO: Implement PDF generation
        return Response({'message': 'PDF export not yet implemented'})
    
    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None):
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
    def quick_balance_sheet(self, request):
        """Quick balance sheet for current period."""
        company_id = request.user.company_id
        
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
    def quick_income_statement(self, request):
        """Quick income statement for current period."""
        company_id = request.user.company_id
        
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
    def comparison_data(self, request, pk=None):
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

