# OpenClaw API Integration Manual

> **Generated from codebase audit — April 2026**
> Nord Backend — Multi-tenant ERP / Accounting / HR / Billing / Inventory Platform

---

## 1. System Overview

### 1.1 Domain Summary

Nord Backend is a **multi-tenant enterprise resource planning (ERP) platform** built with Django and Django REST Framework. It provides APIs for:

- **Accounting** — General ledger, chart of accounts (MPTT tree), transactions, journal entries, bank accounts, bank transactions, reconciliation (config, pipelines, suggestions, rules), financial statements, balance history, cost centers, embeddings-based semantic search.
- **Billing** — Business partners, products/services, contracts, invoices, and Brazilian NF-e (Nota Fiscal Eletrônica) import/management.
- **Human Resources** — Positions, employees, time tracking, KPIs, bonuses, recurring adjustments, payroll.
- **Inventory** — Warehouses, units of measure, stock movements (immutable), inventory layers, balances, costing, valuation snapshots, alerts.
- **Multi-tenancy** — Companies (tenants), hierarchical entities (MPTT), users, integration rules, substitution rules, ETL pipelines.
- **Core** — Financial indices/quotes/forecasts, activity feed, Celery job management, AI chat.
- **ERP Integrations** — External ERP providers (Omie, etc.), connections, API definitions, ETL mappings, sync jobs/runs, raw records.
- **Knowledge Base** — Tenant knowledge bases backed by Gemini, document management, Q&A.
- **NPL** — Legal/NLP pipeline: document upload, OCR, span extraction, embeddings, court events, pricing.
- **Feedback** — Supervised feedback for ML models: sessions, candidates, judgments.
- **ML** — Serialized ML models and training tasks.

### 1.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Nord Backend                             │
│                                                                 │
│  ┌──────────┐  ┌───────────┐  ┌──────┐  ┌───────────┐          │
│  │Multitenancy│  │ Accounting│  │  HR  │  │  Billing  │          │
│  │  Users    │  │  GL/Bank  │  │Payroll│  │  NF-e     │          │
│  │  Entities │  │  Recon    │  │  KPI  │  │  Invoices │          │
│  │  ETL      │  │  FinStmt  │  │      │  │  Partners │          │
│  └──────┬───┘  └─────┬─────┘  └──┬───┘  └─────┬─────┘          │
│         │            │           │             │                │
│         └────────────┴───────────┴─────────────┘                │
│                          │                                      │
│  ┌───────────┐  ┌────────┴───────┐  ┌───────────┐              │
│  │ Inventory │  │  Core          │  │  ERP Int.  │              │
│  │  Stock    │  │  Jobs/Chat     │  │  Omie etc  │              │
│  │  Costing  │  │  Fin. Indices  │  │  Sync      │              │
│  └───────────┘  └────────────────┘  └───────────┘              │
│                                                                 │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐    │
│  │Knowledge  │  │   NPL     │  │ Feedback  │  │    ML    │    │
│  │  Base     │  │  Legal    │  │ Supervised│  │  Models  │    │
│  └───────────┘  └───────────┘  └───────────┘  └──────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              api_meta (Introspection Layer)              │   │
│  │  /api/meta/endpoints  /models  /enums  /filters  /health│   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Entity-Relationship Summary

- **Company** (tenant) → has many **Entity** (hierarchical, MPTT tree)
- **Entity** → M2M **Account**, M2M **CostCenter** (with inheritance from parent)
- **Company** → has many **Transaction** → has many **JournalEntry**
- **JournalEntry** → belongs to **Account**, optionally **CostCenter**
- **Account** (MPTT tree) → optionally belongs to **BankAccount** → belongs to **Bank**
- **BankAccount** → has many **BankTransaction**
- **Reconciliation** → M2M **JournalEntry**, M2M **BankTransaction**
- **Company** → has many **BusinessPartner**, **ProductService**, **Contract**, **Invoice**
- **Invoice** → has many **InvoiceLine**
- **Company** → has many **NotaFiscal** → has many **NotaFiscalItem**
- **Company** → has many **Employee** → belongs to **Position**
- **Employee** → has many **TimeTracking**, **KPI**, **Bonus**, **Payroll**
- **Company** → has many **Warehouse**, **StockMovement**, **InventoryBalance**
- **Company** → has many **ERPConnection** → belongs to **ERPProvider**
- **ERPConnection** → has many **ERPSyncJob** → has many **ERPSyncRun**
- **CustomUser** → authenticates; can belong to Companies through tokens

### 1.4 Base URL & Conventions


| Setting                | Value                                                |
| ---------------------- | ---------------------------------------------------- |
| **Base URL**           | `https://<your-host>/`                               |
| **API versioning**     | None — all endpoints are unversioned (current)       |
| **Content-Type**       | `application/json`                                   |
| **Trailing slashes**   | Most endpoints accept with or without trailing slash |
| **Timezone**           | UTC (`USE_TZ = True`)                                |
| **Date format**        | ISO 8601: `YYYY-MM-DD`                               |
| **Datetime format**    | ISO 8601: `YYYY-MM-DDTHH:MM:SS.ffffffZ`              |
| **Default auto-field** | `BigAutoField` (integer PKs)                         |


### 1.5 Multi-Tenancy

Tenant-scoped endpoints use a **URL-path prefix**: `/{tenant_slug}/api/...`

The tenant slug is the Company's `subdomain` field. The middleware resolves the tenant from the first path segment. Superusers can use `all` as tenant slug to access all companies.

**Non-tenant endpoints** (no prefix): `/api/core/...`, `/api/meta/...`, `/login`, `/logout`, core financial indices, NPL, feedback.

---

## 2. Authentication

### 2.1 Token Authentication (Primary)

The API uses **DRF TokenAuthentication** as its primary auth mechanism.

**Header format:**

```
Authorization: Token <token_key>
```

Tokens are obtained via the login endpoint (`POST /login/`) which returns a token key, or pre-created via Django admin / management command.

### 2.2 JWT (Available but not default)

JWT endpoints exist but are NOT in the default authentication classes:

- `POST /api/token/` — obtain JWT pair (access + refresh)
- `POST /api/token/refresh/` — refresh access token

### 2.3 OpenClaw Read-Only Token

OpenClaw authenticates using a standard DRF Token belonging to a dedicated user:


| Property              | Value                                                                              |
| --------------------- | ---------------------------------------------------------------------------------- |
| **Username**          | `openclaw_agent`                                                                   |
| **Token type**        | DRF Token (long-lived)                                                             |
| **Header**            | `Authorization: Token <openclaw_token>`                                            |
| **Access scope**      | All `GET` endpoints + all `/api/meta/`* endpoints                                  |
| **Denied operations** | Any `POST`, `PUT`, `PATCH`, `DELETE` on business resources returns `403 Forbidden` |


**Provisioning the token:**

```bash
python manage.py create_openclaw_token
```

This creates the `openclaw_agent` user (non-staff, non-superuser, inactive for login) and prints the token.

### 2.4 What OpenClaw CAN access

- `GET` on ALL list and detail endpoints across all apps
- All `/api/meta/*` introspection endpoints
- `/api/meta/health/` (no auth required)

### 2.5 What OpenClaw CANNOT access

- Any mutating operation (POST/PUT/PATCH/DELETE) on business resources
- Django admin
- Management commands

### 2.6 AUTH_OFF Flag

**Important:** The codebase has `AUTH_OFF = True` in settings. When this flag is `True`, many ViewSets set `permission_classes = []`, effectively making them public. This is a development convenience. In production, `AUTH_OFF` should be `False`.

---

## 3. Introspection Endpoints

All introspection endpoints live under `/api/meta/` and require authentication (except `/api/meta/health/`).

### 3.1 GET /api/meta/health

Health check — no authentication required.

**Response:**

```json
{
  "status": "healthy",
  "api_version": "1.0.0",
  "timestamp": "2026-04-12T20:00:00.000000Z",
  "service": "Nord Backend"
}
```

### 3.2 GET /api/meta/endpoints

Returns the complete registry of all API endpoints, auto-discovered from Django URL patterns.

**Request:**

```
GET /api/meta/endpoints/
Authorization: Token <openclaw_token>
```

**Response:**

```json
{
  "count": 150,
  "endpoints": [
    {
      "method": "GET",
      "path": "/api/core/users/",
      "name": "user-list",
      "summary": "List all users",
      "tags": ["user"],
      "auth_required": true,
      "path_params": [],
      "serializer": "CustomUserSerializer",
      "filterset": null,
      "search_fields": [],
      "ordering_fields": []
    },
    {
      "method": "GET",
      "path": "/:tenant_id/api/transactions/",
      "name": "transaction-list",
      "summary": "List all transactions",
      "tags": ["transaction"],
      "auth_required": true,
      "path_params": [
        {"name": "tenant_id", "type": "string", "description": "URL parameter: tenant_id"}
      ],
      "serializer": "TransactionSerializer",
      "filterset": "TransactionFilter",
      "search_fields": ["description"],
      "ordering_fields": ["date", "amount", "id", "created_at"]
    }
  ]
}
```

### 3.3 GET /api/meta/models

Returns the full data-model catalog with field definitions, constraints, and relationships.

**Request:**

```
GET /api/meta/models/
Authorization: Token <openclaw_token>
```

**Response (abbreviated):**

```json
{
  "count": 65,
  "models": [
    {
      "name": "Company",
      "app": "multitenancy",
      "table": "multitenancy_company",
      "description": "",
      "fields": [
        {"name": "id", "type": "integer", "required": false, "primary_key": true, "description": ""},
        {"name": "name", "type": "string", "required": true, "unique": true, "max_length": 100, "description": ""},
        {"name": "subdomain", "type": "string", "required": true, "unique": true, "max_length": 100, "description": ""}
      ],
      "relationships": [...],
      "constraints": [],
      "indexes": [],
      "timestamps": ["created_at", "updated_at"],
      "soft_delete": true,
      "inherits": ["BaseModel"]
    }
  ]
}
```

### 3.4 GET /api/meta/models/:modelName

Returns detail for a single model.

**Request:**

```
GET /api/meta/models/Transaction/
Authorization: Token <openclaw_token>
```

**Response:** Same schema as a single item from the `models` array above.

### 3.5 GET /api/meta/models/:modelName/relationships

Returns relationship graph for a model — direct + one transitive hop.

**Request:**

```
GET /api/meta/models/Transaction/relationships/
Authorization: Token <openclaw_token>
```

**Response:**

```json
{
  "model": "Transaction",
  "direct_relationships": [
    {
      "name": "company",
      "type": "belongs_to",
      "related_model": "multitenancy.Company",
      "foreign_key": "company_id",
      "cascade_delete": true
    },
    {
      "name": "entity",
      "type": "belongs_to",
      "related_model": "multitenancy.Entity",
      "foreign_key": "entity_id",
      "cascade_delete": true
    },
    {
      "name": "currency",
      "type": "belongs_to",
      "related_model": "accounting.Currency",
      "foreign_key": "currency_id",
      "cascade_delete": true
    }
  ],
  "transitive_relationships": [
    {
      "name": "entities",
      "type": "has_many",
      "related_model": "multitenancy.Entity",
      "via": "company"
    }
  ]
}
```

### 3.6 GET /api/meta/enums

Returns every enum/choices field across all models.

**Request:**

```
GET /api/meta/enums/
Authorization: Token <openclaw_token>
```

**Response:**

```json
{
  "count": 42,
  "enums": {
    "Transaction.state": {
      "model": "Transaction",
      "field": "state",
      "values": ["draft", "posted", "cancelled"],
      "labels": {"draft": "Draft", "posted": "Posted", "cancelled": "Cancelled"},
      "description": ""
    },
    "JournalEntry.state": {
      "model": "JournalEntry",
      "field": "state",
      "values": ["draft", "posted", "cancelled"],
      "labels": {"draft": "Draft", "posted": "Posted", "cancelled": "Cancelled"},
      "description": ""
    },
    "IntegrationRule.trigger_event": {
      "model": "IntegrationRule",
      "field": "trigger_event",
      "values": ["payroll_approved", "payroll_created", "transaction_created", "journal_entry_created", "etl_import_completed"],
      "labels": {
        "payroll_approved": "Payroll Approved",
        "payroll_created": "Payroll Created",
        "transaction_created": "Transaction Created (ETL)",
        "journal_entry_created": "Journal Entry Created (ETL)",
        "etl_import_completed": "ETL Import Completed"
      },
      "description": ""
    }
  }
}
```

### 3.7 GET /api/meta/filters

Returns filterable fields per resource, including operators and types.

**Request:**

```
GET /api/meta/filters/
Authorization: Token <openclaw_token>
```

**Response:**

```json
{
  "BankTransaction": {
    "filterset_class": "BankTransactionFilter",
    "filters": [
      {"name": "date_from", "type": "DateFilter", "field_name": "date", "lookup_expr": "gte", "method": null},
      {"name": "date_to", "type": "DateFilter", "field_name": "date", "lookup_expr": "lte", "method": null},
      {"name": "amount_min", "type": "NumberFilter", "field_name": "amount", "lookup_expr": "gte", "method": null},
      {"name": "amount_max", "type": "NumberFilter", "field_name": "amount", "lookup_expr": "lte", "method": null},
      {"name": "unreconciled", "type": "BooleanFilter", "field_name": "unreconciled", "lookup_expr": "exact", "method": "filter_unreconciled"},
      {"name": "entity", "type": "NumberFilter", "field_name": "bank_account__entity_id", "lookup_expr": "exact", "method": null}
    ]
  },
  "Transaction": {
    "filterset_class": "TransactionFilter",
    "filters": [...]
  },
  "JournalEntry": {
    "filterset_class": "JournalEntryFilter",
    "filters": [...]
  }
}
```

### 3.8 GET /api/meta/capabilities

Returns system-wide capability summary.

**Request:**

```
GET /api/meta/capabilities/
Authorization: Token <openclaw_token>
```

**Response:**

```json
{
  "authentication": {
    "methods": ["TokenAuthentication"],
    "token_header": "Authorization: Token <token>",
    "jwt_available": true,
    "jwt_obtain_url": "/api/token/",
    "jwt_refresh_url": "/api/token/refresh/"
  },
  "pagination": {
    "strategy": "not_configured_globally",
    "note": "Pagination is not configured at the DRF global level."
  },
  "filtering": {
    "global_backends": [
      "django_filters.rest_framework.DjangoFilterBackend",
      "rest_framework.filters.SearchFilter",
      "rest_framework.filters.OrderingFilter"
    ]
  },
  "content_type": "application/json",
  "cors": {"allow_all_origins": true, "allow_credentials": true},
  "timezone": "UTC",
  "date_format": "ISO 8601 (YYYY-MM-DD)",
  "datetime_format": "ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)",
  "multi_tenancy": {
    "strategy": "URL-path based.",
    "example": "/{tenant_slug}/api/transactions/"
  },
  "soft_delete": {
    "convention": "is_deleted boolean. Filter with ?deleted=true."
  },
  "error_format": {
    "shape": {"success": false, "error": "<message>", "html": "<optional>"}
  }
}
```

---

## 4. Data Model Reference

### 4.1 Common Base Classes

All business models inherit from one of two abstract base classes:

**BaseModel** (abstract):


| Field      | Type            | Description                                                      |
| ---------- | --------------- | ---------------------------------------------------------------- |
| created_by | FK → CustomUser | Auto-set via django-crum on creation                             |
| updated_by | FK → CustomUser | Auto-set via django-crum on every save                           |
| created_at | datetime        | Auto-set on creation                                             |
| updated_at | datetime        | Auto-set on creation (note: uses `auto_now_add`, not `auto_now`) |
| is_deleted | boolean         | Soft delete flag, default `false`                                |
| notes      | text (nullable) | Metadata about record origin                                     |


**TenantAwareBaseModel** extends BaseModel:


| Field   | Type         | Description                   |
| ------- | ------------ | ----------------------------- |
| company | FK → Company | Tenant owner. CASCADE delete. |


Uses `TenantAwareManager` which auto-filters by the current tenant. Has `clean()` that validates company coherence across related FK objects.

### 4.2 Multitenancy Models

#### CustomUser

**Table:** `multitenancy_customuser` (extends Django AbstractUser)


| Field                | Type        | Required | Unique | Default | Description                         |
| -------------------- | ----------- | -------- | ------ | ------- | ----------------------------------- |
| id                   | integer     | auto     | yes    | auto    | PK                                  |
| username             | string(150) | yes      | yes    | —       | Login username                      |
| email                | string(254) | yes      | no     | —       | Email address                       |
| first_name           | string(150) | no       | no     | ""      |                                     |
| last_name            | string(150) | no       | no     | ""      |                                     |
| password             | string(128) | yes      | no     | —       | Hashed password                     |
| is_active            | boolean     | —        | no     | true    |                                     |
| is_staff             | boolean     | —        | no     | false   |                                     |
| is_superuser         | boolean     | —        | no     | false   |                                     |
| must_change_password | boolean     | —        | no     | false   | Force password change on next login |
| email_last_sent_at   | datetime    | no       | no     | null    | Tracks email cooldown               |
| date_joined          | datetime    | auto     | no     | auto    |                                     |
| last_login           | datetime    | no       | no     | null    |                                     |


#### Company

**Table:** `multitenancy_company` — Inherits BaseModel


| Field     | Type        | Required | Unique | Default | Description                                            |
| --------- | ----------- | -------- | ------ | ------- | ------------------------------------------------------ |
| id        | integer     | auto     | yes    | auto    | PK                                                     |
| name      | string(100) | yes      | yes    | —       | Company display name                                   |
| subdomain | string(100) | yes      | yes    | —       | URL slug for tenant routing. Auto-slugified from name. |


**Business rules:** Subdomain is auto-generated from name via `slugify()` if not provided. Uniqueness enforced at DB level.

#### Entity

**Table:** `multitenancy_entity` — Inherits TenantAwareBaseModel + MPTTModel


| Field                     | Type             | Required | Unique | Default | Description                      |
| ------------------------- | ---------------- | -------- | ------ | ------- | -------------------------------- |
| id                        | integer          | auto     | yes    | auto    | PK                               |
| company                   | FK → Company     | yes      | no     | —       |                                  |
| name                      | string(100)      | yes      | no     | —       |                                  |
| cliente_erp_id            | string(128)      | no       | no     | null    | External ERP identifier          |
| parent                    | TreeFK → self    | no       | no     | null    | Parent entity in hierarchy       |
| accounts                  | M2M → Account    | no       | —      | —       | Directly assigned GL accounts    |
| cost_centers              | M2M → CostCenter | no       | —      | —       | Directly assigned cost centers   |
| inherit_accounts          | boolean          | —        | no     | true    | Inherit accounts from parent     |
| inherit_cost_centers      | boolean          | —        | no     | true    | Inherit cost centers from parent |
| lft, rght, tree_id, level | integer          | auto     | —      | auto    | MPTT tree fields                 |


**Constraints:** `unique_together = (company, name)`. Index on `(company, cliente_erp_id)`.

**Computed properties:**

- `get_path()` → full hierarchical path as string (e.g. "Parent > Child > Grandchild")
- `get_path_ids()` → list of IDs from root to this entity
- `get_available_accounts(leaf_only=False)` → resolved account set considering inheritance
- `get_available_cost_centers(leaf_only=False)` → resolved cost center set considering inheritance

#### IntegrationRule

**Table:** `multitenancy_integrationrule` — Inherits TenantAwareBaseModel


| Field             | Type        | Required | Default | Description                                                                                                           |
| ----------------- | ----------- | -------- | ------- | --------------------------------------------------------------------------------------------------------------------- |
| id                | integer     | auto     | auto    | PK                                                                                                                    |
| name              | string(100) | yes      | —       | Rule display name                                                                                                     |
| cliente_erp_id    | string(128) | no       | null    | ERP sync key                                                                                                          |
| description       | text        | no       | null    |                                                                                                                       |
| trigger_event     | enum        | yes      | —       | One of: `payroll_approved`, `payroll_created`, `transaction_created`, `journal_entry_created`, `etl_import_completed` |
| execution_order   | integer     | —        | 0       |                                                                                                                       |
| filter_conditions | text        | no       | null    | Python expression for filtering payload records                                                                       |
| rule              | text        | yes      | —       | Formula engine code to execute                                                                                        |
| use_celery        | boolean     | —        | true    | Run asynchronously                                                                                                    |
| is_active         | boolean     | —        | true    |                                                                                                                       |
| last_run_at       | datetime    | no       | null    |                                                                                                                       |
| times_executed    | integer     | —        | 0       |                                                                                                                       |


#### SubstitutionRule

**Table:** `multitenancy_substitutionrule` — Inherits TenantAwareBaseModel


| Field              | Type        | Required | Default | Description                          |
| ------------------ | ----------- | -------- | ------- | ------------------------------------ |
| id                 | integer     | auto     | auto    | PK                                   |
| title              | string(255) | no       | null    | Human-readable rule title            |
| model_name         | string(255) | yes      | —       | Target Django model name             |
| field_name         | string(255) | yes      | —       | Target field on the model            |
| match_type         | enum        | yes      | "exact" | One of: `exact`, `regex`, `caseless` |
| match_value        | text        | yes      | —       | Value to match                       |
| substitution_value | text        | yes      | —       | Replacement value                    |
| filter_conditions  | json        | no       | null    | Additional conditions                |


**Constraints:** `unique_together = (company, model_name, field_name, match_value, filter_conditions)`

#### ImportTransformationRule

**Table:** `multitenancy_importtransformationrule` — Inherits TenantAwareBaseModel


| Field                    | Type        | Required | Default | Description                                                    |
| ------------------------ | ----------- | -------- | ------- | -------------------------------------------------------------- |
| id                       | integer     | auto     | auto    | PK                                                             |
| name                     | string(100) | yes      | —       |                                                                |
| description              | text        | no       | null    |                                                                |
| source_sheet_name        | string(100) | yes      | —       | Excel sheet to process                                         |
| skip_rows                | integer     | —        | 0       | Rows to skip at beginning                                      |
| header_row               | integer     | —        | 0       | Header row index (0-based after skip)                          |
| target_model             | string(100) | yes      | —       | Target model: Transaction, JournalEntry, BankTransaction, etc. |
| column_mappings          | json        | yes      | {}      | Source→target field mapping                                    |
| column_concatenations    | json        | no       | {}      | Combine multiple columns                                       |
| computed_columns         | json        | no       | {}      | Expression-based derived values                                |
| default_values           | json        | no       | {}      | Static defaults                                                |
| row_filter               | text        | no       | null    | Python expression to filter rows                               |
| extra_fields_for_trigger | json        | no       | {}      | Extra data for trigger payloads                                |
| trigger_options          | json        | no       | {}      | Trigger configuration                                          |
| execution_order          | integer     | —        | 0       |                                                                |
| is_active                | boolean     | —        | true    |                                                                |


#### ETLPipelineLog

**Table:** `multitenancy_etlpipelinelog` — Inherits TenantAwareBaseModel


| Field                  | Type        | Required | Default   | Description                                                                                                    |
| ---------------------- | ----------- | -------- | --------- | -------------------------------------------------------------------------------------------------------------- |
| id                     | integer     | auto     | auto      | PK                                                                                                             |
| file_name              | string(255) | yes      | —         |                                                                                                                |
| file_hash              | string(64)  | no       | null      |                                                                                                                |
| status                 | enum        | yes      | "pending" | One of: `pending`, `transforming`, `substituting`, `validating`, `importing`, `completed`, `failed`, `partial` |
| is_preview             | boolean     | —        | false     |                                                                                                                |
| sheets_found           | json        | —        | []        |                                                                                                                |
| sheets_processed       | json        | —        | []        |                                                                                                                |
| sheets_skipped         | json        | —        | []        |                                                                                                                |
| sheets_failed          | json        | —        | []        |                                                                                                                |
| total_rows_input       | integer     | —        | 0         |                                                                                                                |
| total_rows_transformed | integer     | —        | 0         |                                                                                                                |
| total_rows_imported    | integer     | —        | 0         |                                                                                                                |
| records_created        | json        | —        | {}        | Counts by model                                                                                                |
| warnings               | json        | —        | []        |                                                                                                                |
| errors                 | json        | —        | []        |                                                                                                                |
| started_at             | datetime    | auto     | auto      |                                                                                                                |
| completed_at           | datetime    | no       | null      |                                                                                                                |
| duration_seconds       | float       | no       | null      |                                                                                                                |


### 4.3 Core Models

#### FinancialIndex

**Table:** `core_financialindex`


| Field       | Type    | Required | Unique | Description                     |
| ----------- | ------- | -------- | ------ | ------------------------------- |
| id          | integer | auto     | yes    | PK                              |
| code        | string  | yes      | yes    | Index code (e.g. "IPCA", "CDI") |
| name        | string  | yes      | no     | Display name                    |
| description | text    | no       | no     |                                 |


#### IndexQuote

**Table:** `core_indexquote`


| Field | Type                | Required | Description |
| ----- | ------------------- | -------- | ----------- |
| id    | integer             | auto     | PK          |
| index | FK → FinancialIndex | yes      |             |
| date  | date                | yes      |             |
| value | decimal             | yes      |             |


**Constraints:** `unique_together = (index, date)`

#### FinancialIndexQuoteForecast

**Table:** `core_financialindexquoteforecast`


| Field           | Type                | Required | Description |
| --------------- | ------------------- | -------- | ----------- |
| id              | integer             | auto     | PK          |
| index           | FK → FinancialIndex | yes      |             |
| date            | date                | yes      |             |
| estimated_value | decimal             | yes      |             |
| source          | string              | no       |             |


**Constraints:** `unique_together = (index, date)`

#### Job

**Table:** `core_job`


| Field      | Type     | Description        |
| ---------- | -------- | ------------------ |
| id         | uuid     | PK                 |
| task_name  | string   | Celery task name   |
| state      | string   | Job state          |
| progress   | integer  | 0-100              |
| meta       | json     | Arbitrary metadata |
| result     | json     | Task result        |
| error      | text     | Error message      |
| created_at | datetime |                    |
| updated_at | datetime |                    |


#### ActionEvent

**Table:** `core_actionevent`


| Field               | Type     | Description        |
| ------------------- | -------- | ------------------ |
| id                  | integer  | PK                 |
| company_id          | integer  | Tenant             |
| verb                | string   | Action verb        |
| target_content_type | string   | Target model       |
| target_id           | string   | Target PK          |
| level               | string   | info/warning/error |
| meta                | json     | Extra data         |
| created_at          | datetime |                    |


### 4.4 Accounting Models

#### Currency

**Table:** `accounting_currency` — Inherits TenantAwareBaseModel


| Field          | Type        | Required | Unique | Description                           |
| -------------- | ----------- | -------- | ------ | ------------------------------------- |
| id             | integer     | auto     | yes    | PK                                    |
| code           | string      | yes      | yes    | ISO currency code (e.g. "BRL", "USD") |
| symbol         | string      | no       | no     | Display symbol                        |
| cliente_erp_id | string(128) | no       | no     | ERP sync key                          |


#### CostCenter

**Table:** `accounting_costcenter` — Inherits TenantAwareBaseModel


| Field          | Type        | Required | Default | Description     |
| -------------- | ----------- | -------- | ------- | --------------- |
| id             | integer     | auto     | auto    | PK              |
| name           | string      | yes      | —       |                 |
| center_type    | string      | no       | null    |                 |
| balance        | decimal     | no       | 0       | Current balance |
| balance_date   | date        | no       | null    |                 |
| cliente_erp_id | string(128) | no       | null    |                 |


**Constraints:** `unique_together = (company, name)`

#### Bank

**Table:** `accounting_bank` — Inherits TenantAwareBaseModel


| Field          | Type        | Required | Unique | Description             |
| -------------- | ----------- | -------- | ------ | ----------------------- |
| id             | integer     | auto     | yes    | PK                      |
| name           | string      | yes      | no     |                         |
| bank_code      | string      | yes      | yes    | Bank institutional code |
| country        | string      | no       | no     |                         |
| cliente_erp_id | string(128) | no       | no     |                         |


#### BankAccount

**Table:** `accounting_bankaccount` — Inherits TenantAwareBaseModel


| Field           | Type          | Required | Description   |
| --------------- | ------------- | -------- | ------------- |
| id              | integer       | auto     | PK            |
| entity          | FK → Entity   | yes      | Owning entity |
| bank            | FK → Bank     | yes      |               |
| currency        | FK → Currency | yes      |               |
| name            | string        | yes      | Display name  |
| account_number  | string        | no       |               |
| branch_id       | string        | no       |               |
| initial_balance | decimal       | no       |               |
| current_balance | decimal       | no       |               |
| cliente_erp_id  | string(128)   | no       |               |


**Constraints:** `unique_together = (company, name, bank, account_number, branch_id)`

#### Account (Chart of Accounts)

**Table:** `accounting_account` — Inherits TenantAwareBaseModel + MPTTModel


| Field                         | Type             | Required | Default | Description                            |
| ----------------------------- | ---------------- | -------- | ------- | -------------------------------------- |
| id                            | integer          | auto     | auto    | PK                                     |
| account_code                  | string           | yes      | —       | Account code (e.g. "1.1.01")           |
| name                          | string           | yes      | —       |                                        |
| account_direction             | enum             | yes      | —       | "debit" or "credit"                    |
| balance                       | decimal          | —        | 0       | Current balance                        |
| balance_date                  | date             | no       | null    |                                        |
| currency                      | FK → Currency    | no       | null    |                                        |
| bank_account                  | FK → BankAccount | no       | null    | Links GL account to bank account       |
| parent                        | TreeFK → self    | no       | null    | Parent in account tree                 |
| account_description_embedding | vector(768)      | no       | null    | pgvector embedding for semantic search |
| cliente_erp_id                | string(128)      | no       | null    |                                        |


**Constraints:** `unique_together = (company, account_code, parent, name)`. HNSW vector index on embedding field.

#### Transaction

**Table:** `accounting_transaction` — Inherits TenantAwareBaseModel


| Field                    | Type          | Required | Default | Description                            |
| ------------------------ | ------------- | -------- | ------- | -------------------------------------- |
| id                       | integer       | auto     | auto    | PK                                     |
| date                     | date          | yes      | —       | Transaction date                       |
| entity                   | FK → Entity   | yes      | —       |                                        |
| description              | text          | no       | ""      |                                        |
| amount                   | decimal(20,2) | yes      | —       |                                        |
| currency                 | FK → Currency | yes      | —       |                                        |
| state                    | enum          | yes      | "draft" | One of: `draft`, `posted`, `cancelled` |
| is_balanced              | boolean       | —        | false   | Whether debits equal credits           |
| balance_validated        | boolean       | —        | false   |                                        |
| due_date                 | date          | no       | null    |                                        |
| nf_number                | string        | no       | null    | Nota Fiscal reference                  |
| numero_boleto            | string        | no       | null    | Bank slip number                       |
| cnpj                     | string        | no       | null    | Brazilian tax ID                       |
| description_embedding    | vector(768)   | no       | null    | Semantic search embedding              |
| cliente_erp_id           | string(128)   | no       | null    |                                        |
| recon_score_amount       | float         | no       | null    | Reconciliation metric                  |
| recon_score_date         | float         | no       | null    |                                        |
| recon_score_desc         | float         | no       | null    |                                        |
| recon_score_combined     | float         | no       | null    |                                        |
| recon_matched_bank_tx_id | integer       | no       | null    |                                        |


**State machine:**

- `draft` → `posted` (via POST `/{tenant}/transactions/{id}/post/`)
- `posted` → `cancelled` (via POST `/{tenant}/transactions/{id}/cancel/`)
- `posted` → `draft` (via POST `/{tenant}/transactions/{id}/unpost/`)

**Business rules:**

- `amount` is quantized to 2 decimal places in `save()`/`clean_fields()`
- `description_embedding` uses HNSW index for vector similarity search

#### JournalEntry

**Table:** `accounting_journalentry` — Inherits TenantAwareBaseModel


| Field                    | Type             | Required    | Default | Description                                     |
| ------------------------ | ---------------- | ----------- | ------- | ----------------------------------------------- |
| id                       | integer          | auto        | auto    | PK                                              |
| transaction              | FK → Transaction | yes         | —       | Parent transaction                              |
| account                  | FK → Account     | conditional | null    | Required unless `bank_designation_pending=True` |
| cost_center              | FK → CostCenter  | no          | null    |                                                 |
| debit                    | decimal(20,2)    | —           | 0       | Debit amount                                    |
| credit                   | decimal(20,2)    | —           | 0       | Credit amount                                   |
| state                    | enum             | —           | "draft" | Same as Transaction state                       |
| date                     | date             | yes         | —       | Must be ≥ transaction.date                      |
| description              | text             | no          | ""      |                                                 |
| bank_designation_pending | boolean          | —           | false   | If true, account is not required                |
| is_cash                  | boolean          | —           | false   |                                                 |
| is_reconciled            | boolean          | —           | false   |                                                 |
| tag                      | string           | no          | null    | Classification tag                              |
| cliente_erp_id           | string(128)      | no          | null    |                                                 |


**DB Constraint:** `CheckConstraint: bank_designation_pending=True OR account IS NOT NULL`

**Business rules (clean()):**

- Account is required unless `bank_designation_pending` is True
- Date must be ≥ transaction date
- Exactly one of debit/credit must be > 0 (single-sided entry)
- `save()` calls `full_clean()` automatically

#### BankTransaction

**Table:** `accounting_banktransaction` — Inherits TenantAwareBaseModel


| Field                 | Type             | Required | Description            |
| --------------------- | ---------------- | -------- | ---------------------- |
| id                    | integer          | auto     | PK                     |
| bank_account          | FK → BankAccount | yes      |                        |
| date                  | date             | yes      |                        |
| amount                | decimal(20,2)    | yes      |                        |
| description           | text             | no       |                        |
| currency              | FK → Currency    | no       |                        |
| reference_number      | string           | no       |                        |
| status                | string           | no       |                        |
| tx_hash               | string           | no       | OFX deduplication hash |
| numeros_boleto        | array[string]    | no       | Bank slip numbers      |
| cnpj                  | string           | no       |                        |
| tag                   | string           | no       | Classification tag     |
| description_embedding | vector(768)      | no       |                        |
| cliente_erp_id        | string(128)      | no       |                        |


**Computed property:** `entity` → derived from `bank_account.entity`

#### Reconciliation

**Table:** `accounting_reconciliation` — Inherits TenantAwareBaseModel


| Field             | Type                  | Required | Description                                          |
| ----------------- | --------------------- | -------- | ---------------------------------------------------- |
| id                | integer               | auto     | PK                                                   |
| journal_entries   | M2M → JournalEntry    | —        | Matched journal entries                              |
| bank_transactions | M2M → BankTransaction | —        | Matched bank transactions                            |
| status            | enum                  | yes      | One of: `pending`, `matched`, `approved`, `rejected` |
| reference         | string                | no       |                                                      |
| notes             | text                  | no       |                                                      |


#### ReconciliationConfig

**Table:** `accounting_reconciliationconfig` — Inherits TenantAwareBaseModel


| Field                    | Type            | Required    | Description                          |
| ------------------------ | --------------- | ----------- | ------------------------------------ |
| id                       | integer         | auto        | PK                                   |
| name                     | string          | yes         |                                      |
| scope                    | enum            | yes         | global, company, user, company_user  |
| user                     | FK → CustomUser | conditional | Required for user/company_user scope |
| Various weight fields    | float           | —           | Must sum to 1.0                      |
| Various tolerance fields | float/integer   | —           |                                      |
| require_cnpj_match       | boolean         | —           | false                                |
| filters                  | json            | no          |                                      |


**Constraints:** `unique_together = (company, user, name)`. `clean()` validates weight sum = 1.0.

#### ReconciliationPipeline, ReconciliationPipelineStage

Multi-stage reconciliation pipeline configuration.

#### ReconciliationTask

Async reconciliation task tracking (status, stats, timing).

#### ReconciliationSuggestion

Auto-generated reconciliation suggestions with bank/JE ID arrays and scoring.

#### ReconciliationRule

Learned reconciliation patterns for auto-matching.

### 4.5 Financial Statement Models

#### FinancialStatementTemplate

**Table:** `accounting_financialstatementtemplate`


| Field          | Type         | Description                                        |
| -------------- | ------------ | -------------------------------------------------- |
| id             | integer      | PK                                                 |
| company        | FK → Company |                                                    |
| name           | string       | Template name                                      |
| statement_type | enum         | balance_sheet, income_statement, cash_flow, custom |
| description    | text         |                                                    |
| is_active      | boolean      |                                                    |


#### FinancialStatementLineTemplate

Line definitions within a template: line type, calculation method, formulas, account mapping.

#### FinancialStatement

Generated financial statement instances with totals and metadata.

#### FinancialStatementLine

Individual lines in a generated statement.

#### AccountBalanceHistory

**Constraints:** `unique_together = (company, account, year, month, currency)`

Stores monthly balance snapshots per account.

### 4.6 Billing Models

#### BusinessPartner

**Table:** `billing_businesspartner` — Inherits TenantAwareBaseModel


| Field          | Type                         | Required | Description              |
| -------------- | ---------------------------- | -------- | ------------------------ |
| id             | integer                      | auto     | PK                       |
| name           | string                       | yes      |                          |
| identifier     | string                       | yes      | Tax ID / CNPJ            |
| email          | string                       | no       |                          |
| phone          | string                       | no       |                          |
| address        | text                         | no       |                          |
| category       | FK → BusinessPartnerCategory | no       |                          |
| partner_type   | enum                         | —        | customer, supplier, both |
| is_active      | boolean                      | —        | true                     |
| cliente_erp_id | string(128)                  | no       |                          |


**Constraints:** `UniqueConstraint(company, identifier)`

#### ProductService

**Table:** `billing_productservice` — Inherits TenantAwareBaseModel


| Field           | Type                        | Description            |
| --------------- | --------------------------- | ---------------------- |
| id              | integer                     | PK                     |
| name            | string                      |                        |
| code            | string                      | Product/service code   |
| category        | FK → ProductServiceCategory |                        |
| unit_price      | decimal                     |                        |
| revenue_account | FK → Account                | GL account for revenue |
| expense_account | FK → Account                | GL account for expense |
| cliente_erp_id  | string(128)                 |                        |


#### Contract

**Table:** `billing_contract`

Contracts with RRULE-style recurrence fields for recurring billing.

#### Invoice / InvoiceLine

Standard invoice with line items. Each line has product/service, quantity, unit price, total.

#### NotaFiscal (NF-e)

**Table:** `billing_notafiscal` — Inherits TenantAwareBaseModel

Brazilian electronic invoice with full fiscal fields:

- `chave` (access key) — unique
- `numero`, `serie`, `tipo`, `natureza_operacao`
- Emitter/recipient data as JSON blobs
- Tax totals, payment info
- `inventory_processing_status` for inventory integration

#### NotaFiscalItem

**Table:** `billing_notafiscalitem`
**Constraints:** `unique_together = (nota, numero_item)`

#### NFeEvento, NFeInutilizacao

Fiscal events and invoice number invalidation records.

#### CFOP

**Table:** `billing_cfop`
National fiscal operation code table. `codigo` is unique.

### 4.7 HR Models

#### Position

**Table:** `hr_position` — Inherits TenantAwareBaseModel


| Field      | Type    | Required | Unique           | Description |
| ---------- | ------- | -------- | ---------------- | ----------- |
| id         | integer | auto     | yes              | PK          |
| title      | string  | yes      | **yes (global)** |             |
| min_salary | decimal | no       | no               |             |
| max_salary | decimal | no       | no               |             |


**Business rule:** `clean()` validates min_salary ≤ max_salary.

#### Employee

**Table:** `hr_employee` — Inherits TenantAwareBaseModel


| Field       | Type          | Required | Unique           | Description      |
| ----------- | ------------- | -------- | ---------------- | ---------------- |
| id          | integer       | auto     | yes              | PK               |
| name        | string        | yes      | no               |                  |
| cpf         | string        | yes      | **yes (global)** | Brazilian tax ID |
| position    | FK → Position | yes      | no               |                  |
| base_salary | decimal       | yes      | no               |                  |
| hire_date   | date          | yes      | no               |                  |
| department  | string        | no       | no               |                  |


**Business rule:** `clean()` validates salary within position's min/max range.

#### TimeTracking

**Table:** `hr_timetracking`
**Constraints:** `unique_together = (employee, month_date)`

Tracks monthly hours, overtime, bank hours.

#### KPI, Bonus, RecurringAdjustment, Payroll

Standard HR models for performance tracking and payroll processing.

**Payroll constraints:** `unique_together = (employee, pay_date)`

### 4.8 Inventory Models

#### Warehouse

**Table:** `inventory_warehouse` — Inherits TenantAwareBaseModel
**Constraints:** `unique_together = (company, code)`

#### UnitOfMeasure

**Table:** `inventory_unitofmeasure`
**Constraints:** `unique_together = (company, code)`

#### StockMovement

**Table:** `inventory_stockmovement` — Inherits TenantAwareBaseModel


| Field           | Type                | Required | Description                             |
| --------------- | ------------------- | -------- | --------------------------------------- |
| id              | integer             | auto     | PK                                      |
| product         | FK → ProductService | yes      |                                         |
| warehouse       | FK → Warehouse      | yes      |                                         |
| movement_type   | enum                | yes      | inbound, outbound, adjustment, transfer |
| quantity        | decimal             | yes      | Must be positive                        |
| unit_cost       | decimal             | no       |                                         |
| reference_type  | string              | no       | e.g. "nfe"                              |
| reference_id    | string              | no       |                                         |
| idempotency_key | string              | yes      | For deduplication                       |


**Constraints:** `unique_together = (company, idempotency_key)`
**Business rule:** Model is **immutable** — `save()` and `delete()` are guarded after initial creation.

#### InventoryBalance

**Table:** `inventory_inventorybalance`
**Constraints:** `unique_together = (company, product, warehouse)`

### 4.9 ERP Integration Models

#### ERPProvider

**Table:** `erp_integrations_erpprovider`


| Field | Type   | Unique | Description |
| ----- | ------ | ------ | ----------- |
| slug  | string | yes    | e.g. "omie" |
| name  | string | —      |             |


#### ERPConnection

**Table:** `erp_integrations_erpconnection`
**Constraints:** `unique_together = (company, provider)`

#### ERPAPIDefinition

**Table:** `erp_integrations_erpapidefinition`
**Constraints:** `unique_together = (provider, api_call)`
`clean()` validates `transform_config` and `unique_id_config`.

#### ERPSyncJob, ERPSyncRun, ERPRawRecord

Sync job configuration, execution tracking, and raw data storage.

### 4.10 Knowledge Base Models

#### KnowledgeBase


| Field             | Type   | Unique | Description                 |
| ----------------- | ------ | ------ | --------------------------- |
| gemini_store_name | string | yes    | Gemini File Search store ID |


#### KnowledgeDocument

Status tracking for document ingestion (pending, processing, ready, error).

#### Answer, AnswerFeedback

Q&A responses and user feedback with ratings.

### 4.11 Relationship Map

```
Company ──┬── Entity (tree) ──── Account (M2M)
          │                  └── CostCenter (M2M)
          │
          ├── Transaction ──── JournalEntry ──── Account
          │                                  └── CostCenter
          │
          ├── BankAccount ──── BankTransaction
          │   └── Bank
          │   └── Entity
          │
          ├── Reconciliation ──── JournalEntry (M2M)
          │                   └── BankTransaction (M2M)
          │
          ├── BusinessPartner
          ├── ProductService ──── Account (revenue/expense)
          ├── Contract ──── BusinessPartner
          ├── Invoice ──── InvoiceLine ──── ProductService
          ├── NotaFiscal ──── NotaFiscalItem
          │
          ├── Employee ──── Position
          │   ├── TimeTracking
          │   ├── Payroll
          │   ├── KPI
          │   └── Bonus
          │
          ├── Warehouse
          ├── StockMovement ──── ProductService, Warehouse
          ├── InventoryBalance ──── ProductService, Warehouse
          │
          ├── ERPConnection ──── ERPProvider
          │   └── ERPSyncJob ──── ERPSyncRun
          │
          ├── IntegrationRule
          ├── SubstitutionRule
          ├── ImportTransformationRule
          └── ETLPipelineLog
```

---

## 5. Endpoint Reference

### 5.1 Authentication Endpoints

#### POST /login/

**Purpose:** Authenticate user and obtain token.
**Auth:** None required.
**Request body:**

```json
{"username": "admin", "password": "secret123"}
```

**Success response (200):**

```json
{
  "token": "abc123def456...",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "first_name": "Admin",
    "last_name": "User",
    "is_superuser": true,
    "must_change_password": false
  }
}
```

**Errors:** 400 (invalid credentials), 401 (authentication failed)

#### POST /logout/

**Purpose:** Invalidate session.
**Auth:** Token required.

#### POST /change-password/

**Purpose:** Change current user's password.
**Request body:**

```json
{"old_password": "current123", "new_password": "newSecure456"}
```

#### POST /users/create/

**Purpose:** Create a new user (admin only).
**Request body:**

```json
{
  "username": "newuser",
  "email": "newuser@example.com",
  "first_name": "New",
  "last_name": "User",
  "is_active": true,
  "is_superuser": false,
  "is_staff": false
}
```

### 5.2 Multitenancy / Core Endpoints (under /api/core/)

#### Users — /api/core/users/


| Method | Path                  | Description                                             |
| ------ | --------------------- | ------------------------------------------------------- |
| GET    | /api/core/users/      | List users (scoped: non-superusers see only themselves) |
| GET    | /api/core/users/{id}/ | Retrieve user detail                                    |
| POST   | /api/core/users/      | Create user                                             |
| PUT    | /api/core/users/{id}/ | Update user                                             |
| PATCH  | /api/core/users/{id}/ | Partial update user                                     |
| DELETE | /api/core/users/{id}/ | Delete user                                             |


**Query params:** `?format=csv` or `?format=xlsx` for export on list.

#### Companies — /api/core/companies/


| Method    | Path                                             | Description                          |
| --------- | ------------------------------------------------ | ------------------------------------ |
| GET       | /api/core/companies/                             | List companies                       |
| GET       | /api/core/companies/{id}/                        | Retrieve company                     |
| POST      | /api/core/companies/                             | Create company                       |
| PUT/PATCH | /api/core/companies/{id}/                        | Update company                       |
| DELETE    | /api/core/companies/{id}/                        | Soft delete company                  |
| GET       | /api/core/companies/{id}/reconciliation_summary/ | Reconciliation summary for a company |


**Soft delete:** Pass `?deleted=true` to include soft-deleted records.

#### Currencies — /api/core/currencies/

Standard CRUD. Fields: code, symbol, cliente_erp_id.

#### Integration Rules — /api/core/integration-rules/


| Method | Path                                  | Description                  |
| ------ | ------------------------------------- | ---------------------------- |
| GET    | /api/core/integration-rules/          | List rules                   |
| POST   | /api/core/integration-rules/          | Create rule                  |
| POST   | /api/core/integration-rules/{id}/run/ | Execute rule (sync or async) |


#### Substitution Rules — /api/core/substitution-rules/

Standard CRUD for data cleanup/standardization rules.

#### ETL Transformation Rules — /api/core/etl/transformation-rules/


| Method | Path                                                 | Description                  |
| ------ | ---------------------------------------------------- | ---------------------------- |
| GET    | /api/core/etl/transformation-rules/                  | List ETL rules               |
| POST   | /api/core/etl/transformation-rules/                  | Create ETL rule              |
| GET    | /api/core/etl/transformation-rules/available_models/ | List available target models |


#### ETL Pipeline Operations


| Method | Path                                  | Description                  |
| ------ | ------------------------------------- | ---------------------------- |
| POST   | /api/core/etl/preview/                | Preview ETL import (dry run) |
| POST   | /api/core/etl/execute/                | Execute ETL import           |
| POST   | /api/core/etl/analyze/                | Analyze Excel file columns   |
| GET    | /api/core/etl/logs/                   | List ETL pipeline logs       |
| GET    | /api/core/etl/logs/{id}/error-report/ | Download error report        |


#### Bulk Operations


| Method | Path                            | Description                  |
| ------ | ------------------------------- | ---------------------------- |
| POST   | /api/core/bulk-import/          | Upload Excel for bulk import |
| POST   | /api/core/bulk-import-preview/  | Preview bulk import          |
| POST   | /api/core/bulk-import-execute/  | Execute bulk import          |
| GET    | /api/core/bulk-import-template/ | Download import template     |
| POST   | /api/core/merge-records/        | Merge duplicate records      |


#### Validate/Execute Rules


| Method | Path                     | Description                 |
| ------ | ------------------------ | --------------------------- |
| POST   | /api/core/validate-rule/ | Validate a formula rule     |
| POST   | /api/core/test-rule/     | Execute/test a formula rule |


### 5.3 Accounting Endpoints (under /{tenant}/api/)

#### Accounts (Chart of Accounts) — /{tenant}/api/accounts/


| Method    | Path                                | Description                    |
| --------- | ----------------------------------- | ------------------------------ |
| GET       | /{tenant}/api/accounts/             | List accounts (tree structure) |
| GET       | /{tenant}/api/accounts/{id}/        | Account detail                 |
| POST      | /{tenant}/api/accounts/             | Create account                 |
| PUT/PATCH | /{tenant}/api/accounts/{id}/        | Update account                 |
| DELETE    | /{tenant}/api/accounts/{id}/        | Delete account                 |
| POST      | /{tenant}/api/accounts/bulk_create/ | Bulk create accounts           |
| POST      | /{tenant}/api/accounts/bulk_update/ | Bulk update accounts           |
| POST      | /{tenant}/api/accounts/bulk_delete/ | Bulk delete accounts           |


**Serializer response fields:** id, company, account_code, name, account_direction, balance, balance_date, currency, bank_account, parent, level (computed), path (computed), path_ids (computed), current_balance (computed).

#### Transactions — /{tenant}/api/transactions/


| Method    | Path                                                | Description                                          |
| --------- | --------------------------------------------------- | ---------------------------------------------------- |
| GET       | /{tenant}/api/transactions/                         | List transactions                                    |
| GET       | /{tenant}/api/transactions/{id}/                    | Transaction detail (includes nested journal entries) |
| POST      | /{tenant}/api/transactions/                         | Create transaction                                   |
| PUT/PATCH | /{tenant}/api/transactions/{id}/                    | Update transaction                                   |
| DELETE    | /{tenant}/api/transactions/{id}/                    | Delete transaction                                   |
| POST      | /{tenant}/transactions/{id}/post/                   | Post transaction (draft → posted)                    |
| POST      | /{tenant}/transactions/{id}/unpost/                 | Unpost transaction (posted → draft)                  |
| POST      | /{tenant}/transactions/{id}/cancel/                 | Cancel transaction (posted → cancelled)              |
| POST      | /{tenant}/transactions/{id}/create_balancing_entry/ | Create balancing journal entry                       |
| GET       | /{tenant}/transactions/filtered/                    | Filtered transaction list                            |


**Filters (TransactionFilter):**


| Filter            | Type         | Description                                                          |
| ----------------- | ------------ | -------------------------------------------------------------------- |
| date_from         | date         | Transactions on or after this date                                   |
| date_to           | date         | Transactions on or before this date                                  |
| amount_min        | number       | Minimum amount                                                       |
| amount_max        | number       | Maximum amount                                                       |
| state__in         | string list  | Filter by states (comma-separated)                                   |
| entity            | integer      | Filter by entity ID                                                  |
| entity__in        | integer list | Filter by multiple entity IDs                                        |
| currency          | integer      | Filter by currency ID                                                |
| description       | string       | Case-insensitive contains search                                     |
| nf_number         | string       | Filter by NF number (icontains)                                      |
| due_date_from     | date         | Due date range start                                                 |
| due_date_to       | date         | Due date range end                                                   |
| unreconciled      | boolean      | Only unreconciled transactions                                       |
| is_balanced       | boolean      | Only balanced/unbalanced                                             |
| bank_recon_status | string       | One of: matched, pending, open, mixed, na                            |
| ordering          | string       | Sort by: date, amount, id, created_at (prefix with - for descending) |


**Example request:**

```
GET /mycompany/api/transactions/?date_from=2026-01-01&date_to=2026-03-31&state__in=draft,posted&ordering=-date
Authorization: Token <token>
```

**Example response:**

```json
[
  {
    "id": 1042,
    "date": "2026-03-15",
    "entity": 5,
    "entity_name": "Headquarters",
    "description": "Monthly rent payment",
    "amount": "15000.00",
    "currency": 1,
    "currency_code": "BRL",
    "state": "posted",
    "is_balanced": true,
    "due_date": "2026-03-20",
    "nf_number": null,
    "journal_entries": [
      {
        "id": 2084,
        "account": 42,
        "account_code": "4.1.01",
        "account_name": "Rent Expense",
        "debit": "15000.00",
        "credit": "0.00",
        "date": "2026-03-15",
        "state": "posted"
      },
      {
        "id": 2085,
        "account": 15,
        "account_code": "1.1.02",
        "account_name": "Banco do Brasil",
        "debit": "0.00",
        "credit": "15000.00",
        "date": "2026-03-15",
        "state": "posted"
      }
    ],
    "created_at": "2026-03-15T10:30:00Z",
    "updated_at": "2026-03-15T10:30:00Z"
  }
]
```

#### Journal Entries — /{tenant}/api/journal_entries/


| Method    | Path                                       | Description                      |
| --------- | ------------------------------------------ | -------------------------------- |
| GET       | /{tenant}/api/journal_entries/             | List journal entries             |
| GET       | /{tenant}/api/journal_entries/{id}/        | Journal entry detail             |
| POST      | /{tenant}/api/journal_entries/             | Create journal entry             |
| PUT/PATCH | /{tenant}/api/journal_entries/{id}/        | Update journal entry             |
| POST      | /{tenant}/api/journal_entries/{id}/derive/ | Derive new entries from existing |
| POST      | /api/journal-entries/fix-imported-dates/   | Fix dates from import metadata   |


**Filters (JournalEntryFilter):**


| Filter                    | Type    | Description                              |
| ------------------------- | ------- | ---------------------------------------- |
| bank_designation_pending  | boolean | Filter by pending bank designation       |
| has_designated_bank       | boolean | Filter by whether account has bank link  |
| tag                       | string  | Exact tag match                          |
| cliente_erp_id            | string  | Exact ERP ID match                       |
| transaction_nf_number     | string  | Filter by parent transaction's NF number |
| transaction_due_date_from | date    | Parent transaction due date range        |
| transaction_due_date_to   | date    |                                          |


#### Bank Transactions — /{tenant}/api/bank_transactions/


| Method | Path                                         | Description             |
| ------ | -------------------------------------------- | ----------------------- |
| GET    | /{tenant}/api/bank_transactions/             | List bank transactions  |
| GET    | /{tenant}/api/bank_transactions/{id}/        | Bank transaction detail |
| POST   | /{tenant}/api/bank_transactions/             | Create bank transaction |
| POST   | /{tenant}/api/bank_transactions/import_ofx/  | Import OFX file         |
| POST   | /{tenant}/api/bank_transactions/bulk_create/ | Bulk create             |


**Filters (BankTransactionFilter):**


| Filter                 | Type         | Description                           |
| ---------------------- | ------------ | ------------------------------------- |
| date_from, date_to     | date         | Date range                            |
| amount_min, amount_max | number       | Amount range                          |
| id__in                 | integer list | Filter by IDs                         |
| status__in             | string list  | Filter by statuses                    |
| unreconciled           | boolean      | Only unreconciled                     |
| entity                 | integer      | Filter by entity                      |
| entity__in             | integer list | Multiple entities                     |
| entity_name            | string       | Entity name contains                  |
| bank_account           | integer      | Bank account ID                       |
| currency               | integer      | Currency ID                           |
| bank                   | integer      | Bank ID                               |
| description            | string       | Description contains                  |
| reference_number       | string       | Reference contains                    |
| tag                    | string       | Exact tag                             |
| ordering               | string       | Sort by: date, amount, id, created_at |


#### Banks & Bank Accounts

Standard CRUD at `/{tenant}/api/banks/` and `/{tenant}/api/bank_accounts/`.

#### Cost Centers — /{tenant}/api/cost_centers/

Standard CRUD.

#### Reconciliation — /{tenant}/api/reconciliation/


| Method | Path                                       | Description                  |
| ------ | ------------------------------------------ | ---------------------------- |
| GET    | /{tenant}/api/reconciliation/              | List reconciliations         |
| POST   | /{tenant}/api/reconciliation/              | Create reconciliation match  |
| GET    | /{tenant}/api/reconciliation/{id}/         | Reconciliation detail        |
| PATCH  | /{tenant}/api/reconciliation/{id}/         | Update status                |
| POST   | /{tenant}/api/reconciliation/{id}/approve/ | Approve match                |
| POST   | /{tenant}/api/reconciliation/{id}/reject/  | Reject match                 |
| GET    | /{tenant}/reconciliation-dashboard/        | Unreconciled items dashboard |


#### Reconciliation Tasks — /{tenant}/api/reconciliation-tasks/

CRUD + async task management for batch reconciliation.

#### Reconciliation Configs — /{tenant}/api/reconciliation_configs/

Configuration for reconciliation weights and tolerances.

#### Reconciliation Pipelines — /{tenant}/api/reconciliation-pipelines/

Multi-stage pipeline configuration.

#### Reconciliation Rules — /{tenant}/api/reconciliation-rules/

Learned matching patterns.

#### Account Summary — /{tenant}/account_summary/

**GET** — Returns account balance summaries.

#### Reconciliation Metrics


| Method | Path                                                     | Description                       |
| ------ | -------------------------------------------------------- | --------------------------------- |
| POST   | /{tenant}/api/reconciliation-metrics/recalculate/        | Recalculate reconciliation scores |
| GET    | /{tenant}/api/reconciliation-metrics/transaction/{id}/   | Metrics for a transaction         |
| GET    | /{tenant}/api/reconciliation-metrics/journal-entry/{id}/ | Metrics for a journal entry       |


#### Reconciliation Record Tags

**POST** `/{tenant}/api/reconciliation-record-tags/` — Bulk update tags on JEs and bank transactions.

#### Bank-Book Daily Balances

**GET** `/{tenant}/api/bank-book-daily-balances/` — Daily running balance comparison between bank and GL. **Required query params:** `date_from`, `date_to` (`YYYY-MM-DD`). **Optional:** `bank_account_id` (detailed bank/book lines for one account), `include_pending_book`, `company_id` (when tenant is `all`). **Always returned:** `bank_accounts` (all company bank accounts, summary rows) and `aggregate` (`by_currency` with summed daily bank vs book lines per currency, plus `difference.line` as bank balance minus book balance per day). With `bank_account_id`, the response also includes the single-account `bank` / `book` payload as before.

#### Embeddings


| Method | Path                                  | Description                         |
| ------ | ------------------------------------- | ----------------------------------- |
| GET    | /{tenant}/embeddings/health/          | Embedding service health            |
| GET    | /{tenant}/embeddings/missing-counts/  | Count of records missing embeddings |
| POST   | /{tenant}/embeddings/backfill/        | Start embedding generation          |
| GET    | /{tenant}/embeddings/tasks/{task_id}/ | Check embedding task status         |
| GET    | /{tenant}/embeddings/jobs/            | List embedding jobs                 |
| POST   | /{tenant}/embeddings/test/            | Test embedding generation           |
| POST   | /{tenant}/embeddings/search/          | Semantic search across records      |


#### Financial Statements


| Method | Path                                            | Description                      |
| ------ | ----------------------------------------------- | -------------------------------- |
| GET    | /{tenant}/api/financial-statement-templates/    | List templates                   |
| POST   | /{tenant}/api/financial-statement-templates/    | Create template                  |
| GET    | /{tenant}/api/financial-statements/             | List generated statements        |
| POST   | /{tenant}/api/financial-statements/generate/    | Generate statement from template |
| POST   | /{tenant}/api/financial-statements/time_series/ | Time series analysis             |
| GET    | /{tenant}/api/financial-statement-comparisons/  | List comparisons                 |
| GET    | /{tenant}/api/balance-history/                  | Balance history records          |
| POST   | /{tenant}/api/balance-history/recalculate/      | Recalculate balance history      |


#### Entities (Tenant-Scoped) — /{tenant}/api/entities/


| Method | Path                                           | Description                     |
| ------ | ---------------------------------------------- | ------------------------------- |
| GET    | /{tenant}/api/entities/                        | List entities                   |
| GET    | /{tenant}/api/entities/{id}/                   | Entity detail                   |
| GET    | /{tenant}/api/entities/{id}/context_options/   | Available accounts/cost centers |
| GET    | /{tenant}/api/entities/{id}/effective_context/ | Resolved (inherited) context    |
| GET    | /{tenant}/api/entities-mini/                   | Lightweight entity list         |
| GET    | /{tenant}/entity-tree/{company_id}/            | Full entity tree                |
| GET    | /{tenant}/entities-dynamic-transposed/         | Transposed entity view          |


### 5.4 Billing Endpoints (under /{tenant}/api/)

#### Business Partners — /{tenant}/api/business_partners/

Standard CRUD + bulk operations.

#### Product/Services — /{tenant}/api/product_services/

Standard CRUD + bulk operations.

#### Contracts — /{tenant}/api/contracts/

Standard CRUD.

#### Invoices — /{tenant}/api/invoices/

Standard CRUD. Detail includes nested invoice lines.

#### Invoice Lines — /{tenant}/api/invoice_lines/

Standard CRUD.

#### NF-e (Nota Fiscal)


| Method | Path                              | Description                         |
| ------ | --------------------------------- | ----------------------------------- |
| GET    | /{tenant}/api/nfe/                | List notas fiscais                  |
| GET    | /{tenant}/api/nfe/{id}/           | Nota fiscal detail (includes items) |
| POST   | /{tenant}/api/nfe/import/         | Import NF-e XML files (up to 10000) |
| GET    | /{tenant}/api/nfe-itens/          | List NF-e items                     |
| GET    | /{tenant}/api/nfe-eventos/        | List NF-e events                    |
| POST   | /{tenant}/api/nfe/eventos/import/ | Import NF-e events                  |


### 5.5 HR Endpoints (under /{tenant}/api/)


| Resource              | Path                                 | Methods       | Notes                         |
| --------------------- | ------------------------------------ | ------------- | ----------------------------- |
| Positions             | /{tenant}/api/positions/             | CRUD          |                               |
| Employees             | /{tenant}/api/employees/             | CRUD          | salary validation vs position |
| Time Tracking         | /{tenant}/api/timetracking/          | CRUD          |                               |
| KPIs                  | /{tenant}/api/kpis/                  | CRUD          |                               |
| Bonuses               | /{tenant}/api/bonuses/               | CRUD          |                               |
| Recurring Adjustments | /{tenant}/api/recurring-adjustments/ | CRUD          |                               |
| Payrolls              | /{tenant}/api/payrolls/              | CRUD + custom |                               |


**Payroll custom actions:**


| Method | Path                                       | Description                                    |
| ------ | ------------------------------------------ | ---------------------------------------------- |
| POST   | /{tenant}/api/payrolls/recalculate/        | Recalculate payroll                            |
| POST   | /{tenant}/api/payrolls/generate-monthly/   | Generate monthly payroll (simulate or commit)  |
| POST   | /{tenant}/api/payrolls/bulk-update-status/ | Bulk status update (triggers rules on approve) |


### 5.6 Inventory Endpoints (under /{tenant}/api/inventory/)


| Resource         | Path                                     | Methods                 | Notes |
| ---------------- | ---------------------------------------- | ----------------------- | ----- |
| Warehouses       | /{tenant}/api/inventory/warehouses/      | CRUD                    |       |
| Units of Measure | /{tenant}/api/inventory/uom/             | CRUD                    |       |
| UoM Conversions  | /{tenant}/api/inventory/uom-conversions/ | CRUD                    |       |
| Stock Movements  | /{tenant}/api/inventory/movements/       | **Read-only** + actions |       |
| Balances         | /{tenant}/api/inventory/balances/        | **Read-only**           |       |
| Alerts           | /{tenant}/api/inventory/alerts/          | GET/PATCH + detect      |       |
| Costing          | /{tenant}/api/inventory/costing/         | compute action          |       |
| Comparison       | /{tenant}/api/inventory/comparison/      | report/sku/movement     |       |


**Stock Movement actions:**

- `POST /{tenant}/api/inventory/movements/manual/` — Create manual adjustment
- `POST /{tenant}/api/inventory/movements/ingest_nf/` — Ingest from NF-e
- `POST /{tenant}/api/inventory/movements/ingest_pending/` — Batch ingest pending NFs

### 5.7 ERP Integration Endpoints (under /{tenant}/api/)


| Resource        | Path                           | Methods |
| --------------- | ------------------------------ | ------- |
| Connections     | /{tenant}/api/connections/     | CRUD    |
| API Definitions | /{tenant}/api/api-definitions/ | CRUD    |
| Sync Jobs       | /{tenant}/api/sync-jobs/       | CRUD    |
| Sync Runs       | /{tenant}/api/sync-runs/       | CRUD    |
| Raw Records     | /{tenant}/api/raw-records/     | CRUD    |
| Build Payload   | /{tenant}/api/build-payload/   | POST    |
| ETL Import      | /{tenant}/api/etl-import/      | POST    |


### 5.8 ML Endpoints (under /{tenant}/)


| Method | Path                            | Description     |
| ------ | ------------------------------- | --------------- |
| GET    | /{tenant}/ml-models/            | List ML models  |
| POST   | /{tenant}/ml-models/            | Create ML model |
| POST   | /{tenant}/ml-models/{id}/train/ | Train model     |


### 5.9 Knowledge Base Endpoints (under /{tenant}/api/)


| Method | Path                                    | Description            |
| ------ | --------------------------------------- | ---------------------- |
| GET    | /{tenant}/api/knowledge-bases/          | List knowledge bases   |
| POST   | /{tenant}/api/knowledge-bases/          | Create knowledge base  |
| POST   | /{tenant}/api/knowledge-bases/{id}/ask/ | Ask a question         |
| GET    | /{tenant}/api/documents/                | List documents         |
| POST   | /{tenant}/api/documents/                | Upload document        |
| POST   | /{tenant}/api/answers/{id}/feedback/    | Submit answer feedback |


### 5.10 Core / Infrastructure Endpoints

#### Financial Indices — /api/financial_indices/

Standard CRUD for financial index definitions.

#### Index Quotes — /api/index_quotes/

Standard CRUD for historical index values.

#### Index Forecasts — /api/index_forecasts/

Standard CRUD for forecast values.

#### Activity Feed — /api/activity/

**GET** — Returns activity/audit events.

#### Task Management


| Method | Path                       | Description          |
| ------ | -------------------------- | -------------------- |
| GET    | /api/tasks/                | List all tasks       |
| GET    | /api/tasks/types/          | Available task types |
| GET    | /api/tasks/statistics/     | Task statistics      |
| GET    | /api/tasks/{task_id}/      | Task detail/status   |
| POST   | /api/tasks/{task_id}/stop/ | Stop a running task  |


#### Chat / AI


| Method | Path                     | Description            |
| ------ | ------------------------ | ---------------------- |
| POST   | /api/chat/ask/           | Ask AI with context    |
| POST   | /api/chat/ask_nocontext/ | Ask AI without context |
| POST   | /api/chat/diag/          | Diagnostic chat        |
| POST   | /api/chat/flexible/      | Flexible chat endpoint |


#### Jobs (Legacy)


| Method | Path                    | Description |
| ------ | ----------------------- | ----------- |
| GET    | /jobs/                  | List jobs   |
| GET    | /jobs/{task_id}/        | Job status  |
| POST   | /jobs/{task_id}/cancel/ | Cancel job  |


### 5.11 NPL (Legal Pipeline) Endpoints


| Method | Path                                 | Description                 |
| ------ | ------------------------------------ | --------------------------- |
| POST   | /docs/upload                         | Upload legal document       |
| POST   | /docs/{id}/label/weak                | Weak labeling               |
| POST   | /docs/{id}/events/suggest/apply      | Apply suggested events      |
| GET    | /docs/{id}/spans                     | List spans for document     |
| PATCH  | /docs/{id}/embedding-mode/           | Update embedding mode       |
| POST   | /documents/{id}/rerun_full_pipeline/ | Rerun full NLP pipeline     |
| POST   | /documents/{id}/rerun_doctype_spans/ | Rerun doctype + spans       |
| GET    | /documents/list/                     | List all documents          |
| GET    | /search                              | Semantic search             |
| POST   | /pricing/run                         | Run pricing                 |
| GET    | /documents/                          | DRF router: list documents  |
| GET    | /spans/                              | DRF router: list spans      |
| GET    | /doctype-rules/                      | DRF router: list rules      |
| GET    | /span-rules/                         | DRF router: list span rules |


### 5.12 Feedback Endpoints


| Method | Path                   | Description                |
| ------ | ---------------------- | -------------------------- |
| POST   | /doctype/{document_id} | Submit doctype feedback    |
| POST   | /span/{document_id}    | Submit span feedback       |
| POST   | /ecode/{span_id}       | Submit event code feedback |
| POST   | /search                | Submit search feedback     |
| POST   | /train/{task}          | Trigger training task      |
| GET    | /models/versions       | List model versions        |


---

## 6. Common Patterns

### 6.1 Pagination

**No global pagination is configured.** Individual views may implement custom pagination. Most list endpoints return all results as a JSON array. For large datasets, use filters to limit results.

### 6.2 Filtering

Filtering uses `django-filter` backend. Supported syntax:

```
?field_name=value           # Exact match
?field_name__in=a,b,c       # IN filter (for CharInFilter/NumberInFilter)
?field_from=value            # Greater than or equal (range start)
?field_to=value              # Less than or equal (range end)
?description=text            # icontains (case-insensitive substring)
```

**Documented filter sets:** See Section 3.7 (`GET /api/meta/filters/`) for the complete programmatic listing.

### 6.3 Sorting

Most list endpoints support `?ordering=field_name` (prefix with `-` for descending):

```
?ordering=date               # Ascending by date
?ordering=-amount            # Descending by amount
?ordering=date,-amount       # Multi-field sort
```

### 6.4 Search

Many ViewSets enable DRF's `SearchFilter`:

```
?search=term                 # Full-text search across configured fields
```

### 6.5 Soft Delete

Models inheriting from `BaseModel` have an `is_deleted` boolean field.

- Default queries **exclude** soft-deleted records
- Pass `?deleted=true` to **include** soft-deleted records in results
- Soft-deleted records are never physically removed unless explicitly purged

### 6.6 Error Responses

**DRF standard errors (400, 401, 403, 404):**

```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Validation errors (400):**

```json
{
  "field_name": ["This field is required."],
  "non_field_errors": ["The fields must match."]
}
```

**Server errors (500):**

```json
{
  "success": false,
  "error": "Error description",
  "html": "<div>...</div>"
}
```

### 6.7 Date & Time Conventions

- All dates: ISO 8601 `YYYY-MM-DD`
- All datetimes: ISO 8601 `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC)
- Server timezone: UTC
- Client-side rendering should handle timezone conversion

### 6.8 Tenant Context

For tenant-scoped endpoints, the tenant slug is the first URL path segment:

```
/{tenant_slug}/api/transactions/
```

The tenant slug corresponds to the `Company.subdomain` field. Superusers can use `all` as the tenant slug to query across all companies.

---

## 7. Workflow & State Machine Reference

### 7.1 Transaction Lifecycle

```
         ┌─────────┐
         │  draft   │
         └────┬─────┘
              │ POST /{tenant}/transactions/{id}/post/
              ▼
         ┌─────────┐
         │ posted   │
         └────┬─────┘
              │
     ┌────────┼────────┐
     │                  │
     ▼                  ▼
POST .../unpost/    POST .../cancel/
     │                  │
     ▼                  ▼
┌─────────┐      ┌───────────┐
│  draft   │      │ cancelled │
└─────────┘      └───────────┘
```

### 7.2 Reconciliation Workflow

1. **Configure** — Set up `ReconciliationConfig` with weights and tolerances
2. **Create Pipeline** — Define multi-stage `ReconciliationPipeline`
3. **Run Task** — Start async `ReconciliationTask`
4. **Review Suggestions** — System generates `ReconciliationSuggestion` records
5. **Accept/Reject** — User approves or rejects suggestions
6. **Create Match** — Approved suggestions create `Reconciliation` records (status: matched → approved)

**Reconciliation status flow:**

```
pending → matched → approved
                  → rejected
```

### 7.3 ETL Import Pipeline

```
Upload Excel → Analyze → Preview (dry run) → Execute (commit)
                  │
                  ▼
          ETLPipelineLog created with status:
          pending → transforming → substituting → validating → importing → completed/failed/partial
```

### 7.4 NF-e Import Flow

```
Upload XML files → Parse → Create NotaFiscal + NotaFiscalItem records
                        → Optionally trigger inventory processing
```

### 7.5 Payroll Lifecycle

```
Generate monthly → Review → Approve (bulk-update-status)
                              │
                              ▼
                    Triggers integration rules
                    (payroll_approved event)
```

### 7.6 Embedding Backfill

```
POST /embeddings/backfill/ → Celery task → Generates embeddings for records missing them
                                          → Models: Account, Transaction, BankTransaction
```

---

## 8. Frontend Guidance for OpenClaw

### 8.1 Suggested Navigation Structure

```
├── Dashboard
│   ├── Financial Overview (account balances, reconciliation status)
│   ├── Recent Activity (activity feed)
│   └── Task Status (running jobs)
│
├── Accounting
│   ├── Chart of Accounts (tree view)
│   ├── Transactions (list + detail + create/edit)
│   ├── Journal Entries (list + detail)
│   ├── Banks & Bank Accounts
│   ├── Bank Transactions (list + import OFX)
│   ├── Reconciliation
│   │   ├── Dashboard (unreconciled items)
│   │   ├── Matches (list + approve/reject)
│   │   ├── Configuration
│   │   └── Pipelines
│   ├── Financial Statements
│   │   ├── Templates
│   │   └── Generated Statements
│   └── Cost Centers
│
├── Billing
│   ├── Business Partners
│   ├── Products & Services
│   ├── Contracts
│   ├── Invoices
│   └── NF-e (Notas Fiscais)
│       ├── List
│       ├── Import XML
│       └── Events
│
├── HR
│   ├── Positions
│   ├── Employees
│   ├── Time Tracking
│   ├── KPIs & Bonuses
│   ├── Payroll
│   │   ├── Monthly Generation
│   │   ├── Review & Approve
│   │   └── Recurring Adjustments
│   └── Reports
│
├── Inventory
│   ├── Warehouses
│   ├── Products & UoM
│   ├── Stock Movements
│   ├── Balances
│   ├── Costing & Valuation
│   └── Alerts
│
├── Settings
│   ├── Company Management
│   ├── Users
│   ├── Entities (Organization Tree)
│   ├── Integration Rules
│   ├── Substitution Rules
│   ├── ETL Configuration
│   └── ERP Connections
│
└── Tools
    ├── AI Chat
    ├── Semantic Search
    ├── Knowledge Base
    └── Import/Export
```

### 8.2 Endpoint-to-View Mapping


| View Type       | Endpoint Pattern                                  | Example                 |
| --------------- | ------------------------------------------------- | ----------------------- |
| **List view**   | `GET /{tenant}/api/{resource}/`                   | Transactions list       |
| **Detail view** | `GET /{tenant}/api/{resource}/{id}/`              | Transaction detail      |
| **Create form** | `POST /{tenant}/api/{resource}/`                  | New transaction         |
| **Edit form**   | `PATCH /{tenant}/api/{resource}/{id}/`            | Edit transaction        |
| **Dashboard**   | `GET /{tenant}/reconciliation-dashboard/`         | Reconciliation overview |
| **Tree view**   | `GET /{tenant}/entity-tree/{company_id}/`         | Entity hierarchy        |
| **Aggregation** | `GET /{tenant}/account_summary/`                  | Account balances        |
| **Import**      | `POST /{tenant}/api/nfe/import/`                  | NF-e XML upload         |
| **Bulk action** | `POST /{tenant}/api/payrolls/bulk-update-status/` | Payroll approval        |


### 8.3 Recommended Data-Fetching Patterns

1. **List views:** Fetch the list endpoint with appropriate filters. Use `?ordering=-created_at` for most-recent-first.
2. **Detail views:** Fetch the detail endpoint. For Transactions, the response includes nested journal entries — no separate call needed.
3. **Entity context:** Use `/entities/{id}/effective_context/` to get the resolved (inherited) accounts and cost centers for forms.
4. **Dropdowns/selectors:** Use mini endpoints (`entities-mini`) or the standard list with limited fields.
5. **Search:** Use `?search=term` on list endpoints.
6. **Reconciliation:** Fetch dashboard first, then drill down into individual matches.
7. **Financial statements:** Fetch templates first, then use `generate` action to produce statements.

### 8.4 UI Component Suggestions


| Field / Data                     | Suggested UI Component                   |
| -------------------------------- | ---------------------------------------- |
| `state` (draft/posted/cancelled) | Badge with color coding (blue/green/red) |
| `is_balanced`                    | Checkmark icon (green ✓ / red ✗)         |
| `amount` / `debit` / `credit`    | Formatted number with currency symbol    |
| Account tree                     | Collapsible tree view (MPTT hierarchy)   |
| Entity tree                      | Collapsible tree with drag-and-drop      |
| Date fields                      | Date picker with ISO format              |
| `is_deleted` (soft delete)       | Strikethrough or dimmed row              |
| `status` enums                   | Colored status pills/badges              |
| Reconciliation matches           | Side-by-side comparison panels           |
| Financial statement              | Table with indented line hierarchy       |
| NF-e list                        | Data table with XML preview              |
| Embedding search results         | Card list with similarity scores         |
| ETL logs                         | Timeline/step indicator                  |
| `tags`                           | Chip/pill components                     |
| `description`                    | Truncated with expand-on-click           |


### 8.5 Search & Filter UX per Resource


| Resource          | Recommended Filters                                    | Search Fields          |
| ----------------- | ------------------------------------------------------ | ---------------------- |
| Transactions      | Date range, state, entity, amount range, NF number     | description            |
| Journal Entries   | Account, tag, bank designation, NF number              | description            |
| Bank Transactions | Date range, bank account, entity, amount range, status | description, reference |
| Accounts          | Account code, direction, has bank link                 | name, code             |
| Business Partners | Type, category, active status                          | name, identifier       |
| Employees         | Department, position                                   | name, CPF              |
| Invoices          | Date range, status                                     | partner name           |
| NF-e              | Date range, tipo, status                               | chave, numero          |
| Stock Movements   | Warehouse, movement type, date range                   | product                |


---

## Appendix: Issues & Inconsistencies

### A.1 Code Issues Found

1. `**IntegrationRule.__str__`** references `self.target_module`, which is not a defined field on the model. Likely should reference `self.trigger_event` or a removed field.
2. `**IntegrationRuleLog.__str__**` references `self.executed_at`, which is not defined. Should use `self.created_at`.
3. `**IntegrationRule.run_rule()**` increments `times_executed` twice on success (once before log creation, once after).
4. `**Position.title**` has `unique=True` globally (not per-tenant). Two companies cannot have positions with the same title. This is likely a bug — should be `unique_together = (company, title)`.
5. `**Employee.cpf**` has `unique=True` globally. Two companies cannot have employees with the same CPF. This may be intentional (CPF is a national ID) but prevents the same person from being an employee at multiple tenant companies.
6. `**BaseModel.updated_at**` uses `auto_now_add=True` instead of `auto_now=True`. This means `updated_at` is set only on creation and never updated on subsequent saves.
7. `**Payroll` model** appears to define a duplicate `company` ForeignKey (one from `TenantAwareBaseModel` and one explicitly). This would typically cause a Django error.
8. `**MLModelViewSet`** does not use tenant scoping on its queryset — all ML models are visible regardless of tenant.
9. `**AUTH_OFF = True**` in settings means many ViewSets disable permissions entirely. This is a development flag that must be set to `False` in production.
10. **JWT routes** use `path(r'^api/token/?$', ...)` which is `path()` (not `re_path()`), so the `^`, `?`, and `$` are treated as literal characters, making these routes unreachable via normal URLs.
11. `**core/urls.py`** uses `path(r'^api/?$', include(router.urls))` — same issue as #10. The router URLs may not resolve correctly.
12. **Hardcoded database credentials** exist in `settings.py`. These should be moved to environment variables for production.
13. `**EntityDynamicTransposedView`** uses `Entity.objects.all(company__subdomain=tenant_id)` which looks like invalid Django ORM usage (`.all()` doesn't accept filter kwargs).
14. **Knowledge Base ViewSets** use `AllowAny` permission with empty `authentication_classes`, making them fully public even in production.

### A.2 Fields Defined but Not Exposed

- `Transaction.recon_score_`* fields (amount, date, desc, combined) and `recon_matched_bank_tx_id` are model fields used for reconciliation metrics but may not be directly exposed in the standard serializer.
- `Account.account_description_embedding` and `Transaction.description_embedding` are vector fields for internal semantic search — not intended for API consumers.

### A.3 Endpoints Defined but Potentially Broken

- `POST /celery/start/` references `demo_add.delay` which may not be properly imported.
- JWT endpoints (`/api/token/`, `/api/token/refresh/`) may be unreachable due to `path()` vs `re_path()` issue (see #10).
- `core/urls.py` router URLs under `path(r'^api/?$', ...)` may not resolve (see #11).

