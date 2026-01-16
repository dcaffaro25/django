# Account Balance History Table - Implementation Plan

## Overview

This document outlines the design and implementation plan for an Account Balance History table that will store pre-calculated monthly account balances. This will improve performance for financial statement generation by avoiding on-the-fly calculations from journal entries.

## Key Design Decisions

1. **Three Balance Types Per Account/Month**:
   - **Posted Transactions** (`balance_type='posted'`): Only includes journal entries where `state='posted'` (regardless of reconciliation status)
   - **Bank-Reconciled** (`balance_type='bank_reconciled'`): Only includes journal entries where `is_reconciled=True` (typically also posted)
   - **All Transactions** (`balance_type='all'`): Includes all journal entries (posted + pending, reconciled + unreconciled)

2. **Always Calculate All Three**: The recalculation endpoint always calculates and stores all three balance types for each account/month

3. **Always Overwrite**: Recalculation always deletes and recreates existing records (no update logic)

4. **Monthly Granularity**: Time dimension is month (year + month fields)

## Objectives

1. **Performance**: Pre-calculate and store monthly account balances to speed up financial statement generation
2. **Historical Tracking**: Maintain a historical record of account balances by month
3. **Recalculation**: Allow users to trigger recalculation of balances for specific periods (start required, end optional)
4. **Integration**: Modify financial statement service to use pre-calculated balances when available

---

## 1. Database Model Design

### AccountBalanceHistory Model

**Location**: `accounting/models.py` or `accounting/models_financial_statements.py`

```python
class AccountBalanceHistory(TenantAwareBaseModel):
    """
    Stores monthly account balances for efficient financial statement generation.
    
    Each record represents the ending balance of an account at the end of a specific month.
    This table is populated by a recalculation process and used by financial statements.
    """
    
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name='balance_history',
        help_text="The account this balance belongs to"
    )
    
    # Time dimension: Month
    year = models.IntegerField(
        help_text="Year (e.g., 2024)"
    )
    month = models.IntegerField(
        help_text="Month (1-12)"
    )
    
    # Balance information
    opening_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Balance at the start of the month"
    )
    ending_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Balance at the end of the month"
    )
    
    # Movement during the month
    total_debit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total debits during the month"
    )
    total_credit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total credits during the month"
    )
    
    # Metadata
    currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        help_text="Currency of the balance"
    )
    
    # Balance type: posted, bank_reconciled, or all transactions
    BALANCE_TYPE_CHOICES = [
        ('posted', 'Posted Transactions Only'),
        ('bank_reconciled', 'Bank-Reconciled Only'),
        ('all', 'All Transactions'),
    ]
    
    balance_type = models.CharField(
        max_length=20,
        choices=BALANCE_TYPE_CHOICES,
        help_text="Type of balance: posted (state='posted'), bank_reconciled (is_reconciled=True), or all (everything)"
    )
    
    # Calculation metadata
    calculated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this balance was last calculated"
    )
    calculated_by = models.ForeignKey(
        'multitenancy.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who triggered the calculation"
    )
    
    # Validation
    is_validated = models.BooleanField(
        default=False,
        help_text="Whether this balance has been manually validated"
    )
    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this balance was validated"
    )
    validated_by = models.ForeignKey(
        'multitenancy.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='validated_balance_history',
        help_text="User who validated this balance"
    )
    
    class Meta:
        unique_together = ('company', 'account', 'year', 'month', 'currency', 'balance_type')
        indexes = [
            models.Index(fields=['company', 'account', 'year', 'month', 'balance_type']),
            models.Index(fields=['company', 'year', 'month']),
            models.Index(fields=['account', 'year', 'month']),
            models.Index(fields=['calculated_at']),
        ]
        ordering = ['year', 'month', 'account', 'balance_type']
    
    def __str__(self):
        return f"{self.account.name} - {self.year}-{self.month:02d}: {self.ending_balance}"
    
    @property
    def period_start(self):
        """Return the first day of the month"""
        return date(self.year, self.month, 1)
    
    @property
    def period_end(self):
        """Return the last day of the month"""
        if self.month == 12:
            return date(self.year, 12, 31)
        else:
            return date(self.year, self.month + 1, 1) - timedelta(days=1)
    
    @classmethod
    def get_balance_for_period(cls, account, year, month, currency, balance_type='all'):
        """Get balance for a specific period"""
        try:
            return cls.objects.get(
                account=account,
                year=year,
                month=month,
                currency=currency,
                balance_type=balance_type,
                company=account.company
            )
        except cls.DoesNotExist:
            return None
```

**Key Design Decisions:**
- **Monthly granularity**: Stores one record per account per month
- **Three balance types**: Always stores THREE records per account/month:
  - `balance_type='posted'`: Only posted transactions (state='posted')
  - `balance_type='bank_reconciled'`: Only bank-reconciled transactions (is_reconciled=True)
  - `balance_type='all'`: All transactions (posted + pending, reconciled + unreconciled)
- **Always calculate all three**: Recalculation endpoint always calculates all three balance types
- **Always overwrite**: Recalculation always deletes and recreates existing records (no update)
- **Opening and ending balances**: Both stored for flexibility
- **Currency support**: Each balance is currency-specific
- **Validation tracking**: Allows manual validation of balances
- **Unique constraint**: Prevents duplicate records for same account/month/currency/balance_type

---

## 2. Recalculation Service

### BalanceRecalculationService

**Location**: `accounting/services/balance_recalculation_service.py`

```python
class BalanceRecalculationService:
    """
    Service for calculating and storing account balance history.
    """
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
    def recalculate_balances(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        account_ids: Optional[List[int]] = None,
        currency_id: Optional[int] = None,
        calculated_by=None,
    ) -> Dict[str, Any]:
        """
        Recalculate account balances for a given period.
        
        This method ALWAYS calculates ALL THREE balance types:
        - Posted transactions only (balance_type='posted')
        - Bank-reconciled only (balance_type='bank_reconciled')
        - All transactions (balance_type='all')
        
        Existing records are ALWAYS overwritten.
        
        Parameters:
        -----------
        start_date : date
            Start of the period (required). Will use the first day of the month.
        end_date : Optional[date]
            End of the period (optional). If not provided, calculates only for start_date's month.
            Will use the last day of the month.
        account_ids : Optional[List[int]]
            Specific accounts to recalculate. If None, recalculates all accounts.
        currency_id : Optional[int]
            Specific currency to recalculate. If None, recalculates all currencies.
        calculated_by : User
            User who triggered the recalculation
        
        Returns:
        --------
        Dict with statistics about the recalculation
        """
        # Implementation details below
        pass
    
    def _calculate_month_balance(
        self,
        account: Account,
        year: int,
        month: int,
        currency: Currency,
        balance_type: str = 'all',
    ) -> Dict[str, Decimal]:
        """
        Calculate balance for a specific account and month.
        
        Parameters:
        -----------
        balance_type : str
            One of: 'posted', 'bank_reconciled', 'all'
            - 'posted': Only journal entries where state='posted'
            - 'bank_reconciled': Only journal entries where is_reconciled=True
            - 'all': All journal entries (posted + pending, reconciled + unreconciled)
        
        Returns:
        --------
        Dict with 'opening_balance', 'ending_balance', 'total_debit', 'total_credit'
        """
        # Implementation details below
        pass
    
    def _get_opening_balance_for_month(
        self,
        account: Account,
        year: int,
        month: int,
        currency: Currency,
        balance_type: str = 'all',
    ) -> Decimal:
        """
        Get the opening balance for a month.
        This is the ending balance of the previous month (same balance_type),
        or account.balance if it's the first month.
        """
        # Implementation details below
        pass
    
    def _get_journal_entry_filter(self, balance_type: str) -> Q:
        """
        Get the Q filter for journal entries based on balance_type.
        
        Returns:
        --------
        Q object for filtering journal entries
        """
        if balance_type == 'posted':
            return Q(state='posted')
        elif balance_type == 'bank_reconciled':
            return Q(is_reconciled=True)
        elif balance_type == 'all':
            return Q()  # No filter - include everything
        else:
            raise ValueError(f"Invalid balance_type: {balance_type}")
```

**Calculation Logic:**
1. **Always calculate all three types**: For each account/month, calculate:
   - `balance_type='posted'`: Only journal entries where `state='posted'`
     - Filter: `JournalEntry.objects.filter(account=account, state='posted', ...)`
   - `balance_type='bank_reconciled'`: Only journal entries where `is_reconciled=True`
     - Filter: `JournalEntry.objects.filter(account=account, is_reconciled=True, ...)`
   - `balance_type='all'`: All journal entries (posted + pending, reconciled + unreconciled)
     - Filter: `JournalEntry.objects.filter(account=account, ...)` (no filters)
2. **Month boundaries**: Always calculate for full months (first day to last day)
3. **Opening balance**: 
   - If previous month exists in history (same balance_type), use its ending balance
   - Otherwise, use account.balance if account.balance_date is before the month
   - Otherwise, calculate from journal entries from beginning (with same balance_type filter)
4. **Ending balance**: Opening balance + (debits - credits) * account_direction
5. **Always overwrite**: Existing records are deleted and recreated (no update logic)
   - Before creating new records, delete existing records for the same account/month/currency
6. **Batch processing**: Process accounts in batches for performance
7. **Note**: The 'posted' balance type only filters by state, not reconciliation status. The 'bank_reconciled' type filters by reconciliation status (and typically these entries are also posted).

---

## 3. API Endpoint

### Recalculation Endpoint

**Location**: `accounting/views_financial_statements.py` or new `accounting/views_balance_history.py`

**Endpoint**: `POST /api/accounting/balance-history/recalculate/`

**Request Body:**
```json
{
    "start_date": "2024-01-01",  // Required
    "end_date": "2024-12-31",    // Optional
    "account_ids": [1, 2, 3],    // Optional - specific accounts
    "currency_id": 1             // Optional - specific currency
}
```

**Note**: The endpoint always calculates ALL THREE balance types (posted, bank-reconciled, and all transactions) and always overwrites existing records.

**Response:**
```json
{
    "status": "success",
    "message": "Recalculation completed",
    "statistics": {
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "accounts_processed": 150,
        "months_processed": 12,
        "records_created": 5400,  // 3 records per account/month (posted + reconciled + all)
        "records_deleted": 0,      // Records that were overwritten
        "duration_seconds": 45.2
    },
    "errors": []
}
```

**View Implementation:**
```python
class BalanceHistoryRecalculateView(APIView):
    """
    Endpoint to trigger recalculation of account balances for a period.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = BalanceHistoryRecalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get company from request (multitenancy)
        company = request.user.company  # Adjust based on your multitenancy setup
        
        service = BalanceRecalculationService(company_id=company.id)
        
        result = service.recalculate_balances(
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data.get('end_date'),
            account_ids=serializer.validated_data.get('account_ids'),
            currency_id=serializer.validated_data.get('currency_id'),
            calculated_by=request.user,
        )
        
        return Response(result, status=status.HTTP_200_OK)
```

**Serializer:**
```python
class BalanceHistoryRecalculateSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    account_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    currency_id = serializers.IntegerField(required=False, allow_null=True)
```

---

## 4. Integration with Financial Statement Service

### Modifying FinancialStatementGenerator

**Location**: `accounting/services/financial_statement_service.py`

**Changes needed:**
1. Add method to check if balance history exists for a period
2. Modify `_calculate_cumulative_ending_balance_with_metadata` to use history when available
3. Fallback to on-the-fly calculation if history doesn't exist

**New Method:**
```python
def _get_balance_from_history(
    self,
    account: Account,
    as_of_date: date,
    balance_type: str = 'all',
    currency: Optional[Currency] = None,
) -> Optional[Decimal]:
    """
    Get balance from AccountBalanceHistory if available.
    
    Parameters:
    -----------
    balance_type : str
        One of: 'posted', 'bank_reconciled', 'all'
        Determines which balance type to retrieve from history
    
    Returns:
    --------
    Ending balance from the history table for the month containing as_of_date.
    Returns None if history doesn't exist for that period.
    """
    if currency is None:
        currency = account.currency
    
    year = as_of_date.year
    month = as_of_date.month
    
    try:
        history = AccountBalanceHistory.objects.get(
            account=account,
            year=year,
            month=month,
            currency=currency,
            balance_type=balance_type,
            company_id=self.company_id
        )
        return history.ending_balance
    except AccountBalanceHistory.DoesNotExist:
        return None
```

**Modified Method:**
```python
def _calculate_cumulative_ending_balance_with_metadata(
    self,
    account: Account,
    as_of_date: date,
    include_pending: bool = False,
    balance_type: str = 'all',
) -> Tuple[Decimal, Dict[str, Any]]:
    """
    Calculate cumulative ending balance, using history table if available.
    
    Parameters:
    -----------
    balance_type : str
        One of: 'posted', 'bank_reconciled', 'all'
        Determines which balance type to use from history or calculate on-the-fly
    """
    # Try to get from history first
    balance_from_history = self._get_balance_from_history(
        account=account,
        as_of_date=as_of_date,
        balance_type=balance_type,
    )
    
    if balance_from_history is not None:
        # Use pre-calculated balance
        metadata = {
            'source': 'balance_history',
            'from_history': True,
            'balance_type': balance_type,
            'as_of_date': str(as_of_date),
        }
        return balance_from_history, metadata
    
    # Fallback to on-the-fly calculation (existing logic)
    # Apply balance_type filter to journal entries
    # ... existing implementation ...
```

---

## 5. URL Configuration

**Location**: `accounting/urls.py`

```python
urlpatterns = [
    # ... existing patterns ...
    path(
        'balance-history/recalculate/',
        BalanceHistoryRecalculateView.as_view(),
        name='balance-history-recalculate'
    ),
    path(
        'balance-history/',
        BalanceHistoryViewSet.as_view({'get': 'list'}),
        name='balance-history-list'
    ),
]
```

---

## 6. Admin Interface

**Location**: `accounting/admin.py`

```python
@admin.register(AccountBalanceHistory)
class AccountBalanceHistoryAdmin(CompanyScopedAdmin):
    list_display = [
        'account',
        'year',
        'month',
        'opening_balance',
        'ending_balance',
        'currency',
        'balance_type',
        'calculated_at',
        'is_validated',
    ]
    list_filter = [
        'year',
        'month',
        'currency',
        'balance_type',
        'is_validated',
        'calculated_at',
    ]
    search_fields = [
        'account__name',
        'account__account_code',
    ]
    readonly_fields = [
        'calculated_at',
        'calculated_by',
    ]
    date_hierarchy = 'calculated_at'
    
    fieldsets = (
        ('Account & Period', {
            'fields': ('account', 'year', 'month', 'currency')
        }),
        ('Balances', {
            'fields': ('opening_balance', 'ending_balance', 'total_debit', 'total_credit')
        }),
        ('Metadata', {
            'fields': ('balance_type', 'calculated_at', 'calculated_by')
        }),
        ('Validation', {
            'fields': ('is_validated', 'validated_at', 'validated_by')
        }),
    )
```

---

## 7. Migration Strategy

### Initial Data Population

1. **Create migration** for the new model
2. **Optional**: Create a management command to populate initial data:
   ```bash
   python manage.py populate_balance_history --start-date 2020-01-01 --end-date 2024-12-31
   ```

### Backward Compatibility

- Financial statement service should work with or without history table
- If history doesn't exist, fall back to on-the-fly calculation
- No breaking changes to existing functionality

---

## 8. Performance Considerations

### Indexing
- Index on `(company, account, year, month)` for fast lookups
- Index on `(company, year, month)` for period-based queries
- Index on `calculated_at` for audit purposes

### Batch Processing
- Process accounts in batches (e.g., 100 at a time)
- Use `bulk_create` and `bulk_update` for database efficiency
- Consider using Celery for large recalculations

### Caching
- Consider caching frequently accessed balances
- Cache invalidation when new journal entries are posted

---

## 9. Testing Strategy

### Unit Tests
- Test balance calculation logic
- Test month boundary handling
- Test opening balance derivation
- Test currency handling
- Test posted vs bank-reconciled vs all transactions filtering
- Test that all three balance types are always calculated
- Test that existing records are overwritten

### Integration Tests
- Test recalculation service end-to-end
- Test API endpoint
- Test financial statement integration
- Test fallback to on-the-fly calculation

### Performance Tests
- Compare financial statement generation time with vs without history table
- Test recalculation performance for large datasets

---

## 10. Implementation Steps

1. **Phase 1: Model & Migration**
   - Create `AccountBalanceHistory` model
   - Create and run migration
   - Add to admin interface

2. **Phase 2: Recalculation Service**
   - Implement `BalanceRecalculationService`
   - Add unit tests
   - Create management command for initial population

3. **Phase 3: API Endpoint**
   - Create serializer
   - Create view
   - Add URL routing
   - Add API documentation

4. **Phase 4: Financial Statement Integration**
   - Modify `FinancialStatementGenerator` to use history
   - Add fallback logic
   - Test with existing financial statements

5. **Phase 5: Documentation & Testing**
   - Update API documentation
   - Add integration tests
   - Performance testing
   - User documentation

---

## 11. Future Enhancements

1. **Automatic Recalculation**: Trigger recalculation when journal entries are posted
2. **Daily Granularity**: Option to store daily balances for more detailed analysis
3. **Balance Validation**: UI for users to validate and lock balances
4. **Balance Comparison**: Compare calculated vs validated balances
5. **Audit Trail**: Track all changes to balance history
6. **Async Processing**: Use Celery for large recalculations
7. **Incremental Updates**: Only recalculate affected months when entries change

---

## 12. Example Usage

### Recalculating Balances via API

```bash
curl -X POST http://localhost:8000/api/accounting/balance-history/recalculate/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }'
```

### Using in Financial Statements

The financial statement service will automatically use balance history if available:

```python
generator = FinancialStatementGenerator(company_id=1)
statement = generator.generate_statement(
    template=template,
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
)
# Balances will be retrieved from AccountBalanceHistory if available
```

---

## Questions & Decisions Needed

1. **Granularity**: Confirm monthly is sufficient, or if daily/weekly needed?
2. **Validation**: Do we need manual validation workflow, or is calculated always trusted?
3. **Auto-recalculation**: Should we automatically recalculate when journal entries change?
4. **Retention**: How long should we keep balance history? Archive old data?
5. **Performance**: Should recalculation be async (Celery) or synchronous?
6. **Financial Statement Usage**: Should financial statements use posted, bank-reconciled, or all-transactions balance by default?

---

## Summary

This plan provides a comprehensive approach to implementing account balance history:

- **Model**: Stores monthly balances with full metadata
- **Service**: Handles recalculation logic
- **API**: Endpoint for triggering recalculations
- **Integration**: Seamless integration with financial statements
- **Performance**: Optimized for fast lookups
- **Flexibility**: Falls back to on-the-fly calculation if history unavailable

The implementation is backward-compatible and can be rolled out incrementally.

