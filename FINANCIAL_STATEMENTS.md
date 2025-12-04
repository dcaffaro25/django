# Financial Statements - Complete Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Models](#models)
4. [Service Layer](#service-layer)
5. [API Endpoints](#api-endpoints)
6. [Time Series Analysis](#time-series-analysis)
7. [Period Comparisons](#period-comparisons)
8. [Output Formats](#output-formats)
9. [Preview Functionality](#preview-functionality)
10. [Account Mapping](#account-mapping)
11. [Calculation Types](#calculation-types)
12. [Report Types](#report-types)
13. [Usage Examples](#usage-examples)
14. [Integration Guide](#integration-guide)

---

## Overview

The Financial Statements system is a comprehensive reporting solution that generates structured financial reports from accounting data. It supports:

- **Balance Sheet** - Assets, Liabilities, and Equity as of a specific date
- **Income Statement (P&L)** - Revenue and Expenses for a period
- **Cash Flow Statement** - Cash inflows and outflows over time
- **Trial Balance** - All account balances
- **General Ledger** - Detailed transaction listing
- **Custom Reports** - User-defined report structures

### Key Features

- **Template-based**: Define report structures once, generate multiple times
- **Time Series Analysis**: Group data by time dimensions (day, week, month, quarter, semester, year)
- **Period Comparisons**: Compare current period with previous periods or years
- **Multiple Output Formats**: JSON, Markdown, HTML, Excel
- **Preview Mode**: Test reports without saving to database
- **Formatting Support**: Indentation, bold text, font sizes, collapsible rows (HTML)
- **Pending Transactions**: Option to include or exclude pending journal entries

---

## Architecture

### Core Components

1. **Models** (`accounting/models_financial_statements.py`)
   - Define data structures for templates, statements, and lines
   - Store generated reports and their metadata

2. **Service Layer** (`accounting/services/financial_statement_service.py`)
   - `FinancialStatementGenerator`: Core generation engine
   - Handles calculations, formulas, and data aggregation

3. **API Layer** (`accounting/views_financial_statements.py`)
   - RESTful endpoints for all operations
   - Format conversion (JSON, Markdown, HTML)
   - Preview functionality

4. **Utilities** (`accounting/utils_time_dimensions.py`)
   - Time dimension calculations
   - Period comparison logic
   - Date range generation

---

## Models

### FinancialStatementTemplate

Defines the structure of a financial statement.

**Key Fields:**
- `name`: Template name
- `report_type`: Type of report (balance_sheet, income_statement, cash_flow, etc.)
- `company_id`: Tenant/company association
- `is_default`: Whether this is the default template for the report type
- `is_active`: Whether the template is active

**Relationships:**
- `line_templates`: One-to-many with `FinancialStatementLineTemplate`

### FinancialStatementLineTemplate

Defines individual line items in a template.

**Key Fields:**
- `template`: Foreign key to `FinancialStatementTemplate`
- `line_number`: Order of this line in the statement
- `label`: Display label for the line
- `line_type`: Type (header, account, subtotal, total, spacer)
- `account`: Single account (optional)
- `account_code_prefix`: Match accounts by code prefix (optional)
- `account_path_contains`: Match accounts by path (optional)
- `account_ids`: List of specific account IDs (optional)
- `calculation_type`: How to calculate (sum, difference, balance, formula)
- `formula`: Formula string referencing other lines (e.g., "L1 + L2 - L3")
- `indent_level`: Indentation level (0-4) for hierarchical display
- `is_bold`: Whether to display in bold
- `parent_line`: Parent line for hierarchical grouping

### FinancialStatement

A generated statement instance.

**Key Fields:**
- `template`: Template used to generate this statement
- `report_type`: Type of report
- `name`: Statement name
- `start_date`, `end_date`: Reporting period
- `as_of_date`: For balance sheets, the specific date
- `status`: draft, final, or archived
- `currency`: Currency used
- `total_assets`, `total_liabilities`, `total_equity`: Calculated totals
- `net_income`: For income statements

**Relationships:**
- `lines`: One-to-many with `FinancialStatementLine`

### FinancialStatementLine

A single line in a generated statement.

**Key Fields:**
- `statement`: Foreign key to `FinancialStatement`
- `line_template`: Reference to template line (may be null if template changed)
- `line_number`: Line number
- `label`: Display label
- `line_type`: Type of line
- `debit_amount`, `credit_amount`, `balance`: Calculated values
- `indent_level`: Indentation level
- `is_bold`: Bold formatting flag
- `account_ids`: Account IDs that contributed to this line

---

## Service Layer

### FinancialStatementGenerator

The core service class that generates financial statements.

**Location:** `accounting/services/financial_statement_service.py`

**Initialization:**
```python
generator = FinancialStatementGenerator(company_id=1)
```

#### Key Methods

##### `generate_statement()`

Generates a financial statement from a template and saves it to the database.

**Parameters:**
- `template`: `FinancialStatementTemplate` instance
- `start_date`: `date` - Start of reporting period
- `end_date`: `date` - End of reporting period
- `currency_id`: `Optional[int]` - Currency ID (defaults to company currency)
- `as_of_date`: `Optional[date]` - For balance sheets, specific date
- `status`: `str` - Statement status (default: 'draft')
- `generated_by`: User instance (optional)
- `notes`: `Optional[str]` - Additional notes
- `include_pending`: `bool` - Include pending journal entries (default: False)

**Returns:** `FinancialStatement` instance

**Process:**
1. Creates `FinancialStatement` record
2. Iterates through `line_templates` in order
3. For each line, calls `_calculate_line_value()` to compute the value
4. Creates `FinancialStatementLine` records with calculated values
5. Calls `_calculate_totals()` to compute statement totals
6. Returns the generated statement

##### `preview_statement()`

Generates a financial statement preview without saving to the database.

**Parameters:** Same as `generate_statement()` (except `status`, `generated_by`, `notes`)

**Returns:** `Dict[str, Any]` with statement data structure

**Use Case:** Testing templates and calculations without creating database records.

##### `_calculate_line_value()`

Calculates the value for a single line item.

**Parameters:**
- `line_template`: `FinancialStatementLineTemplate` instance
- `start_date`, `end_date`, `as_of_date`: Date ranges
- `report_type`: Type of report
- `line_values`: `Dict[int, Decimal]` - Previously calculated line values (for formulas)
- `include_pending`: `bool` - Include pending entries

**Returns:** `Decimal` - Calculated line value

**Logic:**
1. If line type is `header` or `spacer`, returns `Decimal('0.00')`
2. If `calculation_type` is `formula`, evaluates the formula using `_evaluate_formula()`
3. Otherwise, gets accounts using `_get_accounts_for_line()`
4. Based on `report_type`, calls appropriate calculation method:
   - `balance_sheet`: `_calculate_balance_sheet_line()`
   - `income_statement`: `_calculate_income_statement_line()`
   - `cash_flow`: `_calculate_cash_flow_line()`

##### `_get_accounts_for_line()`

Retrieves accounts that match the line template's criteria.

**Parameters:**
- `line_template`: `FinancialStatementLineTemplate` instance

**Returns:** `List[Account]` - Matching accounts

**Matching Strategy (in order of priority):**
1. If `account` is set, returns that single account
2. If `account_ids` is set, returns those accounts
3. If `account_code_prefix` is set, returns accounts with codes starting with prefix
4. If `account_path_contains` is set, returns accounts with path containing the string
5. Returns empty list if no criteria match

##### `_calculate_balance_sheet_line()`

Calculates balance sheet line value as of a specific date.

**Parameters:**
- `accounts`: `List[Account]` - Accounts to include
- `as_of_date`: `date` - Date to calculate balance as of
- `calculation_type`: `str` - Calculation method
- `include_pending`: `bool` - Include pending entries

**Returns:** `Decimal` - Line balance

**Process:**
1. For each account, calls `_calculate_account_balance_with_children()` to get balance as of date
2. Applies `account_direction` if `calculation_type` is `balance`
3. Sums all account balances
4. Applies calculation type logic (sum, difference, balance)

##### `_calculate_income_statement_line()`

Calculates income statement line value for a period.

**Parameters:**
- `accounts`: `List[Account]` - Accounts to include
- `start_date`, `end_date`: Period dates
- `calculation_type`: `str` - Calculation method
- `include_pending`: `bool` - Include pending entries

**Returns:** `Decimal` - Line balance

**Process:**
1. Filters journal entries by date range and state (posted/pending)
2. Aggregates debits and credits for the period
3. Applies calculation type logic

##### `_calculate_cash_flow_line()`

Calculates cash flow line value for a period.

**Parameters:**
- `accounts`: `List[Account]` - Cash accounts to include
- `start_date`, `end_date`: Period dates
- `calculation_type`: `str` - Calculation method
- `include_pending`: `bool` - Include pending entries

**Returns:** `Decimal` - Cash flow amount

**Process:**
1. Calculates beginning balance (as of `start_date`)
2. Calculates ending balance (as of `end_date`)
3. Calculates period activity (ending - beginning)
4. Applies calculation type logic

##### `_calculate_account_balance_with_children()`

Calculates account balance including child accounts.

**Parameters:**
- `account`: `Account` instance
- `include_pending`: `bool` - Include pending entries
- `beginning_date`: `Optional[date]` - Start date (None = from beginning)
- `end_date`: `date` - End date

**Returns:** `Decimal` - Account balance

**Process:**
1. If account has children, recursively calculates children balances
2. Sums all child balances
3. If no children, calculates account balance directly using `account.calculate_balance()`
4. Respects `include_pending` flag

##### `_evaluate_formula()`

Evaluates a formula string referencing other line numbers.

**Parameters:**
- `formula`: `str` - Formula string (e.g., "L1 + L2 - L3")
- `line_values`: `Dict[int, Decimal]` - Previously calculated line values

**Returns:** `Decimal` - Calculated formula result

**Formula Syntax:**
- `L1`, `L2`, etc. refer to line numbers
- Supports `+`, `-`, `*`, `/` operators
- Supports parentheses for grouping

**Example:** `"L1 + L2 - L3"` calculates line 1 + line 2 - line 3

##### `generate_time_series()`

Generates time series data grouped by time dimension.

**Parameters:**
- `template`: `FinancialStatementTemplate` instance
- `start_date`, `end_date`: Overall period dates
- `dimension`: `Union[str, List[str]]` - Time dimension(s): 'day', 'week', 'month', 'quarter', 'semester', 'year'
- `line_numbers`: `Optional[List[int]]` - Specific lines to include (None = all lines)
- `include_pending`: `bool` - Include pending entries

**Returns:** `Dict[str, Any]` with time series data

**Process:**
1. If `dimension` is a list, generates data for each dimension and returns a dictionary keyed by dimension
2. If single dimension, generates periods using `generate_periods()` from `utils_time_dimensions`
3. For each period, calls `preview_statement()` to generate statement for that period
4. Extracts line values and formats as time series data
5. Includes `indent_level` and `is_bold` from line templates

**Response Structure (single dimension):**
```json
{
  "template_id": 1,
  "template_name": "Cash Flow Statement",
  "report_type": "cash_flow",
  "dimension": "month",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "lines": [
    {
      "line_number": 1,
      "label": "Operating Cash Flow",
      "indent_level": 0,
      "is_bold": false,
      "data": [
        {
          "period_key": "2025-01",
          "period_label": "January 2025",
          "start_date": "2025-01-01",
          "end_date": "2025-01-31",
          "value": 50000.00
        },
        ...
      ]
    }
  ]
}
```

**Response Structure (multiple dimensions):**
```json
{
  "template_id": 1,
  "template_name": "Cash Flow Statement",
  "report_type": "cash_flow",
  "dimensions": ["month", "quarter"],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "data": {
    "month": {
      "dimension": "month",
      "lines": [...]
    },
    "quarter": {
      "dimension": "quarter",
      "lines": [...]
    }
  }
}
```

##### `generate_with_comparisons()`

Generates financial statement with period comparisons.

**Parameters:**
- `template`: `FinancialStatementTemplate` instance
- `start_date`, `end_date`: Current period dates
- `comparison_types`: `List[str]` - Comparison types: 'previous_period', 'previous_year', 'ytd_previous_year', 'last_12_months', 'same_period_last_year'
- `dimension`: `Optional[str]` - Time dimension to break down current period (optional)
- `include_pending`: `bool` - Include pending entries

**Returns:** `Dict[str, Any]` with statement and comparisons

**Process:**
1. Generates current period statement using `generate_statement()`
2. If `dimension` is provided, breaks down current period into sub-periods and generates comparisons for each
3. For each comparison type:
   - Calculates comparison period dates using `get_comparison_period()` from `utils_time_dimensions`
   - Generates comparison statement
   - Calculates comparison metrics using `calculate_period_comparison()` from `utils_time_dimensions`
4. Returns statement with comparison data

**Response Structure:**
```json
{
  "statement": {
    "id": 123,
    "name": "Income Statement Q1 2025",
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "lines": [
      {
        "line_number": 1,
        "label": "Revenue",
        "balance": 100000.00,
        "indent_level": 0,
        "is_bold": false
      },
      ...
    ]
  },
  "comparisons": {
    "previous_period": {
      "start_date": "2024-10-01",
      "end_date": "2024-12-31",
      "lines": {
        "1": {
          "current_value": 100000.00,
          "comparison_value": 95000.00,
          "absolute_change": 5000.00,
          "percentage_change": 5.26,
          "comparison_type": "previous_period"
        },
        ...
      }
    },
    "previous_year": {
      ...
    }
  }
}
```

**Response Structure (with dimension):**
```json
{
  "template_name": "Income Statement",
  "report_type": "income_statement",
  "dimension": "month",
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "periods": [
    {
      "period_label": "January 2025",
      "start_date": "2025-01-01",
      "end_date": "2025-01-31",
      "statement": {...},
      "comparisons": {...}
    },
    ...
  ]
}
```

##### `preview_time_series()`

Generates time series preview without saving to database.

**Parameters:** Same as `generate_time_series()`

**Returns:** Same structure as `generate_time_series()` with `is_preview: true` flag

##### `preview_with_comparisons()`

Generates comparisons preview without saving to database.

**Parameters:** Same as `generate_with_comparisons()`

**Returns:** Same structure as `generate_with_comparisons()` with `is_preview: true` flag

---

## API Endpoints

### Base URL
All endpoints are under `/api/financial-statements/` or `/api/financial-statement-templates/`

### Templates

#### List Templates
```
GET /api/financial-statement-templates/
```

#### Create Template
```
POST /api/financial-statement-templates/
{
  "name": "Standard Balance Sheet",
  "report_type": "balance_sheet",
  "is_default": true,
  "is_active": true
}
```

#### Get Template
```
GET /api/financial-statement-templates/{id}/
```

#### Update Template
```
PUT /api/financial-statement-templates/{id}/
```

#### Set Default Template
```
POST /api/financial-statement-templates/{id}/set_default/
```

#### Duplicate Template
```
POST /api/financial-statement-templates/{id}/duplicate/
```

### Statements

#### Generate Statement
```
POST /api/financial-statements/generate/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "as_of_date": "2025-12-31",
  "status": "draft",
  "include_pending": false
}
```

**Query Parameters:**
- `format`: `json` (default), `markdown`, or `html`

#### List Statements
```
GET /api/financial-statements/
```

#### Get Statement
```
GET /api/financial-statements/{id}/
```

#### Finalize Statement
```
POST /api/financial-statements/{id}/finalize/
```

#### Archive Statement
```
POST /api/financial-statements/{id}/archive/
```

#### Export to Excel
```
GET /api/financial-statements/{id}/export_excel/
```

#### Quick Balance Sheet
```
GET /api/financial-statements/quick_balance_sheet/
```

#### Quick Income Statement
```
GET /api/financial-statements/quick_income_statement/
```

### Time Series

#### Generate Time Series
```
POST /api/financial-statements/time_series/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimension": "month",  // or ["month", "quarter"] for multiple
  "line_numbers": [1, 2, 3],  // optional
  "include_pending": false
}
```

**Query Parameters:**
- `format`: `json` (default), `markdown`, or `html`
- `preview`: `true` to generate preview without saving
- `include_metadata`: `true` to include detailed calculation metadata for debugging

**Response:** Time series data with values grouped by period

### Comparisons

#### Generate with Comparisons
```
POST /api/financial-statements/with_comparisons/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_period", "previous_year"],
  "dimension": "month",  // optional: break down current period
  "include_pending": false
}
```

**Query Parameters:**
- `format`: `json` (default), `markdown`, or `html`
- `preview`: `true` to generate preview without saving

**Response:** Statement with comparison data for each comparison type

### Preview

#### Preview Statement
```
POST /api/financial-statements/preview/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "include_pending": false
}
```

**Query Parameters:**
- `format`: `json` (default), `markdown`, or `html`

**Response:** Statement data without database record

---

## Time Series Analysis

### Overview

Time series analysis groups financial statement data by time dimensions, allowing trend analysis over time. This is particularly useful for Cash Flow statements.

### Available Dimensions

- `day`: Group by day
- `week`: Group by week (Monday to Sunday)
- `month`: Group by month
- `quarter`: Group by quarter
- `semester`: Group by semester
- `year`: Group by year

### Multiple Dimensions

You can request multiple dimensions in a single request:

```json
POST /api/financial-statements/time_series/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimensions": ["month", "quarter", "year"]
}
```

The response will include a `data` dictionary keyed by dimension.

### Utility Functions

**Location:** `accounting/utils_time_dimensions.py`

#### `get_period_start(date, dimension)`
Returns the start date of the period containing the given date.

#### `get_period_end(date, dimension)`
Returns the end date of the period containing the given date.

#### `get_period_key(date, dimension)`
Returns a unique key for the period (e.g., "2025-01" for January 2025).

#### `generate_periods(start_date, end_date, dimension)`
Generates a list of all periods within the date range.

**Returns:** `List[Dict[str, Any]]` with period information:
```python
[
  {
    "period_key": "2025-01",
    "period_label": "January 2025",
    "start_date": date(2025, 1, 1),
    "end_date": date(2025, 1, 31)
  },
  ...
]
```

#### `format_period_label(date, dimension)`
Formats a date as a human-readable period label.

---

## Period Comparisons

### Overview

Period comparisons allow you to compare the current period with other periods, calculating absolute and percentage changes. This is useful for Income Statements and Balance Sheets.

### Comparison Types

- `previous_period`: Same length period ending the day before current_start
- `previous_year`: Same period dates from the previous year
- `ytd_previous_year`: Year-to-date from the previous year (Jan 1 to current_end of previous year)
- `last_12_months`: Rolling 12 months ending at current_end
- `same_period_last_year`: Exact same dates from the previous year

### Dimension Breakdown

You can break down the current period by a time dimension and compare each sub-period:

```json
POST /api/financial-statements/with_comparisons/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_year"],
  "dimension": "month"  // Break down Q1 into months
}
```

This generates comparisons for January, February, and March separately.

### Utility Functions

#### `get_comparison_period(current_start, current_end, comparison_type)`
Calculates the comparison period dates based on comparison type.

**Returns:** `Tuple[date, date]` - (comparison_start, comparison_end)

#### `calculate_period_comparison(current_value, comparison_value, comparison_type)`
Calculates comparison metrics between two values.

**Returns:** `Dict[str, Any]`:
```python
{
  "current_value": float,
  "comparison_value": float,
  "absolute_change": float,  # current - comparison
  "percentage_change": float,  # ((current - comparison) / comparison) * 100
  "comparison_type": str
}
```

**Note:** `percentage_change` is `None` if `comparison_value` is 0.

---

## Output Formats

### JSON (Default)

The default format returns structured JSON data.

**Content-Type:** `application/json`

**Features:**
- Complete data structure
- Includes `formatted.markdown` and `formatted.html` in response
- All metadata included

**Example Response:**
```json
{
  "id": 1,
  "name": "Balance Sheet 2025",
  "report_type": "balance_sheet",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "lines": [...],
  "total_assets": "1000000.00",
  "formatted": {
    "markdown": "# Balance Sheet 2025\n\n...",
    "html": "<!DOCTYPE html>..."
  }
}
```

### Markdown

Formatted Markdown output for documentation and version control.

**Content-Type:** `text/markdown; charset=utf-8`

**Features:**
- Table format with proper alignment
- Hierarchical headers
- Indentation using `&nbsp;` entities (4 per level)
- Bold formatting for entire rows when `is_bold` is true
- Monetary value formatting

**Usage:**
```
POST /api/financial-statements/generate/?format=markdown
```

**Example Output:**
```markdown
# Balance Sheet 2025

**Report Type:** Balance Sheet
**Period:** 2025-01-01 to 2025-12-31
**Currency:** USD
**Status:** draft

---

| Line | Label | Debit | Credit | Balance |
|------|-------|-------|--------|---------|
| 1 | **ASSETS** | - | - | - |
| 2 | &nbsp;&nbsp;&nbsp;&nbsp;**Current Assets** | - | - | - |
| 3 | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Cash and Cash Equivalents | - | - | **$50,000.00** |
```

### HTML

Formatted HTML with embedded CSS for browser viewing.

**Content-Type:** `text/html; charset=utf-8`

**Features:**
- Embedded CSS styling
- Responsive tables
- Indentation using inline `padding-left` styles
- Font sizes based on indent level (font-level-0 to font-level-4)
- Bold formatting for entire rows
- Collapsible rows (click to expand/collapse child rows)
- Color coding for positive/negative values in comparisons
- Arial font throughout

**Usage:**
```
POST /api/financial-statements/generate/?format=html
```

**Styling:**
- Headers with colored borders
- Hover effects on table rows
- Right-aligned amounts
- Metadata section with gray text
- Collapsible row icons (▶/▼)

### Excel

Excel export for spreadsheet analysis.

**Content-Type:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

**Usage:**
```
GET /api/financial-statements/{id}/export_excel/
```

**Features:**
- .xlsx format
- Formatted headers
- Calculated totals
- Direct download

---

## Preview Functionality

### Overview

Preview mode allows you to generate and test financial statements without saving them to the database. This is useful for:
- Testing template configurations
- Iterating on report designs
- Avoiding database clutter during development

### Endpoints

#### Preview Statement
```
POST /api/financial-statements/preview/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "include_pending": false
}
```

**Query Parameters:**
- `format`: `json`, `markdown`, or `html`

#### Preview Time Series
```
POST /api/financial-statements/time_series/?preview=true
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimension": "month"
}
```

#### Preview Comparisons
```
POST /api/financial-statements/with_comparisons/?preview=true
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_year"]
}
```

### Response Indicators

Preview responses include an `is_preview: true` flag and may show "Preview (not saved)" in formatted outputs.

---

## Account Mapping

### Strategies

Account mapping determines which accounts contribute to each line item. Multiple strategies are supported:

#### 1. By Specific Account
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=1,
    label="Main Cash Account",
    account=account_instance,  # Single account
    calculation_type="balance",
)
```

#### 2. By Account ID List
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=2,
    label="Cash Accounts",
    account_ids=[1, 2, 3],  # Specific account IDs
    calculation_type="balance",
)
```

#### 3. By Code Prefix
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=3,
    label="Accounts Receivable",
    account_code_prefix="1200",  # All accounts starting with 1200
    calculation_type="balance",
)
```

#### 4. By Path Contains
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=4,
    label="Operating Expenses",
    account_path_contains="Expenses > Operating",  # Path contains this
    calculation_type="balance",
)
```

### Matching Priority

The system checks criteria in this order:
1. `account` (single account)
2. `account_ids` (list of IDs)
3. `account_code_prefix` (code prefix)
4. `account_path_contains` (path string)

Only the first matching criterion is used.

---

## Calculation Types

### Available Types

#### `sum`
Simple sum of account balances.

**Use Case:** Aggregating multiple accounts of the same type.

#### `difference`
Debit amount minus Credit amount.

**Use Case:** Net change calculations.

#### `balance`
Uses `account_direction` to determine normal balance (debit/credit).

**Use Case:** Standard balance sheet and income statement calculations, including Cash Balance lines in Cash Flow statements.

**Account Direction:**
- `1`: Debit normal (Assets, Expenses)
- `-1`: Credit normal (Liabilities, Equity, Revenue)

**Cash Balance Calculation:**
For Cash Flow statements with `calculation_type='balance'`, the system calculates the **cumulative ending balance** as of each period's end date:

1. If `as_of_date >= account.balance_date`: Uses stored opening balance + journal entries from `balance_date` to `as_of_date`
2. If `as_of_date < account.balance_date` (or no `balance_date`): Sums ALL journal entries from the beginning up to `as_of_date`

This ensures Cash Balance shows the running total, not just period changes.

#### `formula`
References other lines using formula syntax.

**Use Case:** Calculated lines (totals, subtotals, net income).

**Formula Syntax:**
- `L1`, `L2`, etc. refer to line numbers
- Supports `+`, `-`, `*`, `/` operators
- Supports parentheses for grouping

**Examples:**
- `"L1 + L2"`: Sum of lines 1 and 2
- `"L10 - L20"`: Line 10 minus line 20
- `"(L1 + L2) - L3"`: Sum of lines 1 and 2, minus line 3

---

## Calculation Metadata (Debugging)

### Overview

When troubleshooting financial statement calculations, you can request detailed metadata showing exactly how each value was computed. This is particularly useful for understanding Cash Balance calculations.

### Enabling Metadata

Add `include_metadata=true` query parameter to time series requests:

```
POST /api/financial-statements/time_series/?include_metadata=true
{
  "template_id": 1,
  "start_date": "2020-01-01",
  "end_date": "2025-12-31",
  "dimension": "month"
}
```

### Metadata Structure for Balance Calculations

For lines with `calculation_type='balance'`, each period's data includes a `calculation_metadata` object with detailed breakdown:

#### Leaf Account Metadata
```json
{
  "calculation_metadata": {
    "accounts": [
      {
        "id": 123,
        "name": "Cash - Checking",
        "account_code": "1010",
        "calculation_type": "balance",
        "opening_balance": 0.0,
        "balance_date": "2025-08-01",
        "ending_balance": -34089.19,
        "value": -34089.19,
        "balance_calculation": {
          "is_parent": false,
          "calculation_mode": "from_beginning",
          "as_of_date": "2020-01-31",
          "account_balance_date": "2025-08-01",
          "used_opening_balance": false,
          "stored_opening_balance": 0.0,
          "entry_count": 145,
          "entries_date_range": {
            "min_date": "2019-03-15",
            "max_date": "2020-01-28"
          },
          "total_debit": 50000.00,
          "total_credit": 84089.19,
          "net_movement": -34089.19,
          "account_direction": 1,
          "adjusted_change": -34089.19,
          "ending_balance": -34089.19,
          "calculation_explanation": "Net movement (-34089.19) × direction (1) = -34089.19"
        }
      }
    ]
  }
}
```

#### Parent Account Metadata
For parent accounts, the metadata shows the sum of children:
```json
{
  "balance_calculation": {
    "is_parent": true,
    "children_count": 3,
    "children": [
      {
        "account_id": 124,
        "account_name": "Cash - Bradesco",
        "account_code": "1010.01",
        "balance_contribution": -20000.00,
        "details": { ... }
      },
      {
        "account_id": 125,
        "account_name": "Cash - Safra",
        "account_code": "1010.02",
        "balance_contribution": -14089.19,
        "details": { ... }
      }
    ],
    "total_from_children": -34089.19
  }
}
```

### Key Metadata Fields

| Field | Description |
|-------|-------------|
| `calculation_mode` | `"from_beginning"` (sum all entries) or `"from_balance_date"` (use stored balance + entries) |
| `used_opening_balance` | Whether the account's stored `balance` was used as starting point |
| `stored_opening_balance` | The account's stored `balance` field value |
| `account_balance_date` | The date the stored balance is valid as of |
| `entry_count` | Number of journal entries included in calculation |
| `entries_date_range` | Min/max transaction dates of included entries |
| `total_debit` / `total_credit` | Raw sums of debit and credit amounts |
| `net_movement` | `total_debit - total_credit` before direction applied |
| `account_direction` | `1` (debit normal) or `-1` (credit normal) |
| `adjusted_change` | Net movement × account direction |
| `ending_balance` | Final calculated balance |
| `calculation_explanation` | Human-readable formula showing the calculation |

### Debugging Use Cases

1. **Cash Balance showing 0**: Check `entry_count` - if 0, no journal entries matched the date range
2. **Unexpected values**: Compare `total_debit` and `total_credit` against expected amounts
3. **Wrong sign**: Check `account_direction` - may need to adjust the account's normal balance setting
4. **Missing historical data**: Check `entries_date_range` - entries may be outside expected range
5. **Balance date issues**: If `calculation_mode` is `"from_beginning"`, the stored `balance_date` is after the period being calculated

---

## Report Types

### Balance Sheet

**Purpose:** Shows assets, liabilities, and equity as of a specific date.

**Key Characteristics:**
- Uses `as_of_date` for balance calculations
- Typically uses `balance` calculation type
- Accounts are calculated as of the specific date
- Includes `total_assets`, `total_liabilities`, `total_equity`

**Example:**
```python
statement = generator.generate_statement(
    template=balance_sheet_template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
    as_of_date=date(2025, 12, 31),  # Balance as of year-end
)
```

### Income Statement (P&L)

**Purpose:** Shows revenue and expenses for a period.

**Key Characteristics:**
- Uses period (`start_date` to `end_date`) for activity
- Typically uses `difference` or `balance` calculation type
- Calculates period activity (not balance as of date)
- Includes `net_income` calculation

**Example:**
```python
statement = generator.generate_statement(
    template=income_statement_template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 3, 31),  # Q1 activity
    as_of_date=date(2025, 3, 31),  # Same as end_date
)
```

### Cash Flow Statement

**Purpose:** Shows cash inflows and outflows over time.

**Key Characteristics:**
- Uses period activity
- Focuses on cash accounts
- Calculates beginning balance, ending balance, and period change
- Useful for time series analysis

**Example:**
```python
statement = generator.generate_statement(
    template=cash_flow_template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)
```

---

## Usage Examples

### Python Examples

#### Generate Balance Sheet
```python
from accounting.services.financial_statement_service import FinancialStatementGenerator
from accounting.models_financial_statements import FinancialStatementTemplate
from datetime import date

generator = FinancialStatementGenerator(company_id=1)
template = FinancialStatementTemplate.objects.get(id=1)

statement = generator.generate_statement(
    template=template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
    as_of_date=date(2025, 12, 31),
    status='draft',
    include_pending=False,
)

print(f"Total Assets: {statement.total_assets}")
print(f"Total Liabilities: {statement.total_liabilities}")
print(f"Total Equity: {statement.total_equity}")
```

#### Generate Time Series
```python
time_series = generator.generate_time_series(
    template=template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
    dimension='month',
    include_pending=False,
)

for line in time_series['lines']:
    print(f"{line['label']}:")
    for period in line['data']:
        print(f"  {period['period_label']}: {period['value']}")
```

#### Generate with Comparisons
```python
result = generator.generate_with_comparisons(
    template=template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 3, 31),
    comparison_types=['previous_period', 'previous_year'],
    include_pending=False,
)

statement = result['statement']
comparisons = result['comparisons']

for line in statement['lines']:
    line_num = line['line_number']
    prev_year = comparisons['previous_year']['lines'][line_num]
    print(f"{line['label']}:")
    print(f"  Current: {line['balance']}")
    print(f"  Previous Year: {prev_year['comparison_value']}")
    print(f"  Change: {prev_year['absolute_change']} ({prev_year['percentage_change']}%)")
```

### API Examples

#### Generate Statement (JSON)
```bash
curl -X POST https://api.example.com/api/financial-statements/generate/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "as_of_date": "2025-12-31",
    "include_pending": false
  }'
```

#### Generate Statement (Markdown)
```bash
curl -X POST "https://api.example.com/api/financial-statements/generate/?format=markdown" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'
```

#### Generate Time Series
```bash
curl -X POST https://api.example.com/api/financial-statements/time_series/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "dimension": "month"
  }'
```

#### Generate with Comparisons (HTML)
```bash
curl -X POST "https://api.example.com/api/financial-statements/with_comparisons/?format=html" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "comparison_types": ["previous_year"]
  }'
```

### JavaScript Examples

#### Generate and Display HTML
```javascript
const response = await fetch('/api/financial-statements/generate/?format=html', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Token YOUR_TOKEN'
  },
  body: JSON.stringify({
    template_id: 1,
    start_date: '2025-01-01',
    end_date: '2025-12-31'
  })
});

const html = await response.text();
document.getElementById('report-container').innerHTML = html;
```

#### Generate Time Series for Chart
```javascript
const response = await fetch('/api/financial-statements/time_series/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Token YOUR_TOKEN'
  },
  body: JSON.stringify({
    template_id: 1,
    start_date: '2025-01-01',
    end_date: '2025-12-31',
    dimension: 'month'
  })
});

const data = await response.json();
const line = data.lines[0]; // First line

// Prepare for Chart.js
const labels = line.data.map(d => d.period_label);
const values = line.data.map(d => d.value);

new Chart(ctx, {
  type: 'line',
  data: {
    labels: labels,
    datasets: [{
      label: line.label,
      data: values
    }]
  }
});
```

---

## Integration Guide

### Frontend Integration

#### Displaying HTML Reports
```javascript
// Fetch HTML directly
const htmlResponse = await fetch(
  `/api/financial-statements/generate/?format=html`,
  {
    method: 'POST',
    body: JSON.stringify({ template_id: 1, ... })
  }
);
const html = await htmlResponse.text();

// Render in iframe or container
document.getElementById('report').innerHTML = html;
```

#### Building Custom Tables from JSON
```javascript
const jsonResponse = await fetch('/api/financial-statements/generate/');
const data = await jsonResponse.json();

// Build table
const table = document.createElement('table');
data.lines.forEach(line => {
  const row = document.createElement('tr');
  row.innerHTML = `
    <td>${line.line_number}</td>
    <td style="padding-left: ${line.indent_level * 20}px">${line.label}</td>
    <td>${formatCurrency(line.balance)}</td>
  `;
  if (line.is_bold) {
    row.style.fontWeight = 'bold';
  }
  table.appendChild(row);
});
```

### Backend Integration

#### Scheduled Report Generation
```python
from celery import shared_task
from accounting.services.financial_statement_service import FinancialStatementGenerator
from datetime import date

@shared_task
def generate_monthly_reports():
    generator = FinancialStatementGenerator(company_id=1)
    template = FinancialStatementTemplate.objects.get(
        report_type='income_statement',
        is_default=True
    )
    
    # Generate for previous month
    today = date.today()
    start_date = date(today.year, today.month - 1, 1)
    end_date = date(today.year, today.month, 1) - timedelta(days=1)
    
    statement = generator.generate_statement(
        template=template,
        start_date=start_date,
        end_date=end_date,
        status='final',
    )
    
    # Send via email, store in S3, etc.
    return statement.id
```

#### Custom Report Formatting
```python
from accounting.views_financial_statements import FinancialStatementViewSet

# Access formatting methods
viewset = FinancialStatementViewSet()
currency = viewset._get_company_currency(company_id=1)

# Format as markdown
markdown = viewset._format_as_markdown(statement, currency)

# Format as HTML
html = viewset._format_as_html(statement, currency)
```

---

## Key Functions Reference

### Service Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `generate_statement()` | Generate and save statement | `FinancialStatement` |
| `preview_statement()` | Generate preview (no save) | `Dict[str, Any]` |
| `generate_time_series()` | Generate time series data | `Dict[str, Any]` |
| `generate_with_comparisons()` | Generate with comparisons | `Dict[str, Any]` |
| `_calculate_line_value()` | Calculate single line value | `Decimal` |
| `_get_accounts_for_line()` | Get accounts for line | `List[Account]` |
| `_calculate_balance_sheet_line()` | Calculate balance sheet line | `Decimal` |
| `_calculate_income_statement_line()` | Calculate income statement line | `Decimal` |
| `_calculate_cash_flow_line()` | Calculate cash flow line | `Decimal` |
| `_evaluate_formula()` | Evaluate formula string | `Decimal` |

### Utility Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `get_period_start(date, dimension)` | Get period start date | `date` |
| `get_period_end(date, dimension)` | Get period end date | `date` |
| `get_period_key(date, dimension)` | Get period key | `str` |
| `generate_periods(start, end, dimension)` | Generate period list | `List[Dict]` |
| `format_period_label(date, dimension)` | Format period label | `str` |
| `get_comparison_period(start, end, type)` | Get comparison dates | `Tuple[date, date]` |
| `calculate_period_comparison(current, comp, type)` | Calculate comparison metrics | `Dict[str, Any]` |

---

## Notes and Best Practices

### Performance

- **Time Series**: Can generate many periods (especially with `dimension='day'`). Consider limiting date ranges or using `line_numbers` to filter specific lines.
- **Comparisons**: Generate additional statements, which can be costly. Use `include_pending=False` for better performance.
- **Preview Mode**: Use preview mode during development to avoid database clutter.

### Data Consistency

- **Pending Transactions**: Use `include_pending` carefully. Posted transactions are typically more reliable for final reports.
- **Currency**: Ensure currency is set correctly. The system attempts to find company currency from accounts, but may fall back to first available currency.
- **Account Mapping**: Test account mappings thoroughly. Use preview mode to verify before generating final statements.

### Formatting

- **Indentation**: Markdown uses `&nbsp;` entities (4 per level). HTML uses inline `padding-left` styles.
- **Bold**: When `is_bold` is true, the entire row (including numbers) is bold in both Markdown and HTML.
- **Font Sizes**: HTML includes font size classes based on indent level (font-level-0 to font-level-4).
- **Collapsible Rows**: HTML supports collapsible rows for hierarchical data. Click parent rows to expand/collapse.

### Error Handling

- **Missing Accounts**: If no accounts match a line template, the line value is `Decimal('0.00')`.
- **Formula Errors**: Invalid formulas result in `Decimal('0.00')`. Check formula syntax carefully.
- **Comparison Errors**: If a comparison period cannot be generated (e.g., insufficient data), an error is included in the comparison data.

---

## Future Enhancements

Potential improvements and features:

1. **PDF Export** - Generate PDF reports
2. **Budget vs Actual** - Compare actuals to budgets
3. **Multi-Currency** - Support multiple currencies in one statement
4. **Drill-Down** - Click line item to see underlying transactions
5. **Scheduled Reports** - Auto-generate statements on schedule
6. **Email Reports** - Send statements via email
7. **Custom Formulas** - More advanced formula engine
8. **Account Groups** - Pre-defined account groupings
9. **Notes and Disclosures** - Add notes to statements
10. **Export Templates** - Save and reuse export configurations

---

## File Locations

- **Models**: `accounting/models_financial_statements.py`
- **Service**: `accounting/services/financial_statement_service.py`
- **Views/API**: `accounting/views_financial_statements.py`
- **Serializers**: `accounting/serializers_financial_statements.py`
- **Utilities**: `accounting/utils_time_dimensions.py`
- **URLs**: `accounting/urls.py` (routes added)

---

## Support

For issues or questions:
1. Check this documentation
2. Review code comments in service files
3. Use preview mode to test configurations
4. Check database logs for calculation details

---

*Last Updated: 2025-12-01*

