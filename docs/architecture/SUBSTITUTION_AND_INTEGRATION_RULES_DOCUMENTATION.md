# Substitution and Integration Rules - Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Substitution Rules](#substitution-rules)
   - [Introduction](#substitution-rules-introduction)
   - [Model Structure](#substitution-rule-model-structure)
   - [Match Types](#match-types)
   - [Filter Conditions](#filter-conditions)
   - [Usage in ETL Pipeline](#substitution-rules-in-etl)
   - [API Endpoints](#substitution-rule-api)
   - [Examples](#substitution-rule-examples)
   - [Best Practices](#substitution-rule-best-practices)
3. [Integration Rules](#integration-rules)
   - [Introduction](#integration-rules-introduction)
   - [Model Structure](#integration-rule-model-structure)
   - [Available Triggers](#available-triggers)
   - [Trigger Payloads](#trigger-payloads)
   - [Rule Execution Context](#rule-execution-context)
   - [Available Functions](#available-functions)
   - [API Endpoints](#integration-rule-api)
   - [Examples](#integration-rule-examples)
   - [Best Practices](#integration-rule-best-practices)
4. [Working Together](#working-together)
5. [Troubleshooting](#troubleshooting)

---

## Overview

The system provides two powerful rule engines for data transformation and automation:

- **Substitution Rules**: Clean and standardize data by replacing values based on matching patterns
- **Integration Rules**: Execute custom Python code when specific events occur (ETL imports, payroll approvals, etc.)

Both rule types are company-scoped and can work together to create sophisticated data processing workflows.

---

## Substitution Rules

### Introduction

Substitution Rules provide a declarative way to clean, normalize, and standardize data during ETL imports and other data processing operations. They apply value replacements based on matching patterns before data is saved to the database.

**Key Characteristics:**
- Applied automatically during ETL pipeline (Step 2: Substitution)
- Can target specific models and fields
- Support three match types: exact, regex, and caseless
- Optional filter conditions for conditional application
- Company-scoped (each company has its own rules)

### Model Structure

```python
class SubstitutionRule:
    company: ForeignKey          # Company this rule belongs to
    title: str                  # Optional human-readable title
    model_name: str             # Target model name (e.g., "JournalEntry", "Transaction")
    field_name: str             # Target field name (e.g., "account_path", "description")
    match_type: str             # 'exact', 'regex', or 'caseless'
    match_value: str            # Value/pattern to match
    substitution_value: str      # Replacement value
    filter_conditions: JSON      # Optional conditions for applying rule
```

**Unique Constraint:**
- Rules are unique per: `(company, model_name, field_name, match_value, filter_conditions)`

### Match Types

#### 1. `exact` (Default)

Direct string equality comparison. Case-sensitive and exact match required.

**Use Cases:**
- Replacing specific entity names with IDs
- Standardizing exact values
- Mapping codes

**Example:**
```json
{
  "model_name": "Transaction",
  "field_name": "entity_id",
  "match_type": "exact",
  "match_value": "Main Company",
  "substitution_value": "10"
}
```

**Behavior:**
- `"Main Company"` → `"10"` ✅
- `"main company"` → No change ❌ (case-sensitive)
- `"Main Company "` → No change ❌ (exact match)

---

#### 2. `regex`

Regular expression replacement using Python's `re.sub()`. Supports full regex syntax.

**Use Cases:**
- Removing prefixes/suffixes
- Pattern-based replacements
- Cleaning formatted strings

**Example:**
```json
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^(PIX|TED|DOC)\\s*-?\\s*",
  "substitution_value": ""
}
```

**Behavior:**
- `"PIX ENVIADO"` → `"ENVIADO"` ✅
- `"TED - FORNECEDOR"` → `"FORNECEDOR"` ✅
- `"DOC 12345"` → `"12345"` ✅

**Important Notes:**
- Uses `re.sub()` - replaces ALL matches in the string
- Invalid regex patterns will cause the rule to be skipped (warning logged)
- Escape special regex characters if matching literally

---

#### 3. `caseless`

Case and accent insensitive comparison. Normalizes both strings before comparison.

**Use Cases:**
- Normalizing account paths with different cases
- Handling Portuguese accents (á, é, í, ó, ú, ç)
- Case-insensitive value mapping

**Example:**
```json
{
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "ATIVO > BANCOS > BRADESCO",
  "substitution_value": "Assets > Banks > Bradesco"
}
```

**Behavior:**
- `"Ativo > Bancos > Bradesco"` → `"Assets > Banks > Bradesco"` ✅
- `"ATIVO > BANCOS > BRADESCO"` → `"Assets > Banks > Bradesco"` ✅
- `"Ativo > Bancos > Bradesco"` → `"Assets > Banks > Bradesco"` ✅
- `"Ativo > Bancos > Bradesco"` → `"Assets > Banks > Bradesco"` ✅

**Normalization Process:**
1. Converts to lowercase
2. Removes accents (NFD normalization + ASCII encoding)
3. Compares normalized strings

---

### Filter Conditions

Filter conditions allow you to apply substitution rules only when certain conditions are met. This is useful for context-dependent replacements.

**Format:**
```json
{
  "field_name": {
    "operator": "value"
  }
}
```

**Supported Operators:**
- `eq` / `==` - Equal
- `ne` / `!=` - Not equal
- `lt` / `<` - Less than
- `lte` / `<=` - Less than or equal
- `gt` / `>` - Greater than
- `gte` / `>=` - Greater than or equal
- `in` - Value in list
- `contains` - String contains
- `startswith` - String starts with
- `endswith` - String ends with

**Example:**
```json
{
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Despesas > Serviços",
  "substitution_value": "Expenses > Services",
  "filter_conditions": {
    "description": {
      "contains": "CONSULTORIA"
    }
  }
}
```

**Behavior:**
- Only applies when `description` contains "CONSULTORIA"
- Other journal entries are not affected

**Multiple Conditions:**
```json
{
  "filter_conditions": {
    "amount": {
      "gte": 1000
    },
    "date": {
      "startswith": "2025-01"
    }
  }
}
```
All conditions must be met (AND logic).

---

### Substitution Rules in ETL Pipeline

Substitution rules are automatically applied during the ETL pipeline at **Step 2: Substitution**, after transformation but before validation and import.

**Execution Flow:**
1. **Transformation** - Excel columns mapped to model fields
2. **Substitution** ← Rules applied here
3. **Post-Processing** - Account lookups, debit/credit calculations
4. **Validation** - Required fields, data types, foreign keys
5. **Import** - Records created in database
6. **Triggers** - Integration rules fired

**How Rules Are Applied:**
1. For each model in transformed data (e.g., `Transaction`, `JournalEntry`)
2. Get all active substitution rules for that model and company
3. For each rule, check if target field exists in row
4. If field exists and value is not None:
   - Check filter conditions (if any)
   - Apply match logic based on `match_type`
   - Replace value if match found
5. Continue to next rule (rules can chain)

**Important Notes:**
- Rules are applied in database order (no guaranteed execution order)
- Multiple rules can apply to the same field
- Rules only apply if the field exists in the transformed data
- Null/None values are skipped
- Errors in regex patterns are logged as warnings, rule is skipped

---

### Substitution Rule API

#### List Substitution Rules

```http
GET /api/core/substitution-rules/
```

**Query Parameters:**
- `model_name` - Filter by model name
- `field_name` - Filter by field name
- `company` - Filter by company ID

**Response:**
```json
{
  "count": 10,
  "results": [
    {
      "id": 1,
      "company": 1,
      "title": "Normalize Account Paths",
      "model_name": "JournalEntry",
      "field_name": "account_path",
      "match_type": "caseless",
      "match_value": "Ativo > Bancos",
      "substitution_value": "Assets > Banks",
      "filter_conditions": null
    }
  ]
}
```

#### Create Substitution Rule

```http
POST /api/core/substitution-rules/
Content-Type: application/json

{
  "company": 1,
  "title": "Normalize Account Paths",
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Ativo > Bancos > Bradesco",
  "substitution_value": "Assets > Banks > Bradesco",
  "filter_conditions": null
}
```

#### Update Substitution Rule

```http
PUT /api/core/substitution-rules/{id}/
Content-Type: application/json

{
  "substitution_value": "Assets > Banks > Bradesco > Checking"
}
```

#### Delete Substitution Rule

```http
DELETE /api/core/substitution-rules/{id}/
```

---

### Substitution Rule Examples

#### Example 1: Normalize Account Paths (Portuguese to English)

```json
{
  "company": 1,
  "title": "PT to EN Account Paths",
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Ativo > Bancos > Bradesco",
  "substitution_value": "Assets > Banks > Bradesco"
}
```

#### Example 2: Clean Transaction Descriptions

Remove payment method prefixes from descriptions:

```json
{
  "company": 1,
  "title": "Remove Payment Prefixes",
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^(PIX|TED|DOC|BOLETO)\\s*-?\\s*",
  "substitution_value": ""
}
```

**Before:** `"PIX ENVIADO - FORNECEDOR"`
**After:** `"ENVIADO - FORNECEDOR"`

#### Example 3: Map Entity Names to IDs

```json
{
  "company": 1,
  "title": "Entity Name to ID",
  "model_name": "Transaction",
  "field_name": "entity_id",
  "match_type": "exact",
  "match_value": "Main Company",
  "substitution_value": "10"
}
```

#### Example 4: Conditional Replacement

Only normalize account paths for transactions above a certain amount:

```json
{
  "company": 1,
  "title": "High Value Account Normalization",
  "model_name": "JournalEntry",
  "field_name": "account_path",
  "match_type": "caseless",
  "match_value": "Despesas > Serviços",
  "substitution_value": "Expenses > Services",
  "filter_conditions": {
    "debit_amount": {
      "gte": 1000
    }
  }
}
```

#### Example 5: Multiple Rules for Same Field

You can create multiple rules that apply to the same field. They will all be evaluated:

```json
// Rule 1: Remove prefixes
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^PIX\\s+",
  "substitution_value": ""
}

// Rule 2: Normalize spacing
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "\\s{2,}",
  "substitution_value": " "
}
```

**Before:** `"PIX  ENVIADO   FORNECEDOR"`
**After Rule 1:** `"ENVIADO   FORNECEDOR"`
**After Rule 2:** `"ENVIADO FORNECEDOR"`

---

### Substitution Rule Best Practices

1. **Use Descriptive Titles**
   - Makes rules easier to identify and manage
   - Example: "PT to EN Account Paths" vs "Rule 1"

2. **Start with Caseless for Account Paths**
   - Handles case variations and accents automatically
   - More forgiving than exact matches

3. **Test Regex Patterns**
   - Use online regex testers before creating rules
   - Remember: uses `re.sub()`, not `re.match()`

4. **Use Filter Conditions Sparingly**
   - Adds complexity and can make debugging harder
   - Consider if the condition should be in the transformation rule instead

5. **Order Matters (Conceptually)**
   - While execution order isn't guaranteed, think about rule dependencies
   - Example: Clean prefixes before normalizing spacing

6. **Monitor Rule Performance**
   - Rules are applied to every row - complex regex can be slow
   - Use exact or caseless when possible (faster than regex)

7. **Document Complex Rules**
   - Add notes in the `title` or create separate documentation
   - Explain why the rule exists and what it does

8. **Version Control**
   - Export rules as JSON for version control
   - Track changes to rules over time

---

## Integration Rules

### Introduction

Integration Rules are event-driven automation scripts that execute custom Python code when specific triggers fire. They enable sophisticated business logic automation, data transformations, and cross-model record creation.

**Key Characteristics:**
- Execute Python code in a sandboxed environment
- Triggered by events (ETL imports, payroll approvals, etc.)
- Can create, update, and query database records
- Support async execution via Celery
- Company-scoped with execution ordering
- Full audit logging of executions

**Common Use Cases:**
- Create JournalEntries from Transactions
- Automate double-entry bookkeeping
- Generate related records based on imported data
- Send notifications or webhooks
- Calculate derived values
- Enforce business rules

### Model Structure

```python
class IntegrationRule:
    company: ForeignKey          # Company this rule belongs to
    name: str                    # Rule name (required)
    description: str             # Optional description
    trigger_event: str          # Event that triggers this rule
    execution_order: int         # Order when multiple rules fire (default: 0)
    filter_conditions: str       # Optional Python expression for filtering
    rule: str                    # Python code to execute (required)
    use_celery: bool             # Run async via Celery (default: True)
    is_active: bool              # Enable/disable rule (default: True)
    last_run_at: datetime        # Last execution timestamp
    times_executed: int          # Execution counter
```

**Execution Flow:**
1. Event fires (e.g., `transaction_created`)
2. System finds all active rules for that event and company
3. Rules are sorted by `execution_order`
4. For each rule:
   - Apply `filter_conditions` (if any)
   - Execute `rule` code in sandboxed environment
   - Log execution in `IntegrationRuleLog`
   - Update `last_run_at` and `times_executed`

---

### Available Triggers

| Trigger | Description | When It Fires | Payload Type |
|---------|-------------|---------------|--------------|
| `transaction_created` | Transaction created by ETL | After Transaction import | Single dict |
| `journal_entry_created` | JournalEntry created by ETL | After JournalEntry import | Single dict |
| `etl_import_completed` | ETL import finished | After entire ETL pipeline completes | Summary dict |
| `payroll_created` | Payroll batch created | When payroll batch is created | Payroll data |
| `payroll_approved` | Payroll batch approved | When payroll batch is approved | Payroll data |

**Note:** More triggers can be added as needed. Contact development team to add new trigger types.

---

### Trigger Payloads

#### `transaction_created` Payload

Fired when a Transaction is created during ETL import.

```python
{
    'transaction_id': 123,
    'transaction': {
        'id': 123,
        'date': '2025-01-15',
        'description': 'PIX ENVIADO - FORNECEDOR',
        'amount': '500.00',
        'entity_id': 10,
        'currency_id': 12,
        'state': 'pending',
        'company_id': 1
    },
    'extra_fields': {
        'account_path': 'Expenses > Services',
        'bank_account_id': '5',
        'cost_center_path': 'Operations'
    },
    'source': 'etl_import',
    'log_id': 45
}
```

**Key Fields:**
- `transaction_id` - ID of created transaction
- `transaction` - Full transaction data dict
- `extra_fields` - Additional fields from `extra_fields_for_trigger` in transformation rule
- `source` - Always `'etl_import'` for ETL-created records
- `log_id` - ETL pipeline log ID

---

#### `journal_entry_created` Payload

Fired when a JournalEntry is created during ETL import.

```python
{
    'journal_entry_id': 456,
    'journal_entry': {
        'id': 456,
        'transaction_id': 123,
        'account_id': 25,
        'debit_amount': '500.00',
        'credit_amount': None,
        'description': 'PIX ENVIADO',
        'date': '2025-01-15',
        'state': 'pending'
    },
    'extra_fields': {
        'cost_center_path': 'Operations'
    },
    'source': 'etl_import',
    'log_id': 45
}
```

---

#### `etl_import_completed` Payload

Fired after entire ETL pipeline completes (all sheets processed).

```python
{
    'company_id': 1,
    'log_id': 45,
    'summary': {
        'sheets_found': 2,
        'sheets_processed': 1,
        'sheets_failed': 0,
        'total_rows_imported': 50
    },
    'created_records': {
        'Transaction': [123, 124, 125],
        'JournalEntry': [456, 457, 458]
    },
    'source': 'etl_import'
}
```

---

### Rule Execution Context

Integration rules execute Python code in a sandboxed environment with restricted access for security.

**Available Variables:**

| Variable | Type | Description |
|----------|------|-------------|
| `payload` | dict/list | Trigger payload data (varies by trigger) |
| `company_id` | int | Current company ID |
| `result` | any | Must be set - rule output (can be any type) |

**Important:**
- You **must** set `result` in your rule code
- `result` can be any Python type (dict, list, string, etc.)
- `result` is logged in `IntegrationRuleLog` for auditing

---

### Available Functions

The rule execution environment provides helper functions for common operations:

#### Account Lookup Functions

##### `lookup_account_by_path(path, separator=' > ')`

Find an Account by its hierarchical path.

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

##### `lookup_account_by_code(code)`

Find an Account by its account code.

**Parameters:**
- `code` (str): Account code (e.g., "1.1.1.001")

**Returns:** Account instance or None

**Example:**
```python
account = lookup_account_by_code('1.1.1.001')
```

---

##### `lookup_account_by_name(name)`

Find an Account by name (first match).

**Parameters:**
- `name` (str): Account name

**Returns:** Account instance or None

**Example:**
```python
account = lookup_account_by_name('Bradesco Checking')
```

---

#### Record Creation Functions

##### `create_transaction_with_entries(payload)`

**Most Powerful Function** - Creates a complete Transaction with two balanced JournalEntries.

**Parameters:**
```python
{
    'date': '2025-01-15',              # Required: Transaction date (YYYY-MM-DD)
    'description': 'PIX ENVIADO',       # Optional: Transaction description
    'amount': '-500.00',                # Required: Amount (positive or negative)
    'entity_id': 10,                   # Required: Entity FK
    'currency_id': 12,                 # Required: Currency FK
    'state': 'pending',                # Optional: Transaction state (default: 'pending')
    'bank_account_id': 5,              # Optional: BankAccount FK (for bank entry)
    'account_id': 25,                  # Optional: Opposing Account FK
    'account_code': '4.1.1.001',       # Optional: Opposing Account code
    'account_path': 'Expenses > Services',  # Optional: Opposing Account path
    'path_separator': ' > ',           # Optional: Path separator (default: ' > ')
    'cost_center_id': 3                # Optional: Cost center FK
}
```

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

**Debit/Credit Logic:**
- **Positive amount** (deposit/income):
  - Bank account: **DEBIT** (asset increases)
  - Opposing account: **CREDIT**
- **Negative amount** (payment/expense):
  - Bank account: **CREDIT** (asset decreases)
  - Opposing account: **DEBIT**

**Example:**
```python
result = create_transaction_with_entries({
    'date': payload['transaction']['date'],
    'description': payload['transaction']['description'],
    'amount': payload['transaction']['amount'],
    'entity_id': payload['transaction']['entity_id'],
    'currency_id': payload['transaction']['currency_id'],
    'bank_account_id': payload['extra_fields'].get('bank_account_id'),
    'account_path': payload['extra_fields'].get('account_path')
})

if result['errors']:
    debug_log(f"Errors: {result['errors']}")
else:
    debug_log(f"Created Transaction {result['transaction']['id']}")
```

---

##### `create_transaction(...)`

Create a single Transaction record.

**Parameters:**
- `date` (str): Transaction date
- `description` (str): Description
- `amount` (Decimal/str): Amount
- `entity_id` (int): Entity FK
- `currency_id` (int): Currency FK
- `state` (str): Transaction state

**Returns:** Transaction instance

**Example:**
```python
tx = create_transaction(
    date='2025-01-15',
    description='Manual Entry',
    amount=Decimal('1000.00'),
    entity_id=10,
    currency_id=12,
    state='pending'
)
```

---

##### `create_journal_entry(...)`

Create a single JournalEntry record.

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

**Example:**
```python
je = create_journal_entry(
    transaction_id=123,
    account_id=25,
    date='2025-01-15',
    description='Services',
    debit_amount=Decimal('500.00'),
    credit_amount=None,
    state='pending'
)
```

---

#### Calculation Functions

##### `calculate_debit_credit(amount, account)`

Calculate debit/credit amounts based on amount sign and account direction.

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
# Returns: {'debit_amount': Decimal('500.00'), 'credit_amount': None}
```

---

#### Data Processing Functions

##### `group_by(records, key)`

Group records by a key field.

**Parameters:**
- `records` (list): List of dicts
- `key` (str): Field name to group by

**Returns:** List of groups with 'group' and 'items' keys

**Example:**
```python
groups = group_by(payload, 'department')
# Returns: [
#   {'group': 'HR', 'items': [...]},
#   {'group': 'IT', 'items': [...]}
# ]
```

---

##### `sum_group(group, key)`

Sum values in a group.

**Parameters:**
- `group` (list): List of dicts
- `key` (str): Field name to sum

**Returns:** Sum of values

**Example:**
```python
total = sum_group(group['items'], 'amount')
```

---

##### `max_group(group, key)` / `min_group(group, key)`

Find max/min value in a group.

**Example:**
```python
max_amount = max_group(group['items'], 'amount')
```

---

#### Utility Functions

##### `apply_substitutions(model, fields=None)`

Apply substitution rules to payload data.

**Parameters:**
- `model` (str): Model name
- `fields` (list): Optional list of field names to apply rules to

**Returns:** Modified payload

**Example:**
```python
payload = apply_substitutions('JournalEntry', ['account_path'])
```

---

##### `to_decimal(value, places=2)`

Convert value to Decimal with specified decimal places.

**Example:**
```python
amount = to_decimal('1234.567', places=2)  # Returns Decimal('1234.57')
```

---

##### `debug_log(*args)`

Log debug messages (visible in IntegrationRuleLog).

**Example:**
```python
debug_log(f"Processing transaction {payload['transaction_id']}")
debug_log("Step 1", "Step 2", "Step 3")
```

---

#### Available Types

| Type | Description |
|------|-------------|
| `Decimal` | Python Decimal class for precise calculations |
| `Account` | Account model class |
| `Transaction` | Transaction model class |
| `JournalEntry` | JournalEntry model class |

#### Python Builtins

Available: `sum`, `len`, `str`, `int`, `float`, `abs`, `round`

**Not Available:**
- File I/O operations
- Network operations
- System calls
- Import statements (except provided models)

---

### Integration Rule API

#### List Integration Rules

```http
GET /api/core/integration-rules/
```

**Query Parameters:**
- `trigger_event` - Filter by trigger event
- `is_active` - Filter by active status
- `company` - Filter by company ID

**Response:**
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "company": 1,
      "name": "Create JournalEntries from Transaction",
      "description": "Auto-create journal entries for bank transactions",
      "trigger_event": "transaction_created",
      "execution_order": 0,
      "filter_conditions": null,
      "rule": "# Python code here...",
      "use_celery": false,
      "is_active": true,
      "last_run_at": "2025-01-15T10:30:00Z",
      "times_executed": 45
    }
  ]
}
```

#### Create Integration Rule

```http
POST /api/core/integration-rules/
Content-Type: application/json

{
  "company": 1,
  "name": "Create JournalEntries from Transaction",
  "description": "Auto-create journal entries for bank transactions",
  "trigger_event": "transaction_created",
  "execution_order": 0,
  "filter_conditions": null,
  "rule": "# Get payload data\ntx_id = payload['transaction_id']\ntx = payload['transaction']\nextra = payload.get('extra_fields', {})\n\n# Create journal entries\nresult = create_transaction_with_entries({\n    'date': tx['date'],\n    'description': tx['description'],\n    'amount': tx['amount'],\n    'entity_id': tx['entity_id'],\n    'currency_id': tx['currency_id'],\n    'bank_account_id': extra.get('bank_account_id'),\n    'account_path': extra.get('account_path')\n})\n\nresult = result",
  "use_celery": false,
  "is_active": true
}
```

#### Update Integration Rule

```http
PUT /api/core/integration-rules/{id}/
Content-Type: application/json

{
  "rule": "# Updated rule code..."
}
```

#### Delete Integration Rule

```http
DELETE /api/core/integration-rules/{id}/
```

#### Validate Rule Syntax

```http
POST /api/core/validate-rule/
Content-Type: application/json

{
  "rule": "# Python code to validate..."
}
```

**Response:**
```json
{
  "valid": true,
  "errors": []
}
```

#### Test Rule Execution

```http
POST /api/core/test-rule/
Content-Type: application/json

{
  "rule": "# Python code...",
  "payload": {
    "transaction_id": 123,
    "transaction": {...}
  },
  "company_id": 1
}
```

**Response:**
```json
{
  "result": {...},
  "debug_logs": ["Debug message 1", "Debug message 2"],
  "success": true
}
```

---

### Integration Rule Examples

#### Example 1: Create JournalEntries from Transaction

**Scenario:** When a Transaction is created via ETL, automatically create two JournalEntries (bank account + opposing account).

```python
# Get payload data
tx_id = payload['transaction_id']
tx = payload['transaction']
extra = payload.get('extra_fields', {})

# Build payload for create_transaction_with_entries
# Note: Transaction already exists, so we'll create JEs manually

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
```

---

#### Example 2: Using `create_transaction_with_entries` Helper

**Simpler approach** - Use the helper function (but note: Transaction already exists, so this creates a duplicate).

**Better approach** - Use helper in a different trigger or create Transaction + JEs together:

```python
# This would be used if creating Transaction + JEs from scratch
result = create_transaction_with_entries({
    'date': payload['date'],
    'description': payload.get('description', 'Imported transaction'),
    'amount': payload['amount'],
    'entity_id': payload['entity_id'],
    'currency_id': payload['currency_id'],
    'bank_account_id': payload.get('bank_account_id'),
    'account_path': payload.get('account_path'),
    'cost_center_id': payload.get('cost_center_id')
})

if result['errors']:
    debug_log(f"Errors: {result['errors']}")

result = result
```

---

#### Example 3: Conditional Execution with Filter

Only create JournalEntries for transactions above a certain amount:

**Filter Condition:**
```python
payload['transaction']['amount'] >= 1000
```

**Rule Code:**
```python
tx = payload['transaction']
extra = payload.get('extra_fields', {})

# Same logic as Example 1, but only runs if filter passes
# (amount >= 1000)

result = {'message': 'Journal entries created for high-value transaction'}
```

---

#### Example 4: Post-Import Summary

Process `etl_import_completed` trigger to send summary email or create summary records:

```python
summary = payload['summary']
created = payload['created_records']

debug_log(f"ETL Import completed:")
debug_log(f"  - Sheets processed: {summary['sheets_processed']}")
debug_log(f"  - Total rows: {summary['total_rows_imported']}")
debug_log(f"  - Transactions created: {len(created.get('Transaction', []))}")
debug_log(f"  - JournalEntries created: {len(created.get('JournalEntry', []))}")

# Could send email, create summary record, etc.
result = {
    'summary': summary,
    'created_counts': {k: len(v) for k, v in created.items()}
}
```

---

#### Example 5: Group and Aggregate

Process payroll data and create summary transactions:

```python
# Group by department
groups = group_by(payload, 'department')

summary_transactions = []

for group in groups:
    dept = group['group']
    items = group['items']
    
    total = sum_group(items, 'amount')
    
    debug_log(f"Department {dept}: Total = {total}")
    
    # Create summary transaction for each department
    tx = create_transaction(
        date=payload[0]['date'],  # Use first item's date
        description=f'Payroll Summary - {dept}',
        amount=total,
        entity_id=payload[0]['entity_id'],
        currency_id=payload[0]['currency_id'],
        state='pending'
    )
    
    summary_transactions.append(tx.id)

result = {'summary_transactions': summary_transactions}
```

---

### Integration Rule Best Practices

1. **Always Set `result`**
   - Your rule must set `result` variable
   - Use descriptive values for debugging

2. **Use `debug_log()` Liberally**
   - Helps troubleshoot issues
   - Visible in IntegrationRuleLog
   - Include key values and decision points

3. **Handle Errors Gracefully**
   - Check for None values before using
   - Validate required fields exist
   - Use try/except for risky operations

4. **Test Rules Before Production**
   - Use `/api/core/test-rule/` endpoint
   - Test with sample payloads
   - Verify expected behavior

5. **Use Helper Functions**
   - Prefer `create_transaction_with_entries()` over manual creation
   - Use account lookup functions instead of raw queries
   - Leverage `calculate_debit_credit()` for accounting logic

6. **Set Execution Order**
   - Rules with same trigger execute in `execution_order`
   - Lower numbers execute first
   - Consider dependencies between rules

7. **Use Filter Conditions Wisely**
   - Filter at rule level when possible (more efficient)
   - Use Python conditions in rule code for complex logic

8. **Async vs Sync**
   - Use `use_celery=True` for long-running rules
   - Use `use_celery=False` for quick operations that need immediate results

9. **Keep Rules Simple**
   - Break complex logic into multiple rules
   - Each rule should have a single responsibility
   - Easier to debug and maintain

10. **Document Complex Logic**
   - Add comments in rule code
   - Update `description` field
   - Explain business logic

---

## Working Together

Substitution and Integration Rules work together seamlessly in the ETL pipeline:

### Typical Workflow

1. **Excel File Uploaded**
2. **Transformation (Step 1)**
   - Columns mapped to model fields
   - Computed columns calculated
   - Default values applied
3. **Substitution (Step 2)** ← Substitution Rules Applied
   - Account paths normalized
   - Descriptions cleaned
   - Entity names mapped to IDs
4. **Post-Processing (Step 3)**
   - Account lookups by path/code
   - Debit/credit calculations
5. **Validation (Step 4)**
   - Required fields checked
   - Data types validated
6. **Import (Step 5)**
   - Records created in database
7. **Triggers (Step 6)** ← Integration Rules Fired
   - JournalEntries created from Transactions
   - Related records generated
   - Notifications sent

### Example: Complete Bank Statement Import

**Step 1: Transformation Rule**
```json
{
  "name": "Bradesco Statement",
  "source_sheet_name": "Extrato",
  "target_model": "Transaction",
  "column_mappings": {
    "Data": "date",
    "Descrição": "description",
    "Valor (R$)": "amount"
  },
  "computed_columns": {
    "amount": "Decimal(str(row['Valor (R$)']).replace('.', '').replace(',', '.'))",
    "date": "datetime.strptime(row['Data'], '%d/%m/%Y').strftime('%Y-%m-%d')"
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

**Step 2: Substitution Rules**
```json
// Rule 1: Normalize account paths
{
  "model_name": "Transaction",
  "field_name": "account_path",  // Note: This is in extra_fields, not Transaction model
  "match_type": "caseless",
  "match_value": "Despesas > Serviços",
  "substitution_value": "Expenses > Services"
}

// Rule 2: Clean descriptions
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "^(PIX|TED|DOC)\\s*-?\\s*",
  "substitution_value": ""
}
```

**Step 3: Integration Rule**
```python
# Create JournalEntries from Transaction
tx = payload['transaction']
extra = payload.get('extra_fields', {})

account_path = extra.get('account_path')
bank_account_id = extra.get('bank_account_id')

# Look up accounts and create entries
# ... (see Example 1 above)
```

**Result:**
- Excel data transformed
- Account paths normalized (PT → EN)
- Descriptions cleaned
- Transactions created
- JournalEntries automatically created with proper debit/credit

---

## Troubleshooting

### Substitution Rules Not Applying

**Symptoms:** Values not being replaced

**Checklist:**
1. ✅ Rule is active (`is_active=True`)
2. ✅ Rule belongs to correct company
3. ✅ `model_name` matches target model exactly
4. ✅ `field_name` exists in transformed data
5. ✅ Field value is not None
6. ✅ Match pattern is correct
   - For `exact`: Case-sensitive, exact match
   - For `regex`: Test pattern online first
   - For `caseless`: Check normalization
7. ✅ Filter conditions (if any) are met
8. ✅ Check ETL logs for substitution warnings

**Debug Steps:**
1. Check ETL preview response - shows transformed data after substitution
2. Add temporary debug rule to log values
3. Verify field name matches exactly (case-sensitive)

---

### Integration Rules Not Firing

**Symptoms:** Rule code not executing

**Checklist:**
1. ✅ Rule is active (`is_active=True`)
2. ✅ Rule belongs to correct company
3. ✅ `trigger_event` matches the event being fired
4. ✅ Trigger is actually firing (check ETL logs)
5. ✅ Filter conditions (if any) are passing
6. ✅ No syntax errors in rule code (use validate endpoint)

**Debug Steps:**
1. Check `IntegrationRuleLog` for execution records
2. Use `/api/core/test-rule/` to test rule independently
3. Add `debug_log()` statements at rule start
4. Check Celery workers if `use_celery=True`

---

### Integration Rule Errors

**Common Errors:**

1. **`NameError: name 'result' is not defined`**
   - **Fix:** Always set `result` variable in your rule

2. **`AttributeError: 'NoneType' object has no attribute 'id'`**
   - **Fix:** Check for None before accessing attributes
   ```python
   account = lookup_account_by_path(path)
   if account:
       account_id = account.id
   ```

3. **`ValueError: Missing required field: 'amount'`**
   - **Fix:** Validate payload structure before using
   ```python
   if 'amount' not in payload['transaction']:
       result = {'error': 'Missing amount'}
   ```

4. **`TypeError: unsupported operand type(s)`**
   - **Fix:** Convert to Decimal for calculations
   ```python
   amount = Decimal(str(payload['transaction']['amount']))
   ```

**Debug Tips:**
- Use `debug_log()` to print variable values
- Check `IntegrationRuleLog.result` for error messages
- Test with `/api/core/test-rule/` endpoint
- Break complex rules into smaller pieces

---

### Performance Issues

**Symptoms:** Slow ETL imports or rule execution

**Optimization Tips:**

1. **Substitution Rules:**
   - Use `exact` or `caseless` instead of `regex` when possible
   - Limit number of rules per field
   - Use filter conditions to skip unnecessary checks

2. **Integration Rules:**
   - Use `use_celery=True` for long-running rules
   - Avoid nested loops over large datasets
   - Cache account lookups if used multiple times
   - Use bulk operations when possible

3. **General:**
   - Monitor execution times in logs
   - Profile rule execution with `debug_log()` timestamps
   - Consider breaking complex rules into multiple simpler rules

---

## Summary

**Substitution Rules:**
- Clean and normalize data
- Applied automatically during ETL
- Three match types: exact, regex, caseless
- Support conditional application

**Integration Rules:**
- Execute custom Python code
- Triggered by events
- Create related records
- Full audit logging

**Together:**
- Substitution rules prepare data
- Integration rules automate business logic
- Complete end-to-end automation

For more information, see:
- [ETL Pipeline Documentation](./ETL_PIPELINE_DOCUMENTATION.md)
- API endpoint documentation
- Code examples in `multitenancy/formula_engine.py`

