# Retool Application - Comprehensive UI/UX Analysis & Migration Guide

## Executive Summary

This document provides a complete analysis of the existing Retool implementation (Nord App - Production) to guide the migration and improvement of all functionalities in the React implementation. The Retool app is a comprehensive accounting and financial management system with multi-tenant support, featuring transactions, bank reconciliation, financial statements, HR management, billing, and configuration management.

**Key Statistics:**
- **Total Pages**: 15+ pages
- **Main Modules**: Transactions, Bank Reconciliation, Chart of Accounts, Financial Statements, HR, Billing, Configuration
- **API Endpoints**: 100+ unique endpoints
- **Authentication**: JWT token-based with multi-tenant support
- **Base URL**: `https://server-production-e754.up.railway.app`

---

## 1. Application Structure & Navigation

### 1.1 Application Theme
- **Primary Color**: `#025736` (Green)
- **Secondary Color**: `#025736`
- **Success Color**: `#059669`
- **Danger Color**: `#dc2626`
- **Warning Color**: `#cd6f00`
- **Info Color**: `#3170f9`
- **Canvas Background**: `#f6f6f6`
- **Border Radius**: `4px`
- **Root Screen**: `login` (redirects to login if not authenticated)

### 1.2 Navigation Structure

#### Sidebar Navigation
- **Tenant Selector**: Dropdown to switch between companies/tenants
- **Embedding Status Alert**: Warning/success indicator for missing embeddings
- **Navigation Items**:
  - Home
  - Transações (Transactions)
  - Conciliação Bancária (Bank Reconciliation)
  - Cadastro Contabilidade (Accounting Registration)
  - Cadastro Billing (Billing Registration)
  - HR
  - Configurações (Settings)
  - Financial Statements (page5)

#### Header Navigation
- **Logo/Image**: Clickable, navigates to home
- **User Dropdown**: 
  - Current username displayed
  - Change Password
  - New User (superuser only)
  - Force Change Password (superuser only)
  - Logout

### 1.3 Pages Overview

| Page ID | Name | URL Slug | Purpose |
|---------|------|----------|---------|
| login | Login | `login` | User authentication |
| home | Home | `home` | Dashboard/home page |
| Transacoes | Transactions | `transacoes` | Transaction management |
| bankReconciliation | Bank Reconciliation | - | Bank reconciliation (legacy) |
| bankReconciliation2 | Bank Reconciliation 2 | - | Enhanced bank reconciliation |
| cadastroContabilidade | Accounting Registration | `cadastro` | Chart of Accounts, Entities, Accounts |
| cadastroBilling | Billing Registration | `cadastro-1` | Business Partners, Products/Services, Contracts |
| hr | HR | `hr` | Employee, Position, Time Tracking, Payroll |
| configuracoes | Settings | `configuracoes` | Integration Rules, Substitution Rules |
| configuracoes2 | Settings 2 | - | Enhanced settings with code editor |
| page2 | Code Editor Test | `page2` | Code editor testing page |
| page3 | Empty Page | - | Placeholder |
| page4 | Empty Page | - | Placeholder |
| page5 | Financial Statements | - | Financial statement generation and preview |

---

## 2. Detailed Page Analysis

### 2.1 Login Page (`login.rsx`)

**Purpose**: User authentication and tenant selection

**Components**:
- **Form**: Login form with username and password fields
- **Tenant Selector**: Dropdown to select company/tenant
- **Submit Button**: Triggers authentication

**API Calls**:
- `POST /login/` - User authentication
- `GET /api/core/users` - Fetch users (superuser only)
- `POST /users/create/` - Create new user (superuser only)

**Workflow**:
1. User enters username and password
2. Optionally selects tenant
3. Submits form
4. On success: Token stored in localStorage, user redirected to home
5. On failure: Error notification shown

**State Management**:
- `currentUser` - Stores authenticated user data with token
- `SelectedTenant` - Selected tenant/company
- `tenant_subdomain` - Current tenant subdomain

---

### 2.2 Transactions Page (`Transacoes.rsx`)

**Purpose**: View, filter, create, and manage accounting transactions

**Key Features**:
- **Transaction Table**: 
  - Columns: ID, Date, Description, Amount, Currency, State, Entity, Journal Entries Count, Balance, Reconciliation Status
  - Expandable rows showing journal entries
  - Filtering by status (pending, posted, canceled)
  - Linked filter component
  - Row selection
  - Toolbar buttons for actions
- **Status Filter**: Dropdown to filter by transaction state
- **Create/Edit Modal**: Full-screen modal for transaction creation/editing

**API Calls**:
- `GET /{tenant}/api/transactions` - List all transactions
- `GET /{tenant}/api/transactions/filtered?status={status}` - Filtered transactions
- `GET /{tenant}/api/entities` - List entities
- `GET /{tenant}/api/bank_transactions` - Bank transactions
- `GET /{tenant}/api/journal_entries` - Journal entries
- `GET /{tenant}/api/schema/transaction/` - Transaction schema
- `GET /{tenant}/api/schema/journal-entry/` - Journal entry schema
- `GET currencies` - List currencies

**Components**:
- **Table5**: Main transactions table with expandable rows
- **Filter1**: Linked filter component
- **TransactionStatusSelect**: Status dropdown filter
- **ModalFrame2**: Full-screen transaction form modal
- **Table5ExpandedRow**: Nested table showing journal entries for each transaction

**Journal Entries Expanded View**:
- Shows journal entries for selected transaction
- Columns: ID, Entity, Account, Debit Amount, Credit Amount, State
- Summary row with totals
- Editable cells (with save actions)

**User Workflows**:
1. **View Transactions**:
   - Page loads with all transactions
   - User can filter by status
   - User can use filter component for advanced filtering
   - User clicks row to expand and see journal entries

2. **Create Transaction**:
   - Click "Create" button
   - Modal opens with transaction form
   - Fill in: Date, Entity, Description, Amount, Currency
   - Add journal entries (Account, Debit, Credit)
   - Submit form
   - Transaction created, table refreshes

3. **Edit Transaction**:
   - Select row in table
   - Click edit button
   - Modal opens pre-filled with transaction data
   - Modify fields
   - Submit changes
   - Transaction updated

4. **Post Transaction**:
   - Select transaction
   - Click "Post" button
   - Transaction state changes to "posted"
   - Cannot be edited after posting

**Data Transformations**:
- `transformer1.js` - Transforms transaction data for display
- `updateJournalEntryQuery.js` - Updates journal entry values

---

### 2.3 Bank Reconciliation Pages

#### 2.3.1 Bank Reconciliation (`bankReconciliation.rsx`)

**Purpose**: Reconcile bank transactions with accounting transactions

**Key Features**:
- **OFX Import**: Import bank statements from OFX files
- **Transaction Import**: Bulk import accounting transactions
- **Automatic Matching**: AI-powered matching between bank and book transactions
- **Manual Reconciliation**: Manual selection and matching
- **Reconciliation Parameters**: Configurable matching rules
- **Reconciliation Tasks**: Background task management
- **Reconciliation Dashboard**: Summary of pending reconciliations
- **AI Chat**: Chat interface for reconciliation assistance

**API Calls**:
- `POST /{tenant}/api/bank_transactions/import_ofx/` - Import OFX file
- `POST /{tenant}/api/bank_transactions/finalize_ofx_import/` - Finalize OFX import
- `POST /{tenant}/api/transactions/bulk_import/` - Bulk import transactions
- `GET /{tenant}/api/bank_transactions/?unreconciled=true` - Unreconciled bank transactions
- `GET /{tenant}/api/journal_entries/unmatched/` - Unmatched journal entries
- `POST /{tenant}/api/bank_transactions/match_many_to_many/` - Automatic matching
- `POST /{tenant}/api/bank_transactions/match_many_to_many_with_set2/` - Enhanced matching
- `POST /{tenant}/api/bank_transactions/finalize_reconciliation_matches/` - Finalize matches
- `GET /{tenant}/api/reconciliation/summaries/` - Reconciliation summaries
- `POST /{tenant}/api/reconciliation/bulk_delete/` - Delete reconciliations
- `GET /{tenant}/api/reconciliation-tasks/start/` - Start reconciliation task
- `GET /{tenant}/api/reconciliation-tasks/{id}/status/` - Task status
- `GET /{tenant}/api/reconciliation-tasks/queued/` - Queued tasks
- `GET /{tenant}/api/reconciliation-tasks/task_counts/` - Task counts
- `GET /{tenant}/api/reconciliation_configs/` - Reconciliation configurations
- `POST /{tenant}/api/reconciliation_configs/` - Create reconciliation config
- `PUT /{tenant}/api/reconciliation_configs/{id}/` - Update reconciliation config
- `GET /{tenant}/api/reconciliation-pipelines/` - Reconciliation pipelines
- `POST /{tenant}/api/bank_transactions/suggest_matches/` - Suggest matches
- `POST /{tenant}/api/bank_transactions/create_suggestions/` - Create suggestions
- `POST /api/chat/ask/` - AI chat query

**Components**:
- **File Dropzones**: For OFX and transaction file uploads
- **Tables**: Bank transactions, book transactions, reconciliation matches
- **Parameter Controls**: Matching rules configuration
- **Task Status Indicators**: Show reconciliation task progress
- **AI Chat Interface**: Chat component for assistance

**Reconciliation Parameters**:
- `bank_ids`: Selected bank IDs
- `book_ids`: Selected book/transaction IDs
- `enforce_same_bank`: Boolean - require same bank
- `enforce_same_entity`: Boolean - require same entity
- `max_bank_entries`: Maximum bank entries to combine
- `max_book_entries`: Maximum book entries to combine
- `amount_tolerance`: Amount matching tolerance
- `date_tolerance_days`: Date matching tolerance in days
- `min_confidence`: Minimum confidence score
- `max_suggestions`: Maximum suggestions to generate
- `weight_date`: Date matching weight (0.4)
- `weight_amount`: Amount matching weight (0.6)
- `strategy`: Matching strategy ("optimized")

**User Workflows**:

1. **Import Bank Statement (OFX)**:
   - Click "Import OFX" button
   - Modal opens with file dropzone
   - Upload OFX file
   - Preview imported transactions
   - Click "Import All" to finalize
   - Transactions appear in bank transactions table

2. **Import Accounting Transactions**:
   - Click "Import Transactions" button
   - Upload CSV/Excel file
   - Transactions imported and appear in book transactions table

3. **Automatic Reconciliation**:
   - Configure reconciliation parameters
   - Select bank transactions and book transactions
   - Click "Start Reconciliation" button
   - Background task starts
   - Monitor task status
   - Review suggested matches
   - Accept or reject matches
   - Finalize reconciliation

4. **Manual Reconciliation**:
   - Select bank transactions (multiple)
   - Select journal entries (multiple)
   - Click "Manual Reconciliation" button
   - Modal opens with selected items
   - Review totals and dates
   - Confirm reconciliation
   - Reconciliation created

5. **View Reconciliation Summary**:
   - Dashboard shows pending reconciliations
   - Grouped by period (week, month, quarter, year)
   - Shows counts and totals
   - Click to view details

**Data Transformations**:
- `transformOFX.js` - Transforms OFX data
- `groupedBankTransactions.js` - Groups bank transactions by period
- `groupedTransactions.js` - Groups book transactions by period
- `ReconciliationParameters.js` - Builds reconciliation payload
- `VisibleBankIds.js` - Filters visible bank transaction IDs
- `VisibleBookIds.js` - Filters visible book transaction IDs

---

#### 2.3.2 Bank Reconciliation 2 (`bankReconciliation2.rsx`)

**Purpose**: Enhanced bank reconciliation interface

**Key Features**:
- Similar to bankReconciliation but with improved UI
- Better organization of pending reconciliations
- Enhanced parameter controls
- Improved matching interface
- Reconciliation shortcuts/presets

**Additional API Calls**:
- `GET /{tenant}/api/transactions/download_import_template/` - Download import template
- `GET /{tenant}/api/reconciliation` - List reconciliations
- `POST /{tenant}/api/reconciliation-tasks/{id}/cancel/` - Cancel task

**Components**:
- **Collapsible Summary**: Pending reconciliations summary (expandable)
- **Parameter Toggle**: Show/hide parameters
- **Auto/Manual Toggle**: Switch between automatic and manual mode
- **Reconciliation Shortcuts**: Saved reconciliation configurations

**Modals**:
- `modalImportOFX2` - OFX import modal
- `modalImportTransactions2` - Transaction import modal
- `modalManualConciliation2` - Manual reconciliation modal
- `modalNewEditReconShortcut` - Reconciliation shortcut configuration

---

### 2.4 Chart of Accounts (`cadastroContabilidade.rsx`)

**Purpose**: Manage accounting entities, accounts, cost centers, and related master data

**Key Features**:
- **Entity Management**: Create, edit, delete entities (companies, departments, etc.)
- **Account Management**: Chart of Accounts (hierarchical tree structure)
- **Cost Center Management**: Cost center CRUD operations
- **Tree View**: Hierarchical display of accounts
- **Context Options**: Dynamic form fields based on entity type

**API Calls**:
- `GET /{tenant}/api/entities-mini/` - List entities (mini version)
- `GET /{tenant}/api/entities/{id}/context-options/` - Entity context options
- `GET /{tenant}/api/entities/` - List all entities
- `POST /{tenant}/api/entities/` - Create entity
- `PUT /{tenant}/api/entities/{id}/` - Update entity
- `GET /{tenant}/api/accounts/` - List accounts
- `POST /{tenant}/api/accounts/` - Create account
- `PUT /{tenant}/api/accounts/{id}/` - Update account
- `GET /{tenant}/api/cost_centers/` - List cost centers
- `POST /{tenant}/api/cost_centers/` - Create cost center
- `PUT /{tenant}/api/cost_centers/{id}/` - Update cost center

**Components**:
- **Entity Table**: List of entities with CRUD actions
- **Account Tree**: Hierarchical tree view of accounts
- **Account Table**: Flat list view of accounts
- **Cost Center Table**: List of cost centers
- **Modals**: 
  - `modalEntidade` - Entity form
  - `modalAccount` - Account form
  - `modalCostCenter` - Cost center form

**User Workflows**:

1. **Manage Entities**:
   - View entities in table
   - Click "New" to create entity
   - Fill form with entity details
   - Submit to create
   - Click row to edit existing entity
   - Update and save

2. **Manage Accounts**:
   - View accounts in tree or table view
   - Create new account (with parent selection)
   - Edit account details
   - Accounts organized hierarchically (MPTT structure)

3. **Manage Cost Centers**:
   - View cost centers in table
   - Create, edit, delete cost centers

---

### 2.5 Billing Registration (`cadastroBilling.rsx`)

**Purpose**: Manage business partners, products/services, and contracts

**Key Features**:
- **Business Partner Categories**: Categorize business partners
- **Business Partners**: Customers, vendors, suppliers
- **Product/Service Categories**: Categorize products and services
- **Products/Services**: Product and service catalog
- **Contracts**: Contract management

**API Calls**:
- `GET /{tenant}/api/business_partner_categories/` - List categories
- `GET /{tenant}/api/entities/{id}/context-options/` - Context options
- `POST /{tenant}/api/business_partner_categories/` - Create category
- `PUT /{tenant}/api/business_partner_categories/{id}/` - Update category
- `GET /{tenant}/api/business_partners/` - List business partners
- `POST /{tenant}/api/business_partners/` - Create business partner
- `PUT /{tenant}/api/business_partners/{id}/` - Update business partner
- `GET /{tenant}/api/product_service_categories/` - List product/service categories
- `POST /{tenant}/api/product_service_categories/` - Create category
- `PUT /{tenant}/api/product_service_categories/{id}/` - Update category
- `GET /{tenant}/api/product_services/` - List products/services
- `POST /{tenant}/api/product_services/` - Create product/service
- `PUT /{tenant}/api/product_services/{id}/` - Update product/service
- `GET /{tenant}/api/contracts/` - List contracts
- `POST /{tenant}/api/contracts/` - Create contract
- `PUT /{tenant}/api/contracts/{id}/` - Update contract
- `GET /{tenant}/api/banks/` - List banks

**Components**:
- **Tabs**: Separate tabs for each entity type
- **Tables**: CRUD tables for each entity
- **Modals**: 
  - `modalBusinessPartnerCategory` - Category form
  - `modalBusinessPartner` - Business partner form
  - `modalProductServiceCategory` - Product/service category form
  - `modalProductService` - Product/service form
  - `modalContract` - Contract form

**User Workflows**:
1. Navigate to Billing Registration page
2. Select tab (Business Partners, Products/Services, Contracts)
3. View list in table
4. Create new record via modal
5. Edit existing record by clicking row
6. Delete records (with confirmation)

---

### 2.6 HR Module (`hr.rsx`)

**Purpose**: Human resources management

**Key Features**:
- **Employee Management**: Employee CRUD operations
- **Position Management**: Job positions
- **Time Tracking**: Employee time tracking
- **Payroll**: Payroll generation and management
- **Recurring Adjustments**: Recurring payroll adjustments

**API Calls**:
- `GET /{tenant}/api/hr/employees` - List employees
- `POST /{tenant}/api/hr/employees/` - Create employee
- `PUT /{tenant}/api/hr/employees/{id}/` - Update employee
- `GET /{tenant}/api/hr/positions` - List positions
- `POST /{tenant}/api/hr/positions/` - Create position
- `PUT /{tenant}/api/hr/positions/{id}/` - Update position
- `GET /{tenant}/api/hr/timetracking` - List time tracking records
- `POST /{tenant}/api/hr/timetracking/` - Create time tracking
- `PUT /{tenant}/api/hr/timetracking/{id}/` - Update time tracking
- `POST /{tenant}/api/hr/timetracking/{id}/approve/` - Approve time tracking
- `POST /{tenant}/api/hr/timetracking/{id}/reject/` - Reject time tracking
- `GET /{tenant}/api/hr/payrolls` - List payrolls
- `POST /{tenant}/api/hr/payrolls/generate-monthly/` - Generate monthly payroll
- `POST /{tenant}/api/hr/payrolls/recalculate/` - Recalculate payroll
- `DELETE /{tenant}/api/hr/payrolls/{id}/` - Delete payroll
- `GET /{tenant}/api/hr/recurring-adjustments` - List recurring adjustments
- `POST /{tenant}/api/hr/recurring-adjustments/` - Create adjustment
- `PUT /{tenant}/api/hr/recurring-adjustments/{id}/` - Update adjustment

**Components**:
- **Tabs**: Separate sections for Employees, Positions, Time Tracking, Payroll, Adjustments
- **Tables**: CRUD tables for each entity
- **Modals**: Forms for creating/editing records
- **Action Buttons**: Generate payroll, approve/reject time tracking

**User Workflows**:

1. **Manage Employees**:
   - View employees in table
   - Create new employee
   - Edit employee details
   - Link employee to position

2. **Time Tracking**:
   - View time tracking records
   - Create time entry
   - Approve/reject time entries
   - Filter by employee, date range

3. **Payroll**:
   - Generate monthly payroll
   - View payroll details
   - Recalculate payroll
   - Delete payroll

---

### 2.7 Settings/Configuration Pages

#### 2.7.1 Settings (`configuracoes.rsx`)

**Purpose**: Integration rules and substitution rules management

**Key Features**:
- **Integration Rules**: Rules for data integration
- **Substitution Rules**: Text substitution rules
- **Rule Validation**: Test and validate rules
- **Code Editor**: JavaScript/Python code editor for rules

**API Calls**:
- `GET /{tenant}/api/core/substitution-rules/` - List substitution rules
- `GET /{tenant}/api/core/integration-rules/` - List integration rules
- `POST /{tenant}/api/core/integration-rules/` - Create integration rule
- `PUT /{tenant}/api/core/integration-rules/{id}/` - Update integration rule
- `POST /{tenant}/api/core/validate-rule/` - Validate rule
- `POST /{tenant}/api/core/test-rule/` - Test rule execution

**Components**:
- **Rule Table**: List of integration rules
- **Code Editors**: 
  - Setup data editor
  - Payload editor
  - Filtered payload editor
  - Rule code editor
- **Test Results**: Display rule test results
- **Modals**: Rule creation/editing forms

**User Workflows**:

1. **Create Integration Rule**:
   - Click "New Rule"
   - Fill in rule details (trigger event, rule code, filter conditions)
   - Validate rule
   - Test rule with sample data
   - Save rule

2. **Edit Rule**:
   - Select rule from table
   - Modify rule code
   - Validate and test
   - Save changes

3. **Test Rule**:
   - Enter test payload
   - Click "Test Rule"
   - View results in code editor
   - Debug and iterate

---

#### 2.7.2 Settings 2 (`configuracoes2.rsx`)

**Purpose**: Enhanced settings with improved code editor

**Key Features**:
- Similar to configuracoes but with better code editor integration
- Syntax highlighting
- Better validation feedback
- Improved test interface

---

### 2.8 Financial Statements (`page5.rsx`)

**Purpose**: Generate and preview financial statements

**Key Features**:
- **Statement Generation**: Generate financial statements with comparisons
- **Time Series**: Generate time series data
- **Preview Mode**: Preview statements before saving
- **Charts**: Visual representation of financial data
- **Multiple Formats**: HTML, Markdown, JSON output

**API Calls**:
- `GET /{tenant}/api/financial-statements/` - List financial statements
- `POST /{tenant}/api/financial-statements/with_comparisons/?preview=true` - Generate with comparisons
- `POST /{tenant}/api/financial-statements/time_series/?preview=true&include_metadata=true` - Generate time series

**Request Body Example**:
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

**Components**:
- **Statement Preview**: HTML/Markdown preview
- **Charts**: Bar charts for time series data
- **Form Controls**: Date range, template selection, comparison options

**User Workflows**:

1. **Generate Statement**:
   - Select template
   - Choose date range
   - Select comparison types
   - Choose dimension (month, quarter, year)
   - Click "Generate"
   - Preview statement
   - Export or save

2. **View Time Series**:
   - Generate time series data
   - View in chart format
   - Analyze trends

---

## 3. Component Inventory

### 3.1 Data Display Components

#### Tables
- **Standard Table**: Used throughout for listing entities
  - Features: Sorting, filtering, pagination, row selection, expandable rows
  - Actions: Edit, delete, view details
  - Summary rows for totals
  - Custom column formatting (currency, dates, tags)

#### Cards/Metrics
- **Reconciliation Summary Cards**: Show pending reconciliation counts and totals
- **Financial Statement Cards**: Display key financial metrics

#### Charts
- **Bar Charts**: Used in financial statements for time series visualization
- **Plotly Charts**: Advanced charting in some pages

### 3.2 Form Components

#### Create/Edit Forms
- **Transaction Form**: Date, entity, description, amount, currency, journal entries
- **Entity Form**: Dynamic fields based on entity type
- **Account Form**: Account code, name, parent, type
- **Reconciliation Form**: Bank transactions, journal entries, parameters
- **Integration Rule Form**: Trigger event, rule code, filter conditions

#### Filters
- **Linked Filters**: Connected to tables for real-time filtering
- **Status Filters**: Dropdown filters for transaction states
- **Date Range Filters**: For time-based filtering
- **Multi-select Filters**: For selecting multiple entities

### 3.3 Action Components

#### Buttons
- **Primary Actions**: Create, Save, Submit, Post, Cancel
- **Secondary Actions**: Edit, Delete, View
- **Toolbar Buttons**: Table toolbar actions
- **Toggle Buttons**: Show/hide sections, toggle modes
- **Button Groups**: Grouped related actions

#### Dropdowns/Selects
- **Entity Selectors**: Select entities, accounts, etc.
- **Status Selectors**: Transaction states, reconciliation status
- **Multi-select**: Select multiple items for bulk operations

### 3.4 Modal/Dialog Components

#### Modals
- **Full-screen Modals**: Transaction forms, imports
- **Medium Modals**: Standard forms, confirmations
- **Small Modals**: Quick actions, confirmations

**Common Modals**:
- `modalFrame2` - Transaction form (full-screen)
- `modalImportOFX2` - OFX import (full-screen)
- `modalImportTransactions2` - Transaction import
- `modalManualConciliation2` - Manual reconciliation
- `modalNewEditReconShortcut` - Reconciliation shortcut
- `modalEntidade` - Entity form
- `modalAccount` - Account form
- `modalBank` - Bank form
- `modalBankAccount` - Bank account form
- `modalNewUser` - User creation
- `modalChangePassword` - Password change
- `modalSelectTenant` - Tenant selection

#### Drawers
- **Detail Drawers**: Side panels for viewing details
- `drawerFrame1` - AI chat drawer
- `drawerAIChat` - Chat interface

### 3.5 Navigation Components

#### Tabs
- **Page Tabs**: Separate sections within pages (Billing, HR)
- **Tabbed Containers**: Organize related content

#### Breadcrumbs
- Not extensively used, navigation primarily via sidebar

---

## 4. API Endpoints Reference

### 4.1 Authentication & Users
- `POST /login/` - User login
- `GET /api/core/users` - List users (superuser)
- `POST /users/create/` - Create user (superuser)

### 4.2 Transactions
- `GET /{tenant}/api/transactions` - List transactions
- `GET /{tenant}/api/transactions/filtered?status={status}` - Filtered transactions
- `POST /{tenant}/api/transactions/` - Create transaction
- `PUT /{tenant}/api/transactions/{id}/` - Update transaction
- `POST /{tenant}/api/transactions/{id}/post/` - Post transaction
- `POST /{tenant}/api/transactions/{id}/unpost/` - Unpost transaction
- `POST /{tenant}/api/transactions/{id}/cancel/` - Cancel transaction
- `POST /{tenant}/api/transactions/bulk_import/` - Bulk import
- `GET /{tenant}/api/transactions/download_import_template/` - Download template
- `GET /{tenant}/api/schema/transaction/` - Transaction schema

### 4.3 Journal Entries
- `GET /{tenant}/api/journal_entries` - List journal entries
- `GET /{tenant}/api/journal_entries/unmatched/` - Unmatched entries
- `GET /{tenant}/api/journal_entries/?unreconciled=true` - Unreconciled entries
- `GET /{tenant}/api/schema/journal-entry/` - Journal entry schema

### 4.4 Bank Transactions
- `GET /{tenant}/api/bank_transactions/` - List bank transactions
- `GET /{tenant}/api/bank_transactions/?unreconciled=true` - Unreconciled
- `POST /{tenant}/api/bank_transactions/import_ofx/` - Import OFX
- `POST /{tenant}/api/bank_transactions/finalize_ofx_import/` - Finalize import
- `POST /{tenant}/api/bank_transactions/match_many_to_many/` - Match transactions
- `POST /{tenant}/api/bank_transactions/match_many_to_many_with_set2/` - Enhanced matching
- `POST /{tenant}/api/bank_transactions/finalize_reconciliation_matches/` - Finalize matches
- `POST /{tenant}/api/bank_transactions/suggest_matches/` - Suggest matches
- `POST /{tenant}/api/bank_transactions/create_suggestions/` - Create suggestions

### 4.5 Reconciliation
- `GET /{tenant}/api/reconciliation` - List reconciliations
- `GET /{tenant}/api/reconciliation/summaries/` - Reconciliation summaries
- `POST /{tenant}/api/reconciliation/bulk_delete/` - Bulk delete
- `GET /{tenant}/api/reconciliation_configs/` - List configurations
- `POST /{tenant}/api/reconciliation_configs/` - Create configuration
- `PUT /{tenant}/api/reconciliation_configs/{id}/` - Update configuration
- `GET /{tenant}/api/reconciliation-pipelines/` - List pipelines
- `GET /{tenant}/api/reconciliation-tasks/start/` - Start task
- `GET /{tenant}/api/reconciliation-tasks/{id}/status/` - Task status
- `GET /{tenant}/api/reconciliation-tasks/queued/` - Queued tasks
- `GET /{tenant}/api/reconciliation-tasks/task_counts/` - Task counts
- `POST /{tenant}/api/reconciliation-tasks/{id}/cancel/` - Cancel task

### 4.6 Entities & Accounts
- `GET /{tenant}/api/entities/` - List entities
- `GET /{tenant}/api/entities-mini/` - List entities (mini)
- `GET /{tenant}/api/entities/{id}/context-options/` - Context options
- `POST /{tenant}/api/entities/` - Create entity
- `PUT /{tenant}/api/entities/{id}/` - Update entity
- `GET /{tenant}/api/accounts/` - List accounts
- `POST /{tenant}/api/accounts/` - Create account
- `PUT /{tenant}/api/accounts/{id}/` - Update account
- `GET /{tenant}/api/cost_centers/` - List cost centers
- `POST /{tenant}/api/cost_centers/` - Create cost center
- `PUT /{tenant}/api/cost_centers/{id}/` - Update cost center

### 4.7 Banks & Bank Accounts
- `GET /{tenant}/api/banks/` - List banks
- `POST /{tenant}/api/banks/` - Create bank
- `PUT /{tenant}/api/banks/{id}/` - Update bank
- `GET /{tenant}/api/bank_accounts/` - List bank accounts
- `POST /{tenant}/api/bank_accounts/` - Create bank account
- `PUT /{tenant}/api/bank_accounts/{id}/` - Update bank account

### 4.8 Business Partners & Billing
- `GET /{tenant}/api/business_partner_categories/` - List categories
- `POST /{tenant}/api/business_partner_categories/` - Create category
- `PUT /{tenant}/api/business_partner_categories/{id}/` - Update category
- `GET /{tenant}/api/business_partners/` - List business partners
- `POST /{tenant}/api/business_partners/` - Create business partner
- `PUT /{tenant}/api/business_partners/{id}/` - Update business partner
- `GET /{tenant}/api/product_service_categories/` - List categories
- `POST /{tenant}/api/product_service_categories/` - Create category
- `PUT /{tenant}/api/product_service_categories/{id}/` - Update category
- `GET /{tenant}/api/product_services/` - List products/services
- `POST /{tenant}/api/product_services/` - Create product/service
- `PUT /{tenant}/api/product_services/{id}/` - Update product/service
- `GET /{tenant}/api/contracts/` - List contracts
- `POST /{tenant}/api/contracts/` - Create contract
- `PUT /{tenant}/api/contracts/{id}/` - Update contract

### 4.9 HR
- `GET /{tenant}/api/hr/employees` - List employees
- `POST /{tenant}/api/hr/employees/` - Create employee
- `PUT /{tenant}/api/hr/employees/{id}/` - Update employee
- `GET /{tenant}/api/hr/positions` - List positions
- `POST /{tenant}/api/hr/positions/` - Create position
- `PUT /{tenant}/api/hr/positions/{id}/` - Update position
- `GET /{tenant}/api/hr/timetracking` - List time tracking
- `POST /{tenant}/api/hr/timetracking/` - Create time tracking
- `PUT /{tenant}/api/hr/timetracking/{id}/` - Update time tracking
- `POST /{tenant}/api/hr/timetracking/{id}/approve/` - Approve
- `POST /{tenant}/api/hr/timetracking/{id}/reject/` - Reject
- `GET /{tenant}/api/hr/payrolls` - List payrolls
- `POST /{tenant}/api/hr/payrolls/generate-monthly/` - Generate payroll
- `POST /{tenant}/api/hr/payrolls/recalculate/` - Recalculate
- `DELETE /{tenant}/api/hr/payrolls/{id}/` - Delete payroll
- `GET /{tenant}/api/hr/recurring-adjustments` - List adjustments
- `POST /{tenant}/api/hr/recurring-adjustments/` - Create adjustment
- `PUT /{tenant}/api/hr/recurring-adjustments/{id}/` - Update adjustment

### 4.10 Configuration
- `GET /{tenant}/api/core/substitution-rules/` - List substitution rules
- `POST /{tenant}/api/core/substitution-rules/` - Create rule
- `PUT /{tenant}/api/core/substitution-rules/{id}/` - Update rule
- `GET /{tenant}/api/core/integration-rules/` - List integration rules
- `POST /{tenant}/api/core/integration-rules/` - Create rule
- `PUT /{tenant}/api/core/integration-rules/{id}/` - Update rule
- `POST /{tenant}/api/core/validate-rule/` - Validate rule
- `POST /{tenant}/api/core/test-rule/` - Test rule

### 4.11 Financial Statements
- `GET /{tenant}/api/financial-statements/` - List statements
- `POST /{tenant}/api/financial-statements/with_comparisons/?preview=true` - Generate with comparisons
- `POST /{tenant}/api/financial-statements/time_series/?preview=true&include_metadata=true` - Generate time series

### 4.12 Chat/AI
- `POST /api/chat/ask/` - AI chat query
- `POST https://chat-service-production-d54a.up.railway.app/api/generate/` - External chat service

### 4.13 Currencies
- `GET currencies` - List currencies (global endpoint)

---

## 5. User Workflows

### 5.1 Authentication Workflow
1. User navigates to login page
2. Enters username and password
3. Optionally selects tenant
4. Submits form
5. System authenticates and returns JWT token
6. Token stored in localStorage
7. User redirected to home page
8. Token included in all subsequent API requests

### 5.2 Transaction Management Workflow
1. Navigate to Transactions page
2. View transactions in table
3. Filter by status if needed
4. Click row to expand and see journal entries
5. Create new transaction:
   - Click "Create" button
   - Fill form (date, entity, description, amount, currency)
   - Add journal entries (account, debit, credit)
   - Submit form
6. Edit transaction:
   - Select row
   - Click edit button
   - Modify fields
   - Save changes
7. Post transaction:
   - Select transaction
   - Click "Post" button
   - Transaction becomes posted (read-only)

### 5.3 Bank Reconciliation Workflow
1. Import bank statement:
   - Click "Import OFX"
   - Upload OFX file
   - Preview transactions
   - Finalize import
2. Import accounting transactions (if needed):
   - Click "Import Transactions"
   - Upload file
   - Transactions imported
3. Configure reconciliation parameters:
   - Set matching rules (tolerances, weights)
   - Select bank and book transactions
4. Start automatic reconciliation:
   - Click "Start Reconciliation"
   - Monitor task progress
   - Review suggested matches
   - Accept/reject matches
   - Finalize reconciliation
5. Manual reconciliation (alternative):
   - Select bank transactions
   - Select journal entries
   - Click "Manual Reconciliation"
   - Confirm match
   - Reconciliation created

### 5.4 Chart of Accounts Management Workflow
1. Navigate to Accounting Registration page
2. Manage entities:
   - View entities in table
   - Create/edit/delete entities
3. Manage accounts:
   - View in tree or table format
   - Create account with parent selection
   - Edit account details
   - Accounts organized hierarchically
4. Manage cost centers:
   - View cost centers
   - Create/edit/delete cost centers

---

## 6. UI/UX Patterns

### 6.1 Layout Patterns
- **Sidebar Navigation**: Persistent sidebar with tenant selector
- **Header Bar**: Top bar with logo and user menu
- **Main Content Area**: Scrollable content area
- **Modal Overlays**: Full-screen or medium modals for forms
- **Drawer Panels**: Side drawers for details/chat

### 6.2 Visual Design
- **Color Scheme**: Green primary (#025736), professional accounting theme
- **Typography**: Clear hierarchy with h1-h6 fonts
- **Spacing**: Consistent padding (8px, 12px)
- **Borders**: 4px border radius
- **Icons**: Bold interface icons from Retool icon library

### 6.3 Feedback Mechanisms
- **Toast Notifications**: Top-center position, 4.5s duration
- **Loading States**: Query status indicators
- **Error Handling**: Toast notifications for errors
- **Success Feedback**: Toast notifications (disabled by default, enabled per query)

### 6.4 Data Display Patterns
- **Tables**: Primary data display method
- **Expandable Rows**: Nested data (journal entries in transactions)
- **Summary Rows**: Totals and aggregations
- **Filtering**: Linked filters connected to tables
- **Grouping**: Data grouped by period (week, month, quarter, year)

---

## 7. Advanced Features

### 7.1 Multi-tenancy
- **Tenant Selection**: Dropdown in sidebar
- **Tenant Context**: All API calls include tenant subdomain
- **Tenant Isolation**: Data scoped to selected tenant

### 7.2 Background Tasks
- **Reconciliation Tasks**: Long-running reconciliation processes
- **Task Status**: Polling for task status
- **Task Queue**: View queued tasks
- **Task Cancellation**: Cancel running tasks

### 7.3 AI Integration
- **Chat Interface**: AI assistant for reconciliation help
- **Semantic Search**: Vector embeddings for search
- **Embedding Status**: Monitor missing embeddings

### 7.4 Import/Export
- **OFX Import**: Bank statement import
- **CSV/Excel Import**: Transaction bulk import
- **Template Download**: Download import templates
- **Export**: Data export capabilities (implied)

### 7.5 Code Editor
- **Integration Rules**: JavaScript/Python code editor
- **Syntax Highlighting**: CodeMirror integration
- **Validation**: Rule validation before saving
- **Testing**: Test rules with sample data

---

## 8. State Management

### 8.1 Global State
- `currentUser` - Authenticated user with token
- `SelectedTenant` - Selected tenant/company
- `tenant_subdomain` - Current tenant subdomain
- `baseUrl` - API base URL

### 8.2 Page-level State
- Selected records (entity_selected, account_selected, etc.)
- Form modes (new/edit)
- UI toggles (show/hide sections)
- Filter values

### 8.3 Component State
- Table selections
- Modal visibility
- Form data
- Query results

---

## 9. Data Transformations

### 9.1 Client-side Transformations
- `transformer1.js` - Transaction data transformation
- `groupedBankTransactions.js` - Group bank transactions by period
- `groupedTransactions.js` - Group book transactions by period
- `ReconciliationParameters.js` - Build reconciliation payload
- `VisibleBankIds.js` - Filter visible bank transaction IDs
- `VisibleBookIds.js` - Filter visible book transaction IDs
- `updateJournalEntryQuery.js` - Update journal entry values
- `transformOFX.js` - Transform OFX import data

### 9.2 Data Formatting
- Currency: Brazilian Real (R$) format with 2 decimals
- Dates: Various formats (ISO, localized)
- Numbers: Decimal formatting with separators

---

## 10. Error Handling

### 10.1 API Errors
- Toast notifications for API errors
- Error messages displayed to user
- Query failure handling

### 10.2 Validation Errors
- Form validation before submission
- Field-level validation
- Server-side validation feedback

### 10.3 Network Errors
- Timeout handling (some queries have extended timeouts)
- Retry logic (implied)
- Error notifications

---

## 11. Performance Considerations

### 11.1 Query Optimization
- Caching: Some queries use caching (300s TTL)
- Timeouts: Extended timeouts for long-running queries (up to 600s)
- Pagination: Implied for large datasets
- Lazy Loading: Queries disabled until tenant selected

### 11.2 UI Optimization
- Debounced functions: Transformations use debouncing
- Conditional rendering: Components hidden until needed
- Query disabling: Queries disabled when dependencies not met

---

## 12. Migration Checklist & Priorities

### 12.1 High Priority (Core Features)
- [ ] Authentication & Multi-tenancy
- [ ] Transactions Management
- [ ] Bank Reconciliation (Basic)
- [ ] Chart of Accounts
- [ ] Journal Entries

### 12.2 Medium Priority (Important Features)
- [ ] Enhanced Bank Reconciliation
- [ ] Financial Statements
- [ ] Business Partners & Billing
- [ ] HR Module
- [ ] Settings/Configuration

### 12.3 Low Priority (Nice-to-Have)
- [ ] AI Chat Integration
- [ ] Advanced Code Editor
- [ ] Reconciliation Shortcuts
- [ ] Enhanced Reporting

### 12.4 Improvements to Make
- [ ] Better error handling and user feedback
- [ ] Improved loading states (skeletons)
- [ ] Better mobile responsiveness
- [ ] Enhanced accessibility
- [ ] Improved performance (virtualization, pagination)
- [ ] Better data visualization
- [ ] Enhanced filtering and search
- [ ] Bulk operations UI improvements
- [ ] Better form validation and UX
- [ ] Improved navigation and breadcrumbs

---

## 13. API Integration Notes

### 13.1 Authentication
- JWT token-based authentication
- Token stored in localStorage
- Token included in Authorization header: `Token {token}`
- Token refresh mechanism (implied)

### 13.2 Request Headers
- `Content-Type: application/json`
- `Authorization: Token {token}`
- Tenant context in URL path

### 13.3 Response Formats
- JSON responses
- Error responses with detail messages
- Pagination (implied)

### 13.4 Base URLs
- Production: `https://server-production-e754.up.railway.app`
- Chat Service: `https://chat-service-production-d54a.up.railway.app`
- Tenant-specific paths: `/{tenant_subdomain}/api/...`

---

## 14. Notes & Observations

### 14.1 UX Issues in Retool
1. **Full-screen modals**: Some modals are full-screen which can be overwhelming
2. **Limited breadcrumbs**: Navigation context not always clear
3. **Error messages**: Could be more descriptive
4. **Loading states**: Some queries lack clear loading indicators
5. **Mobile experience**: Not optimized for mobile devices
6. **Accessibility**: Limited keyboard navigation and screen reader support

### 14.2 Missing Features
1. **Undo/Redo**: No undo functionality for actions
2. **Bulk Edit**: Limited bulk editing capabilities
3. **Advanced Search**: No global search functionality
4. **Export**: Limited export options
5. **Print**: No print functionality
6. **Keyboard Shortcuts**: No keyboard shortcuts documented

### 14.3 Best Practices to Follow
1. **Modal-first for add/edit**: ✅ Already implemented
2. **Drawer-based detail views**: ✅ Partially implemented (chat drawer)
3. **Table-centric design**: ✅ Well implemented
4. **Progressive disclosure**: ✅ Expandable rows, collapsible sections
5. **Context preservation**: ⚠️ Could be improved with breadcrumbs
6. **Feedback & status**: ✅ Toast notifications, but could be enhanced
7. **Data density**: ✅ Good use of tables and summaries

---

## 15. Next Steps

1. **Review this documentation** with the team
2. **Prioritize features** for migration
3. **Create detailed implementation plans** for each feature
4. **Set up API client** with authentication and tenant context
5. **Implement core pages** (Login, Transactions, Reconciliation)
6. **Add advanced features** progressively
7. **Improve UX** based on identified issues
8. **Test thoroughly** with real data
9. **Get user feedback** and iterate

---

*This document should be continuously updated as features are implemented and new requirements are discovered.*
