# Detailed Income Statement Endpoint Usage Guide

## Overview

The `detailed_income_statement` endpoint generates a hierarchical income statement from parent accounts, showing only accounts with balances. It uses pre-calculated `AccountBalanceHistory` for fast performance.

## Endpoint

**URL:** `POST /api/financial-statements/detailed_income_statement/`

**Base URL:** `/{tenant}/api/financial-statements/detailed_income_statement/`

## Request Parameters

### Required Parameters

- **`revenue_parent_ids`** (array of integers, optional): List of parent account IDs for revenue accounts
- **`cost_parent_ids`** (array of integers, optional): List of parent account IDs for cost of goods sold (COGS) accounts
- **`expense_parent_ids`** (array of integers, optional): List of parent account IDs for expense accounts
- **`start_date`** (string, required): Start date of the reporting period (format: `YYYY-MM-DD`)
- **`end_date`** (string, required): End date of the reporting period (format: `YYYY-MM-DD`)

**Note:** At least one of `revenue_parent_ids`, `cost_parent_ids`, or `expense_parent_ids` must be provided.

### Optional Parameters

- **`currency_id`** (integer, optional): Currency ID. If not provided, uses the currency from the first account found, or the company's default currency
- **`balance_type`** (string, optional): Balance type to use. Default: `"posted"`
  - `"posted"`: Only posted transactions (state='posted')
  - `"bank_reconciled"`: Only bank-reconciled transactions (is_reconciled=True)
  - `"all"`: All transactions (posted + pending, reconciled + unreconciled)
- **`include_zero_balances`** (boolean, optional): Include accounts with zero balances. Default: `false`

## Request Example

### Basic Request

```bash
POST /api/financial-statements/detailed_income_statement/
Content-Type: application/json

{
  "revenue_parent_ids": [10, 11],
  "cost_parent_ids": [20, 21],
  "expense_parent_ids": [30, 31],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31"
}
```

### Full Request with All Parameters

```bash
POST /api/financial-statements/detailed_income_statement/
Content-Type: application/json

{
  "revenue_parent_ids": [10, 11],
  "cost_parent_ids": [20, 21],
  "expense_parent_ids": [30, 31],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "currency_id": 1,
  "balance_type": "posted",
  "include_zero_balances": false
}
```

### Request with Only Revenues

```bash
POST /api/financial-statements/detailed_income_statement/
Content-Type: application/json

{
  "revenue_parent_ids": [10],
  "start_date": "2025-01-01",
  "end_date": "2025-03-31"
}
```

## Response Structure

### Success Response (200 OK)

```json
{
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "currency": {
    "id": 1,
    "code": "USD",
    "name": "US Dollar"
  },
  "balance_type": "posted",
  "revenues": [
    {
      "id": 10,
      "account_code": "4000",
      "name": "Revenue",
      "path": "Revenue",
      "balance": 150000.00,
      "depth": 0,
      "is_leaf": false,
      "children": [
        {
          "id": 101,
          "account_code": "4100",
          "name": "Product Sales",
          "path": "Revenue > Product Sales",
          "balance": 100000.00,
          "depth": 1,
          "is_leaf": false,
          "children": [
            {
              "id": 1011,
              "account_code": "4110",
              "name": "Online Sales",
              "path": "Revenue > Product Sales > Online Sales",
              "balance": 60000.00,
              "depth": 2,
              "is_leaf": true,
              "children": null
            },
            {
              "id": 1012,
              "account_code": "4120",
              "name": "Retail Sales",
              "path": "Revenue > Product Sales > Retail Sales",
              "balance": 40000.00,
              "depth": 2,
              "is_leaf": true,
              "children": null
            }
          ]
        },
        {
          "id": 102,
          "account_code": "4200",
          "name": "Service Revenue",
          "path": "Revenue > Service Revenue",
          "balance": 50000.00,
          "depth": 1,
          "is_leaf": true,
          "children": null
        }
      ]
    }
  ],
  "costs": [
    {
      "id": 20,
      "account_code": "5000",
      "name": "Cost of Goods Sold",
      "path": "Cost of Goods Sold",
      "balance": 60000.00,
      "depth": 0,
      "is_leaf": false,
      "children": [
        {
          "id": 201,
          "account_code": "5100",
          "name": "Direct Materials",
          "path": "Cost of Goods Sold > Direct Materials",
          "balance": 40000.00,
          "depth": 1,
          "is_leaf": true,
          "children": null
        },
        {
          "id": 202,
          "account_code": "5200",
          "name": "Direct Labor",
          "path": "Cost of Goods Sold > Direct Labor",
          "balance": 20000.00,
          "depth": 1,
          "is_leaf": true,
          "children": null
        }
      ]
    }
  ],
  "expenses": [
    {
      "id": 30,
      "account_code": "6000",
      "name": "Operating Expenses",
      "path": "Operating Expenses",
      "balance": 45000.00,
      "depth": 0,
      "is_leaf": false,
      "children": [
        {
          "id": 301,
          "account_code": "6100",
          "name": "Salaries",
          "path": "Operating Expenses > Salaries",
          "balance": 30000.00,
          "depth": 1,
          "is_leaf": true,
          "children": null
        },
        {
          "id": 302,
          "account_code": "6200",
          "name": "Rent",
          "path": "Operating Expenses > Rent",
          "balance": 15000.00,
          "depth": 1,
          "is_leaf": true,
          "children": null
        }
      ]
    }
  ],
  "totals": {
    "total_revenue": 150000.00,
    "total_costs": 60000.00,
    "gross_profit": 90000.00,
    "total_expenses": 45000.00,
    "net_income": 45000.00
  }
}
```

### Error Responses

#### 400 Bad Request - Missing Required Fields

```json
{
  "error": "start_date and end_date are required"
}
```

#### 400 Bad Request - No Parent Account IDs

```json
{
  "error": "At least one parent account ID list is required"
}
```

#### 400 Bad Request - Invalid Date Format

```json
{
  "error": "Invalid date format. Use YYYY-MM-DD"
}
```

#### 400 Bad Request - Invalid Balance Type

```json
{
  "error": "balance_type must be one of: posted, bank_reconciled, all"
}
```

#### 400 Bad Request - Company Not Found

```json
{
  "error": "Company/tenant not found in request"
}
```

## Response Fields Explanation

### Account Node Structure

Each account in the hierarchy contains:

- **`id`** (integer): Account ID
- **`account_code`** (string): Account code (may be empty)
- **`name`** (string): Account name
- **`path`** (string): Full hierarchical path (e.g., "Revenue > Product Sales > Online Sales")
- **`balance`** (float): Account balance for the period (debit - credit) × account_direction
- **`depth`** (integer): Depth level in the hierarchy (0 = root, 1 = first level, etc.)
- **`is_leaf`** (boolean): Whether this is a leaf account (no children)
- **`children`** (array or null): Array of child account nodes, or null if no children

### Totals Section

- **`total_revenue`**: Sum of all revenue accounts
- **`total_costs`**: Sum of all cost accounts (COGS)
- **`gross_profit`**: total_revenue - total_costs
- **`total_expenses`**: Sum of all expense accounts
- **`net_income`**: gross_profit - total_expenses

## How It Works

1. **Account Discovery**: For each parent account ID, the system finds all descendant accounts using MPTT (Modified Preorder Tree Traversal)

2. **Balance Calculation**: 
   - For leaf accounts: Calculates net movement from `AccountBalanceHistory` for the period
   - For parent accounts: Rolls up balances from children

3. **Filtering**: By default, only accounts with non-zero balances are included (unless `include_zero_balances: true`)

4. **Hierarchy Building**: Builds a tree structure maintaining parent-child relationships

5. **Totals Calculation**: Calculates totals for each section and overall financial metrics

## Use Cases

### 1. Monthly Income Statement

```bash
POST /api/financial-statements/detailed_income_statement/
{
  "revenue_parent_ids": [10],
  "cost_parent_ids": [20],
  "expense_parent_ids": [30],
  "start_date": "2025-03-01",
  "end_date": "2025-03-31"
}
```

### 2. Quarterly Report with All Transactions

```bash
POST /api/financial-statements/detailed_income_statement/
{
  "revenue_parent_ids": [10],
  "cost_parent_ids": [20],
  "expense_parent_ids": [30],
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "balance_type": "all",
  "include_zero_balances": true
}
```

### 3. Year-to-Date Income Statement

```bash
POST /api/financial-statements/detailed_income_statement/
{
  "revenue_parent_ids": [10],
  "cost_parent_ids": [20],
  "expense_parent_ids": [30],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31"
}
```

### 4. Bank-Reconciled Only Report

```bash
POST /api/financial-statements/detailed_income_statement/
{
  "revenue_parent_ids": [10],
  "cost_parent_ids": [20],
  "expense_parent_ids": [30],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "balance_type": "bank_reconciled"
}
```

## Performance Considerations

- **Fast**: Uses pre-calculated `AccountBalanceHistory` instead of querying journal entries directly
- **Efficient**: Aggregates monthly movements rather than summing individual transactions
- **Cached**: If balance history exists for the period, calculations are very fast

## Prerequisites

1. **Balance History**: Ensure `AccountBalanceHistory` records exist for the period
   - If missing, the endpoint will attempt to calculate balances from journal entries
   - For best performance, pre-calculate balance history using the recalculation endpoint

2. **Account Structure**: Accounts must be properly organized in a hierarchy with parent-child relationships

3. **Active Accounts**: Only active accounts (`is_active=True`) are included

## Integration Examples

### Python (using requests)

```python
import requests

url = "https://your-api.com/api/financial-statements/detailed_income_statement/"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-token"
}

payload = {
    "revenue_parent_ids": [10, 11],
    "cost_parent_ids": [20, 21],
    "expense_parent_ids": [30, 31],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "balance_type": "posted"
}

response = requests.post(url, json=payload, headers=headers)
data = response.json()

print(f"Total Revenue: {data['totals']['total_revenue']}")
print(f"Net Income: {data['totals']['net_income']}")
```

### JavaScript (using fetch)

```javascript
const url = 'https://your-api.com/api/financial-statements/detailed_income_statement/';

const payload = {
  revenue_parent_ids: [10, 11],
  cost_parent_ids: [20, 21],
  expense_parent_ids: [30, 31],
  start_date: '2025-01-01',
  end_date: '2025-12-31',
  balance_type: 'posted'
};

fetch(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer your-token'
  },
  body: JSON.stringify(payload)
})
  .then(response => response.json())
  .then(data => {
    console.log('Total Revenue:', data.totals.total_revenue);
    console.log('Net Income:', data.totals.net_income);
  });
```

### cURL

```bash
curl -X POST \
  https://your-api.com/api/financial-statements/detailed_income_statement/ \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your-token' \
  -d '{
    "revenue_parent_ids": [10, 11],
    "cost_parent_ids": [20, 21],
    "expense_parent_ids": [30, 31],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "balance_type": "posted"
  }'
```

## Notes

- The endpoint automatically includes all descendant accounts of the specified parent accounts
- Accounts are filtered to show only those with balances (unless `include_zero_balances: true`)
- The hierarchy preserves the account tree structure
- Balances are calculated as: `(debit - credit) × account_direction`
- The endpoint requires tenant/company context (usually set by middleware)

