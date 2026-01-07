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
    dimension = serializers.CharField(required=False, default='month')
    # Support both single dimension string or list of dimensions
    dimensions = serializers.ListField(
        child=serializers.ChoiceField(choices=['day', 'week', 'month', 'quarter', 'semester', 'year']),
        required=False,
        allow_null=True
    )
    line_numbers = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    include_pending = serializers.BooleanField(required=False, default=False)
    
    def validate(self, data):
        """Handle dimension vs dimensions."""
        if 'dimensions' in data and data['dimensions']:
            # If dimensions list is provided, use it
            data['dimension'] = data['dimensions']
        elif 'dimension' in data and isinstance(data['dimension'], str):
            # Single dimension string
            if data['dimension'] not in ['day', 'week', 'month', 'quarter', 'semester', 'year']:
                raise serializers.ValidationError({
                    'dimension': 'Invalid dimension. Must be one of: day, week, month, quarter, semester, year'
                })
        return data


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
    dimension = serializers.ChoiceField(
        choices=['day', 'week', 'month', 'quarter', 'semester', 'year'],
        required=False,
        allow_null=True,
        help_text="Time dimension to break down current period. If provided, compares each sub-period."
    )
    include_pending = serializers.BooleanField(required=False, default=False)


class TemplateSuggestionRequestSerializer(serializers.Serializer):
    """
    Serializer for AI-powered template suggestion requests.
    
    Used by POST /api/financial-statements/suggest_templates/
    """
    
    user_preferences = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "Free-text preferences for template customization. "
            "Examples: 'I want revenue broken down to 3 levels', "
            "'Simplify the template for external investors', "
            "'Group small accounts into Other buckets'"
        )
    )
    apply_changes = serializers.BooleanField(
        required=False,
        default=True,
        help_text="If true, apply changes to database. If false, simulate and return what would be done."
    )
    ai_provider = serializers.ChoiceField(
        choices=['openai', 'anthropic'],
        required=False,
        default='openai',
        help_text="AI provider to use for generating suggestions."
    )
    ai_model = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Specific AI model to use. Defaults vary by provider."
    )


class TemplateSuggestionResponseSerializer(serializers.Serializer):
    """Serializer for template suggestion response."""
    
    status = serializers.CharField()
    applied_changes = serializers.BooleanField()
    templates_created = serializers.IntegerField(required=False, default=0)
    templates_updated = serializers.IntegerField(required=False, default=0)
    lines_created = serializers.IntegerField(required=False, default=0)
    lines_updated = serializers.IntegerField(required=False, default=0)
    validation_errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    validation_warnings = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    error = serializers.CharField(required=False, allow_null=True)
    error_type = serializers.CharField(required=False, allow_null=True)
    ai_raw_response = serializers.JSONField(required=False, allow_null=True)
