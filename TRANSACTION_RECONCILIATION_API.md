# Transaction Reconciliation API Documentation

This document describes the API endpoints and features for the Transaction Reconciliation Page, enabling users to manage transactions, classify journal entries, and track bank reconciliation status.

---

## Table of Contents

1. [Overview](#overview)
2. [Transaction List Enhancements](#transaction-list-enhancements)
3. [Transaction Filters](#transaction-filters)
4. [Summary Stats Endpoint](#summary-stats-endpoint)
5. [Account Suggestion Endpoint](#account-suggestion-endpoint)
6. [Classification History Endpoint](#classification-history-endpoint)
7. [Existing Transaction Actions](#existing-transaction-actions)
8. [Usage Examples](#usage-examples)

---

## Overview

The Transaction Reconciliation API provides endpoints to:

- **View transactions** with enhanced reconciliation status information
- **Filter transactions** by balance status, bank reconciliation status, and other criteria
- **Get summary statistics** for dashboard displays
- **Suggest accounts** for journal entry classification based on historical patterns
- **Review classification history** to understand past patterns

### Base URL

All endpoints are tenant-scoped:

```
https://<server>/<tenant_subdomain>/api/
```

---

## Transaction List Enhancements

### Endpoint

```
GET /api/transactions/
```

### New Response Fields

The transaction list now includes additional fields for reconciliation tracking:

| Field | Type | Description |
|-------|------|-------------|
| `is_balanced` | boolean | Whether total debits equal total credits |
| `bank_recon_status` | string | Bank reconciliation status: `matched`, `pending`, `mixed`, or `na` |
| `bank_linked_je_count` | integer | Number of journal entries linked to bank accounts |
| `bank_reconciled_je_count` | integer | Number of bank-linked JEs that are reconciled |
| `total_debit` | decimal | Sum of all debit amounts across journal entries |
| `total_credit` | decimal | Sum of all credit amounts across journal entries |

### Bank Reconciliation Status Values

| Status | Description |
|--------|-------------|
| `matched` | All bank-linked JEs have reconciliations with status `matched` or `approved` |
| `pending` | Has bank-linked JEs with no reconciliation |
| `mixed` | Some bank-linked JEs are reconciled, some are not |
| `na` | No journal entries linked to bank accounts |

### Example Response

```json
{
  "id": 123,
  "company": 1,
  "entity": 5,
  "currency": 1,
  "date": "2026-01-10",
  "description": "Pagamento fornecedor XYZ",
  "amount": "1500.00",
  "state": "pending",
  "is_balanced": true,
  "bank_recon_status": "pending",
  "bank_linked_je_count": 2,
  "bank_reconciled_je_count": 1,
  "total_debit": 1500.00,
  "total_credit": 1500.00,
  "journal_entries_count": 2,
  "balance": 0.0,
  "reconciliation_status": "mixed"
}
```

---

## Transaction Filters

### Endpoint

```
GET /api/transactions/?<filters>
```

### Available Filters

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Transactions on or after this date |
| `date_to` | date | Transactions on or before this date |
| `amount_min` | decimal | Minimum transaction amount |
| `amount_max` | decimal | Maximum transaction amount |
| `state__in` | string | Comma-separated states: `pending,posted,canceled` |
| `entity` | integer | Filter by entity ID |
| `entity__in` | string | Comma-separated entity IDs |
| `currency` | integer | Filter by currency ID |
| `description` | string | Case-insensitive description search |
| `is_balanced` | boolean | Filter by balance status (`true` or `false`) |
| `bank_recon_status` | string | Filter by bank recon status: `matched`, `pending`, `mixed`, `na` |
| `unreconciled` | boolean | If `true`, show only transactions with unreconciled bank JEs |
| `balance_validated` | boolean | Filter by balance validation flag |
| `ordering` | string | Sort by: `date`, `-date`, `amount`, `-amount`, `id`, `-id` |

### Example Requests

**Get unbalanced transactions:**
```
GET /api/transactions/?is_balanced=false
```

**Get transactions ready to post (balanced with all bank JEs reconciled):**
```
GET /api/transactions/?is_balanced=true&state__in=pending&bank_recon_status=matched
```

**Get transactions with pending bank reconciliation:**
```
GET /api/transactions/?bank_recon_status=pending
```

**Get transactions for a specific entity in a date range:**
```
GET /api/transactions/?entity=5&date_from=2026-01-01&date_to=2026-01-31
```

---

## Summary Stats Endpoint

Returns aggregated statistics for transactions based on applied filters. Useful for dashboard summary cards.

### Endpoint

```
GET /api/transactions/summary-stats/
```

### Query Parameters

Accepts the same filter parameters as the transaction list endpoint.

### Response

```json
{
  "total_count": 150,
  "balanced_count": 138,
  "unbalanced_count": 12,
  "ready_to_post_count": 45,
  "pending_bank_recon_count": 23,
  "total_debit": 125000.00,
  "total_credit": 118500.00,
  "by_state": {
    "pending": 100,
    "posted": 45,
    "canceled": 5
  },
  "by_bank_recon_status": {
    "matched": 50,
    "pending": 30,
    "mixed": 10,
    "na": 60
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `total_count` | integer | Total transactions matching filters |
| `balanced_count` | integer | Transactions where `is_balanced=true` |
| `unbalanced_count` | integer | Transactions where `is_balanced=false` |
| `ready_to_post_count` | integer | Balanced + pending state + (no bank JEs OR all reconciled) |
| `pending_bank_recon_count` | integer | Has unreconciled bank-linked JEs |
| `total_debit` | decimal | Sum of all debit amounts across all JEs |
| `total_credit` | decimal | Sum of all credit amounts across all JEs |
| `by_state` | object | Count breakdown by transaction state |
| `by_bank_recon_status` | object | Count breakdown by bank reconciliation status |

### Example Requests

**Get stats for all pending transactions:**
```
GET /api/transactions/summary-stats/?state__in=pending
```

**Get stats for a specific entity this month:**
```
GET /api/transactions/summary-stats/?entity=5&date_from=2026-01-01&date_to=2026-01-31
```

---

## Account Suggestion Endpoint

Suggests accounts for journal entry classification based on historical patterns.

### Endpoint

```
POST /api/journal_entries/suggest-account/
```

### Request Body

```json
{
  "transaction_description": "Pagamento fornecedor XYZ",
  "amount": 1500.00,
  "entity_id": 5,
  "je_description": "Pagamento ref. NF 12345",
  "limit": 5
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `transaction_description` | string | Yes | The transaction's description |
| `amount` | decimal | No | Transaction amount (for pattern matching) |
| `entity_id` | integer | No | Entity ID (for entity-specific patterns) |
| `je_description` | string | No | Journal entry description |
| `limit` | integer | No | Max suggestions to return (default: 5) |

### Response

```json
{
  "suggestions": [
    {
      "account_id": 123,
      "account_code": "2.1.01",
      "account_name": "Fornecedores",
      "account_path": "Passivo > Circulante > Fornecedores",
      "confidence": 0.92,
      "reason": "description_match, entity_pattern",
      "historical_count": 47,
      "last_used": "2026-01-05"
    },
    {
      "account_id": 456,
      "account_code": "4.1.02",
      "account_name": "Despesas com Serviços",
      "account_path": "Despesas > Operacionais > Serviços",
      "confidence": 0.65,
      "reason": "description_match",
      "historical_count": 12,
      "last_used": "2025-12-20"
    }
  ]
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | integer | Account primary key |
| `account_code` | string | Account code (e.g., "2.1.01") |
| `account_name` | string | Account name |
| `account_path` | string | Full hierarchical path |
| `confidence` | decimal | Confidence score (0.0 to 1.0) |
| `reason` | string | Why this account was suggested |
| `historical_count` | integer | How many times this pattern was used |
| `last_used` | string | Date when last used (YYYY-MM-DD) |

### Suggestion Reasons

| Reason | Description |
|--------|-------------|
| `description_match` | Words in description matched historical entries |
| `entity_pattern` | Account commonly used for this entity |
| `amount_pattern` | Account used for similar transaction amounts |

---

## Classification History Endpoint

Returns recent classification patterns and frequently used accounts.

### Endpoint

```
GET /api/journal_entries/classification-history/
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `account_id` | integer | Filter by specific account |
| `entity_id` | integer | Filter by specific entity |
| `limit` | integer | Max results (default: 20) |

### Response

```json
{
  "recent_classifications": [
    {
      "account_id": 123,
      "account_code": "2.1.01",
      "account_name": "Fornecedores",
      "description_pattern": "Pagamento fornecedor*",
      "count": 15,
      "last_used": "2026-01-05"
    },
    {
      "account_id": 456,
      "account_code": "3.1.01",
      "account_name": "Receitas de Vendas",
      "description_pattern": "Recebimento cliente*",
      "count": 23,
      "last_used": "2026-01-04"
    }
  ],
  "recent_accounts": [
    {
      "account_id": 123,
      "account_code": "2.1.01",
      "account_name": "Fornecedores",
      "usage_count": 47,
      "last_used": "2026-01-05"
    },
    {
      "account_id": 789,
      "account_code": "1.1.01",
      "account_name": "Caixa",
      "usage_count": 156,
      "last_used": "2026-01-05"
    }
  ]
}
```

### Example Requests

**Get classification history for a specific entity:**
```
GET /api/journal_entries/classification-history/?entity_id=5
```

**Get history for a specific account:**
```
GET /api/journal_entries/classification-history/?account_id=123&limit=50
```

---

## Existing Transaction Actions

These endpoints already exist and are relevant for the reconciliation workflow:

### Post Transaction

```
POST /api/transactions/{id}/post/
```

Posts a balanced transaction. Requires `is_balanced=true`.

### Unpost Transaction

```
POST /api/transactions/{id}/unpost/
```

Reverts a posted transaction to pending state.

### Cancel Transaction

```
POST /api/transactions/{id}/cancel/
```

Cancels a transaction. Admin-only for posted transactions.

### Create Balancing Entry

```
POST /api/transactions/{id}/create_balancing_entry/
```

Automatically creates a journal entry to balance the transaction.

**Request Body:**
```json
{
  "account_id": 123
}
```

### Check Balance Status

```
GET /api/transactions/{id}/balance-status/
```

Returns detailed balance information for a transaction.

### Validate Balance

```
POST /api/transactions/{id}/validate-balance/
```

Validates and updates the `is_balanced` flag.

---

## Usage Examples

### Retool: Transaction List Query

```javascript
// REST Query configuration
{
  "method": "GET",
  "url": "/{{ tenant }}/api/transactions/",
  "params": {
    "date_from": "{{ dateRangePicker.startDate }}",
    "date_to": "{{ dateRangePicker.endDate }}",
    "state__in": "{{ stateFilter.value.join(',') }}",
    "is_balanced": "{{ balanceFilter.value }}",
    "bank_recon_status": "{{ bankReconFilter.value }}",
    "ordering": "-date"
  }
}
```

### Retool: Summary Stats for Dashboard

```javascript
// REST Query configuration
{
  "method": "GET",
  "url": "/{{ tenant }}/api/transactions/summary-stats/",
  "params": {
    "date_from": "{{ dateRangePicker.startDate }}",
    "date_to": "{{ dateRangePicker.endDate }}"
  }
}

// Usage in Text component
"Total: {{ summaryStats.data.total_count }} | " +
"Unbalanced: {{ summaryStats.data.unbalanced_count }} | " +
"Ready to Post: {{ summaryStats.data.ready_to_post_count }}"
```

### Retool: Account Suggestion Dropdown

```javascript
// REST Query configuration (triggered on JE selection)
{
  "method": "POST",
  "url": "/{{ tenant }}/api/journal_entries/suggest-account/",
  "body": {
    "transaction_description": "{{ selectedTransaction.description }}",
    "amount": "{{ selectedTransaction.amount }}",
    "entity_id": "{{ selectedTransaction.entity }}",
    "limit": 5
  }
}

// Use in Select component
{
  "data": "{{ suggestAccount.data.suggestions }}",
  "valueKey": "account_id",
  "labelKey": "account_name",
  "secondaryLabelKey": "account_code"
}
```

### Retool: Quick Filter Buttons

```javascript
// "Needs Attention" button
function filterNeedsAttention() {
  transactionList.setFilters({
    is_balanced: false
  });
}

// "Ready to Post" button
function filterReadyToPost() {
  transactionList.setFilters({
    is_balanced: true,
    state__in: "pending",
    bank_recon_status: "matched,na"
  });
}

// "Pending Bank Recon" button
function filterPendingRecon() {
  transactionList.setFilters({
    bank_recon_status: "pending,mixed"
  });
}
```

---

## Error Handling

All endpoints return standard HTTP status codes:

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 500 | Internal Server Error |

Error responses include a message:

```json
{
  "error": "Account ID is required"
}
```

---

## Related Documentation

- [RECONCILIATION.md](RECONCILIATION.md) - Bank reconciliation workflow
- [FINANCIAL_STATEMENTS.md](FINANCIAL_STATEMENTS.md) - Financial statement generation
- [ETL_PIPELINE_DOCUMENTATION.md](ETL_PIPELINE_DOCUMENTATION.md) - Data import processes

