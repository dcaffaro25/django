# ETL Pipeline Documentation

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
│  - Concatenate multiple columns                                             │
│  - Compute derived values                                                   │
│  - Apply default values                                                     │
│  - Filter rows                                                              │
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
2. [ImportTransformationRule](#importtransformationrule)
3. [SubstitutionRule](#substitutionrule)
4. [IntegrationRule](#integrationrule)
5. [Helper Functions](#helper-functions)
6. [Complete Examples](#complete-examples)
7. [Error Handling](#error-handling)

---

## API Endpoints

### ETL Pipeline Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/core/etl/analyze/` | POST | Analyze Excel file structure (sheets, columns, sample data) |
| `/api/core/etl/preview/` | POST | Run full pipeline WITHOUT committing (preview mode) |
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

## Error Handling

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

---

## Best Practices

1. **Always preview first** - Use `/etl/preview/` before `/etl/execute/`

2. **Use substitution rules for normalization** - Clean data before import

3. **Keep transformation rules generic** - Use `extra_fields_for_trigger` for data needed by IntegrationRules

4. **Test integration rules in sandbox** - Use `/api/core/test-rule/` endpoint

5. **Use `create_transaction_with_entries`** - For complete double-entry bookkeeping

6. **Handle errors gracefully** - Check `errors` and `warnings` in responses

7. **Use Celery for heavy operations** - Set `use_celery: true` in trigger_options

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

