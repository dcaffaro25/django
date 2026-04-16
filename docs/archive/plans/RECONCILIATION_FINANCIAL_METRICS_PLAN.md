# Reconciliation Financial Metrics Plan

## Overview

This document outlines the proposed financial and business metrics to be calculated for transactions and journal entries based on their bank reconciliation relationships. These metrics help analyze payment timing, value differences, and operational efficiency.

## Metrics Categories

### 1. Date/Timing Metrics

#### 1.1 Payment Day Delta (Expected vs Effective)
- **Metric Name**: `payment_day_delta`
- **Description**: Number of days between expected payment date and effective payment date
- **Formula**: `(BankTransaction.date - Transaction.date).days`
- **Interpretation**: 
  - Positive: Payment happened later than expected (delay)
  - Negative: Payment happened earlier than expected (early)
  - Zero: Payment on time
- **Use Cases**:
  - Cash flow forecasting accuracy
  - Vendor payment timing analysis
  - Customer payment behavior analysis

#### 1.2 Journal Entry Date Delta
- **Metric Name**: `journal_entry_date_delta`
- **Description**: Number of days between journal entry date and bank transaction date
- **Formula**: `(BankTransaction.date - JournalEntry.date).days`
- **Interpretation**: Accounting entry timing vs actual bank movement
- **Use Cases**: Book-to-bank timing analysis

#### 1.3 Transaction-to-Bank Lead Time
- **Metric Name**: `transaction_to_bank_lead_days`
- **Description**: Days from transaction creation to bank reconciliation
- **Formula**: `(Reconciliation.created_at.date() - Transaction.date).days`
- **Use Cases**: Process efficiency metrics

#### 1.4 Payment Date Variance
- **Metric Name**: `payment_date_variance`
- **Description**: Statistical variance in payment timing (for entity/account)
- **Calculation**: Standard deviation of payment_day_delta over time
- **Use Cases**: Predictability analysis

### 2. Value/Amount Metrics

#### 2.1 Amount Discrepancy (Expected vs Actual)
- **Metric Name**: `amount_discrepancy`
- **Description**: Difference between expected transaction amount and actual bank amount
- **Formula**: `BankTransaction.amount - Transaction.amount`
- **Interpretation**:
  - Positive: Bank amount higher (fees added, interest, etc.)
  - Negative: Bank amount lower (fees deducted, discounts, etc.)
  - Zero: Exact match
- **Use Cases**:
  - Fee analysis
  - Discount tracking
  - Foreign exchange impact

#### 2.2 Amount Discrepancy Percentage
- **Metric Name**: `amount_discrepancy_percentage`
- **Description**: Percentage difference between expected and actual amounts
- **Formula**: `(amount_discrepancy / Transaction.amount) * 100`
- **Use Cases**: Relative impact analysis

#### 2.3 Journal Entry Amount Discrepancy
- **Metric Name**: `journal_entry_amount_discrepancy`
- **Description**: Difference between journal entry amount and bank transaction amount
- **Formula**: `BankTransaction.amount - JournalEntry.get_amount()`
- **Use Cases**: Per-entry reconciliation accuracy

#### 2.4 Reconciliation Discrepancy
- **Metric Name**: `reconciliation_discrepancy` (already exists as property)
- **Description**: Difference between total bank amount and total journal entry amount
- **Formula**: `Reconciliation.total_bank_amount - Reconciliation.total_journal_amount`
- **Use Cases**: Multi-entry reconciliation accuracy

#### 2.5 Value Variance
- **Metric Name**: `value_variance`
- **Description**: Statistical variance in amount discrepancies (for entity/account)
- **Calculation**: Standard deviation of amount_discrepancy over time
- **Use Cases**: Predictability and consistency analysis

### 3. Efficiency Metrics

#### 3.1 Reconciliation Time to Completion
- **Metric Name**: `reconciliation_time_days`
- **Description**: Days from transaction creation to reconciliation approval
- **Formula**: `(Reconciliation.updated_at - Transaction.date).days`
- **Use Cases**: Process efficiency, SLA tracking

#### 3.2 Days Outstanding
- **Metric Name**: `days_outstanding`
- **Description**: Days between transaction date and reconciliation date
- **Formula**: `(Reconciliation.updated_at.date() - Transaction.date).days`
- **Use Cases**: Aging analysis

#### 3.3 First Match Time
- **Metric Name**: `first_match_time_days`
- **Description**: Days from bank transaction date to first reconciliation match
- **Formula**: `(Reconciliation.created_at.date() - BankTransaction.date).days`
- **Use Cases**: Matching speed analysis

### 4. Accuracy Metrics

#### 4.1 Exact Match Rate
- **Metric Name**: `is_exact_match`
- **Description**: Boolean indicating if amounts match exactly (within tolerance)
- **Formula**: `abs(amount_discrepancy) <= tolerance`
- **Use Cases**: Quality metrics

#### 4.2 Date Match Accuracy
- **Metric Name**: `is_date_match`
- **Description**: Boolean indicating if dates match within acceptable range
- **Formula**: `abs(payment_day_delta) <= acceptable_days`
- **Use Cases**: Date accuracy tracking

#### 4.3 Perfect Match
- **Metric Name**: `is_perfect_match`
- **Description**: Both amount and date match within tolerance
- **Formula**: `is_exact_match AND is_date_match`
- **Use Cases**: Overall quality score

### 5. Aggregate/Analytical Metrics

#### 5.1 Average Payment Delay
- **Metric Name**: `avg_payment_delay_days`
- **Aggregation Level**: Entity, Account, Period
- **Formula**: `AVG(payment_day_delta) WHERE payment_day_delta > 0`
- **Use Cases**: Payment behavior analysis

#### 5.2 Average Payment Advance
- **Metric Name**: `avg_payment_advance_days`
- **Aggregation Level**: Entity, Account, Period
- **Formula**: `AVG(ABS(payment_day_delta)) WHERE payment_day_delta < 0`
- **Use Cases**: Early payment tracking

#### 5.3 Total Amount Discrepancy
- **Metric Name**: `total_amount_discrepancy`
- **Aggregation Level**: Period, Entity, Account
- **Formula**: `SUM(amount_discrepancy)`
- **Use Cases**: Financial impact analysis

#### 5.4 Average Amount Discrepancy
- **Metric Name**: `avg_amount_discrepancy`
- **Aggregation Level**: Period, Entity, Account
- **Formula**: `AVG(amount_discrepancy)`
- **Use Cases**: Fee/discount analysis

#### 5.5 Discrepancy Rate
- **Metric Name**: `discrepancy_rate`
- **Description**: Percentage of transactions with discrepancies
- **Formula**: `(COUNT(amount_discrepancy != 0) / COUNT(*)) * 100`
- **Use Cases**: Quality metrics

### 6. Pattern Recognition Metrics

#### 6.1 Recurring Discrepancy Pattern
- **Metric Name**: `recurring_discrepancy_amount`
- **Description**: Identified recurring fee or adjustment amount
- **Use Cases**: Automated fee detection

#### 6.2 Payment Timing Pattern
- **Metric Name**: `payment_timing_pattern`
- **Description**: Classification of payment timing behavior (on-time, consistently late, variable)
- **Use Cases**: Behavioral analysis

#### 6.3 Seasonal Payment Pattern
- **Metric Name**: `seasonal_payment_delay`
- **Description**: Average delay by month/quarter
- **Use Cases**: Seasonal cash flow analysis

## Implementation Structure

### Per-Transaction Metrics (stored/computed on Transaction)
```python
class TransactionMetrics:
    # Date metrics
    payment_day_delta: int  # days
    transaction_to_bank_lead_days: int
    
    # Amount metrics
    amount_discrepancy: Decimal
    amount_discrepancy_percentage: Decimal
    
    # Efficiency metrics
    days_outstanding: int
    reconciliation_time_days: int
    
    # Accuracy metrics
    is_exact_match: bool
    is_date_match: bool
    is_perfect_match: bool
    
    # Aggregates (for related transactions)
    avg_payment_delay_for_entity: Decimal
    total_discrepancy_for_entity: Decimal
```

### Per-Journal Entry Metrics (stored/computed on JournalEntry)
```python
class JournalEntryMetrics:
    # Date metrics
    journal_entry_date_delta: int  # days
    
    # Amount metrics
    journal_entry_amount_discrepancy: Decimal
    
    # Reconciliation context
    reconciliation_id: int
    reconciliation_discrepancy: Decimal  # total for the reconciliation
```

### Per-Reconciliation Metrics (properties/methods on Reconciliation)
```python
class ReconciliationMetrics:
    # Existing
    total_journal_amount: Decimal
    total_bank_amount: Decimal
    discrepancy: Decimal
    
    # New additions
    avg_date_delta: Decimal  # average date difference across all entries
    max_date_delta: int
    min_date_delta: int
    
    # Efficiency
    reconciliation_time_days: int
    first_match_time_days: int
    
    # Accuracy
    perfect_match_count: int
    partial_match_count: int
    
    # Composition
    transaction_count: int
    journal_entry_count: int
    bank_transaction_count: int
```

### Aggregate Metrics (computed on demand or cached)
```python
class AggregateMetrics:
    # Period-level (e.g., monthly, quarterly)
    period: str
    entity_id: int
    
    avg_payment_delay_days: Decimal
    avg_payment_advance_days: Decimal
    total_amount_discrepancy: Decimal
    avg_amount_discrepancy: Decimal
    discrepancy_rate: Decimal
    exact_match_rate: Decimal
    
    # Pattern metrics
    recurring_discrepancy_amount: Optional[Decimal]
    payment_timing_pattern: str
```

## Database Considerations

### Option 1: Computed Properties (Recommended for MVP)
- Calculate metrics on-demand using model properties/methods
- No database schema changes required
- Flexible but potentially slower for large datasets

### Option 2: Denormalized Fields
- Add metric fields to Transaction/JournalEntry/Reconciliation models
- Update via signals or background tasks
- Faster queries but requires maintenance

### Option 3: Separate Metrics Table
- `TransactionMetrics`, `JournalEntryMetrics`, `ReconciliationMetrics` tables
- Computed and stored separately
- Best for complex aggregations and historical tracking
- Enables metric versioning and historical analysis

### Recommended Approach: Hybrid
- **Simple metrics**: Computed properties (payment_day_delta, amount_discrepancy)
- **Complex aggregations**: Cached in separate metrics table or materialized views
- **Periodic metrics**: Background task to compute and store aggregate metrics

## API Endpoints

### Get Transaction Metrics
```
GET /api/transactions/{id}/metrics/
Response: {
    "payment_day_delta": 3,
    "amount_discrepancy": 5.00,
    "amount_discrepancy_percentage": 0.5,
    "days_outstanding": 5,
    "is_exact_match": false,
    "is_perfect_match": false,
    "reconciliation_id": 123
}
```

### Get Reconciliation Metrics
```
GET /api/reconciliation/{id}/metrics/
Response: {
    "discrepancy": 5.00,
    "avg_date_delta": 2.5,
    "reconciliation_time_days": 3,
    "perfect_match_count": 2,
    "transaction_count": 3
}
```

### Get Aggregate Metrics
```
GET /api/metrics/aggregate/?entity_id=1&period=2025-01
Response: {
    "period": "2025-01",
    "entity_id": 1,
    "avg_payment_delay_days": 2.5,
    "total_amount_discrepancy": 150.00,
    "discrepancy_rate": 15.5,
    "exact_match_rate": 84.5
}
```

## Use Cases & Business Value

### 1. Cash Flow Forecasting
- **Metrics**: `payment_day_delta`, `avg_payment_delay_days`
- **Value**: Improve forecast accuracy by understanding payment timing patterns

### 2. Vendor/Supplier Analysis
- **Metrics**: `avg_payment_delay_days`, `amount_discrepancy`, `discrepancy_rate`
- **Value**: Identify problematic vendors, track fee patterns, negotiate better terms

### 3. Customer Payment Behavior
- **Metrics**: `payment_day_delta`, `payment_timing_pattern`, `days_outstanding`
- **Value**: Understand customer payment habits, improve collections

### 4. Process Efficiency
- **Metrics**: `reconciliation_time_days`, `first_match_time_days`
- **Value**: Identify bottlenecks, measure improvement over time

### 5. Financial Accuracy
- **Metrics**: `discrepancy_rate`, `exact_match_rate`, `amount_discrepancy`
- **Value**: Track accounting accuracy, identify systematic issues

### 6. Fee Analysis
- **Metrics**: `amount_discrepancy`, `recurring_discrepancy_amount`
- **Value**: Identify hidden fees, negotiate better rates, budget accurately

## Implementation Priority

### Phase 1: Core Metrics (High Priority)
1. `payment_day_delta` - Expected vs effective payment day
2. `amount_discrepancy` - Expected vs effective value
3. `reconciliation_discrepancy` - Already exists, enhance
4. `is_exact_match` - Accuracy flag

### Phase 2: Efficiency Metrics (Medium Priority)
1. `days_outstanding` - Aging analysis
2. `reconciliation_time_days` - Process efficiency
3. `journal_entry_date_delta` - Book vs bank timing

### Phase 3: Aggregate Analytics (Medium Priority)
1. `avg_payment_delay_days` - Entity/account level
2. `total_amount_discrepancy` - Period aggregation
3. `discrepancy_rate` - Quality metrics

### Phase 4: Advanced Analytics (Lower Priority)
1. Pattern recognition metrics
2. Seasonal analysis
3. Predictive metrics

## Technical Notes

### Date Handling
- Use timezone-aware dates for accurate calculations
- Consider business days vs calendar days for some metrics
- Handle edge cases (weekends, holidays)

### Amount Handling
- Use Decimal for precise calculations
- Handle currency conversion if needed
- Consider sign conventions (debit vs credit)

### Performance
- Index on dates and amounts for efficient queries
- Cache aggregate metrics to avoid repeated calculations
- Consider materialized views for period-based aggregations

### Data Quality
- Handle missing reconciliations gracefully
- Validate metrics against business rules
- Flag anomalies for review

## Future Enhancements

1. **Machine Learning**: Use historical metrics to predict payment timing and discrepancies
2. **Alerting**: Set up alerts for metrics exceeding thresholds
3. **Dashboard**: Visualize metrics trends over time
4. **Benchmarking**: Compare metrics across entities, periods, or industry standards
5. **Anomaly Detection**: Automatically identify unusual patterns

---

## Account Assignment Verification

Based on historical transactions, we verify that journal entries are assigned to the correct accounts.

### Verification Criteria
1. **Exact Description Match**: Same company, entity, and exact description
2. **Amount Range Match**: Similar amounts (±10%) with same company/entity
3. **Date Proximity Match**: Transactions within 30 days with same entity
4. **Pattern Frequency**: Count of historical matches using same account

### Verification Results
- `confidence_score`: 0-1 score indicating assignment confidence
- `historical_matches`: Number of historical transactions with same account
- `suggested_account_id`: Alternative account from history (if current assignment differs)
- `match_reasons`: List of matching criteria that were met

## Transaction-Level Aggregation

Transactions show aggregated metrics from their journal entries:

### Aggregated Metrics (Read-Only)
- `avg_payment_day_delta`: Average payment delay across all journal entries
- `min_payment_day_delta` / `max_payment_day_delta`: Range of delays
- `total_amount_discrepancy`: Sum of all journal entry discrepancies
- `avg_amount_discrepancy`: Average discrepancy per entry
- `exact_match_count`: Number of entries with exact amount matches
- `perfect_match_count`: Number of entries with perfect matches
- `reconciliation_rate`: Percentage of journal entries that are reconciled
- `days_outstanding`: Days from transaction date to first reconciliation

### Storage Strategy
- Metrics are **read-only** (system calculated only)
- Stored as model fields on Transaction and JournalEntry
- Updated via recalculation endpoint or background tasks
- Can be computed on-demand if not stored

## Recalculation Endpoint

### Endpoint Specification
```
POST /api/reconciliation-metrics/recalculate/
```

### Request Body
```json
{
  "start_date": "2025-01-01",  // Required
  "end_date": "2025-01-31",     // Optional, defaults to today
  "company_id": 1,               // Optional
  "entity_id": 2,                // Optional
  "account_id": 10,              // Optional (filters journal entries)
  "transaction_ids": [100, 101]  // Optional (specific transactions)
}
```

### Response
```json
{
  "success": true,
  "stats": {
    "transactions_processed": 150,
    "journal_entries_processed": 450,
    "metrics_calculated": 600,
    "errors": []
  },
  "filters": {
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "company_id": 1,
    "entity_id": 2,
    "account_id": 10,
    "transaction_ids": null
  }
}
```

### Use Cases
1. **Periodic Recalculation**: Recalculate metrics for a month/quarter
2. **After Reconciliation**: Recalculate when new reconciliations are created
3. **Data Correction**: Recalculate after fixing transaction data
4. **Account Changes**: Recalculate when account assignments change

## Implementation Notes

### Model Fields (Read-Only)
Journal Entry fields:
- `metrics_payment_day_delta` (IntegerField, null=True)
- `metrics_journal_entry_date_delta` (IntegerField, null=True)
- `metrics_amount_discrepancy` (DecimalField, null=True)
- `metrics_amount_discrepancy_percentage` (DecimalField, null=True)
- `metrics_is_exact_match` (BooleanField, default=False)
- `metrics_is_date_match` (BooleanField, default=False)
- `metrics_is_perfect_match` (BooleanField, default=False)
- `metrics_account_confidence_score` (DecimalField, null=True)
- `metrics_account_historical_matches` (IntegerField, default=0)
- `metrics_last_calculated_at` (DateTimeField, null=True)

Transaction fields:
- `metrics_avg_payment_day_delta` (DecimalField, null=True)
- `metrics_min_payment_day_delta` (IntegerField, null=True)
- `metrics_max_payment_day_delta` (IntegerField, null=True)
- `metrics_total_amount_discrepancy` (DecimalField, default=0)
- `metrics_avg_amount_discrepancy` (DecimalField, null=True)
- `metrics_exact_match_count` (IntegerField, default=0)
- `metrics_perfect_match_count` (IntegerField, default=0)
- `metrics_reconciliation_rate` (DecimalField, default=0)
- `metrics_days_outstanding` (IntegerField, null=True)
- `metrics_last_calculated_at` (DateTimeField, null=True)

### Field Protection
- Fields should be read-only in serializers (write=False)
- Only updateable via service methods
- Signals can trigger recalculation on reconciliation changes

## Questions for Discussion

1. Which metrics are most valuable for your use case?
2. Should metrics be computed on-demand or pre-calculated?
3. What aggregation levels are needed (entity, account, period)?
4. Do we need historical tracking of metrics over time?
5. What are acceptable tolerances for "exact match" vs "close match"?
6. Should we track metrics separately for different transaction types (AR, AP, etc.)?
7. Should account assignment verification block incorrect assignments or just warn?
8. How often should automatic recalculation run (background task frequency)?

