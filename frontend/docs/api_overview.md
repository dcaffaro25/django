# API Overview

This document provides a comprehensive overview of the Django REST Framework API endpoints used by the React frontend.

## Base URL Configuration

- **Development**: `http://localhost:8000`
- **Production**: Configured via `VITE_API_BASE_URL` environment variable
- **Tenant Path**: `/{tenant_subdomain}/api/...`

## Authentication

### Authentication Method

The backend uses **DRF TokenAuthentication** (not JWT).

### Login Endpoint

```http
POST /login/
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "detail": "Login successful",
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 1,
    "username": "user@example.com",
    "email": "user@example.com",
    "is_superuser": false,
    "is_staff": false,
    "must_change_password": false
  }
}
```

### Authenticated Requests

All authenticated requests must include:
```http
Authorization: Token {token}
```

**Note**: Use `Token` (not `Bearer`) for DRF TokenAuthentication.

### Logout Endpoint

```http
POST /api/logout/
Authorization: Token {token}
```

## Multi-Tenancy

### Tenant Identification

Tenants are identified via **URL path prefix**:

```
/{tenant_subdomain}/api/...
```

Example:
```
GET /acme-corp/api/transactions/
```

### Tenant Middleware

The `TenantMiddleware` automatically:
1. Extracts tenant subdomain from URL path
2. Validates tenant exists
3. Sets `request.tenant` for queryset filtering
4. Bypasses tenant check for: `/admin`, `/api/login`, `/api/core/*`

### Tenant Scoping

All tenant-aware endpoints automatically filter data by:
- Current user's tenant (if not superuser)
- Selected tenant (if superuser)

## API Endpoints by Module

### Authentication & Users

#### Login
- `POST /login/` - User login, returns token

#### Logout
- `POST /api/logout/` - User logout

#### Users
- `GET /api/core/users/` - List users (superuser only)
- `POST /api/core/users/` - Create user (superuser only)
- `GET /api/core/users/{id}/` - Get user
- `PUT /api/core/users/{id}/` - Update user
- `DELETE /api/core/users/{id}/` - Delete user

#### Password Management
- `PUT /api/core/users/{id}/change-password/` - Change password
- `POST /api/core/users/{id}/force-password-change/` - Force password change (admin)

### Multi-Tenancy

#### Companies
- `GET /api/core/companies/` - List companies
- `GET /api/core/companies/{id}/` - Get company
- `POST /api/core/companies/` - Create company (superuser)
- `PUT /api/core/companies/{id}/` - Update company
- `DELETE /api/core/companies/{id}/` - Delete company

**Note**: Currently no branding/theme endpoints. See [theming_and_tenancy.md](./theming_and_tenancy.md) for future implementation.

### Accounting

#### Transactions
- `GET /{tenant}/api/transactions/` - List transactions
- `GET /{tenant}/api/transactions/filtered?status={status}` - Filtered transactions
- `GET /{tenant}/api/transactions/{id}/` - Get transaction
- `POST /{tenant}/api/transactions/` - Create transaction
- `PUT /{tenant}/api/transactions/{id}/` - Update transaction
- `DELETE /{tenant}/api/transactions/{id}/` - Delete transaction
- `POST /{tenant}/api/transactions/{id}/post/` - Post transaction
- `POST /{tenant}/api/transactions/{id}/unpost/` - Unpost transaction
- `POST /{tenant}/api/transactions/{id}/cancel/` - Cancel transaction
- `POST /{tenant}/api/transactions/{id}/create_balancing_entry/` - Create balancing entry
- `POST /{tenant}/api/transactions/bulk_import/` - Bulk import transactions
- `GET /{tenant}/api/transactions/download_import_template/` - Download import template
- `GET /{tenant}/api/schema/transaction/` - Get transaction schema

#### Journal Entries
- `GET /{tenant}/api/journal_entries/` - List journal entries
- `GET /{tenant}/api/journal_entries/?unreconciled=true` - Unreconciled entries
- `GET /{tenant}/api/journal_entries/unmatched/` - Unmatched entries
- `GET /{tenant}/api/journal_entries/{id}/` - Get journal entry
- `POST /{tenant}/api/journal_entries/` - Create journal entry
- `PUT /{tenant}/api/journal_entries/{id}/` - Update journal entry
- `DELETE /{tenant}/api/journal_entries/{id}/` - Delete journal entry
- `GET /{tenant}/api/schema/journal-entry/` - Get journal entry schema

#### Accounts
- `GET /{tenant}/api/accounts/` - List accounts (hierarchical)
- `GET /{tenant}/api/accounts/{id}/` - Get account
- `POST /{tenant}/api/accounts/` - Create account
- `PUT /{tenant}/api/accounts/{id}/` - Update account
- `DELETE /{tenant}/api/accounts/{id}/` - Delete account
- `GET /{tenant}/api/account_summary/` - Account summary

#### Cost Centers
- `GET /{tenant}/api/cost_centers/` - List cost centers
- `GET /{tenant}/api/cost_centers/{id}/` - Get cost center
- `POST /{tenant}/api/cost_centers/` - Create cost center
- `PUT /{tenant}/api/cost_centers/{id}/` - Update cost center
- `DELETE /{tenant}/api/cost_centers/{id}/` - Delete cost center

#### Entities
- `GET /{tenant}/api/entities/` - List entities (full)
- `GET /{tenant}/api/entities-mini/` - List entities (mini, optimized)
- `GET /{tenant}/api/entities/{id}/` - Get entity
- `GET /{tenant}/api/entities/{id}/context-options/` - Get entity context options
- `POST /{tenant}/api/entities/` - Create entity
- `PUT /{tenant}/api/entities/{id}/` - Update entity
- `DELETE /{tenant}/api/entities/{id}/` - Delete entity
- `GET /{tenant}/api/entity-tree/{company_id}/` - Get entity tree
- `GET /{tenant}/api/entities-dynamic-transposed/` - Dynamic transposed view

#### Currencies
- `GET /api/core/currencies/` - List currencies (global, no tenant)
- `GET /api/core/currencies/{id}/` - Get currency

### Banking & Reconciliation

#### Banks
- `GET /{tenant}/api/banks/` - List banks
- `GET /{tenant}/api/banks/{id}/` - Get bank
- `POST /{tenant}/api/banks/` - Create bank
- `PUT /{tenant}/api/banks/{id}/` - Update bank
- `DELETE /{tenant}/api/banks/{id}/` - Delete bank

#### Bank Accounts
- `GET /{tenant}/api/bank_accounts/` - List bank accounts
- `GET /{tenant}/api/bank_accounts/{id}/` - Get bank account
- `POST /{tenant}/api/bank_accounts/` - Create bank account
- `PUT /{tenant}/api/bank_accounts/{id}/` - Update bank account
- `DELETE /{tenant}/api/bank_accounts/{id}/` - Delete bank account

#### Bank Transactions
- `GET /{tenant}/api/bank_transactions/` - List bank transactions
- `GET /{tenant}/api/bank_transactions/?unreconciled=true` - Unreconciled transactions
- `GET /{tenant}/api/bank_transactions/{id}/` - Get bank transaction
- `POST /{tenant}/api/bank_transactions/` - Create bank transaction
- `PUT /{tenant}/api/bank_transactions/{id}/` - Update bank transaction
- `DELETE /{tenant}/api/bank_transactions/{id}/` - Delete bank transaction
- `POST /{tenant}/api/bank_transactions/import_ofx/` - Import OFX file
- `POST /{tenant}/api/bank_transactions/finalize_ofx_import/` - Finalize OFX import
- `POST /{tenant}/api/bank_transactions/match_many_to_many/` - Automatic matching
- `POST /{tenant}/api/bank_transactions/match_many_to_many_with_set2/` - Enhanced matching
- `POST /{tenant}/api/bank_transactions/finalize_reconciliation_matches/` - Finalize matches
- `POST /{tenant}/api/bank_transactions/suggest_matches/` - Suggest matches
- `POST /{tenant}/api/bank_transactions/create_suggestions/` - Create suggestions

#### Reconciliation
- `GET /{tenant}/api/reconciliation/` - List reconciliations
- `GET /{tenant}/api/reconciliation/{id}/` - Get reconciliation
- `POST /{tenant}/api/reconciliation/` - Create reconciliation
- `PUT /{tenant}/api/reconciliation/{id}/` - Update reconciliation
- `DELETE /{tenant}/api/reconciliation/{id}/` - Delete reconciliation
- `POST /{tenant}/api/reconciliation/bulk_delete/` - Bulk delete reconciliations
- `GET /{tenant}/api/reconciliation/summaries/` - Reconciliation summaries
- `GET /{tenant}/api/reconciliation-dashboard/` - Reconciliation dashboard data

#### Reconciliation Tasks
- `GET /{tenant}/api/reconciliation-tasks/` - List reconciliation tasks
- `GET /{tenant}/api/reconciliation-tasks/{id}/` - Get task
- `POST /{tenant}/api/reconciliation-tasks/start/` - Start reconciliation task
- `GET /{tenant}/api/reconciliation-tasks/{id}/status/` - Get task status
- `GET /{tenant}/api/reconciliation-tasks/queued/?hours_ago={hours}` - Queued tasks
- `GET /{tenant}/api/reconciliation-tasks/task_counts/?hours_ago={hours}` - Task counts
- `POST /{tenant}/api/reconciliation-tasks/{id}/cancel/` - Cancel task
- `GET /{tenant}/api/reconciliation-tasks/{id}/fresh-suggestions/?limit={limit}` - Fresh suggestions

#### Reconciliation Configs
- `GET /{tenant}/api/reconciliation_configs/` - List configurations
- `GET /{tenant}/api/reconciliation_configs/{id}/` - Get configuration
- `POST /{tenant}/api/reconciliation_configs/` - Create configuration
- `PUT /{tenant}/api/reconciliation_configs/{id}/` - Update configuration
- `DELETE /{tenant}/api/reconciliation_configs/{id}/` - Delete configuration

#### Reconciliation Pipelines
- `GET /{tenant}/api/reconciliation-pipelines/` - List pipelines
- `GET /{tenant}/api/reconciliation-pipelines/{id}/` - Get pipeline
- `POST /{tenant}/api/reconciliation-pipelines/` - Create pipeline
- `PUT /{tenant}/api/reconciliation-pipelines/{id}/` - Update pipeline
- `DELETE /{tenant}/api/reconciliation-pipelines/{id}/` - Delete pipeline

### Financial Statements

#### Financial Statements
- `GET /{tenant}/api/financial-statements/` - List statements
- `GET /{tenant}/api/financial-statements/{id}/` - Get statement
- `POST /{tenant}/api/financial-statements/` - Create statement
- `PUT /{tenant}/api/financial-statements/{id}/` - Update statement
- `DELETE /{tenant}/api/financial-statements/{id}/` - Delete statement
- `POST /{tenant}/api/financial-statements/with_comparisons/?preview=true` - Generate with comparisons
- `POST /{tenant}/api/financial-statements/time_series/?preview=true&include_metadata=true` - Generate time series

**Request Body Example:**
```json
{
  "template_id": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_period"],
  "dimension": "month",
  "include_pending": true
}
```

#### Financial Statement Templates
- `GET /{tenant}/api/financial-statement-templates/` - List templates
- `GET /{tenant}/api/financial-statement-templates/{id}/` - Get template
- `POST /{tenant}/api/financial-statement-templates/` - Create template
- `PUT /{tenant}/api/financial-statement-templates/{id}/` - Update template
- `DELETE /{tenant}/api/financial-statement-templates/{id}/` - Delete template

#### Financial Statement Comparisons
- `GET /{tenant}/api/financial-statement-comparisons/` - List comparisons
- `GET /{tenant}/api/financial-statement-comparisons/{id}/` - Get comparison

### HR Module

#### Employees
- `GET /{tenant}/api/hr/employees` - List employees
- `GET /{tenant}/api/hr/employees/{id}/` - Get employee
- `POST /{tenant}/api/hr/employees/` - Create employee
- `PUT /{tenant}/api/hr/employees/{id}/` - Update employee
- `DELETE /{tenant}/api/hr/employees/{id}/` - Delete employee

#### Positions
- `GET /{tenant}/api/hr/positions` - List positions
- `GET /{tenant}/api/hr/positions/{id}/` - Get position
- `POST /{tenant}/api/hr/positions/` - Create position
- `PUT /{tenant}/api/hr/positions/{id}/` - Update position
- `DELETE /{tenant}/api/hr/positions/{id}/` - Delete position

#### Time Tracking
- `GET /{tenant}/api/hr/timetracking` - List time tracking records
- `GET /{tenant}/api/hr/timetracking/{id}/` - Get record
- `POST /{tenant}/api/hr/timetracking/` - Create record
- `PUT /{tenant}/api/hr/timetracking/{id}/` - Update record
- `DELETE /{tenant}/api/hr/timetracking/{id}/` - Delete record
- `POST /{tenant}/api/hr/timetracking/{id}/approve/` - Approve record
- `POST /{tenant}/api/hr/timetracking/{id}/reject/` - Reject record

#### Payrolls
- `GET /{tenant}/api/hr/payrolls` - List payrolls
- `GET /{tenant}/api/hr/payrolls/{id}/` - Get payroll
- `POST /{tenant}/api/hr/payrolls/generate-monthly/` - Generate monthly payroll
- `POST /{tenant}/api/hr/payrolls/recalculate/` - Recalculate payroll
- `DELETE /{tenant}/api/hr/payrolls/{id}/` - Delete payroll

#### Recurring Adjustments
- `GET /{tenant}/api/hr/recurring-adjustments` - List adjustments
- `GET /{tenant}/api/hr/recurring-adjustments/{id}/` - Get adjustment
- `POST /{tenant}/api/hr/recurring-adjustments/` - Create adjustment
- `PUT /{tenant}/api/hr/recurring-adjustments/{id}/` - Update adjustment
- `DELETE /{tenant}/api/hr/recurring-adjustments/{id}/` - Delete adjustment

### Billing Module

#### Business Partner Categories
- `GET /{tenant}/api/business_partner_categories/` - List categories
- `GET /{tenant}/api/business_partner_categories/{id}/` - Get category
- `POST /{tenant}/api/business_partner_categories/` - Create category
- `PUT /{tenant}/api/business_partner_categories/{id}/` - Update category
- `DELETE /{tenant}/api/business_partner_categories/{id}/` - Delete category

#### Business Partners
- `GET /{tenant}/api/business_partners/` - List business partners
- `GET /{tenant}/api/business_partners/{id}/` - Get business partner
- `POST /{tenant}/api/business_partners/` - Create business partner
- `PUT /{tenant}/api/business_partners/{id}/` - Update business partner
- `DELETE /{tenant}/api/business_partners/{id}/` - Delete business partner

#### Product/Service Categories
- `GET /{tenant}/api/product_service_categories/` - List categories
- `GET /{tenant}/api/product_service_categories/{id}/` - Get category
- `POST /{tenant}/api/product_service_categories/` - Create category
- `PUT /{tenant}/api/product_service_categories/{id}/` - Update category
- `DELETE /{tenant}/api/product_service_categories/{id}/` - Delete category

#### Products/Services
- `GET /{tenant}/api/product_services/` - List products/services
- `GET /{tenant}/api/product_services/{id}/` - Get product/service
- `POST /{tenant}/api/product_services/` - Create product/service
- `PUT /{tenant}/api/product_services/{id}/` - Update product/service
- `DELETE /{tenant}/api/product_services/{id}/` - Delete product/service

#### Contracts
- `GET /{tenant}/api/contracts/` - List contracts
- `GET /{tenant}/api/contracts/{id}/` - Get contract
- `POST /{tenant}/api/contracts/` - Create contract
- `PUT /{tenant}/api/contracts/{id}/` - Update contract
- `DELETE /{tenant}/api/contracts/{id}/` - Delete contract

### Configuration

#### Integration Rules
- `GET /{tenant}/api/core/integration-rules/` - List rules
- `GET /{tenant}/api/core/integration-rules/{id}/` - Get rule
- `POST /{tenant}/api/core/integration-rules/` - Create rule
- `PUT /{tenant}/api/core/integration-rules/{id}/` - Update rule
- `DELETE /{tenant}/api/core/integration-rules/{id}/` - Delete rule
- `POST /{tenant}/api/core/validate-rule/` - Validate rule
- `POST /{tenant}/api/core/test-rule/` - Test rule execution

#### Substitution Rules
- `GET /{tenant}/api/core/substitution-rules/` - List rules
- `GET /{tenant}/api/core/substitution-rules/{id}/` - Get rule
- `POST /{tenant}/api/core/substitution-rules/` - Create rule
- `PUT /{tenant}/api/core/substitution-rules/{id}/` - Update rule
- `DELETE /{tenant}/api/core/substitution-rules/{id}/` - Delete rule

### AI/Chat

#### Chat
- `POST /api/chat/ask/` - Ask question (with context)
- `POST /api/chat/ask_nocontext/` - Ask question (no context)
- `POST /api/chat/diag/` - Diagnostic query

### Embeddings

#### Embedding Health
- `GET /{tenant}/api/embeddings/health/` - Embedding health status
- `GET /{tenant}/api/embeddings/missing-counts/` - Missing embedding counts
- `POST /{tenant}/api/embeddings/backfill/` - Backfill embeddings
- `GET /{tenant}/api/embeddings/tasks/{task_id}/` - Task status
- `GET /{tenant}/api/embeddings/jobs/` - List embedding jobs
- `POST /{tenant}/api/embeddings/test/` - Test embeddings
- `POST /{tenant}/api/embeddings/search/` - Semantic search

## Common Request/Response Patterns

### Pagination

Most list endpoints support pagination:
```json
{
  "count": 100,
  "next": "http://api.example.com/api/transactions/?page=2",
  "previous": null,
  "results": [...]
}
```

### Filtering

Many endpoints support Django Filter Backend:
- `?field=value` - Exact match
- `?field__gte=value` - Greater than or equal
- `?field__lte=value` - Less than or equal
- `?field__contains=value` - Contains
- `?search=term` - Search across multiple fields

### Ordering

- `?ordering=field` - Ascending
- `?ordering=-field` - Descending
- `?ordering=field1,-field2` - Multiple fields

## Error Responses

### Standard Error Format

```json
{
  "detail": "Error message",
  "errors": {
    "field_name": ["Error message 1", "Error message 2"]
  }
}
```

### HTTP Status Codes

- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Validation error
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Permission denied
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Rate Limiting

Currently no rate limiting implemented. Consider adding for production.

## Related Documentation

- [Architecture](./architecture.md) - Overall architecture
- [Theming & Tenancy](./theming_and_tenancy.md) - Multi-tenant details
- [Conventions](./conventions.md) - API usage patterns

