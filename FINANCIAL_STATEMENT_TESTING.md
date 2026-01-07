# Financial Statement Testing Guide

This guide helps you test and debug financial statement generation, especially for parent account calculations.

## Quick Start

### 1. List Available Templates

```bash
python manage.py test_financial_statements --company-id 1 --list-templates
```

This shows all financial statement templates available for your company.

### 2. List Parent Accounts

```bash
python manage.py test_financial_statements --company-id 1 --list-parent-accounts
```

This shows all parent accounts, their children, and balance calculations to help identify which accounts might have calculation issues.

### 3. Create a Test Template

```bash
python manage.py test_financial_statements --company-id 1 --create-template
```

This creates a test template called "Parent Account Test Template" that includes:
- Lines for parent accounts
- Lines for their children accounts
- Proper indentation to show hierarchy

The template is designed to help debug parent account calculation issues.

### 4. Generate a Preview

```bash
# Basic preview with default dates (current year)
python manage.py test_financial_statements --company-id 1 --template-id 1 --preview

# Preview with specific dates
python manage.py test_financial_statements \
  --company-id 1 \
  --template-id 1 \
  --preview \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --as-of-date 2025-12-31

# Preview with detailed account debugging
python manage.py test_financial_statements \
  --company-id 1 \
  --template-id 1 \
  --preview \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --debug-accounts
```

The `--debug-accounts` flag shows:
- For leaf accounts: journal entry counts, debit/credit totals, calculated balance
- For parent accounts: list of children, each child's balance, sum of children, and comparison with parent balance

## Understanding the Output

### Normal Preview Output

```
Line   Label                                              Balance
--------------------------------------------------------------------------------
1      PARENT ACCOUNT TEST
2      
3      1010 - Cash (PARENT)                                   1000.00
4        1010.01 - Cash - Bank A                               500.00
5        1010.02 - Cash - Bank B                               500.00
```

### Debug Output

When using `--debug-accounts`, you'll see detailed information:

**For Leaf Accounts:**
```
Line 4: 1010.01 - Cash - Bank A
Account: 1010.01 - Cash - Bank A (ID: 123)
Is Leaf: True
Account Direction: 1
Stored Balance: 500.00
Balance Date: 2024-12-31
  Entry Count: 10
  Total Debit: 2000.00
  Total Credit: 1500.00
  Net Movement: 500.00
  Calculated Balance: 500.00
```

**For Parent Accounts:**
```
Line 3: 1010 - Cash (PARENT)
Account: 1010 - Cash (ID: 122)
Is Leaf: False
Account Direction: 1
Stored Balance: 1000.00
Balance Date: 2024-12-31
  Children Count: 2
  Children:
    - 1010.01 - Cash - Bank A (ID: 123): 500.00
    - 1010.02 - Cash - Bank B (ID: 124): 500.00
  Sum of Children: 1000.00
  Parent Calculated Balance: 1000.00
  ✓ Balance matches sum of children
```

If there's a mismatch, you'll see:
```
  ⚠ WARNING: Mismatch! Sum of children (1000.00) ≠ Parent balance (0.00)
```

## Common Issues and Solutions

### Issue: Parent Account Shows 0.00

**Possible Causes:**
1. **No children found**: The parent account might not have children for the specified company
   - Check: `--list-parent-accounts` to see if children exist
   - Solution: Ensure children accounts are properly linked to the parent

2. **Children filtered out**: The `get_children().filter(company_id=company_id)` might be filtering out children
   - Check: Verify children have the same `company_id` as the parent
   - Solution: Ensure all accounts in the hierarchy have the correct `company_id`

3. **Date range issues**: Children might have entries outside the date range
   - Check: Use `--debug-accounts` to see entry counts for each child
   - Solution: Adjust date range or check journal entry dates

### Issue: Parent Balance Doesn't Match Sum of Children

**Possible Causes:**
1. **Account direction mismatch**: Children might have different account directions
   - Check: Look at `account_direction` in debug output
   - Solution: Verify account directions are correct

2. **Calculation method mismatch**: Different calculation methods used for parent vs children
   - Check: The `calculation_type` in line template (balance, sum, difference)
   - Solution: Ensure consistent calculation type

3. **Pending entries**: One calculation includes pending, the other doesn't
   - Check: Use `--include-pending` flag consistently
   - Solution: Ensure both parent and children use same pending flag

## Using the API

You can also use the API endpoints directly:

### Preview via API

```bash
curl -X POST http://localhost:8000/api/financial-statements/preview/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "as_of_date": "2025-12-31",
    "include_pending": false
  }'
```

### Preview with Metadata (for debugging)

```bash
curl -X POST "http://localhost:8000/api/financial-statements/time_series/?include_metadata=true&preview=true" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "template_id": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "dimension": "month"
  }'
```

## Best Practices

1. **Always use `--debug-accounts` first** when investigating parent account issues
2. **Check `--list-parent-accounts`** to understand the account hierarchy
3. **Create a test template** with known parent accounts to isolate the issue
4. **Compare stored balances vs calculated balances** using the debug output
5. **Verify date ranges** - ensure journal entries fall within the period
6. **Check company_id filtering** - ensure all accounts belong to the same company

## Troubleshooting

### No templates found
- Create a template using `--create-template` or via the admin interface

### Template not found
- Verify the template ID with `--list-templates`
- Ensure the template belongs to the correct company

### All balances are zero
- Check if journal entries exist for the date range
- Verify account codes match between template and accounts
- Check if accounts are active (`is_active=True`)

### Parent account has no children
- Verify parent-child relationships in the database
- Check if children have the same `company_id`
- Ensure MPTT tree structure is correct (run `python manage.py rebuild_tree` if needed)

## Related Files

- `accounting/services/financial_statement_service.py` - Main service for generating statements
- `accounting/models_financial_statements.py` - Template and statement models
- `accounting/models.py` - Account model with `calculate_balance()` method

