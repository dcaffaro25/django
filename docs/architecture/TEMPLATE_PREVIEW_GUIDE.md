# Financial Statement Template Preview Guide

This guide shows you how to access and use the financial statement template preview feature.

## Accessing the Preview Page

### Option 1: Web Interface

Navigate to:
```
http://your-domain/<tenant_id>/financial-statements/template-preview/
```

For example:
```
http://localhost:8000/1/financial-statements/template-preview/
```

This will open a web interface where you can:
1. Select a financial statement template
2. Set date ranges
3. Generate a preview
4. View debug information for parent accounts

### Option 2: Management Command

Use the command-line tool:

```bash
# List available templates
python manage.py test_financial_statements --company-id 1 --list-templates

# Generate a preview
python manage.py test_financial_statements \
  --company-id 1 \
  --template-id 1 \
  --preview \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --debug-accounts
```

### Option 3: API Endpoint

Use the REST API:

```bash
POST /<tenant_id>/api/financial-statements/preview/
Content-Type: application/json

{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "as_of_date": "2025-12-31",
  "include_pending": false
}
```

## Features

### 1. Template Selection
- View all active templates for your company
- Filter by report type (Balance Sheet, Income Statement, etc.)

### 2. Date Configuration
- **Start Date**: Beginning of the reporting period
- **End Date**: End of the reporting period
- **As of Date**: For balance sheets, the specific date to calculate balances

### 3. Options
- **Include Pending**: Include pending journal entries in calculations
- **Show Debug Information**: Display detailed calculation breakdowns for each account

### 4. Preview Output
- Formatted table showing all line items
- Balances with proper formatting (negative in red)
- Indentation showing account hierarchy
- Bold formatting for totals and parent accounts

### 5. Debug Information
When enabled, shows for each account:
- **Leaf Accounts**:
  - Journal entry count
  - Total debit and credit amounts
  - Net movement
  - Calculated balance

- **Parent Accounts**:
  - List of all children
  - Each child's balance
  - Sum of children balances
  - Parent calculated balance
  - Warning if balances don't match

## Troubleshooting Parent Account Issues

### Issue: Parent Account Shows 0.00

**Check:**
1. Open the preview with `--debug-accounts` flag
2. Look for warnings about missing children
3. Verify children have the same `company_id` as parent

**Solution:**
- Ensure all child accounts belong to the same company
- Check that children are properly linked to the parent in the account hierarchy

### Issue: Parent Balance Doesn't Match Sum of Children

**Check:**
1. Enable debug information
2. Compare "Sum of Children" vs "Parent Calculated Balance"
3. Check if any children have zero balances unexpectedly

**Common Causes:**
- Date range excludes some journal entries
- Account direction mismatch
- Pending entries not included when they should be

## Quick Test Workflow

1. **List templates:**
   ```bash
   python manage.py test_financial_statements --company-id 1 --list-templates
   ```

2. **Check parent accounts:**
   ```bash
   python manage.py test_financial_statements --company-id 1 --list-parent-accounts
   ```

3. **Create test template (if needed):**
   ```bash
   python manage.py test_financial_statements --company-id 1 --create-template
   ```

4. **Generate preview with debugging:**
   ```bash
   python manage.py test_financial_statements \
     --company-id 1 \
     --template-id 1 \
     --preview \
     --start-date 2025-01-01 \
     --end-date 2025-12-31 \
     --debug-accounts
   ```

5. **Or use web interface:**
   - Navigate to `/<tenant_id>/financial-statements/template-preview/`
   - Select template and dates
   - Check "Show Debug Information"
   - Click "Generate Preview"

## Next Steps

After identifying issues with parent accounts:
1. Review the debug output to see which accounts are problematic
2. Check the account hierarchy in the admin interface
3. Verify journal entries exist for the date range
4. Ensure company_id is consistent across the account tree

For more details, see `FINANCIAL_STATEMENT_TESTING.md`.

