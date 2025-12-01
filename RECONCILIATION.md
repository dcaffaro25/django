# Reconciliation System - Complete Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Models](#models)
4. [Reconciliation Config](#reconciliation-config)
5. [Reconciliation Pipeline](#reconciliation-pipeline)
6. [Matching Functions](#matching-functions)
7. [Variable Impact on Matching](#variable-impact-on-matching)
8. [API Endpoints](#api-endpoints)
9. [Transaction Suggestion System](#transaction-suggestion-system)
10. [Usage Examples](#usage-examples)

---

## Overview

The Reconciliation System automatically matches bank transactions with journal entries (book transactions) using configurable algorithms. The system supports:

- **Single Config Matching**: Run reconciliation with one configuration
- **Pipeline Matching**: Run multiple matching stages in sequence
- **Embedding-Based Matching**: Uses vector embeddings for semantic similarity
- **Many-to-Many Matching**: Match multiple bank transactions with multiple journal entries
- **Auto-Matching**: Automatically apply high-confidence matches
- **Transaction Suggestions**: Generate book transactions for unmatched bank transactions based on historical patterns

### Key Concepts

- **Bank Transactions**: Transactions from bank statements (cash inflows/outflows)
- **Journal Entries (Books)**: Accounting entries in the general ledger
- **Reconciliation**: The process of matching bank transactions with journal entries
- **Config**: A set of matching parameters and rules
- **Pipeline**: A sequence of configs executed in order
- **Suggestion**: A proposed match between bank and book transactions

---

## Architecture

### Core Components

1. **Models** (`accounting/models.py`)
   - `ReconciliationConfig`: Matching configuration
   - `ReconciliationPipeline`: Multi-stage matching sequence
   - `ReconciliationPipelineStage`: Individual stage in a pipeline
   - `ReconciliationTask`: Execution record
   - `Reconciliation`: Match record linking bank and book transactions
   - `ReconciliationSuggestion`: Proposed match suggestion

2. **Service Layer** (`accounting/services/reconciliation_service.py`)
   - `ReconciliationPipelineEngine`: Core matching engine
   - `ReconciliationService`: High-level service wrapper
   - Matching functions for different strategies

3. **Suggestion Service** (`accounting/services/bank_transaction_suggestion_service.py`)
   - `BankTransactionSuggestionService`: Generates book transaction suggestions

4. **API Layer** (`accounting/views.py`)
   - ViewSets for configs, pipelines, tasks, and reconciliations
   - Endpoints for matching and suggestion creation

---

## Models

### ReconciliationConfig

Stores reusable reconciliation settings that control matching behavior.

**Location:** `accounting/models.py`

**Key Fields:**

#### Scope Fields
- `scope`: `str` - Who this config applies to
  - `"global"`: System-wide
  - `"company"`: Company-specific
  - `"user"`: User-specific
  - `"company_user"`: Company + User specific
- `company`: `ForeignKey(Company)` - Required if scope is `"company"` or `"company_user"`
- `user`: `ForeignKey(User)` - Required if scope is `"user"` or `"company_user"`

#### Basic Fields
- `name`: `str` - Configuration name
- `description`: `Text` - Optional description
- `is_default`: `bool` - Whether this is the default config

#### Filter Fields
- `bank_filters`: `JSONField` - Filters for bank transactions
  ```json
  {
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "min_amount": 0,
    "max_amount": 1000000,
    "bank_account_ids": [1, 2, 3],
    "entity_ids": [1, 2]
  }
  ```
- `book_filters`: `JSONField` - Filters for journal entries
  ```json
  {
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "min_amount": 0,
    "max_amount": 1000000,
    "account_ids": [1, 2, 3],
    "entity_ids": [1, 2]
  }
  ```

#### Scoring Weights (Must Sum to 1.0)
- `embedding_weight`: `Decimal` (default: 0.50) - Weight for embedding similarity
- `amount_weight`: `Decimal` (default: 0.35) - Weight for amount matching
- `currency_weight`: `Decimal` (default: 0.10) - Weight for currency matching
- `date_weight`: `Decimal` (default: 0.05) - Weight for date proximity

**Validation:** Weights must sum to 1.0

#### Tolerance and Size Fields
- `amount_tolerance`: `Decimal` (default: 0) - Maximum allowed amount difference
- `group_span_days`: `int` (default: 2) - Max date span within a candidate group
- `avg_date_delta_days`: `int` (default: 2) - Max absolute delta between weighted-average dates of bank and book groups
- `max_group_size_bank`: `int` (default: 1) - Maximum bank transactions in a group
- `max_group_size_book`: `int` (default: 1) - Maximum journal entries in a group

#### Matching Behavior
- `allow_mixed_signs`: `bool` (default: False) - Allow groups with mixed positive/negative amounts
- `min_confidence`: `Decimal` (default: 0.90) - Minimum confidence score to include suggestion
- `max_suggestions`: `int` (default: 1000) - Maximum number of suggestions to return
- `max_alternatives_per_match`: `int` (default: 2) - Number of alternative matches per anchor

#### Runtime Control
- `soft_time_limit_seconds`: `int` (optional) - Soft runtime limit in seconds

#### Additional Tuning
- `fee_accounts`: `JSONField` - List of account IDs for fee handling
- `duplicate_window_days`: `int` (default: 3) - Window for duplicate detection
- `text_similarity`: `JSONField` - Text similarity configuration

### ReconciliationPipeline

Defines an ordered sequence of reconciliation stages.

**Location:** `accounting/models.py`

**Key Fields:**

#### Scope Fields
- `scope`: `str` - Same as ReconciliationConfig
- `company`: `ForeignKey(Company)` - Optional
- `user`: `ForeignKey(User)` - Optional

#### Basic Fields
- `name`: `str` - Pipeline name
- `description`: `Text` - Optional description
- `is_default`: `bool` - Whether this is the default pipeline

#### Pipeline Behavior
- `auto_apply_score`: `Decimal` (default: 1.0) - Confidence threshold for auto-applying matches
- `max_suggestions`: `int` (default: 1000) - Maximum suggestions across all stages
- `soft_time_limit_seconds`: `int` (optional) - Overall runtime limit

**Relationships:**
- `stages`: One-to-many with `ReconciliationPipelineStage` (ordered by `order`)

### ReconciliationPipelineStage

Links a pipeline to a config and defines optional per-stage overrides.

**Location:** `accounting/models.py`

**Key Fields:**

#### Required Fields
- `pipeline`: `ForeignKey(ReconciliationPipeline)`
- `config`: `ForeignKey(ReconciliationConfig)`
- `order`: `int` - Execution order (must be unique per pipeline)
- `enabled`: `bool` (default: True) - Whether this stage is enabled

#### Optional Overrides
All override fields are optional. When `null`, they inherit from the linked `ReconciliationConfig`:

- `max_group_size_bank`: `int` (optional)
- `max_group_size_book`: `int` (optional)
- `amount_tolerance`: `Decimal` (optional)
- `group_span_days`: `int` (optional)
- `avg_date_delta_days`: `int` (optional)
- `embedding_weight`: `Decimal` (optional)
- `amount_weight`: `Decimal` (optional)
- `currency_weight`: `Decimal` (optional)
- `date_weight`: `Decimal` (optional)

**Note:** Override weights must still sum to 1.0 if provided.

### ReconciliationTask

Represents a reconciliation execution.

**Location:** `accounting/models.py`

**Key Fields:**

#### Status
- `status`: `str` - Task status
  - `"queued"`: Waiting to start
  - `"running"`: Currently executing
  - `"completed"`: Finished successfully
  - `"failed"`: Failed with error
  - `"cancelled"`: Cancelled by user
- `task_id`: `str` - Celery task ID (if async)
- `tenant_id`: `str` - Company/tenant identifier

#### Configuration Reference
- `config`: `ForeignKey(ReconciliationConfig)` - Config used (if single config)
- `pipeline`: `ForeignKey(ReconciliationPipeline)` - Pipeline used (if pipeline)
- `config_name`: `str` - Snapshot of config name
- `pipeline_name`: `str` - Snapshot of pipeline name
- `soft_time_limit_seconds`: `int` - Effective runtime limit used

#### Execution Data
- `parameters`: `JSONField` - Input parameters
- `result`: `JSONField` - Execution results
- `error_message`: `Text` - Error details (if failed)

#### Statistics
- `bank_candidates`: `int` - Number of bank transaction candidates
- `journal_candidates`: `int` - Number of journal entry candidates
- `suggestion_count`: `int` - Number of suggestions generated
- `matched_bank_transactions`: `int` - Number of matched bank transactions
- `matched_journal_entries`: `int` - Number of matched journal entries
- `auto_match_enabled`: `bool` - Whether auto-matching was enabled
- `auto_match_applied`: `int` - Number of auto-applied matches
- `auto_match_skipped`: `int` - Number of skipped auto-matches
- `duration_seconds`: `float` - Execution duration

### Reconciliation

Represents a matched relationship between bank transactions and journal entries.

**Location:** `accounting/models.py`

**Key Fields:**

#### Relationships
- `journal_entries`: `ManyToMany(JournalEntry)` - Matched journal entries
- `bank_transactions`: `ManyToMany(BankTransaction)` - Matched bank transactions

#### Status
- `status`: `str` - Reconciliation status
  - `"pending"`: Pending review
  - `"matched"`: Matched
  - `"unmatched"`: Unmatched
  - `"review"`: Pending review
  - `"approved"`: Approved

#### Metadata
- `reference`: `str` - Optional reference
- `notes`: `Text` - Optional notes

#### Computed Properties
- `total_journal_amount`: Sum of journal entry amounts
- `total_bank_amount`: Sum of bank transaction amounts
- `discrepancy`: Difference between bank and journal totals

### ReconciliationSuggestion

Represents a proposed match suggestion.

**Location:** `accounting/models.py`

**Key Fields:**

#### Status
- `status`: `str`
  - `"pending"`: No decision yet
  - `"accepted"`: Used to create reconciliation
  - `"rejected"`: Explicitly rejected
  - `"superseded"`: Another suggestion accepted instead

#### Reference
- `task`: `ForeignKey(ReconciliationTask)` - Task that generated this suggestion
- `company_id`: `int` - Company ID

#### Match Data
- `match_type`: `str` - Type of match (e.g., "1-to-1", "many-to-many")
- `confidence_score`: `Decimal` - Confidence score (0-1)
- `bank_transaction_ids`: `JSONField` - List of bank transaction IDs
- `journal_entry_ids`: `JSONField` - List of journal entry IDs

---

## Reconciliation Config

### Creating a Config

```python
from accounting.models import ReconciliationConfig

config = ReconciliationConfig.objects.create(
    scope="company",
    company_id=1,
    name="High Precision Match",
    description="Strict matching for high-value transactions",
    
    # Scoring weights (must sum to 1.0)
    embedding_weight=0.60,  # Emphasize description similarity
    amount_weight=0.30,      # Amount must be close
    currency_weight=0.05,     # Currency must match
    date_weight=0.05,        # Date must be close
    
    # Tolerances
    amount_tolerance=0.01,   # Allow $0.01 difference
    group_span_days=1,       # Max 1 day span within group
    avg_date_delta_days=1,   # Max 1 day difference between groups
    
    # Group sizes
    max_group_size_bank=1,   # Single bank transaction
    max_group_size_book=1,   # Single journal entry
    
    # Thresholds
    min_confidence=0.95,     # Very high confidence required
    max_suggestions=500,
    
    # Filters
    bank_filters={
        "min_amount": 1000,  # Only transactions >= $1000
    },
    book_filters={
        "min_amount": 1000,
    },
)
```

### Config Variables and Their Impact

#### Scoring Weights

**`embedding_weight`** (default: 0.50)
- **Impact**: Controls how much description similarity affects confidence
- **Higher value**: More emphasis on semantic similarity of descriptions
- **Lower value**: Less emphasis on description matching
- **Use case**: Increase for transactions with descriptive text, decrease for generic descriptions

**`amount_weight`** (default: 0.35)
- **Impact**: Controls how much amount matching affects confidence
- **Higher value**: Amount must match more closely
- **Lower value**: Amount differences are more acceptable
- **Use case**: Increase for exact amount matching, decrease when fees/adjustments are common

**`currency_weight`** (default: 0.10)
- **Impact**: Controls how much currency matching affects confidence
- **Higher value**: Currency must match
- **Lower value**: Currency differences are more acceptable
- **Use case**: Increase for single-currency companies, decrease for multi-currency

**`date_weight`** (default: 0.05)
- **Impact**: Controls how much date proximity affects confidence
- **Higher value**: Dates must be closer
- **Lower value**: Date differences are more acceptable
- **Use case**: Increase for real-time reconciliation, decrease for batch processing

#### Tolerance Fields

**`amount_tolerance`** (default: 0)
- **Impact**: Maximum allowed difference between bank and book amounts
- **Higher value**: Allows larger amount differences (e.g., fees, rounding)
- **Lower value**: Requires exact or near-exact amounts
- **Use case**: Set to 0.01 for exact matching, 10.00 for loose matching with fees

**`group_span_days`** (default: 2)
- **Impact**: Maximum date span allowed within a candidate group
- **Higher value**: Allows groups with transactions spread over more days
- **Lower value**: Requires transactions to be closer in time
- **Use case**: Increase for batch transactions, decrease for real-time matching

**`avg_date_delta_days`** (default: 2)
- **Impact**: Maximum difference between weighted-average dates of bank and book groups
- **Higher value**: Allows larger date differences between groups
- **Lower value**: Requires groups to be closer in time
- **Use case**: Increase for delayed book entries, decrease for same-day matching

#### Group Size Fields

**`max_group_size_bank`** (default: 1)
- **Impact**: Maximum number of bank transactions in a match group
- **Higher value**: Allows many-to-one matching (multiple banks → one book)
- **Lower value**: Restricts to one-to-one or one-to-many
- **Use case**: Set to 1 for simple matching, 3+ for batch reconciliation

**`max_group_size_book`** (default: 1)
- **Impact**: Maximum number of journal entries in a match group
- **Higher value**: Allows one-to-many matching (one bank → multiple books)
- **Lower value**: Restricts to one-to-one or many-to-one
- **Use case**: Set to 1 for simple matching, 3+ for split transactions

#### Threshold Fields

**`min_confidence`** (default: 0.90)
- **Impact**: Minimum confidence score to include a suggestion
- **Higher value**: Only very confident matches are suggested
- **Lower value**: More suggestions, including lower-confidence matches
- **Use case**: Increase for automated matching, decrease for manual review

**`max_suggestions`** (default: 1000)
- **Impact**: Maximum number of suggestions to return
- **Higher value**: More suggestions (may be slower)
- **Lower value**: Fewer suggestions (faster)
- **Use case**: Adjust based on data volume and performance requirements

**`max_alternatives_per_match`** (default: 2)
- **Impact**: Number of alternative matches to return per anchor
- **Higher value**: More alternative suggestions
- **Lower value**: Only the best match
- **Use case**: Increase for manual review, decrease for automated matching

#### Behavior Fields

**`allow_mixed_signs`** (default: False)
- **Impact**: Whether to allow groups with mixed positive/negative amounts
- **True**: Allows matching positive and negative amounts together
- **False**: Only matches amounts with the same sign as the bank transaction
- **Use case**: Set to True for complex transactions with reversals/adjustments

---

## Reconciliation Pipeline

### Creating a Pipeline

```python
from accounting.models import ReconciliationPipeline, ReconciliationPipelineStage

# Create pipeline
pipeline = ReconciliationPipeline.objects.create(
    scope="company",
    company_id=1,
    name="Multi-Stage Reconciliation",
    description="Progressive matching: exact → fuzzy → many-to-many",
    auto_apply_score=1.0,  # Auto-apply perfect matches
    max_suggestions=2000,
)

# Create stages
# Stage 1: Exact 1-to-1 matches
exact_config = ReconciliationConfig.objects.get(name="Exact Match")
ReconciliationPipelineStage.objects.create(
    pipeline=pipeline,
    config=exact_config,
    order=1,
    enabled=True,
)

# Stage 2: Fuzzy matches with overrides
fuzzy_config = ReconciliationConfig.objects.get(name="Fuzzy Match")
ReconciliationPipelineStage.objects.create(
    pipeline=pipeline,
    config=fuzzy_config,
    order=2,
    enabled=True,
    # Override some settings for this stage
    amount_tolerance=10.00,
    group_span_days=5,
    embedding_weight=0.40,  # Less emphasis on embeddings
    amount_weight=0.50,     # More emphasis on amounts
)

# Stage 3: Many-to-many matches
m2m_config = ReconciliationConfig.objects.get(name="Many-to-Many")
ReconciliationPipelineStage.objects.create(
    pipeline=pipeline,
    config=m2m_config,
    order=3,
    enabled=True,
    max_group_size_bank=3,
    max_group_size_book=3,
)
```

### Pipeline Execution Flow

1. **Stage 1**: Run with first config, mark matched items as used
2. **Stage 2**: Run with second config on remaining unmatched items
3. **Stage 3**: Continue through all enabled stages
4. **Result**: Combined suggestions from all stages

### Pipeline Variables

**`auto_apply_score`** (default: 1.0)
- **Impact**: Confidence threshold for automatically creating reconciliations
- **Higher value**: Only perfect matches are auto-applied
- **Lower value**: More matches are auto-applied
- **Use case**: Set to 1.0 for fully automated, 0.95 for semi-automated

**`max_suggestions`** (default: 1000)
- **Impact**: Maximum total suggestions across all stages
- **Higher value**: More suggestions (may be slower)
- **Lower value**: Fewer suggestions (faster)
- **Use case**: Adjust based on data volume

**`soft_time_limit_seconds`** (optional)
- **Impact**: Overall runtime limit for the pipeline
- **Use case**: Set to prevent long-running pipelines

---

## Matching Functions

### Matching Engine

**Location:** `accounting/services/reconciliation_service.py`

**Class:** `ReconciliationPipelineEngine`

The engine executes matching stages in sequence, using different strategies based on the config.

### Matching Strategies

#### 1. Exact 1-to-1 Matching

**Function:** `_run_exact_1_to_1()`

**Behavior:**
- Matches one bank transaction with one journal entry
- Requires exact amount match (within tolerance)
- Requires same currency
- Requires date within `avg_date_delta_days`
- Uses embedding similarity for confidence

**Variables Impact:**
- `amount_tolerance`: Maximum amount difference
- `avg_date_delta_days`: Maximum date difference
- `embedding_weight`: How much description similarity matters
- `min_confidence`: Minimum score to include

#### 2. Fuzzy Matching

**Function:** `_run_fuzzy()`

**Behavior:**
- Similar to exact but allows larger tolerances
- Uses weighted confidence scoring
- Can match with slight amount/date differences

**Variables Impact:**
- `amount_tolerance`: Larger values allow more flexibility
- `group_span_days`: Allows date spread within groups
- `avg_date_delta_days`: Allows date differences between groups
- All weights affect confidence calculation

#### 3. One-to-Many Matching

**Function:** `_run_one_to_many()`

**Behavior:**
- Matches one bank transaction with multiple journal entries
- Sum of journal entries must equal bank amount (within tolerance)
- Journal entries must be within `group_span_days`
- Weighted-average date must be within `avg_date_delta_days` of bank date

**Variables Impact:**
- `max_group_size_book`: Maximum journal entries in group
- `amount_tolerance`: Maximum difference between sum and bank amount
- `group_span_days`: Maximum date span of journal entries
- `avg_date_delta_days`: Maximum date difference from bank transaction

#### 4. Many-to-One Matching

**Function:** `_run_many_to_one()`

**Behavior:**
- Matches multiple bank transactions with one journal entry
- Sum of bank transactions must equal journal amount (within tolerance)
- Bank transactions must be within `group_span_days`
- Weighted-average date must be within `avg_date_delta_days` of journal date

**Variables Impact:**
- `max_group_size_bank`: Maximum bank transactions in group
- `amount_tolerance`: Maximum difference between sum and journal amount
- `group_span_days`: Maximum date span of bank transactions
- `avg_date_delta_days`: Maximum date difference from journal entry

#### 5. Many-to-Many Matching

**Function:** `_run_many_to_many()`

**Behavior:**
- Matches multiple bank transactions with multiple journal entries
- Sums must match within tolerance
- Both groups must satisfy span constraints
- Weighted-average dates must be within delta

**Variables Impact:**
- `max_group_size_bank`: Maximum bank transactions
- `max_group_size_book`: Maximum journal entries
- `amount_tolerance`: Maximum sum difference
- `group_span_days`: Maximum span for both groups
- `avg_date_delta_days`: Maximum date difference
- `allow_mixed_signs`: Whether to allow mixed positive/negative amounts

### Confidence Score Calculation

The confidence score is calculated as a weighted sum:

```python
confidence = (
    embedding_weight * embedding_similarity +
    amount_weight * amount_score +
    currency_weight * currency_score +
    date_weight * date_score
)
```

Where:
- **`embedding_similarity`**: Cosine similarity between description embeddings (0-1)
- **`amount_score`**: 1 - (abs(difference) / tolerance) if within tolerance, else 0
- **`currency_score`**: 1 if currencies match, 0 otherwise
- **`date_score`**: 1 - (abs(date_delta) / avg_date_delta_days) if within delta, else 0

### Matching Process

1. **Candidate Selection**: Filter bank and book transactions based on filters
2. **Group Generation**: Generate candidate groups based on group size limits
3. **Constraint Checking**: 
   - Amount tolerance
   - Currency matching
   - Date span constraints
   - Date delta constraints
4. **Confidence Calculation**: Calculate weighted confidence score
5. **Filtering**: Remove suggestions below `min_confidence`
6. **Deduplication**: Remove duplicate suggestions
7. **Ranking**: Sort by confidence score (descending)
8. **Limiting**: Return top `max_suggestions`

---

## Variable Impact on Matching

### Amount Tolerance

**Variable:** `amount_tolerance`

**Impact on Matching:**
- **Exact Matching** (`amount_tolerance = 0`): Only matches with exact amounts
- **Fuzzy Matching** (`amount_tolerance > 0`): Allows differences (e.g., fees, rounding)
- **Loose Matching** (`amount_tolerance = 100`): Allows significant differences

**Formula:**
```python
amount_score = max(0, 1 - (abs(difference) / amount_tolerance))
```

**Example:**
- Bank: $1000.00
- Book: $1000.05
- Tolerance: $0.10
- Score: 1 - (0.05 / 0.10) = 0.50

### Group Span Days

**Variable:** `group_span_days`

**Impact on Matching:**
- **Tight** (`group_span_days = 1`): All transactions in group must be within 1 day
- **Moderate** (`group_span_days = 3`): Allows 3-day spread
- **Loose** (`group_span_days = 7`): Allows week-long spread

**Use Case:**
- Set to 1 for same-day transactions
- Set to 3-5 for batch processing
- Set to 7+ for monthly reconciliation

### Average Date Delta Days

**Variable:** `avg_date_delta_days`

**Impact on Matching:**
- **Tight** (`avg_date_delta_days = 1`): Bank and book groups must be within 1 day
- **Moderate** (`avg_date_delta_days = 3`): Allows 3-day difference
- **Loose** (`avg_date_delta_days = 7`): Allows week-long difference

**Formula:**
```python
bank_avg_date = weighted_average(bank_transaction_dates)
book_avg_date = weighted_average(journal_entry_dates)
delta = abs(bank_avg_date - book_avg_date).days
if delta > avg_date_delta_days:
    reject_match
```

### Group Sizes

**Variables:** `max_group_size_bank`, `max_group_size_book`

**Impact on Matching:**
- **1-to-1** (`max_group_size_bank = 1`, `max_group_size_book = 1`): Simple matching
- **1-to-Many** (`max_group_size_bank = 1`, `max_group_size_book = 3`): One bank → multiple books
- **Many-to-1** (`max_group_size_bank = 3`, `max_group_size_book = 1`): Multiple banks → one book
- **Many-to-Many** (`max_group_size_bank = 3`, `max_group_size_book = 3`): Complex matching

**Performance Impact:**
- Larger group sizes = exponentially more combinations to check
- Use with caution for large datasets

### Scoring Weights

**Variables:** `embedding_weight`, `amount_weight`, `currency_weight`, `date_weight`

**Impact on Confidence:**
- **High embedding_weight**: Emphasizes description similarity
- **High amount_weight**: Emphasizes amount matching
- **High currency_weight**: Requires currency match
- **High date_weight**: Requires date proximity

**Example Configurations:**

**Description-Focused:**
```python
embedding_weight=0.70  # High emphasis on descriptions
amount_weight=0.20
currency_weight=0.05
date_weight=0.05
```

**Amount-Focused:**
```python
embedding_weight=0.20
amount_weight=0.70     # High emphasis on amounts
currency_weight=0.05
date_weight=0.05
```

**Balanced:**
```python
embedding_weight=0.50  # Equal emphasis
amount_weight=0.35
currency_weight=0.10
date_weight=0.05
```

---

## API Endpoints

### Reconciliation Configs

#### List Configs
```
GET /api/reconciliation_configs/
```

**Query Parameters:**
- `scope`: Filter by scope (global, company, user, company_user)
- `company_id`: Filter by company
- `is_default`: Filter default configs

**Response:**
```json
[
  {
    "id": 1,
    "name": "High Precision Match",
    "scope": "company",
    "company": 1,
    "embedding_weight": "0.60",
    "amount_weight": "0.30",
    "currency_weight": "0.05",
    "date_weight": "0.05",
    "amount_tolerance": "0.01",
    "group_span_days": 1,
    "avg_date_delta_days": 1,
    "max_group_size_bank": 1,
    "max_group_size_book": 1,
    "min_confidence": "0.95",
    "max_suggestions": 500,
    "is_default": false
  }
]
```

#### Get Resolved Configs
```
GET /api/reconciliation_configs/resolved/
```

Returns all configs available to the current user (global + company + user + company_user).

#### Create Config
```
POST /api/reconciliation_configs/
{
  "scope": "company",
  "company": 1,
  "name": "My Config",
  "embedding_weight": "0.50",
  "amount_weight": "0.35",
  "currency_weight": "0.10",
  "date_weight": "0.05",
  "amount_tolerance": "10.00",
  "group_span_days": 3,
  "avg_date_delta_days": 3,
  "max_group_size_bank": 2,
  "max_group_size_book": 2,
  "min_confidence": "0.80",
  "max_suggestions": 1000,
  "bank_filters": {
    "min_amount": 100
  },
  "book_filters": {
    "min_amount": 100
  }
}
```

#### Update Config
```
PUT /api/reconciliation_configs/{id}/
{
  "amount_tolerance": "5.00",
  "min_confidence": "0.85"
}
```

#### Delete Config
```
DELETE /api/reconciliation_configs/{id}/
```

### Reconciliation Pipelines

#### List Pipelines
```
GET /api/reconciliation-pipelines/
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Multi-Stage Reconciliation",
    "scope": "company",
    "company": 1,
    "auto_apply_score": "1.00",
    "max_suggestions": 2000,
    "stages": [
      {
        "id": 1,
        "order": 1,
        "enabled": true,
        "config": {
          "id": 1,
          "name": "Exact Match"
        },
        "max_group_size_bank": null,
        "amount_tolerance": null
      }
    ]
  }
]
```

#### Get Resolved Pipelines
```
GET /api/reconciliation-pipelines/resolved/
```

#### Create Pipeline
```
POST /api/reconciliation-pipelines/
{
  "scope": "company",
  "company": 1,
  "name": "My Pipeline",
  "description": "Three-stage matching",
  "auto_apply_score": "1.00",
  "max_suggestions": 2000
}
```

#### Add Stage to Pipeline
```
POST /api/reconciliation-pipelines/{pipeline_id}/stages/
{
  "config": 1,
  "order": 1,
  "enabled": true,
  "amount_tolerance": "10.00",  // Optional override
  "max_group_size_bank": 2      // Optional override
}
```

#### Update Pipeline
```
PUT /api/reconciliation-pipelines/{id}/
{
  "auto_apply_score": "0.95",
  "max_suggestions": 1500
}
```

### Reconciliation Tasks

#### Start Reconciliation Task
```
POST /api/reconciliation-tasks/start/
{
  "config_id": 1,              // Use single config
  // OR
  "pipeline_id": 1,             // Use pipeline
  "bank_ids": [1, 2, 3],        // Optional: specific bank transactions
  "book_ids": [10, 20, 30],     // Optional: specific journal entries
  "auto_match_100": false         // Auto-apply perfect matches
}
```

**Response:**
```json
{
  "id": 123,
  "task_id": "celery-task-id",
  "status": "queued",
  "config": 1,
  "config_name": "High Precision Match",
  "parameters": {
    "bank_ids": [1, 2, 3],
    "auto_match_100": false
  }
}
```

#### Get Task Status
```
GET /api/reconciliation-tasks/{id}/
```

**Response:**
```json
{
  "id": 123,
  "status": "completed",
  "bank_candidates": 100,
  "journal_candidates": 150,
  "suggestion_count": 85,
  "matched_bank_transactions": 80,
  "matched_journal_entries": 80,
  "auto_match_applied": 75,
  "duration_seconds": 12.5,
  "result": {
    "suggestions": [...],
    "stats": {...}
  }
}
```

#### Cancel Task
```
POST /api/reconciliation-tasks/{id}/cancel/
{
  "reason": "User cancelled"
}
```

#### List Tasks
```
GET /api/reconciliation-tasks/
```

**Query Parameters:**
- `status`: Filter by status (queued, running, completed, failed, cancelled)
- `tenant_id`: Filter by tenant

#### Get Queued Tasks
```
GET /api/reconciliation-tasks/queued/
```

### Reconciliations

#### List Reconciliations
```
GET /api/reconciliation/
```

**Query Parameters:**
- `status`: Filter by status (comma-separated: `matched,approved`)
- `bank_transaction`: Filter by bank transaction ID
- `journal_entry`: Filter by journal entry ID

#### Create Reconciliation
```
POST /api/reconciliation/
{
  "bank_transactions": [1, 2, 3],
  "journal_entries": [10, 20, 30],
  "status": "matched",
  "reference": "REF-001",
  "notes": "Manual match"
}
```

#### Update Reconciliation
```
PUT /api/reconciliation/{id}/
{
  "status": "approved",
  "notes": "Reviewed and approved"
}
```

#### Delete Reconciliation
```
DELETE /api/reconciliation/{id}/
```

### Bank Transactions

#### Finalize Reconciliation Matches
```
POST /api/bank-transactions/finalize_reconciliation_matches/
{
  "matches": [
    {
      "bank_transaction_ids": [1, 2],
      "journal_entry_ids": [10, 20],
      "adjustment_side": "none"  // "bank" | "journal" | "none"
    }
  ],
  "adjustment_side": "none",
  "reference": "BATCH-001",
  "notes": "Batch reconciliation"
}
```

**Adjustment Side:**
- `"none"`: No adjustment (must balance exactly)
- `"bank"`: Create adjustment bank transaction if needed
- `"journal"`: Create adjustment journal entry if needed

**Response:**
```json
{
  "created": [
    {
      "reconciliation_id": 123,
      "status": "matched",
      "bank_ids_used": [1, 2],
      "journal_ids_used": [10, 20]
    }
  ],
  "problems": []
}
```

#### Get Unreconciled Bank Transactions
```
GET /api/bank-transactions/unreconciled/
```

**Query Parameters:**
- `bank_account`: Filter by bank account ID
- `start_date`: Filter by start date
- `end_date`: Filter by end date
- `min_amount`: Filter by minimum amount
- `max_amount`: Filter by maximum amount

---

## Transaction Suggestion System

### Overview

The transaction suggestion system uses embeddings and historical matched data to suggest book transactions for unmatched bank transactions.

**Service:** `BankTransactionSuggestionService`
**Location:** `accounting/services/bank_transaction_suggestion_service.py`

### How It Works

1. **Find Historical Matches**: Uses vector embeddings to find similar bank transactions that were previously matched
2. **Group by Pattern**: Groups historical matches by transaction pattern (journal entry structure)
3. **Calculate Confidence**: Combines embedding similarity, match count, and amount similarity
4. **Generate Suggestions**: Creates transaction and journal entry suggestions based on historical patterns

### Suggest Matches Endpoint

#### Suggest Book Transactions
```
POST /api/bank-transactions/suggest_matches/
{
  "bank_transaction_ids": [1, 2, 3],
  "max_suggestions_per_bank": 5,
  "min_confidence": 0.3,
  "min_match_count": 1
}
```

**Parameters:**
- `bank_transaction_ids`: `List[int]` - Required. List of unmatched bank transaction IDs
- `max_suggestions_per_bank`: `int` (default: 5) - Maximum suggestions per bank transaction
- `min_confidence`: `float` (default: 0.3) - Minimum confidence score (0-1)
- `min_match_count`: `int` (default: 1) - Minimum number of historical matches required

**Response:**
The endpoint returns two types of suggestions:

1. **`use_existing_book`**: Use an existing unmatched journal entry + create complementing entries
2. **`create_new`**: Create a new transaction + all journal entries

```json
{
  "suggestions": [
    {
      "bank_transaction_id": 1,
      "bank_transaction": {
        "id": 1,
        "date": "2025-01-15",
        "amount": "1000.00",
        "description": "Payment to Vendor ABC",
        "bank_account_id": 5,
        "entity_id": 1,
        "currency_id": 1
      },
      "suggestions": [
        {
          "suggestion_type": "use_existing_book",
          "confidence_score": 0.82,
          "similarity": 0.75,
          "amount_match_score": 0.90,
          "existing_journal_entry": {
            "id": 100,
            "transaction_id": 50,
            "account_id": 5,
            "account_code": "1000",
            "account_name": "Cash",
            "debit_amount": "800.00",
            "credit_amount": null,
            "description": "Payment to Vendor ABC",
            "date": "2025-01-15"
          },
          "complementing_journal_entries": [
            {
              "account_id": 10,
              "account_code": "5000",
              "account_name": "Accounts Payable",
              "debit_amount": "200.00",
              "credit_amount": null,
              "description": "Payment to Vendor ABC",
              "cost_center_id": null
            }
          ],
          "amount_difference": "200.00"
        },
        {
          "suggestion_type": "create_new",
          "confidence_score": 0.85,
          "match_count": 5,
          "pattern": "10:1000.00:0|5:0:1000.00",
          "transaction": {
            "date": "2025-01-15",
            "entity_id": 1,
            "description": "Payment to Vendor ABC",
            "amount": "1000.00",
            "currency_id": 1,
            "state": "pending"
          },
          "journal_entries": [
            {
              "account_id": 10,
              "account_code": "5000",
              "account_name": "Accounts Payable",
              "debit_amount": "1000.00",
              "credit_amount": null,
              "description": "Payment to Vendor ABC",
              "cost_center_id": null
            },
            {
              "account_id": 5,
              "account_code": "1000",
              "account_name": "Cash",
              "debit_amount": null,
              "credit_amount": "1000.00",
              "description": "Payment to Vendor ABC",
              "cost_center_id": null
            }
          ],
          "historical_matches": [
            {
              "bank_transaction_id": 50,
              "transaction_id": 200,
              "similarity": 0.92
            },
            {
              "bank_transaction_id": 51,
              "transaction_id": 201,
              "similarity": 0.88
            }
          ]
        }
      ]
    }
  ],
  "errors": []
}
```

**Suggestion Types:**

1. **`use_existing_book`**: 
   - Uses an existing unmatched journal entry that matches the bank transaction
   - Creates complementing journal entries to balance the difference
   - Useful when a partial transaction already exists
   - Confidence is based on embedding similarity and amount match

2. **`create_new`**:
   - Creates a completely new transaction and all journal entries
   - Based on historical matched patterns
   - Confidence is based on embedding similarity, match count, and amount similarity

**Confidence Score Calculation:**
```python
confidence = (
    0.5 * avg_embedding_similarity +      # Average similarity to historical matches
    0.3 * match_count_factor +             # More matches = higher confidence
    0.2 * amount_similarity                # Amount similarity to historical
)
```

### Create Suggestions Endpoint

#### Create Transactions and Journal Entries from Suggestions
Supports two types of suggestions:

1. **`use_existing_book`**: Use existing journal entry + create complementing entries
2. **`create_new`**: Create new transaction + all journal entries

```
POST /api/bank-transactions/create_suggestions/
{
  "suggestions": [
    {
      "suggestion_type": "use_existing_book",
      "bank_transaction_id": 1,
      "existing_journal_entry": {
        "id": 100
      },
      "complementing_journal_entries": [
        {
          "account_id": 10,
          "debit_amount": "200.00",
          "credit_amount": null,
          "description": "Payment to Vendor ABC",
          "cost_center_id": null
        }
      ]
    },
    {
      "suggestion_type": "create_new",
      "bank_transaction_id": 2,
      "transaction": {
        "date": "2025-01-15",
        "entity_id": 1,
        "description": "Payment to Vendor ABC",
        "amount": "1000.00",
        "currency_id": 1,
        "state": "pending"
      },
      "journal_entries": [
        {
          "account_id": 10,
          "debit_amount": "1000.00",
          "credit_amount": null,
          "description": "Payment to Vendor ABC",
          "cost_center_id": null
        },
        {
          "account_id": 5,
          "debit_amount": null,
          "credit_amount": "1000.00",
          "description": "Payment to Vendor ABC",
          "cost_center_id": null
        }
      ]
    }
  ]
}
```

**Alternative format** (for `use_existing_book`):
```json
{
  "suggestions": [
    {
      "suggestion_type": "use_existing_book",
      "bank_transaction_id": 1,
      "existing_journal_entry_id": 100,
      "complementing_journal_entries": [...]
    }
  ]
}
```

**Response:**
```json
{
  "created_transactions": [
    {
      "transaction_id": 500,
      "bank_transaction_id": 1,
      "journal_entry_ids": [100, 1000]
    },
    {
      "transaction_id": 501,
      "bank_transaction_id": 2,
      "journal_entry_ids": [1001, 1002]
    }
  ],
  "created_reconciliations": [
    {
      "reconciliation_id": 200,
      "bank_transaction_id": 1,
      "transaction_id": 50
    },
    {
      "reconciliation_id": 201,
      "bank_transaction_id": 2,
      "transaction_id": 501
    }
  ],
  "errors": []
}
```

**What Happens:**

**For `use_existing_book` type:**
1. Uses the existing journal entry (no new transaction created)
2. Creates complementing journal entries linked to the existing transaction
3. Updates transaction and journal entry flags
4. Creates `Reconciliation` record linking bank transaction to all journal entries (existing + new)
5. Sets reconciliation status to `"matched"`

**For `create_new` type:**
1. Creates `Transaction` record
2. Creates `JournalEntry` records
3. Updates transaction and journal entry flags (`is_balanced`, `is_reconciled`, etc.)
4. Creates `Reconciliation` record linking bank transaction to journal entries
5. Sets reconciliation status to `"matched"`

**Auto-Matching:**
- The bank transaction and journal entries (existing or newly created) are automatically matched
- Reconciliation is created with status `"matched"`
- Both sides are marked as reconciled

---

## Usage Examples

### Example 1: Create and Use a Simple Config

```python
# Create config
config = ReconciliationConfig.objects.create(
    scope="company",
    company_id=1,
    name="Exact Match",
    embedding_weight=0.50,
    amount_weight=0.35,
    currency_weight=0.10,
    date_weight=0.05,
    amount_tolerance=0.01,
    group_span_days=1,
    avg_date_delta_days=1,
    max_group_size_bank=1,
    max_group_size_book=1,
    min_confidence=0.90,
)

# Start reconciliation
response = requests.post(
    '/api/reconciliation-tasks/start/',
    json={
        'config_id': config.id,
        'auto_match_100': False,
    }
)

task_id = response.json()['id']

# Check status
status_response = requests.get(f'/api/reconciliation-tasks/{task_id}/')
status = status_response.json()['status']

# Get results when completed
if status == 'completed':
    result = status_response.json()['result']
    suggestions = result['suggestions']
```

### Example 2: Create and Use a Pipeline

```python
# Create pipeline
pipeline = ReconciliationPipeline.objects.create(
    scope="company",
    company_id=1,
    name="Progressive Matching",
    auto_apply_score=1.0,
)

# Stage 1: Exact matches
exact_config = ReconciliationConfig.objects.get(name="Exact Match")
ReconciliationPipelineStage.objects.create(
    pipeline=pipeline,
    config=exact_config,
    order=1,
)

# Stage 2: Fuzzy matches
fuzzy_config = ReconciliationConfig.objects.get(name="Fuzzy Match")
ReconciliationPipelineStage.objects.create(
    pipeline=pipeline,
    config=fuzzy_config,
    order=2,
    amount_tolerance=10.00,  # Override for this stage
)

# Run pipeline
response = requests.post(
    '/api/reconciliation-tasks/start/',
    json={
        'pipeline_id': pipeline.id,
        'auto_match_100': True,  # Auto-apply perfect matches
    }
)
```

### Example 3: Use Transaction Suggestions

```python
# Get suggestions for unmatched bank transactions
response = requests.post(
    '/api/bank-transactions/suggest_matches/',
    json={
        'bank_transaction_ids': [1, 2, 3],
        'max_suggestions_per_bank': 5,
        'min_confidence': 0.5,
    }
)

suggestions_data = response.json()['suggestions']

# Review and select suggestions
approved = []
for bank_suggestion in suggestions_data:
    if bank_suggestion['suggestions']:
        # Use the highest confidence suggestion
        best = bank_suggestion['suggestions'][0]
        
        if best['suggestion_type'] == 'use_existing_book':
            # Use existing journal entry + complementing entries
            if best['confidence_score'] >= 0.7:
                approved.append({
                    'suggestion_type': 'use_existing_book',
                    'bank_transaction_id': bank_suggestion['bank_transaction_id'],
                    'existing_journal_entry': {
                        'id': best['existing_journal_entry']['id']
                    },
                    'complementing_journal_entries': best['complementing_journal_entries'],
                })
        else:
            # Create new transaction
            if best['confidence_score'] >= 0.8:
                approved.append({
                    'suggestion_type': 'create_new',
                    'bank_transaction_id': bank_suggestion['bank_transaction_id'],
                    'transaction': best['transaction'],
                    'journal_entries': best['journal_entries'],
                })

# Create approved suggestions
create_response = requests.post(
    '/api/bank-transactions/create_suggestions/',
    json={'suggestions': approved}
)

# Transactions and reconciliations are automatically created
created = create_response.json()['created_transactions']
```

### Example 4: Manual Reconciliation

```python
# Create reconciliation manually
response = requests.post(
    '/api/reconciliation/',
    json={
        'bank_transactions': [1, 2],
        'journal_entries': [10, 20, 30],
        'status': 'matched',
        'reference': 'MANUAL-001',
        'notes': 'Manually matched after review',
    }
)
```

### Example 5: Batch Finalize Matches

```python
# Finalize multiple matches at once
response = requests.post(
    '/api/bank-transactions/finalize_reconciliation_matches/',
    json={
        'matches': [
            {
                'bank_transaction_ids': [1],
                'journal_entry_ids': [10],
                'adjustment_side': 'none',
            },
            {
                'bank_transaction_ids': [2, 3],
                'journal_entry_ids': [20],
                'adjustment_side': 'journal',  # Create adjustment if needed
            },
        ],
        'adjustment_side': 'none',
        'reference': 'BATCH-2025-01',
        'notes': 'Monthly reconciliation batch',
    }
)
```

---

## Best Practices

### Config Design

1. **Start Strict**: Begin with high `min_confidence` and low tolerances
2. **Progressive Relaxation**: Use pipelines to progressively relax constraints
3. **Weight Tuning**: Adjust weights based on your data characteristics
   - High-value transactions: Increase `amount_weight`
   - Descriptive transactions: Increase `embedding_weight`
   - Multi-currency: Increase `currency_weight`
4. **Performance**: Limit `max_suggestions` and group sizes for large datasets

### Pipeline Design

1. **Stage Order**: Order stages from strictest to loosest
2. **Stage Overrides**: Use overrides to fine-tune individual stages
3. **Auto-Apply**: Set `auto_apply_score` based on your confidence level
4. **Time Limits**: Set `soft_time_limit_seconds` to prevent long runs

### Suggestion System

1. **Confidence Thresholds**: Use `min_confidence` to filter low-quality suggestions
2. **Match Count**: Require `min_match_count >= 2` for more reliable suggestions
3. **Review Process**: Always review suggestions before creating transactions
4. **Historical Data**: More historical matches = better suggestions

### Performance Optimization

1. **Filter Early**: Use `bank_filters` and `book_filters` to reduce candidates
2. **Limit Group Sizes**: Keep `max_group_size_*` small (1-3) for performance
3. **Time Limits**: Set reasonable `soft_time_limit_seconds`
4. **Batch Processing**: Process in smaller batches for large datasets

---

## Troubleshooting

### No Suggestions Generated

**Possible Causes:**
- `min_confidence` too high
- `amount_tolerance` too low
- `group_span_days` or `avg_date_delta_days` too restrictive
- No matching candidates in date range
- All candidates already reconciled

**Solutions:**
- Lower `min_confidence`
- Increase tolerances
- Check date filters
- Verify candidates exist and are unmatched

### Low Confidence Scores

**Possible Causes:**
- Embedding similarity low (descriptions don't match)
- Amount differences too large
- Date differences too large
- Currency mismatches

**Solutions:**
- Increase `embedding_weight` if descriptions are important
- Increase `amount_tolerance`
- Increase `avg_date_delta_days`
- Check currency filters

### Performance Issues

**Possible Causes:**
- Large group sizes
- Too many candidates
- No time limits
- Complex many-to-many matching

**Solutions:**
- Reduce `max_group_size_*`
- Add filters to reduce candidates
- Set `soft_time_limit_seconds`
- Use simpler matching strategies first

### Suggestion System Issues

**No Suggestions:**
- Check if bank transactions have embeddings
- Verify historical matches exist
- Lower `min_confidence` and `min_match_count`

**Low Confidence:**
- More historical matches needed
- Descriptions may be too different
- Amounts may vary significantly

---

## File Locations

- **Models**: `accounting/models.py`
- **Service**: `accounting/services/reconciliation_service.py`
- **Suggestion Service**: `accounting/services/bank_transaction_suggestion_service.py`
- **Views/API**: `accounting/views.py`
- **Serializers**: `accounting/serializers.py`
- **URLs**: `accounting/urls.py`

---

*Last Updated: 2025-11-30*

