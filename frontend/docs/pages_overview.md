# Pages Overview

This document maps Retool pages to React routes and describes the purpose, components, and APIs for each page.

## Page Mapping: Retool → React

| Retool Page | React Route | Status | Priority |
|------------|-------------|--------|----------|
| login | `/login` | ✅ Implemented | High |
| home | `/` (redirects) | ⚠️ Partial | Medium |
| Transacoes | `/accounting/transactions` | ✅ Implemented | High |
| bankReconciliation | `/banking/reconciliation-dashboard` | ✅ Implemented | High |
| bankReconciliation2 | `/banking/reconciliation-dashboard` | ✅ Implemented | High |
| cadastroContabilidade | `/accounting/accounts` | ✅ Implemented | High |
| cadastroBilling | `/billing/*` | ❌ Not Implemented | Medium |
| hr | `/hr/*` | ❌ Not Implemented | Medium |
| configuracoes | `/settings/*` | ❌ Not Implemented | Low |
| page5 (Financial Statements) | `/financial-statements/statements` | ✅ Implemented | High |

## Implemented Pages

### 1. Login Page (`/login`)

**Purpose**: User authentication and tenant selection

**Components**:
- Login form (username, password)
- Tenant selector dropdown (optional)
- Error messages

**APIs Used**:
- `POST /login/` - Authenticate user

**Workflow**:
1. User enters credentials
2. Optionally selects tenant
3. Submits form
4. On success: Store token, redirect to home
5. On failure: Show error message

**Status**: ✅ Fully implemented

---

### 2. Transactions Page (`/accounting/transactions`)

**Purpose**: View, filter, create, edit, and manage accounting transactions

**Components**:
- **TransactionsTable**: Main data table with:
  - Columns: ID, Date, Description, Amount, Currency, State, Entity, Journal Entries Count, Balance, Reconciliation Status
  - Expandable rows showing journal entries
  - Row actions: View, Edit, Post, Unpost, Cancel
  - Status filter dropdown
  - Linked filter component
- **TransactionFormModal**: Full-screen modal for create/edit
- **TransactionDetailDrawer**: Side drawer for viewing transaction details

**APIs Used**:
- `GET /{tenant}/api/transactions/filtered?status={status}` - List filtered transactions
- `GET /{tenant}/api/transactions/{id}/` - Get transaction
- `POST /{tenant}/api/transactions/` - Create transaction
- `PUT /{tenant}/api/transactions/{id}/` - Update transaction
- `POST /{tenant}/api/transactions/{id}/post/` - Post transaction
- `POST /{tenant}/api/transactions/{id}/unpost/` - Unpost transaction
- `POST /{tenant}/api/transactions/{id}/cancel/` - Cancel transaction
- `GET /{tenant}/api/entities-mini/` - List entities for dropdown
- `GET /api/core/currencies/` - List currencies

**Special Logic**:
- Expandable rows show nested journal entries table
- Status filter updates table data
- Post/Unpost actions change transaction state
- Form validation for balanced journal entries

**Status**: ✅ Fully implemented

---

### 3. Bank Transactions Page (`/banking/bank-transactions`)

**Purpose**: View and manage bank transactions

**Components**:
- **BankTransactionsTable**: Table of bank transactions
- **Tabs**: All, Unreconciled, Reconciled
- **Filters**: Date range, bank account, amount

**APIs Used**:
- `GET /{tenant}/api/bank_transactions/` - List bank transactions
- `GET /{tenant}/api/bank_transactions/?unreconciled=true` - Unreconciled only
- `GET /{tenant}/api/bank_accounts/` - List bank accounts

**Status**: ✅ Implemented (basic)

**Missing Features**:
- OFX import functionality
- Bulk operations
- Advanced filtering

---

### 4. Reconciliation Dashboard (`/banking/reconciliation-dashboard`)

**Purpose**: Overview of reconciliation status and metrics

**Components**:
- **Metrics Cards**: Pending reconciliations, totals, counts
- **Charts**: Reconciliation trends (Recharts)
- **Summary Tables**: Grouped by period

**APIs Used**:
- `GET /{tenant}/api/reconciliation-dashboard/` - Dashboard data
- `GET /{tenant}/api/reconciliation/summaries/` - Reconciliation summaries

**Status**: ✅ Implemented

---

### 5. Reconciliation Tasks (`/banking/reconciliation-tasks`)

**Purpose**: Manage and monitor reconciliation background tasks

**Components**:
- **TasksTable**: List of reconciliation tasks
- **Status Tabs**: All, Running, Completed, Failed
- **Task Details**: Progress, logs, results
- **Start Dialog**: Configuration for new reconciliation

**APIs Used**:
- `GET /{tenant}/api/reconciliation-tasks/` - List tasks
- `GET /{tenant}/api/reconciliation-tasks/{id}/status/` - Task status
- `POST /{tenant}/api/reconciliation-tasks/start/` - Start task
- `POST /{tenant}/api/reconciliation-tasks/{id}/cancel/` - Cancel task
- `GET /{tenant}/api/reconciliation-tasks/queued/` - Queued tasks

**Status**: ✅ Implemented

---

### 6. Reconciliation Configs (`/banking/reconciliation-configs`)

**Purpose**: Configure reconciliation matching rules and parameters

**Components**:
- **ConfigsTable**: List of configurations
- **ConfigForm**: Accordion-based form with sections:
  - Basic Info (name, description, scope)
  - Scoring Weights (date, amount, description)
  - Tolerances (amount, date)
  - Limits (max entries, suggestions)

**APIs Used**:
- `GET /{tenant}/api/reconciliation_configs/` - List configs
- `POST /{tenant}/api/reconciliation_configs/` - Create config
- `PUT /{tenant}/api/reconciliation_configs/{id}/` - Update config
- `DELETE /{tenant}/api/reconciliation_configs/{id}/` - Delete config

**Status**: ✅ Implemented

---

### 7. Reconciliation Pipelines (`/banking/reconciliation-pipelines`)

**Purpose**: Manage reconciliation pipelines (workflows)

**Components**:
- **PipelinesTable**: List of pipelines
- **PipelineForm**: Create/edit pipeline

**APIs Used**:
- `GET /{tenant}/api/reconciliation-pipelines/` - List pipelines
- `POST /{tenant}/api/reconciliation-pipelines/` - Create pipeline
- `PUT /{tenant}/api/reconciliation-pipelines/{id}/` - Update pipeline

**Status**: ⚠️ Stub (needs implementation)

---

### 8. Accounts Page (`/accounting/accounts`)

**Purpose**: Manage Chart of Accounts (hierarchical account structure)

**Components**:
- **AccountTree**: Hierarchical tree view (MPTT structure)
- **AccountTable**: Flat list view
- **AccountForm**: Create/edit account modal
- **Tabs**: Tree view, List view

**APIs Used**:
- `GET /{tenant}/api/accounts/` - List accounts (hierarchical)
- `POST /{tenant}/api/accounts/` - Create account
- `PUT /{tenant}/api/accounts/{id}/` - Update account
- `DELETE /{tenant}/api/accounts/{id}/` - Delete account

**Special Logic**:
- Accounts organized in tree structure (parent-child relationships)
- Tree view shows hierarchy with expand/collapse
- Parent selection in form

**Status**: ✅ Implemented

---

### 9. Journal Entries Page (`/accounting/journal-entries`)

**Purpose**: View and manage journal entries

**Components**:
- **JournalEntriesTable**: List of journal entries
- **Filters**: Transaction, account, date range

**APIs Used**:
- `GET /{tenant}/api/journal_entries/` - List journal entries
- `GET /{tenant}/api/journal_entries/?unreconciled=true` - Unreconciled entries

**Status**: ⚠️ Stub (needs implementation)

---

### 10. Financial Statements (`/financial-statements/statements`)

**Purpose**: Generate and view financial statements

**Components**:
- **StatementsTable**: List of generated statements
- **GenerateDialog**: Form to generate new statement
- **StatementPreview**: HTML/Markdown preview
- **Charts**: Time series visualization

**APIs Used**:
- `GET /{tenant}/api/financial-statements/` - List statements
- `POST /{tenant}/api/financial-statements/with_comparisons/?preview=true` - Generate with comparisons
- `POST /{tenant}/api/financial-statements/time_series/?preview=true&include_metadata=true` - Generate time series
- `GET /{tenant}/api/financial-statement-templates/` - List templates

**Status**: ✅ Implemented (basic)

---

### 11. Financial Statement Templates (`/financial-statements/templates`)

**Purpose**: Manage financial statement templates

**Components**:
- **TemplatesTable**: List of templates
- **TemplateForm**: Create/edit template

**APIs Used**:
- `GET /{tenant}/api/financial-statement-templates/` - List templates
- `POST /{tenant}/api/financial-statement-templates/` - Create template
- `PUT /{tenant}/api/financial-statement-templates/{id}/` - Update template

**Status**: ⚠️ Stub (needs implementation)

---

## Not Yet Implemented Pages

### 12. Billing Registration (`/billing/*`)

**Purpose**: Manage business partners, products/services, and contracts

**Retool Page**: `cadastroBilling`

**Required Routes**:
- `/billing/business-partners` - Business partners management
- `/billing/products-services` - Products/services catalog
- `/billing/contracts` - Contract management

**Components Needed**:
- Business Partners table and form
- Product/Service categories and items
- Contract management interface
- Tabs for different entity types

**APIs**:
- See [API Overview](./api_overview.md) - Billing Module section

**Priority**: Medium

---

### 13. HR Module (`/hr/*`)

**Purpose**: Human resources management

**Retool Page**: `hr`

**Required Routes**:
- `/hr/employees` - Employee management
- `/hr/positions` - Job positions
- `/hr/time-tracking` - Time tracking
- `/hr/payroll` - Payroll management
- `/hr/adjustments` - Recurring adjustments

**Components Needed**:
- Employee CRUD interface
- Position management
- Time tracking with approval workflow
- Payroll generation and management
- Tabs for different HR functions

**APIs**:
- See [API Overview](./api_overview.md) - HR Module section

**Priority**: Medium

---

### 14. Settings/Configuration (`/settings/*`)

**Purpose**: System configuration and integration rules

**Retool Pages**: `configuracoes`, `configuracoes2`

**Required Routes**:
- `/settings/integration-rules` - Integration rules management
- `/settings/substitution-rules` - Substitution rules
- `/settings/code-editor` - Code editor for rules

**Components Needed**:
- Rules table and form
- Code editor component (Monaco or CodeMirror)
- Rule validation and testing interface
- Setup data, payload, and result editors

**APIs**:
- See [API Overview](./api_overview.md) - Configuration section

**Priority**: Low

---

## Page Implementation Checklist

### High Priority (Core Features)
- [x] Login
- [x] Transactions
- [x] Bank Transactions (basic)
- [x] Reconciliation Dashboard
- [x] Reconciliation Tasks
- [x] Reconciliation Configs
- [x] Accounts
- [x] Financial Statements (basic)

### Medium Priority
- [ ] Journal Entries (full implementation)
- [ ] Reconciliation Pipelines (full implementation)
- [ ] Financial Statement Templates (full implementation)
- [ ] Billing Module (all pages)
- [ ] HR Module (all pages)

### Low Priority
- [ ] Settings/Configuration (all pages)
- [ ] Home/Dashboard page
- [ ] AI Chat integration
- [ ] Advanced reporting

## Common Patterns Across Pages

### Table Pattern
Most pages follow this pattern:
1. **Page Header**: Title, breadcrumbs, action buttons
2. **Filters**: Date range, status, search, etc.
3. **Data Table**: Sortable, filterable, paginated
4. **Row Actions**: View, Edit, Delete, etc.
5. **Modals/Drawers**: For create/edit/view details

### Form Pattern
1. **Modal/Drawer**: For quick forms
2. **Dedicated Page**: For complex multi-step forms
3. **Validation**: Client-side (Zod) + Server-side feedback
4. **Success/Error**: Toast notifications

### Workflow Pattern
1. **List View**: Table with filters
2. **Detail View**: Drawer or modal
3. **Create/Edit**: Modal or dedicated page
4. **Actions**: Buttons trigger API calls with feedback

## Related Documentation

- [API Overview](./api_overview.md) - API endpoints for each page
- [Architecture](./architecture.md) - Overall architecture
- [Conventions](./conventions.md) - Implementation patterns

