"""
Financial Statement Models

This module defines models for generating and storing financial statements
including Balance Sheet, Income Statement (P&L), Cash Flow Statement, and others.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from multitenancy.models import TenantAwareBaseModel
from .models import Account, Currency


class FinancialStatementTemplate(TenantAwareBaseModel):
    """
    Template defining the structure of a financial statement.
    Each template defines which accounts map to which line items.
    """
    
    REPORT_TYPE_CHOICES = [
        ('balance_sheet', 'Balance Sheet'),
        ('income_statement', 'Income Statement (P&L)'),
        ('cash_flow', 'Cash Flow Statement'),
        ('trial_balance', 'Trial Balance'),
        ('general_ledger', 'General Ledger'),
        ('custom', 'Custom Report'),
    ]
    
    name = models.CharField(max_length=200, help_text="Template name (e.g., 'Standard Balance Sheet')")
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Default template for this report type"
    )
    
    # Formatting options
    show_zero_balances = models.BooleanField(default=False)
    show_account_codes = models.BooleanField(default=True)
    show_percentages = models.BooleanField(default=False)
    group_by_cost_center = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('company', 'name')
        indexes = [
            models.Index(fields=['company', 'report_type', 'is_active']),
            models.Index(fields=['company', 'is_default']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class FinancialStatementLineTemplate(models.Model):
    """
    Defines a line item in a financial statement template.
    Maps accounts or account groups to specific line items.
    """
    
    LINE_TYPE_CHOICES = [
        ('header', 'Header/Section'),
        ('account', 'Account'),
        ('subtotal', 'Subtotal'),
        ('total', 'Total'),
        ('spacer', 'Spacer'),
    ]
    
    # NEW: Calculation method enum (replaces calculation_type)
    CALCULATION_METHOD_CHOICES = [
        # Stock measures (point-in-time)
        ('ending_balance', 'Ending Balance'),           # Balance as of end_date (Balance Sheet)
        ('opening_balance', 'Opening Balance'),         # Balance as of start_date - 1 day
        # Flow measures (period activity)
        ('net_movement', 'Net Movement'),               # Σ(debit - credit) in period (Income Statement)
        ('debit_total', 'Debit Total'),                 # Σ debit in period
        ('credit_total', 'Credit Total'),               # Σ credit in period
        # Delta measures (change between points)
        ('change_in_balance', 'Change in Balance'),     # ending - opening (Cash Flow)
        # Aggregation
        ('rollup_children', 'Rollup Children'),         # Sum of child template lines (no GL query)
        ('formula', 'Formula'),                         # Reference other lines
        ('manual_input', 'Manual Input / Constant'),    # User-provided value
    ]
    
    # NEW: Sign policy enum
    SIGN_POLICY_CHOICES = [
        ('natural', 'Natural'),       # Use account.account_direction as-is
        ('invert', 'Invert'),         # Multiply by -1 (for liabilities shown positive)
        ('absolute', 'Absolute'),     # abs(value)
    ]
    
    template = models.ForeignKey(
        FinancialStatementTemplate,
        related_name='line_templates',
        on_delete=models.CASCADE
    )
    
    # Line identification
    line_number = models.IntegerField(help_text="Order of this line in the statement")
    label = models.CharField(max_length=200, help_text="Line item label")
    line_type = models.CharField(max_length=20, choices=LINE_TYPE_CHOICES, default='account')
    
    # Account mapping
    # Option 1: Specific account
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Specific account for this line"
    )
    
    # Option 2: Account filter (for multiple accounts)
    account_code_prefix = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Match accounts with code starting with this prefix"
    )
    account_path_contains = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Match accounts with path containing this string"
    )
    
    # Option 3: Account IDs (for custom groupings)
    account_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of account IDs to include in this line"
    )
    
    # NEW: Selector control - whether to include MPTT descendants
    include_descendants = models.BooleanField(
        default=True,
        help_text="If True, include all MPTT descendants of selected account(s)"
    )
    
    # DEPRECATED: Old calculation type (kept for backward compatibility during migration)
    calculation_type = models.CharField(
        max_length=20,
        choices=[
            ('sum', 'Sum'),
            ('difference', 'Difference (Debit - Credit)'),
            ('balance', 'Balance (with account_direction)'),
            ('formula', 'Formula'),
        ],
        default='balance',
        help_text="DEPRECATED: Use calculation_method instead"
    )
    
    # NEW: Calculation method (replaces calculation_type)
    calculation_method = models.CharField(
        max_length=30,
        choices=CALCULATION_METHOD_CHOICES,
        null=True,
        blank=True,
        help_text="How to calculate the line value"
    )
    
    # NEW: Sign policy for presentation
    sign_policy = models.CharField(
        max_length=20,
        choices=SIGN_POLICY_CHOICES,
        default='natural',
        help_text="How to present the sign of the calculated value"
    )
    
    # Formula for calculated lines (e.g., "line_1 + line_2 - line_3")
    formula = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Formula referencing other line numbers (e.g., 'L1 + L2 - L3')"
    )
    
    # NEW: Manual value for manual_input calculation method
    manual_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Value for manual_input calculation method"
    )
    
    # Formatting
    indent_level = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    is_bold = models.BooleanField(default=False)
    show_negative_in_parentheses = models.BooleanField(default=False)
    
    # NEW: Scale and decimal formatting
    SCALE_CHOICES = [
        ('none', 'None'),
        ('K', 'Thousands'),
        ('M', 'Millions'),
        ('B', 'Billions'),
    ]
    scale = models.CharField(
        max_length=10,
        choices=SCALE_CHOICES,
        default='none',
        help_text="Scale factor for display"
    )
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        help_text="Number of decimal places for display"
    )
    
    # Parent line for grouping
    parent_line = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_lines',
        help_text="Parent line for hierarchical grouping"
    )
    
    class Meta:
        ordering = ['line_number']
        unique_together = ('template', 'line_number')
    
    def __str__(self):
        return f"{self.template.name} - Line {self.line_number}: {self.label}"
    
    def get_effective_calculation_method(self):
        """
        Get the effective calculation method, falling back to legacy calculation_type mapping.
        
        Returns the calculation_method if set, otherwise maps calculation_type to new method.
        """
        if self.calculation_method:
            return self.calculation_method
        
        # Legacy mapping from calculation_type
        mapping = {
            'sum': 'net_movement',
            'difference': 'net_movement',
            'balance': 'ending_balance',
            'formula': 'formula',
        }
        return mapping.get(self.calculation_type, 'ending_balance')


class FinancialStatement(TenantAwareBaseModel):
    """
    A generated financial statement instance.
    Stores the actual report data for a specific period.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('final', 'Final'),
        ('archived', 'Archived'),
    ]
    
    template = models.ForeignKey(
        FinancialStatementTemplate,
        on_delete=models.CASCADE,
        related_name='statements'
    )
    
    REPORT_TYPE_CHOICES = [
        ('balance_sheet', 'Balance Sheet'),
        ('income_statement', 'Income Statement (P&L)'),
        ('cash_flow', 'Cash Flow Statement'),
        ('trial_balance', 'Trial Balance'),
        ('general_ledger', 'General Ledger'),
        ('custom', 'Custom Report'),
    ]
    
    report_type = models.CharField(
        max_length=50,
        choices=REPORT_TYPE_CHOICES
    )  # Denormalized for filtering
    name = models.CharField(max_length=200)  # Denormalized template name
    
    # Period
    start_date = models.DateField()
    end_date = models.DateField()
    as_of_date = models.DateField(
        null=True,
        blank=True,
        help_text="For balance sheet: the specific date. For P&L: same as end_date."
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Currency
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    
    # Metadata
    generated_by = models.ForeignKey(
        'multitenancy.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    # Totals (denormalized for quick access)
    total_assets = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    total_liabilities = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    total_equity = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    net_income = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['company', 'report_type', 'end_date']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['template', 'end_date']),
        ]
        ordering = ['-end_date', '-generated_at']
    
    def __str__(self):
        return f"{self.name} - {self.start_date} to {self.end_date} ({self.status})"


class FinancialStatementLine(models.Model):
    """
    A single line item in a generated financial statement.
    Contains the calculated value for that line.
    """
    
    statement = models.ForeignKey(
        FinancialStatement,
        related_name='lines',
        on_delete=models.CASCADE
    )
    
    line_template = models.ForeignKey(
        FinancialStatementLineTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Reference to template line (may be null if template changed)"
    )
    
    # Line identification
    line_number = models.IntegerField()
    label = models.CharField(max_length=200)
    line_type = models.CharField(max_length=20)
    
    # Values
    debit_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00')
    )
    credit_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00')
    )
    balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Calculated balance for this line"
    )
    
    # Formatting
    indent_level = models.IntegerField(default=0)
    is_bold = models.BooleanField(default=False)
    
    # Metadata
    account_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Account IDs that contributed to this line"
    )
    
    class Meta:
        ordering = ['line_number']
        indexes = [
            models.Index(fields=['statement', 'line_number']),
        ]
    
    def __str__(self):
        return f"{self.statement.name} - Line {self.line_number}: {self.label} = {self.balance}"


class FinancialStatementComparison(TenantAwareBaseModel):
    """
    Compares two financial statements (e.g., current period vs previous period).
    """
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Statements being compared
    base_statement = models.ForeignKey(
        FinancialStatement,
        related_name='comparisons_as_base',
        on_delete=models.CASCADE
    )
    comparison_statement = models.ForeignKey(
        FinancialStatement,
        related_name='comparisons_as_comparison',
        on_delete=models.CASCADE
    )
    
    # Comparison type
    comparison_type = models.CharField(
        max_length=50,
        choices=[
            ('period_over_period', 'Period over Period'),
            ('year_over_year', 'Year over Year'),
            ('budget_vs_actual', 'Budget vs Actual'),
            ('custom', 'Custom'),
        ],
        default='period_over_period'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['company', 'base_statement']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.base_statement} vs {self.comparison_statement}"

