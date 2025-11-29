# Financial Statements Implementation Guide

## Overview

A comprehensive financial reporting system has been added to generate and manage financial statements including:
- **Balance Sheet** - Assets, Liabilities, and Equity as of a specific date
- **Income Statement (P&L)** - Revenue and Expenses for a period
- **Cash Flow Statement** - Cash inflows and outflows
- **Trial Balance** - All account balances
- **General Ledger** - Detailed transaction listing
- **Custom Reports** - User-defined report structures

## Architecture

### Models

1. **FinancialStatementTemplate** (`accounting/models_financial_statements.py`)
   - Defines the structure of a financial statement
   - Maps accounts to line items
   - Supports multiple templates per report type
   - Configurable formatting options

2. **FinancialStatementLineTemplate**
   - Individual line items in a template
   - Maps accounts (by ID, code prefix, or path)
   - Supports formulas and calculations
   - Hierarchical structure (parent/child lines)

3. **FinancialStatement**
   - Generated statement instance
   - Stores period, dates, status
   - Contains calculated totals
   - Links to template used

4. **FinancialStatementLine**
   - Individual line in a generated statement
   - Contains calculated values
   - Preserves formatting

5. **FinancialStatementComparison**
   - Compares two statements (period-over-period, year-over-year, etc.)

### Service Layer

**FinancialStatementGenerator** (`accounting/services/financial_statement_service.py`)
- Generates statements from templates
- Calculates balances based on report type
- Handles formulas and calculations
- Supports different calculation methods

### API Endpoints

#### Templates
- `GET /api/financial-statement-templates/` - List templates
- `POST /api/financial-statement-templates/` - Create template
- `GET /api/financial-statement-templates/{id}/` - Get template
- `PUT /api/financial-statement-templates/{id}/` - Update template
- `POST /api/financial-statement-templates/{id}/set_default/` - Set as default
- `POST /api/financial-statement-templates/{id}/duplicate/` - Duplicate template

#### Statements
- `GET /api/financial-statements/` - List statements
- `POST /api/financial-statements/generate/` - Generate new statement
- `GET /api/financial-statements/{id}/` - Get statement
- `POST /api/financial-statements/{id}/finalize/` - Mark as final
- `POST /api/financial-statements/{id}/archive/` - Archive statement
- `GET /api/financial-statements/{id}/export_excel/` - Export to Excel
- `GET /api/financial-statements/quick_balance_sheet/` - Quick balance sheet
- `GET /api/financial-statements/quick_income_statement/` - Quick P&L

#### Comparisons
- `GET /api/financial-statement-comparisons/` - List comparisons
- `POST /api/financial-statement-comparisons/` - Create comparison
- `GET /api/financial-statement-comparisons/{id}/comparison_data/` - Get comparison data

## Setup Instructions

### 1. Create Migration

```bash
python manage.py makemigrations accounting
python manage.py migrate
```

### 2. Create Default Templates

You'll need to create templates for each report type. Example for Balance Sheet:

```python
from accounting.models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
)

# Create Balance Sheet template
template = FinancialStatementTemplate.objects.create(
    company_id=1,
    name="Standard Balance Sheet",
    report_type="balance_sheet",
    is_default=True,
    is_active=True,
)

# Add line templates
# Assets
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=1,
    label="ASSETS",
    line_type="header",
    indent_level=0,
    is_bold=True,
)

FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=2,
    label="Current Assets",
    line_type="header",
    indent_level=1,
    is_bold=True,
)

FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=3,
    label="Cash and Cash Equivalents",
    line_type="account",
    account_code_prefix="1000",  # Accounts starting with 1000
    calculation_type="balance",
    indent_level=2,
)

# ... continue adding lines
```

### 3. Generate Statements

```python
# Via API
POST /api/financial-statements/generate/
{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "as_of_date": "2025-12-31",
    "status": "draft"
}

# Or programmatically
from accounting.services.financial_statement_service import FinancialStatementGenerator

generator = FinancialStatementGenerator(company_id=1)
statement = generator.generate_statement(
    template=template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
    as_of_date=date(2025, 12, 31),
)
```

## Account Mapping Strategies

### 1. By Account ID
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=1,
    label="Cash",
    account_ids=[1, 2, 3],  # Specific account IDs
    calculation_type="balance",
)
```

### 2. By Code Prefix
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=2,
    label="Accounts Receivable",
    account_code_prefix="1200",  # All accounts starting with 1200
    calculation_type="balance",
)
```

### 3. By Path Contains
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=3,
    label="Operating Expenses",
    account_path_contains="Expenses > Operating",  # Path contains this
    calculation_type="balance",
)
```

### 4. By Specific Account
```python
FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=4,
    label="Main Cash Account",
    account=account_instance,  # Single account
    calculation_type="balance",
)
```

## Calculation Types

- **`sum`** - Simple sum of account balances
- **`difference`** - Debit - Credit
- **`balance`** - Uses account_direction (debit/credit normal)
- **`formula`** - References other lines (e.g., "L1 + L2 - L3")

## Report Types

### Balance Sheet
- Uses `as_of_date` for balances
- Calculates assets, liabilities, equity
- Typically uses `balance` calculation type

### Income Statement
- Uses period (`start_date` to `end_date`)
- Calculates revenue and expenses
- Typically uses `difference` or `balance` calculation type

### Cash Flow
- Uses period activity
- Focuses on cash accounts
- Calculates cash inflows/outflows

## Usage Examples

### Quick Balance Sheet
```bash
GET /api/financial-statements/quick_balance_sheet/
```

### Generate Custom Statement
```bash
POST /api/financial-statements/generate/
{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "as_of_date": "2025-03-31",
    "status": "draft"
}
```

### Export to Excel
```bash
GET /api/financial-statements/1/export_excel/
```

### Compare Periods
```bash
POST /api/financial-statement-comparisons/
{
    "name": "Q1 2025 vs Q1 2024",
    "base_statement": 1,
    "comparison_statement": 2,
    "comparison_type": "year_over_year"
}
```

## Next Steps / Enhancements

1. **PDF Export** - Implement PDF generation (currently placeholder)
2. **Budget vs Actual** - Add budget tracking and comparison
3. **Multi-Currency** - Support multiple currencies in one statement
4. **Drill-Down** - Click line item to see underlying transactions
5. **Scheduled Reports** - Auto-generate statements on schedule
6. **Email Reports** - Send statements via email
7. **Custom Formulas** - More advanced formula engine
8. **Account Groups** - Pre-defined account groupings
9. **Comparative Columns** - Show multiple periods side-by-side
10. **Notes and Disclosures** - Add notes to statements

## Files Created

- `accounting/models_financial_statements.py` - Models
- `accounting/services/financial_statement_service.py` - Generation service
- `accounting/serializers_financial_statements.py` - API serializers
- `accounting/views_financial_statements.py` - API views
- Updated `accounting/urls.py` - Added routes

## Testing

```python
# Test template creation
template = FinancialStatementTemplate.objects.create(...)

# Test statement generation
generator = FinancialStatementGenerator(company_id=1)
statement = generator.generate_statement(...)

# Verify lines
assert statement.lines.count() > 0
assert statement.total_assets is not None
```

## Notes

- Statements are company-scoped (tenant-aware)
- Only posted transactions are included by default
- Templates can be duplicated and customized
- Statements can be draft, final, or archived
- Excel export is implemented, PDF is placeholder

