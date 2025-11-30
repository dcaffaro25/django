"""
Serializers for Financial Statement models.
"""

from rest_framework import serializers
from .models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
    FinancialStatement,
    FinancialStatementLine,
    FinancialStatementComparison,
)


class FinancialStatementLineTemplateSerializer(serializers.ModelSerializer):
    """Serializer for financial statement line templates."""
    
    class Meta:
        model = FinancialStatementLineTemplate
        fields = [
            'id',
            'line_number',
            'label',
            'line_type',
            'account',
            'account_code_prefix',
            'account_path_contains',
            'account_ids',
            'calculation_type',
            'formula',
            'indent_level',
            'is_bold',
            'show_negative_in_parentheses',
            'parent_line',
        ]
        read_only_fields = ['id']


class FinancialStatementTemplateSerializer(serializers.ModelSerializer):
    """Serializer for financial statement templates."""
    
    line_templates = FinancialStatementLineTemplateSerializer(many=True, read_only=True)
    
    class Meta:
        model = FinancialStatementTemplate
        fields = [
            'id',
            'name',
            'report_type',
            'description',
            'is_active',
            'is_default',
            'show_zero_balances',
            'show_account_codes',
            'show_percentages',
            'group_by_cost_center',
            'line_templates',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FinancialStatementLineSerializer(serializers.ModelSerializer):
    """Serializer for financial statement lines."""
    
    class Meta:
        model = FinancialStatementLine
        fields = [
            'id',
            'line_number',
            'label',
            'line_type',
            'debit_amount',
            'credit_amount',
            'balance',
            'indent_level',
            'is_bold',
            'account_ids',
        ]
        read_only_fields = ['id']


class FinancialStatementSerializer(serializers.ModelSerializer):
    """Serializer for financial statements."""
    
    lines = FinancialStatementLineSerializer(many=True, read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    generated_by_name = serializers.CharField(
        source='generated_by.get_full_name',
        read_only=True
    )
    
    class Meta:
        model = FinancialStatement
        fields = [
            'id',
            'template',
            'template_name',
            'report_type',
            'name',
            'start_date',
            'end_date',
            'as_of_date',
            'status',
            'currency',
            'currency_code',
            'generated_by',
            'generated_by_name',
            'generated_at',
            'notes',
            'total_assets',
            'total_liabilities',
            'total_equity',
            'net_income',
            'lines',
        ]
        read_only_fields = [
            'id',
            'generated_at',
            'total_assets',
            'total_liabilities',
            'total_equity',
            'net_income',
        ]


class FinancialStatementComparisonSerializer(serializers.ModelSerializer):
    """Serializer for financial statement comparisons."""
    
    base_statement_name = serializers.CharField(
        source='base_statement.name',
        read_only=True
    )
    comparison_statement_name = serializers.CharField(
        source='comparison_statement.name',
        read_only=True
    )
    
    class Meta:
        model = FinancialStatementComparison
        fields = [
            'id',
            'name',
            'description',
            'base_statement',
            'base_statement_name',
            'comparison_statement',
            'comparison_statement_name',
            'comparison_type',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class GenerateStatementRequestSerializer(serializers.Serializer):
    """Serializer for statement generation requests."""
    
    template_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    as_of_date = serializers.DateField(required=False, allow_null=True)
    currency_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=['draft', 'final', 'archived'],
        default='draft'
    )
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    include_pending = serializers.BooleanField(required=False, default=False)


class TimeSeriesRequestSerializer(serializers.Serializer):
    """Serializer for time series requests."""
    
    template_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    dimension = serializers.ChoiceField(
        choices=['day', 'week', 'month', 'quarter', 'semester', 'year'],
        default='month'
    )
    line_numbers = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    include_pending = serializers.BooleanField(required=False, default=False)


class ComparisonRequestSerializer(serializers.Serializer):
    """Serializer for comparison requests."""
    
    template_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    comparison_types = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'previous_period',
            'previous_year',
            'ytd_previous_year',
            'last_12_months',
            'same_period_last_year',
        ]),
        required=False,
        default=['previous_period', 'previous_year']
    )
    include_pending = serializers.BooleanField(required=False, default=False)

