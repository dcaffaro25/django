# ETL Pipeline Documentation

**Complete Consolidated Guide** - This document contains all ETL system documentation including API usage, query building, testing methods, HTML interface, rule configuration, examples, and troubleshooting.

## Overview

The ETL (Extract, Transform, Load) Pipeline provides a comprehensive system for importing data from Excel files into the database with automatic data transformation, substitution, validation, and optional integration rule triggers.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ETL PIPELINE ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────┐
                    │   EXCEL FILE UPLOAD  │
                    │  (multiple sheets)   │
                    └──────────┬───────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: TRANSFORMATION (ImportTransformationRule)                          │
│  - Map source columns to target fields                                      │
│  - Filter rows #we should filter out rows as soon as the columns mappings are done, to avoid processing rows that wont be in the output.
│  - Concatenate multiple columns                                             │
│  - Compute derived values                                                   │
│  - Apply default values                                                     │
                                                              │
│  - Extract extra fields for triggers                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: SUBSTITUTION (SubstitutionRule)                                    │
│  - Clean and standardize data                                               │
│  - Replace values (exact, regex, case-insensitive)                          │
│  - Normalize account names, codes, paths                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: POST-PROCESSING                                                    │
│  - JournalEntry: Auto debit/credit calculation                              │
│  - Account lookup by path/code/id                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: VALIDATION                                                         │
│  - Check required fields                                                    │
│  - Validate foreign keys                                                    │
│  - Validate data types                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 5: IMPORT                                                             │
│  - Create records in database                                               │
│  - Handle FK references                                                     │
│  - Track created records                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 6: TRIGGERS (IntegrationRule)                                         │
│  - Fire events for created records                                          │
│  - Execute integration rules                                                │
│  - Create related records (e.g., JournalEntries from Transactions)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Table of Contents

1. [API Endpoints](#api-endpoints)
2. [Using the ETL System](#using-the-etl-system)
   - [Query Building & Execution](#query-building--execution)
   - [HTML Interface](#html-interface)
   - [Testing Methods](#testing-methods)
   - [Understanding Responses (v2 Schema)](#understanding-responses-v2-schema)
3. [ImportTransformationRule](#importtransformationrule)
4. [SubstitutionRule](#substitutionrule)
5. [IntegrationRule](#integrationrule)
6. [Helper Functions](#helper-functions)
7. [Complete Examples](#complete-examples)
8. [Error Handling & Troubleshooting](#error-handling--troubleshooting)
9. [Preview Response Format (v2 Schema)](#preview-response-format-v2-schema)
10. [Response Schema v2 Implementation Details](#response-schema-v2-implementation-details)
11. [Valid Target Models](#valid-target-models)

---

## API Endpoints

### ETL Pipeline Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/core/etl/analyze/` | POST | Analyze Excel file structure (sheets, columns, sample data) |
| `/api/core/etl/preview/` | POST | Run full pipeline with simulation - shows what WOULD be created |
| `/api/core/etl/execute/` | POST | Run full pipeline WITH commit to database |
| `/api/core/etl/transformation-rules/` | GET/POST | List/Create transformation rules |
| `/api/core/etl/transformation-rules/{id}/` | GET/PUT/DELETE | CRUD single transformation rule |
| `/api/core/etl/transformation-rules/available_models/` | GET | List valid target models |
| `/api/core/etl/logs/` | GET | List ETL execution logs |
| `/api/core/etl/logs/{id}/` | GET | Get specific log details |

### Substitution Rule Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/core/substitution-rules/` | GET/POST | List/Create substitution rules |
| `/api/core/substitution-rules/{id}/` | GET/PUT/DELETE | CRUD single substitution rule |

### Integration Rule Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/core/integration-rules/` | GET/POST | List/Create integration rules |
| `/api/core/integration-rules/{id}/` | GET/PUT/DELETE | CRUD single integration rule |
| `/api/core/validate-rule/` | POST | Validate integration rule syntax |
| `/api/core/test-rule/` | POST | Test integration rule in sandbox |

---

## Using the ETL System

### Query Building & Execution

#### Required Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File (multipart) | ✅ Yes | Excel file (.xlsx, .xls) to process |
| `company_id` | Integer | ✅ Yes | ID of the company/tenant to process for |

#### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `row_limit` | Integer | `10` (preview) | Number of rows to process (0 = all rows) |
| `auto_create_journal_entries` | JSON String/Object | `None` | Auto-create journal entries configuration |
| `use_celery` | Boolean/String | `false` | Process asynchronously via Celery |

**Auto-Create Journal Entries Configuration:**
```json
{
  "enabled": true,
  "use_pending_bank_account": true,
  "opposing_account_field": "account_path",
  "opposing_account_lookup": "path",
  "path_separator": " > "
}
```

#### Getting Your Company ID

**Option 1: Via Django Shell**
```python
python manage.py shell
>>> from multitenancy.models import Company
>>> Company.objects.filter(is_deleted=False).values('id', 'name')
```

**Option 2: Via SQL**
```sql
SELECT id, name FROM multitenancy_company WHERE is_deleted = false;
```

### HTML Interface

The easiest way to test ETL preview is through the web interface.

**Access URL:**
```
http://localhost:8000/etl/preview/
```

**Features:**
- ✅ File upload form with drag-and-drop
- ✅ Company selection dropdown
- ✅ AJAX processing (no page reload)
- ✅ Tabbed results view:
  - **Summary** - Overview statistics
  - **Grouped by Row** - Records organized by Excel row
  - **All Records** - Flat list of all records
  - **Failed Rows** - Validation failures
  - **Raw JSON** - Complete API response

**Usage:**
1. Start Django server: `python manage.py runserver`
2. Open browser: `http://localhost:8000/etl/preview/`
3. Select company from dropdown
4. Choose Excel file
5. Click "Preview Transformation"
6. View results in organized tabs

### Testing Methods

This section covers various methods for testing the ETL system, including API testing, debugging workflows, and common testing scenarios.

#### Testing Workflow & Best Practices

**Testing Configuration:**
```json
{
  "auto_create_journal_entries": {
    "enabled": true,
    "use_pending_bank_account": true,
    "opposing_account_field": "account_path",
    "opposing_account_lookup": "path",
    "path_separator": " > "
  },
  "commit": false  // Preview mode - don't commit to database
}
```

**Testing Workflow:**

1. **Wait for Server** - After code changes, wait 30+ seconds for Django auto-reload
2. **Check Backend Logs** - Monitor Django server terminal for errors, stack traces, warnings
3. **Test the Feature** - Send preview request with test Excel file
4. **Analyze Results** - Check response for:
   - ✅ `success: true`
   - ✅ `data.rows[*].transactions` - Should have Transaction records
   - ✅ `data.rows[*].transactions[*].journal_entries` - Should have JournalEntries per Transaction
   - ❌ Any errors in `errors` array
   - ❌ Any warnings in `warnings` array
5. **Debug & Fix** - Use error messages, logs, and stack traces to identify issues
6. **Iterate** - After each fix, wait for reload and re-test

**Success Criteria:**
- ✅ Request returns `success: true`
- ✅ Transactions are created from Excel
- ✅ 2 JournalEntries are created per Transaction (debit + credit pair)
- ✅ No errors in response
- ✅ JournalEntries correctly linked to Transactions
- ✅ Debit/credit amounts calculated correctly based on amount sign

**Common Issues & Solutions:**

| Issue | Solution |
|-------|----------|
| "Transaction matching query does not exist" | Ensure using `Transaction.objects.filter().first()` and checking existence before proceeding |
| "JournalEntry validation error" | Check `bank_designation_pending=True` for pending bank account, ensure account is set when `bank_designation_pending=False` |
| "Account not found" | Verify account lookup logic (path/code/ID resolution) |
| "Server not responding" | Wait longer (60s), check if Django server is running, verify port |

**Logging for Debugging:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info(f"ETL: Starting auto-create for {len(transaction_outputs)} Transactions")
logger.debug(f"ETL: Transaction {transaction_id} found: {transaction is not None}")
logger.debug(f"ETL: Using pending bank: {use_pending_bank}")
logger.error(f"ETL: Error creating JournalEntry: {e}", exc_info=True)
```

#### Method 1: Python (requests library)

```python
import requests
import json
from pathlib import Path

url = "http://localhost:8000/api/core/etl/preview/"
file_path = r"C:\path\to\file.xlsx"
company_id = 10

# Optional: Auto-create journal entries config
auto_config = {
    "enabled": True,
    "use_pending_bank_account": True,
    "opposing_account_field": "account_path",
    "opposing_account_lookup": "path",
    "path_separator": " > "
}

with open(file_path, 'rb') as f:
    files = {
        'file': (Path(file_path).name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    data = {
        'company_id': company_id,
        'row_limit': 0,  # 0 = all rows
        'auto_create_journal_entries': json.dumps(auto_config)
    }
    
    response = requests.post(url, files=files, data=data, timeout=300)
    response.raise_for_status()
    
    result = response.json()
    print(json.dumps(result, indent=2))
```

#### Method 2: cURL

```bash
curl -X POST "http://localhost:8000/api/core/etl/preview/" \
  -F "file=@/path/to/file.xlsx" \
  -F "company_id=10" \
  -F "row_limit=0" \
  -o response.json
```

**Windows PowerShell:**
```powershell
curl -X POST "http://localhost:8000/api/core/etl/preview/" `
  -F "file=@`"C:\path\to\file.xlsx`"" `
  -F "company_id=10" `
  -o response.json
```

#### Method 3: PowerShell (Invoke-RestMethod)

```powershell
$filePath = "C:\path\to\file.xlsx"
$url = "http://localhost:8000/api/core/etl/preview/"

$form = @{
    file = Get-Item -Path $filePath
    company_id = 10
    row_limit = 0
}

$response = Invoke-RestMethod -Uri $url -Method Post -Form $form
$response | ConvertTo-Json -Depth 10 | Out-File -FilePath "response.json" -Encoding UTF8
```

#### Method 4: Postman

1. Method: `POST`
2. URL: `http://localhost:8000/api/core/etl/preview/`
3. Body → form-data:
   - `file` (File): Select Excel file
   - `company_id` (Text): `10`
   - `row_limit` (Text): `0` (optional)
   - `auto_create_journal_entries` (Text): JSON string (optional)

### Understanding Responses (v2 Schema)

#### Response Structure (v2)

The preview and execute responses now use the v2 schema format. Key sections:

**Top-Level Fields:**
- `schema_version: "2.0"` - Indicates response format version
- `success` - Whether processing completed successfully
- `log_id` - ID of the ETL log entry (can query later)
- `file_name` - Name of processed Excel file
- `file_hash` - SHA256 hash of the file
- `is_preview` - `true` for preview, `false` for execute
- `duration_seconds` - Processing time in seconds
- `summary` - Aggregated statistics (see below)
- `sheets` - Sheet processing status
- `warnings` - Global non-blocking issues
- `errors` - Global blocking errors
- `data` - Canonical data block with `rows` and `transformations`

#### Key Response Fields

| Field | Description |
|-------|-------------|
| `schema_version` | Response schema version ("2.0") |
| `success` | Whether processing completed successfully |
| `log_id` | ID of the ETL log entry |
| `duration_seconds` | Processing time in seconds |
| `summary.sheets_found` | Total sheets in Excel file |
| `summary.sheets_processed` | Sheets that had matching rules |
| `summary.total_rows_transformed` | Excel rows transformed |
| `summary.rows.ok` | Count of successfully processed rows |
| `summary.rows.failed` | Count of failed rows |
| `summary.rows.skipped` | Count of skipped rows |
| `summary.models.Transaction.created` | Count of Transactions created |
| `summary.models.JournalEntry.created` | Count of JournalEntries created |
| `data.rows[*]` | ⭐ **Per-row canonical structure** (Most useful!) |
| `data.transformations` | Global transformation metadata |
| `warnings` | Non-blocking issues (global + row-level) |
| `errors` | Blocking errors (global + row-level) |

#### Understanding `data.rows[*]` (v2)

This is the most useful structure for understanding how Excel rows map to database records. Each row contains:

- **Excel metadata** (`excel_row`) - Sheet name, row number, row ID
- **Status** - Overall row status (ok/failed/skipped)
- **Source data** (`source_row`) - Optional original Excel row data
- **Transformed data** (`transformed`) - DTOs after transformation
- **Transformation metadata** (`transformation`) - Rule used, substitutions applied
- **Created records** (`transactions`) - Actual/would-be created records grouped by transaction
- **Row-level issues** (`warnings`, `errors`) - Problems specific to this row

**Example:** To see what Excel row 115 created:
```python
# Find row 115 in response
row_115 = next((r for r in response['data']['rows'] if r['excel_row']['row_number'] == 115), None)

if row_115:
    print(f"Status: {row_115['status']}")
    print(f"Transactions: {len(row_115['transactions'])}")
    for txn_bundle in row_115['transactions']:
        print(f"  - Transaction ID: {txn_bundle['transaction']['id']}")
        print(f"  - Journal Entries: {txn_bundle['journal_entry_count']}")
```

#### Preview vs Execute

**Preview Mode** (`/api/core/etl/preview/`):
- ✅ Safe - No database changes
- ✅ Tests transformations before committing
- ✅ Rolls back all transactions
- ✅ Fast - No cleanup needed

**Execute Mode** (`/api/core/etl/execute/`):
- ⚠️ Commits to database
- ⚠️ Creates actual records
- ⚠️ Cannot undo easily

**Best Practice:** Always preview first, then execute when ready.

---

## ImportTransformationRule

Defines how to transform a specific Excel sheet into a target model format.

### Model Fields

```python
class ImportTransformationRule:
    # Identification
    name: str                    # Rule name
    description: str             # Optional description
    company: FK                  # Company this rule belongs to
    
    # Source Configuration
    source_sheet_name: str       # Excel sheet name (case-insensitive matching)
    skip_rows: int               # Rows to skip at beginning (default: 0)
    header_row: int              # Row containing headers (default: 0, 0-indexed after skip)
    
    # Target Configuration
    target_model: str            # Target model: Transaction, JournalEntry, BankTransaction, etc.
    
    # Transformation Configuration
    column_mappings: JSON        # Required column mappings
    column_concatenations: JSON  # Combine multiple columns
    computed_columns: JSON       # Derived values using expressions
    default_values: JSON         # Static defaults
    row_filter: str              # Filter expression
    
    # Trigger Configuration
    extra_fields_for_trigger: JSON  # Extra fields passed to IntegrationRules
    trigger_options: JSON           # Control which triggers fire
    
    # Execution
    execution_order: int         # Order when processing multiple sheets
    is_active: bool              # Enable/disable rule
```

### Field Details

#### `column_mappings` (Required)

Maps source Excel columns to target model fields. All mapped columns are **required** - the import fails if any column is missing.

**Format:**
```json
{
  "Source Column Name": "target_field_name"
}
```

**Example:**
```json
{
  "Data Lançamento": "date",
  "Descrição": "description",
  "Valor (R$)": "amount",
  "Entidade": "entity_id"
}
```

**Notes:**
- Column matching is **case-insensitive**
- Source column must exist in Excel sheet
- Target field should match model field name

---

#### `column_concatenations` (Optional)

Combines multiple source columns into a single target field.

**Format:**
```json
{
  "target_field": {
    "columns": ["Col1", "Col2", "Col3"],
    "separator": " | ",
    "template": "{Col1} - Doc: {Col2}"
  }
}
```

**Example - Using Separator:**
```json
{
  "description": {
    "columns": ["Histórico", "Complemento", "Referência"],
    "separator": " | "
  }
}
```
Result: `"PIX ENVIADO | FULANO DE TAL | 123456"`

**Example - Using Template:**
```json
{
  "description": {
    "columns": ["Histórico", "Doc"],
    "template": "{Histórico} (Doc: {Doc})"
  }
}
```
Result: `"PIX ENVIADO (Doc: 123456)"`

**Notes:**
- If `template` is provided, it overrides `separator`
- Empty values are skipped when using separator
- Template uses Python format string syntax

---

#### `computed_columns` (Optional)

Computes derived values using Python expressions.

**Format:**
```json
{
  "target_field": "python_expression"
}
```

**Available Context:**
| Variable | Description |
|----------|-------------|
| `row` | Dict with all original Excel columns |
| `transformed` | Dict with already-transformed fields |
| `Decimal` | Python Decimal class |
| `datetime` | Python datetime module |
| `re` | Python regex module |
| `abs`, `str`, `int`, `float`, `len`, `round` | Python builtins |

**Example - Brazilian Number Format:**
```json
{
  "amount": "Decimal(str(row['Valor']).replace('.', '').replace(',', '.'))"
}
```

**Example - Date Parsing:**
```json
{
  "date": "datetime.strptime(str(row['Data']).split()[0], '%d/%m/%Y').strftime('%Y-%m-%d')"
}
```

**Example - Conditional Value:**
```json
{
  "entity_id": "10 if 'PIX' in str(row.get('Tipo', '')) else 5"
}
```

**Example - Using Transformed Data:**
```json
{
  "full_description": "f\"{transformed['description']} - Amount: {transformed['amount']}\""
}
```

---

#### `default_values` (Optional)

Static default values for fields not in the source file.

**Format:**
```json
{
  "field_name": value
}
```

**Example:**
```json
{
  "entity_id": 10,
  "currency_id": 12,
  "state": "pending"
}
```

**Notes:**
- Defaults are applied after column_mappings and computed_columns
- Only applied if field is missing or null

---

#### `row_filter` (Optional)

Python expression to filter rows. Return `True` to include, `False` to skip.

**Format:**
```python
"python_expression_returning_bool"
```

**Example - Skip Empty Amounts:**
```json
"row.get('Valor') is not None and str(row.get('Valor', '')).strip() != ''"
```

**Example - Skip Zero Values:**
```json
"float(str(row['Valor']).replace(',', '.')) != 0"
```

**Example - Only Include Specific Types:**
```json
"row.get('Tipo') in ['PIX', 'TED', 'DOC']"
```

---

#### `extra_fields_for_trigger` (Optional)

Maps Excel columns to extra payload fields passed to IntegrationRule triggers. These fields are NOT saved to the model.

**Format:**
```json
{
  "payload_field_name": "Source Column Name"
}
```

**Example:**
```json
{
  "account_path": "Conta",
  "cost_center_path": "Centro de Custo",
  "reference_number": "Nº Doc"
}
```

**Trigger Payload Structure:**
```json
{
  "transaction_id": 123,
  "transaction": {
    "id": 123,
    "date": "2025-01-15",
    "description": "PIX ENVIADO",
    "amount": "500.00"
  },
  "extra_fields": {
    "account_path": "Assets > Banks > Bradesco",
    "cost_center_path": "Operations",
    "reference_number": "12345"
  },
  "source": "etl_import",
  "log_id": 45
}
```

---

#### `trigger_options` (Optional)

Controls which IntegrationRule events are fired after import.

**Format:**
```json
{
  "enabled": true,
  "events": ["transaction_created"],
  "use_celery": true
}
```

**Fields:**
| Field | Description | Default |
|-------|-------------|---------|
| `enabled` | Enable/disable all triggers | `true` |
| `events` | List of events to fire | Model-specific default |
| `use_celery` | Run triggers async via Celery | `true` |

**Available Events:**
- `transaction_created` - When Transaction is created
- `journal_entry_created` - When JournalEntry is created
- `etl_import_completed` - After entire import completes

---

### Complete Transformation Rule Example

```json
{
  "company": 1,
  "name": "Bradesco Bank Statement Import",
  "description": "Import Bradesco bank statement to create Transactions with JournalEntries",
  
  "source_sheet_name": "Movimentação",
  "skip_rows": 3,
  "header_row": 0,
  "target_model": "Transaction",
  
  "column_mappings": {
    "Data": "date",
    "Descrição": "description"
  },
  
  "column_concatenations": {
    "description": {
      "columns": ["Histórico", "Complemento"],
      "separator": " - "
    }
  },
  
  "computed_columns": {
    "amount": "Decimal(str(row['Valor (R$)']).replace('.', '').replace(',', '.'))",
    "date": "datetime.strptime(str(row['Data']).strip(), '%d/%m/%Y').strftime('%Y-%m-%d')"
  },
  
  "default_values": {
    "entity_id": 10,
    "currency_id": 12,
    "state": "pending"
  },
  
  "row_filter": "row.get('Valor (R$)') is not None and str(row.get('Valor (R$)', '')).strip() != ''",
  
  "extra_fields_for_trigger": {
    "account_path": "Conta Contábil",
    "bank_account_id": "ID Conta Banco"
  },
  
  "trigger_options": {
    "enabled": true,
    "events": ["transaction_created"],
    "use_celery": false
  },
  
  "execution_order": 0,
  "is_active": true
}
```

---

## SubstitutionRule

Defines value replacement rules for data cleaning and standardization.

### Model Fields

```python
class SubstitutionRule:
    company: FK              # Company this rule belongs to
    title: str               # Optional title/description
    model_name: str          # Target model name
    field_name: str          # Field to apply substitution
    match_type: str          # 'exact', 'regex', 'caseless'
    match_value: str         # Value to match
    substitution_value: str  # Replacement value
    filter_conditions: JSON  # Optional conditions for applying
```

### Match Types

#### `exact`
Direct string equality comparison.

```json
{
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "exact",
  "match_value": "Banco Bradesco",
  "substitution_value": "Assets > Banks > Bradesco"
}
```

#### `regex`
Regular expression replacement using `re.sub()`.

```json
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^PIX\\s+",
  "substitution_value": "Transferência PIX - "
}
```

#### `caseless`
Case and accent insensitive comparison.

```json
{
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "ATIVO > BANCOS",
  "substitution_value": "Assets > Banks"
}
```

### Substitution Rule Examples

**Normalize Account Names:**
```json
{
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Ativo > Bancos > Bradesco",
  "substitution_value": "Assets > Banks > Bradesco"
}
```

**Clean Description Prefixes:**
```json
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^(PIX|TED|DOC)\\s*-?\\s*",
  "substitution_value": ""
}
```

**Replace Entity Names with IDs:**
```json
{
  "model_name": "Transaction",
  "field_name": "entity_id",
  "match_type": "exact",
  "match_value": "Main Company",
  "substitution_value": "10"
}
```

---

## IntegrationRule

Event-driven rules that execute code when specific triggers fire.

### Model Fields

```python
class IntegrationRule:
    company: FK                 # Company this rule belongs to
    name: str                   # Rule name
    description: str            # Optional description
    trigger_event: str          # Event that triggers this rule
    execution_order: int        # Order of execution
    filter_conditions: str      # Optional filter expression
    rule: str                   # Formula engine code to execute
    use_celery: bool            # Run async via Celery
    is_active: bool             # Enable/disable
    last_run_at: datetime       # Last execution time
    times_executed: int         # Execution count
```

### Available Triggers

| Trigger | Description | Payload |
|---------|-------------|---------|
| `payroll_approved` | Payroll batch approved | Payroll data |
| `payroll_created` | Payroll batch created | Payroll data |
| `transaction_created` | Transaction created by ETL | Transaction + extra_fields |
| `journal_entry_created` | JournalEntry created by ETL | JournalEntry + extra_fields |
| `etl_import_completed` | ETL import finished | Summary data |

### Trigger Payload Structure

**For `transaction_created`:**
```python
{
    'transaction_id': 123,
    'transaction': {
        'id': 123,
        'date': '2025-01-15',
        'description': 'PIX ENVIADO',
        'amount': '500.00',
        'entity_id': 10,
        'currency_id': 12,
        'state': 'pending'
    },
    'extra_fields': {
        'account_path': 'Expenses > Services',
        'bank_account_id': '5'
    },
    'source': 'etl_import',
    'log_id': 45
}
```

### Rule Code Context

The `rule` field contains Python code executed in a sandboxed environment with access to:

#### Available Variables

| Variable | Type | Description |
|----------|------|-------------|
| `payload` | dict/list | Trigger payload data |
| `company_id` | int | Current company ID |
| `result` | any | Must be set - rule output |

#### Available Functions

| Function | Description |
|----------|-------------|
| `create_transaction(...)` | Create a Transaction |
| `create_journal_entry(...)` | Create a JournalEntry |
| `create_transaction_with_entries(payload)` | Create Transaction + 2 JournalEntries |
| `lookup_account_by_path(path, sep)` | Find Account by hierarchy path |
| `lookup_account_by_code(code)` | Find Account by code |
| `lookup_account_by_name(name)` | Find Account by name |
| `calculate_debit_credit(amount, account)` | Calculate debit/credit amounts |
| `apply_substitutions(model, fields)` | Apply substitution rules |
| `group_by(records, key)` | Group records by key |
| `sum_group(group, key)` | Sum values in group |
| `max_group(group, key)` | Max value in group |
| `min_group(group, key)` | Min value in group |
| `debug_log(...)` | Log debug messages |
| `to_decimal(value, places)` | Convert to Decimal |

#### Available Types

| Type | Description |
|------|-------------|
| `Decimal` | Python Decimal class |
| `Account` | Account model |
| `Transaction` | Transaction model |
| `JournalEntry` | JournalEntry model |

#### Basic Python

| Function | Description |
|----------|-------------|
| `sum`, `len`, `str`, `int`, `float`, `abs` | Python builtins |

---

## Helper Functions

### `create_transaction_with_entries(payload)`

Creates a Transaction with two balanced JournalEntries from a generic payload.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | str | Yes | Transaction date (YYYY-MM-DD) |
| `description` | str | No | Transaction description |
| `amount` | str/Decimal | Yes | Amount (positive or negative) |
| `entity_id` | int | Yes | Entity FK |
| `currency_id` | int | Yes | Currency FK |
| `state` | str | No | Transaction state (default: 'pending') |
| `bank_account_id` | int | No | BankAccount FK (for bank entry) |
| `account_id` | int | No | Opposing Account FK |
| `account_code` | str | No | Opposing Account code |
| `account_path` | str | No | Opposing Account path |
| `path_separator` | str | No | Path separator (default: ' > ') |
| `cost_center_id` | int | No | Cost center FK |

**Returns:**
```python
{
    'transaction': {
        'id': 123,
        'date': '2025-01-15',
        'description': 'PIX ENVIADO',
        'amount': '500.00'
    },
    'bank_journal_entry': {
        'id': 456,
        'account_id': 10,
        'account_name': 'Bradesco Checking',
        'debit_amount': None,
        'credit_amount': '500.00'
    },
    'opposing_journal_entry': {
        'id': 457,
        'account_id': 25,
        'account_name': 'Services',
        'account_path': 'Expenses > Services',
        'debit_amount': '500.00',
        'credit_amount': None
    },
    'errors': [],
    'warnings': []
}
```

**Journal Entry Logic:**
- For **positive amount** (deposit/income):
  - Bank account: DEBIT (asset increases)
  - Opposing account: CREDIT
- For **negative amount** (payment/expense):
  - Bank account: CREDIT (asset decreases)
  - Opposing account: DEBIT

**Example Usage:**
```python
result = create_transaction_with_entries({
    'date': '2025-01-15',
    'description': 'PIX ENVIADO - FORNECEDOR',
    'amount': '-500.00',
    'entity_id': 10,
    'currency_id': 12,
    'bank_account_id': 5,
    'account_path': 'Expenses > Services > Consulting'
})

if result['errors']:
    debug_log(f"Errors: {result['errors']}")
else:
    debug_log(f"Created Transaction {result['transaction']['id']}")
```

---

### `lookup_account_by_path(path, separator=' > ')`

Finds an Account by its hierarchical path.

**Parameters:**
- `path` (str): Account path like "Assets > Banks > Bradesco"
- `separator` (str): Path separator (default: ' > ')

**Returns:** Account instance or None

**Example:**
```python
account = lookup_account_by_path('Assets > Banks > Bradesco')
if account:
    debug_log(f"Found account: {account.id} - {account.name}")
```

---

### `lookup_account_by_code(code)`

Finds an Account by its account_code.

**Parameters:**
- `code` (str): Account code

**Returns:** Account instance or None

**Example:**
```python
account = lookup_account_by_code('1.1.1.001')
```

---

### `lookup_account_by_name(name)`

Finds an Account by name (first match).

**Parameters:**
- `name` (str): Account name

**Returns:** Account instance or None

**Example:**
```python
account = lookup_account_by_name('Bradesco Checking')
```

---

### `calculate_debit_credit(amount, account)`

Calculates debit/credit amounts based on amount sign and account direction.

**Parameters:**
- `amount` (Decimal): Amount (can be positive or negative)
- `account` (Account): Account instance

**Returns:**
```python
{
    'debit_amount': Decimal or None,
    'credit_amount': Decimal or None
}
```

**Example:**
```python
account = lookup_account_by_path('Expenses > Services')
dc = calculate_debit_credit(Decimal('-500.00'), account)
# dc = {'debit_amount': Decimal('500.00'), 'credit_amount': None}
```

---

### `create_journal_entry(...)`

Creates a single JournalEntry.

**Parameters:**
- `transaction_id` (int): Parent transaction ID
- `account_id` (int): Account FK
- `date` (str): Entry date
- `description` (str): Entry description
- `debit_amount` (Decimal): Debit amount (or None)
- `credit_amount` (Decimal): Credit amount (or None)
- `cost_center_id` (int): Optional cost center FK
- `state` (str): Entry state

**Returns:** JournalEntry instance

---

### `create_transaction(...)`

Creates a single Transaction.

**Parameters:**
- `date` (str): Transaction date
- `description` (str): Description
- `amount` (Decimal): Amount
- `entity_id` (int): Entity FK
- `currency_id` (int): Currency FK
- `state` (str): Transaction state

**Returns:** Transaction instance

---

## Complete Examples

### Example 1: Import Bank Statement → Create Transactions + JournalEntries

**Step 1: Create Transformation Rule**

```json
POST /api/core/etl/transformation-rules/
{
  "company": 1,
  "name": "Bradesco Statement",
  "source_sheet_name": "Extrato",
  "target_model": "Transaction",
  
  "column_mappings": {
    "Data": "date",
    "Descrição": "description"
  },
  
  "computed_columns": {
    "amount": "Decimal(str(row['Valor']).replace('.', '').replace(',', '.'))",
    "date": "datetime.strptime(row['Data'], '%d/%m/%Y').strftime('%Y-%m-%d')"
  },
  
  "default_values": {
    "entity_id": 10,
    "currency_id": 12
  },
  
  "extra_fields_for_trigger": {
    "account_path": "Conta Contábil",
    "bank_account_id": "5"
  },
  
  "trigger_options": {
    "enabled": true,
    "events": ["transaction_created"]
  }
}
```

**Step 2: Create Substitution Rules (if needed)**

```json
POST /api/core/substitution-rules/
{
  "company": 1,
  "model_name": "Transaction",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Despesas > Serviços",
  "substitution_value": "Expenses > Services"
}
```

**Step 3: Create Integration Rule**

```json
POST /api/core/integration-rules/
{
  "company": 1,
  "name": "Create JournalEntries from Transaction",
  "trigger_event": "transaction_created",
  "is_active": true,
  "use_celery": false,
  
  "rule": "
# Get payload data
tx_id = payload['transaction_id']
tx = payload['transaction']
extra = payload.get('extra_fields', {})

# Build payload for create_transaction_with_entries helper
# But since Transaction already exists, we'll create JEs manually
amount = Decimal(str(tx['amount']))
account_path = extra.get('account_path')
bank_account_id = extra.get('bank_account_id')

# Look up accounts
bank_account = None
if bank_account_id:
    from accounting.models import BankAccount
    ba = BankAccount.objects.filter(id=int(bank_account_id)).first()
    if ba:
        bank_account = Account.objects.filter(bank_account_id=ba.id).first()

opposing_account = lookup_account_by_path(account_path) if account_path else None

# Calculate debit/credit
abs_amount = abs(amount)
if amount >= 0:
    bank_debit, bank_credit = abs_amount, None
    opp_debit, opp_credit = None, abs_amount
else:
    bank_debit, bank_credit = None, abs_amount
    opp_debit, opp_credit = abs_amount, None

# Create JournalEntries
entries_created = []

if bank_account:
    je1 = create_journal_entry(
        transaction_id=tx_id,
        account_id=bank_account.id,
        date=tx['date'],
        description=tx['description'],
        debit_amount=bank_debit,
        credit_amount=bank_credit,
        state='pending'
    )
    entries_created.append(je1.id)

if opposing_account:
    je2 = create_journal_entry(
        transaction_id=tx_id,
        account_id=opposing_account.id,
        date=tx['date'],
        description=tx['description'],
        debit_amount=opp_debit,
        credit_amount=opp_credit,
        state='pending'
    )
    entries_created.append(je2.id)

result = {'journal_entries_created': entries_created}
"
}
```

**Step 4: Run ETL Import**

```
POST /api/core/etl/execute/
Content-Type: multipart/form-data

file: [bank_statement.xlsx]
company_id: 1
```

---

### Example 2: Using `create_transaction_with_entries` in IntegrationRule

```python
# Integration Rule that creates complete transactions with entries
# from external webhook data

# payload = {'date': '2025-01-15', 'amount': '-500', ...}

result = create_transaction_with_entries({
    'date': payload['date'],
    'description': payload.get('description', 'Imported transaction'),
    'amount': payload['amount'],
    'entity_id': 10,
    'currency_id': 12,
    'bank_account_id': payload.get('bank_account_id'),
    'account_path': payload.get('account_path'),
    'cost_center_id': payload.get('cost_center_id')
})

if result['errors']:
    debug_log(f"Errors: {result['errors']}")
    
result = result  # Set result for rule completion
```

---

## Error Handling & Troubleshooting

### Transformation Errors

```json
{
  "type": "missing_columns",
  "message": "Missing required columns in sheet 'Extrato': ['Valor (R$)']",
  "stage": "transformation",
  "sheet": "Extrato",
  "rule": "Bradesco Statement",
  "missing_columns": ["Valor (R$)"],
  "available_columns": ["Data", "Descrição", "Valor", "Saldo"],
  "suggestion": {"Valor (R$)": ["Valor"]}
}
```

### Substitution Errors

```json
{
  "type": "substitution_error",
  "message": "Error applying substitution rule 'Account Mapping': invalid regex",
  "model": "Transaction",
  "field": "description",
  "value": "PIX ENVIADO..."
}
```

### Validation Errors

```json
{
  "type": "missing_required_field",
  "message": "Row 15 in Transaction is missing required field 'entity_id'",
  "model": "Transaction",
  "row_number": 15,
  "field": "entity_id"
}
```

### Account Lookup Errors

```json
{
  "type": "account_not_found",
  "message": "JournalEntry row 5: Account not found for 'account_path' = 'Invalid > Path'",
  "stage": "post_process",
  "row_number": 5,
  "lookup_type": "path",
  "lookup_value": "Invalid > Path"
}
```

### Common Issues & Solutions

#### Issue 1: Server Not Running
```bash
python manage.py runserver
```

#### Issue 2: Wrong Port
Update URL if server runs on different port:
```
http://localhost:YOUR_PORT/api/core/etl/preview/
```

#### Issue 3: File Path with Spaces (Windows)
**PowerShell:**
```powershell
-F "file=@`"C:\path with spaces\file.xlsx`""
```

**CMD:**
```cmd
-F "file=@\"C:\path with spaces\file.xlsx\""
```

#### Issue 4: Large Files / Timeout
- Use `row_limit` to test with subset first
- Increase timeout: `timeout=600` in requests
- Use Celery: `use_celery=true`

#### Issue 5: Response Too Large
- Save to file instead of printing
- Use `jq` to filter: `cat response.json | jq '.data.would_create_by_row[0:5]'`
- Query specific sections in Python

#### Issue 6: Transaction Matching Query Does Not Exist
Ensure transactions exist before creating JournalEntries:
- Use `Transaction.objects.filter().first()` and check if exists
- Verify transaction ID is correctly linked

#### Issue 7: JournalEntry Validation Error
Check that:
- `bank_designation_pending=True` when using pending bank account
- `account` is set when `bank_designation_pending=False`
- Transaction ID is correctly linked

#### Issue 8: Account Not Found
Verify account lookup logic:
- Path resolution works correctly
- Code resolution works correctly
- ID resolution works correctly

### Debugging Tips

**After making code changes:**
1. Wait at least 30 seconds for Django auto-reload
2. Ping server to verify ready: `curl http://localhost:8000/api/core/etl/transformation-rules/`
3. Monitor backend logs in Django server terminal
4. Check API response `errors` and `warnings` fields

**Add logging to debug:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info(f"ETL: Starting auto-create for {len(transaction_outputs)} Transactions")
logger.debug(f"ETL: Transaction {transaction_id} found: {transaction is not None}")
logger.error(f"ETL: Error creating JournalEntry: {e}", exc_info=True)
```

---

## Best Practices

1. **Always preview first** - Use `/etl/preview/` before `/etl/execute/`

2. **Use substitution rules for normalization** - Clean data before import

3. **Keep transformation rules generic** - Use `extra_fields_for_trigger` for data needed by IntegrationRules

---

## Preview Response Format (v2 Schema)

The `/api/core/etl/preview/` endpoint runs the **complete pipeline simulation** including IntegrationRules, then rolls back all changes. This shows exactly what WOULD be created.

**As of v2.0, the response format has been refactored to a cleaner, more canonical structure with per-row grouping.**

### Response Schema Version

All responses now include `schema_version: "2.0"` to indicate the API response format version.

### Top-Level Response Structure (v2)

```json
{
  "success": true,
  "log_id": 54,
  "file_name": "2025.01.xlsx",
  "file_hash": "f2ab6f...",
  "is_preview": true,
  "duration_seconds": 5.64,
  "schema_version": "2.0",
  
  "summary": {
    "sheets_found": 8,
    "sheets_processed": 1,
    "sheets_skipped": 7,
    "sheets_failed": 0,
    "total_rows_transformed": 5,
    "rows": {
      "ok": 5,
      "failed": 0,
      "skipped": 0
    },
    "models": {
      "Transaction": { "created": 5, "failed": 0 },
      "JournalEntry": { "created": 10, "failed": 0 }
    }
  },
  
  "sheets": {
    "found": ["Sheet1", "Sheet2", ...],
    "processed": ["Base Ajustada"],
    "skipped": ["Summary", ...],
    "failed": []
  },
  
  "warnings": [
    {
      "type": "sheet_skipped",
      "message": "Sheet 'Summary' skipped - no matching rule"
    }
  ],
  "errors": [],
  
  "data": {
    "rows": [ /* see Per-Row Structure below */ ],
    "transformations": { /* see Transformations Block below */ }
  }
}
```

### Per-Row Structure: `data.rows[*]`

Each element in `data.rows` represents one Excel row with all its related data:

```json
{
  "excel_row": {
    "sheet_name": "Base Ajustada",
    "row_number": 2,
    "row_id": "Base Ajustada:2"
  },
  
  "status": "ok",  // "ok", "failed", "skipped", or "ignored"
  
  "source_row": {  // Optional: original Excel row data
    "Valor": 3500,
    "Emissão": "2025-01-19",
    "Conta Contábil": "1.2.3.4.5",
    "Tipo de Conta": "FORNECEDOR",
    "Conta": "Hardware E Software",
    "Nº Doc.": "Cabeamento",
    "Pessoa": "Iw Comercio"
  },
  
  "transformed": {  // DTOs after transformation
    "Transaction": [
      {
        "amount": 3500,
        "date": "2025-01-19",
        "account_path": "Ativos\\Ativo Não Circulante\\Imobilizado\\Computadores e Periféricos",
        "description": "FORNECEDOR | Hardware E Software | Cabeamento | Iw Comercio",
        "state": "pending",
        "entity_id": 10,
        "currency_id": 12
      }
    ]
  },
  
  "transformation": {
    "rule_id": 1,
    "rule_name": "teste",
    "substitutions_applied": [
      {
        "field": "account_path",
        "from": "1.2.3.4.5",
        "to": "Ativos\\Ativo Não Circulante\\Imobilizado\\Computadores e Periféricos",
        "rule_id": 3
      }
    ],
    "extra_fields": ["account_path"]
  },
  
  "transactions": [
    {
      "transaction": {
        "id": 41951,
        "created_at": "2025-12-08T21:54:17.523Z",
        "updated_at": "2025-12-08T21:54:17.523Z",
        "company": 4,
        "date": "2025-01-19",
        "entity": 10,
        "description": "FORNECEDOR | Hardware E Software | Cabeamento | Iw Comercio",
        "amount": "3500.00",
        "currency": 12,
        "state": "pending",
        "balance_validated": false,
        "description_embedding": null,
        "is_balanced": false,
        "is_reconciled": false,
        "is_posted": false
      },
      "journal_entries": [
        {
          "id": 38845,
          "transaction_id": 41951,
          "account_path": "Pending Bank Account",
          "debit_amount": "3500.00",
          "credit_amount": null,
          "bank_designation_pending": true,
          "account_id": null
        },
        {
          "id": 38846,
          "transaction_id": 41951,
          "account_path": "Ativo > Ativo Não Circulante > Imobilizado > Computadores e Periféricos > Valor Original",
          "debit_amount": null,
          "credit_amount": "3500.00",
          "bank_designation_pending": false,
          "account_id": 1213,
          "account_code": null
        }
      ],
      "journal_entry_count": 2
    }
  ],
  
  "other_records": {
    "JournalEntry": [ /* JEs not linked to transactions, if any */ ]
  },
  
  "warnings": [
    {
      "code": "ACCOUNT_NOT_FOUND",
      "message": "Account 1.1.3.05 not found",
      "field": "account_code"
    }
  ],
  
  "errors": [
    {
      "code": "VALIDATION_ERROR",
      "message": "Invalid amount",
      "field": "amount"
    }
  ]
}
```

#### Row Status Values

| Status | Description |
|--------|-------------|
| `ok` | Row successfully transformed and mapped to created records |
| `failed` | Row has blocking errors and would not create records |
| `skipped` | Row was explicitly skipped (e.g. by filter/rule) |
| `ignored` | Row was not processed (non-error state) |

### Transformations Block: `data.transformations`

Global transformation-related fields are consolidated here:

```json
{
  "rules_used": [
    {
      "id": 1,
      "name": "teste",
      "target_model": "Transaction",
      "source_sheet_name": "Base Ajustada",
      "column_mappings": {
        "Valor": "amount",
        "Emissão": "date",
        "Conta Contábil": "account_path"
      },
      "column_concatenations": {
        "description": {
          "columns": ["Tipo de Conta", "Conta", "Nº Doc.", "Pessoa"],
          "separator": " | "
        }
      },
      "computed_columns": {},
      "default_values": {
        "state": "pending",
        "entity_id": 10,
        "currency_id": 12
      },
      "row_filter": "row.get('Valor') and ...",
      "extra_fields_for_trigger": {},
      "trigger_options": {},
      "skip_rows": 0,
      "header_row": 0,
      "execution_order": 0
    }
  ],
  
  "import_errors": [
    {
      "type": "fields_moved_to_extra",
      "message": "Fields not in Transaction model moved to extra_fields: ['account_path']",
      "fields": ["account_path"],
      "hint": "Use extra_fields_for_trigger in your transformation rule to pass these to IntegrationRules"
    }
  ],
  
  "integration_rules_available": [],
  "integration_rules_preview": []
}
```

### How Preview Works

1. **Transform** - Apply column mappings, concatenations, computed columns
2. **Substitute** - Apply SubstitutionRules
3. **Simulate Import** - Create records in a transaction
4. **Simulate Triggers** - Execute IntegrationRules
5. **Capture Results** - Record what would be created
6. **Rollback** - Undo all changes (nothing persisted)

This allows users to see the **complete end-to-end result** before committing.

### Migration from v1 to v2

**Breaking Changes:**
- `import_result` field removed - no longer in response
- `data` structure changed - now contains `rows` and `transformations` only
- Legacy fields removed:
  - `data.transformed_data` (now in `data.rows[*].transformed`)
  - `data.would_create` (now in `data.rows[*].transactions` and `other_records`)
  - `data.would_create_by_row` (now `data.rows`)
  - `data.would_fail` (now in `data.rows[*]` where `status: "failed"`)

**Migration Guide:**
- Use `data.rows[*]` instead of `would_create_by_row`
- Access transformed data via `data.rows[*].transformed`
- Access created records via `data.rows[*].transactions`
- Compute summary from `data.rows` (or use the provided `summary` block)
- Find transformation rules in `data.transformations.rules_used`

4. **Test integration rules in sandbox** - Use `/api/core/test-rule/` endpoint

5. **Use `create_transaction_with_entries`** - For complete double-entry bookkeeping

6. **Handle errors gracefully** - Check `errors` and `warnings` in responses

7. **Use Celery for heavy operations** - Set `use_celery: true` in trigger_options

---

## Response Schema v2 Implementation Details

### Files Modified

The v2 response schema refactoring was implemented in:

- **`multitenancy/etl_service.py`** - Core refactoring:
  - `_build_v2_response_rows()` - Builds canonical per-row structure
  - `_build_v2_response_summary()` - Computes summary from rows
  - `_build_v2_response_transformations()` - Builds transformations block
  - `_build_response()` - Updated to use v2 format
  - `_preview_data()` - Stores `extra_fields_by_model` as instance variable
  - `_import_data()` - Builds compatible structure for execute mode

### Helper Methods

**`_build_v2_response_rows(import_result, extra_fields_by_model)`**
- Builds canonical per-row structure (`data.rows`)
- Groups transactions with their journal entries
- Maps Excel row metadata to created records
- Extracts transformation metadata (rules, substitutions, extra fields)
- Handles failed rows separately
- Includes row-level warnings and errors

**`_build_v2_response_summary(v2_rows)`**
- Computes summary statistics from `data.rows`
- Counts rows by status (ok/failed/skipped)
- Counts models created (Transaction, JournalEntry)
- Aggregates sheet-level statistics

**`_build_v2_response_transformations(import_result)`**
- Consolidates transformation-related fields
- Includes `rules_used`, `import_errors`, `integration_rules_available`, `integration_rules_preview`

### Response Builder Changes

**`_build_response()`** now:
- Adds `schema_version: "2.0"` to all responses
- Removes `import_result` field entirely
- Builds v2 `data` structure using helper methods
- Computes summary using `_build_v2_response_summary()`
- Works for both preview (`commit=False`) and execute (`commit=True`) modes

### Execute Mode Compatibility

For execute mode (`commit=True`):
- `_import_data()` builds a compatible structure
- Creates `would_create_by_row` from actual created records
- Preserves Excel row metadata via `extra_fields_by_model` and `source_rows_by_id`
- Response format is identical to preview (except `is_preview: false`)

### Testing the v2 Schema

**Preview endpoint** (`POST /api/core/etl/preview/`):
- Verify `schema_version: "2.0"` present
- Verify `data.rows` structure is correct
- Verify `data.transformations` contains expected data
- Verify `summary.rows` and `summary.models` match `data.rows` contents
- Verify no `import_result` field

**Execute endpoint** (`POST /api/core/etl/execute/`):
- Verify same v2 format returned
- Verify `is_preview: false`
- Verify actual database records match response

**Edge cases to test:**
- Empty file
- Failed rows
- Skipped rows
- Multiple transactions per row
- JournalEntries without transactions

---

## Valid Target Models

Get the list of valid target models:

```
GET /api/core/etl/transformation-rules/available_models/
```

Response:
```json
{
  "models": [
    "Company", "Entity", "Currency", "Account", "CostCenter",
    "Transaction", "JournalEntry", "BankAccount", "BankTransaction",
    "BusinessPartner", "BusinessPartnerCategory", "ProductService",
    "ProductServiceCategory", "Contract", "FinancialIndex", "IndexQuote"
  ]
}
```

