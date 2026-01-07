# Financial Statement Formula Feature Guide

## Overview

The formula feature allows you to create calculated lines in financial statements that reference other line values. This is useful for creating subtotals, totals, and derived metrics like "Net Income" or "Total Assets".

## How It Works

### 1. Formula Syntax

Formulas use a simple syntax where you reference other lines using `L{line_number}`:

- **`L1`** - References line number 1
- **`L2`** - References line number 2
- **`L10`** - References line number 10

### 2. Supported Operations

The formula evaluator supports standard Python mathematical operations:

- **Addition**: `+`
- **Subtraction**: `-`
- **Multiplication**: `*`
- **Division**: `/`
- **Parentheses**: `()` for grouping

### 3. Formula Examples

```
# Simple addition
L1 + L2

# Subtraction
L10 - L11

# Complex calculation
L1 + L2 - L3

# With parentheses
(L1 + L2) - (L3 + L4)

# Net Income calculation (Revenue - Expenses)
L5 - L15

# Total Assets (sum of asset categories)
L1 + L2 + L3 + L4
```

## Implementation Details

### Calculation Order

**Important**: Lines are processed in order by `line_number`. A formula can only reference lines that have already been calculated (lower line numbers).

**Example:**
```
Line 1: Revenue = 1000 (from accounts)
Line 2: Expenses = 500 (from accounts)
Line 3: Net Income = L1 - L2 (formula) ✅ Works - L1 and L2 are already calculated
Line 4: Tax = L3 * 0.2 (formula) ✅ Works - L3 is already calculated
Line 5: Net After Tax = L3 - L4 (formula) ✅ Works - L3 and L4 are already calculated
```

**This won't work:**
```
Line 1: Net Income = L2 - L3 (formula) ❌ Fails - L2 and L3 don't exist yet
Line 2: Revenue = 1000 (from accounts)
Line 3: Expenses = 500 (from accounts)
```

### Code Flow

1. **Line Processing Order**: Lines are processed sequentially by `line_number`
2. **Value Storage**: Each calculated value is stored in `line_values` dictionary: `{line_number: Decimal(value)}`
3. **Formula Detection**: When `calculation_type == 'formula'` and `formula` field is set
4. **Formula Evaluation**: Calls `_evaluate_formula()` method
5. **Substitution**: Replaces `L{number}` with actual values from `line_values`
6. **Evaluation**: Uses Python's `eval()` to calculate the result

### Formula Evaluation Function

```python
def _evaluate_formula(
    self,
    formula: str,
    line_values: Dict[int, Decimal],
) -> Decimal:
    """Evaluate a formula referencing other line numbers."""
    # Replace L{number} with actual values
    result = formula
    for line_num, value in line_values.items():
        result = result.replace(f'L{line_num}', str(value))
    
    # Evaluate using Python's eval()
    try:
        return Decimal(str(eval(result)))
    except Exception as e:
        log.warning("Formula evaluation failed: %s - %s", formula, e)
        return Decimal('0.00')
```

## Setting Up Formulas

### 1. Create a Line Template

1. Set `calculation_type` to `'formula'`
2. Set `formula` field to your formula expression
3. **Do NOT** set account mappings (they're ignored for formula lines)

### 2. Example Template Setup

```python
# Line 1: Revenue (from accounts)
line_1 = FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=1,
    label="Revenue",
    calculation_type='sum',
    account_code_prefix='4.1',  # Revenue accounts
    # ... other fields
)

# Line 2: Expenses (from accounts)
line_2 = FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=2,
    label="Expenses",
    calculation_type='sum',
    account_code_prefix='5.1',  # Expense accounts
    # ... other fields
)

# Line 3: Net Income (formula)
line_3 = FinancialStatementLineTemplate.objects.create(
    template=template,
    line_number=3,
    label="Net Income",
    calculation_type='formula',  # ← Set to formula
    formula='L1 - L2',  # ← Formula expression
    is_bold=True,
    # No account mappings needed
)
```

### 3. Via API/Admin

When creating or updating a line template:

```json
{
  "line_number": 10,
  "label": "Total Assets",
  "calculation_type": "formula",
  "formula": "L1 + L2 + L3 + L4",
  "is_bold": true,
  "line_type": "total"
}
```

## Real-World Examples

### Example 1: Income Statement

```
Line 1:  Revenue                    = 10,000 (from accounts)
Line 2:  Cost of Goods Sold         = 4,000 (from accounts)
Line 3:  Gross Profit               = L1 - L2 = 6,000 (formula)
Line 4:  Operating Expenses         = 2,000 (from accounts)
Line 5:  Operating Income            = L3 - L4 = 4,000 (formula)
Line 6:  Other Income                = 500 (from accounts)
Line 7:  Other Expenses              = 200 (from accounts)
Line 8:  Income Before Tax           = L5 + L6 - L7 = 4,300 (formula)
Line 9:  Tax Expense                 = 1,000 (from accounts)
Line 10: Net Income                  = L8 - L9 = 3,300 (formula)
```

### Example 2: Balance Sheet

```
Line 1:  Current Assets              = 5,000 (from accounts)
Line 2:  Fixed Assets                = 10,000 (from accounts)
Line 3:  Total Assets                = L1 + L2 = 15,000 (formula)
Line 4:  Current Liabilities          = 3,000 (from accounts)
Line 5:  Long-term Liabilities        = 5,000 (from accounts)
Line 6:  Total Liabilities           = L4 + L5 = 8,000 (formula)
Line 7:  Equity                       = 7,000 (from accounts)
Line 8:  Total Liabilities & Equity  = L6 + L7 = 15,000 (formula)
Line 9:  Check (should equal assets) = L3 - L8 = 0 (formula)
```

### Example 3: Financial Ratios

```
Line 1:  Net Income                  = 3,300 (from formula or accounts)
Line 2:  Total Assets                = 15,000 (from formula or accounts)
Line 3:  Return on Assets (ROA)       = L1 / L2 = 0.22 (formula, 22%)
```

## Important Considerations

### 1. Line Number Dependencies

- Formulas can only reference lines with **lower line numbers**
- Always place formula lines **after** the lines they reference
- Circular dependencies are not detected (will cause errors)

### 2. Error Handling

- If a referenced line doesn't exist, it's treated as `0.00`
- If formula evaluation fails, returns `0.00` and logs a warning
- Check logs for formula evaluation errors

### 3. Decimal Precision

- All calculations use Python's `Decimal` type for precision
- Results are stored with 2 decimal places
- Intermediate calculations maintain full precision

### 4. Formula vs Account-Based Lines

- **Formula lines**: Calculate from other line values
- **Account-based lines**: Calculate from account balances
- You can mix both in the same template

### 5. Performance

- Formula evaluation is fast (simple string replacement + eval)
- No database queries needed for formula lines
- Processing order ensures dependencies are met

## Debugging Formulas

### Enable Logging

The comprehensive logging we added will show:

```
Line 10 uses formula: L1 + L2 - L3
Line 10 formula result: 5000.00
```

### Common Issues

1. **Formula returns 0.00**
   - Check if referenced lines exist and have values
   - Verify line numbers in formula match actual line numbers
   - Check logs for evaluation errors

2. **Formula evaluation failed**
   - Check formula syntax (valid Python expression)
   - Ensure all referenced lines are calculated before formula line
   - Verify parentheses are balanced

3. **Wrong calculation result**
   - Verify referenced line values are correct
   - Check formula expression matches intended calculation
   - Ensure line numbers are correct

## Best Practices

1. **Use meaningful line numbers**: Keep them sequential and organized
2. **Document formulas**: Use clear labels that explain the calculation
3. **Test incrementally**: Add formulas one at a time and verify results
4. **Use parentheses**: For complex formulas, use parentheses for clarity
5. **Validate dependencies**: Ensure all referenced lines exist and are calculated first
6. **Mark totals**: Use `is_bold=True` and `line_type='total'` for formula totals

## Limitations

1. **No backward references**: Can't reference lines with higher numbers
2. **No circular dependencies**: Can't have A = B + C and B = A + D
3. **Simple evaluator**: Uses Python `eval()` - not a full expression parser
4. **No functions**: Can't use functions like `SUM()`, `AVG()`, etc. (use multiple operations)
5. **No conditional logic**: Can't use `IF` statements (would need account-based logic)

## Future Enhancements

Potential improvements:
- Support for functions: `SUM(L1, L2, L3)`, `AVG(L1, L2)`
- Conditional formulas: `IF(L1 > 0, L1, 0)`
- Range references: `SUM(L1:L5)` for lines 1-5
- Better error messages with line number context
- Formula validation before saving

