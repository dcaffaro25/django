# UI/UX Documentation & Schema
## Complete Frontend Design Specification for NORD Accounting System

---

## 1. App Overview

### Purpose
NORD is a **multi-tenant accounting and financial management system** designed for companies to manage their complete accounting lifecycle. The system handles:

- **Chart of Accounts** (hierarchical account structure)
- **Transactions & Journal Entries** (double-entry bookkeeping)
- **Bank Transactions & Reconciliation** (automated matching with ML/embeddings)
- **Financial Statements** (Balance Sheet, Income Statement, Cash Flow)
- **Multi-Entity Management** (hierarchical organizational structure)
- **Cost Centers** (cost and profit center tracking)
- **HR & Payroll** (employee management, time tracking, payroll)
- **Billing** (invoices, contracts, business partners)

### Main User Types

1. **Superuser/Admin**
   - Full system access across all tenants
   - Can manage companies, users, and system-wide configurations
   - Access to all entities and data

2. **Company Admin/Accountant**
   - Full access within their company/tenant
   - Manages chart of accounts, transactions, reconciliations
   - Generates financial statements
   - Configures reconciliation pipelines and configs
   - Manages entities, cost centers, bank accounts

3. **Regular User/Bookkeeper**
   - Scoped to their company/tenant
   - Creates and manages transactions
   - Reviews and approves reconciliations
   - Views financial statements (read-only or limited edit)
   - Manages journal entries

4. **Entity-Specific Users** (Future)
   - Access limited to specific entities within a company
   - Can create transactions for their entity only

### Top 10 Core Workflows

1. **Transaction Management**
   - Create transactions with journal entries
   - Post/unpost transactions
   - Balance validation and balancing entry creation
   - Filter and search transactions

2. **Bank Reconciliation**
   - Import bank transactions (OFX files)
   - Run automated reconciliation (configs/pipelines)
   - Review reconciliation suggestions
   - Accept/reject matches
   - Manual reconciliation creation
   - Finalize matches in bulk

3. **Account Management**
   - Manage hierarchical chart of accounts
   - View account balances and summaries
   - Link accounts to bank accounts
   - Track account activity over time

4. **Financial Statement Generation**
   - Create/configure statement templates
   - Generate statements (Balance Sheet, P&L, Cash Flow)
   - View time series analysis
   - Compare periods (previous period, previous year, YTD)
   - Export to Excel, Markdown, HTML

5. **Reconciliation Configuration**
   - Create/edit reconciliation configs (matching rules)
   - Build reconciliation pipelines (multi-stage matching)
   - Set scoring weights, tolerances, filters
   - Test configs with preview

6. **Bank Transaction Management**
   - View unreconciled bank transactions
   - Get transaction suggestions (ML-based)
   - Create transactions from suggestions
   - Filter by date, amount, bank account, entity

7. **Journal Entry Management**
   - View all journal entries
   - Edit pending entries
   - Handle bank designation pending entries
   - Track reconciliation status

8. **Entity & Cost Center Management**
   - Manage hierarchical entity structure
   - Assign accounts and cost centers to entities
   - View entity-specific reports

9. **Dashboard & Analytics**
   - Reconciliation dashboard (unreconciled metrics)
   - Account summary views
   - Transaction activity overview
   - Financial statement comparisons

10. **System Administration**
    - Manage companies (tenants)
    - User management
    - Currency management
    - Bank management
    - Embedding/ML health monitoring

---

## 2. Global UX & Information Architecture

### Information Architecture

The app should be organized into **5 main sections**:

1. **Accounting** (Core)
   - Transactions
   - Journal Entries
   - Chart of Accounts
   - Cost Centers

2. **Banking & Reconciliation**
   - Bank Accounts
   - Bank Transactions
   - Reconciliation Dashboard
   - Reconciliation Tasks
   - Reconciliation Configs & Pipelines

3. **Financial Statements**
   - Templates
   - Generated Statements
   - Time Series Analysis
   - Comparisons

4. **Entities & Structure**
   - Entities (hierarchical)
   - Entity Tree View
   - Entity Reports

5. **Settings & Administration**
   - Companies
   - Users
   - Currencies
   - Banks
   - System Settings

### Navigation Patterns

**Primary Navigation: Sidebar (Left)**
- Collapsible sidebar with icons + labels
- Grouped by main sections
- Active section highlighted
- Breadcrumbs in page header for deep navigation

**Secondary Navigation: Tabs**
- Use tabs for:
  - Different views of the same data (e.g., "All", "Unreconciled", "Reconciled" for bank transactions)
  - Different time periods in financial statements
  - Different stages in reconciliation workflows

**Breadcrumbs**
- Always visible in page header
- Format: `Home > Section > Subsection > Current Page`
- Clickable for navigation

### Global UX Principles

1. **Modal-First for Add/Edit**
   - **Create**: Use modals for simple forms (transactions, accounts, configs)
   - **Edit**: Use modals for quick edits
   - **Complex Forms**: Use drawers (side panels) for multi-step or complex forms
   - **Detail Views**: Use drawers to view/edit details while keeping table context

2. **Table-Centric Design**
   - Most pages are data tables with filters
   - Inline actions (edit, delete, view) via row actions menu
   - Bulk actions via selection checkboxes
   - Pagination, sorting, column configuration

3. **Nested UI for Related Data**
   - Use **expandable rows** for one-to-many relationships (transaction → journal entries)
   - Use **tabs** for different aspects of the same entity (reconciliation detail → matched items, suggestions)
   - Use **side panels/drawers** for detail views that need context

4. **Progressive Disclosure**
   - Show essential info by default
   - Expand/collapse for details
   - Use accordions for grouped settings
   - Hide advanced options behind "Advanced" toggle

5. **Context Preservation**
   - Keep filters/state when navigating
   - Remember column visibility and sort order
   - Preserve scroll position where possible
   - Use URL params for shareable states

6. **Feedback & Status**
   - Toast notifications for actions (success, error, warning)
   - Loading states with skeletons
   - Progress indicators for long-running tasks (reconciliation, statement generation)
   - Inline validation errors

7. **Data Density**
   - Default to compact table view
   - Option to switch to "comfortable" spacing
   - Show/hide columns
   - Responsive: stack on mobile, table on desktop

---

## 3. Component Library Specification

### 3.1 Layout Components

#### AppShell
**Purpose**: Main application container with header, sidebar, and content area.

**Props**:
- `sidebarCollapsed: boolean` - Sidebar state
- `user: User` - Current user object
- `company: Company` - Current company/tenant
- `children: ReactNode` - Page content

**Events**:
- `onSidebarToggle()` - Toggle sidebar
- `onLogout()` - Logout action
- `onCompanyChange(companyId)` - Switch company

**Where Used**: Root layout, wraps all pages

---

#### PageHeader
**Purpose**: Page title, breadcrumbs, and action buttons.

**Props**:
- `title: string` - Page title
- `breadcrumbs: Array<{label, href}>` - Breadcrumb items
- `actions: Array<Button>` - Action buttons (e.g., "Create", "Export")
- `description?: string` - Optional description text
- `badge?: {text, color}` - Optional badge (e.g., count)

**Where Used**: All pages

---

#### Tabs
**Purpose**: Tab navigation for switching between views.

**Props**:
- `tabs: Array<{id, label, count?, icon?}>` - Tab definitions
- `activeTab: string` - Active tab ID
- `onTabChange(tabId)` - Tab change handler

**Where Used**: 
- Bank Transactions (All / Unreconciled / Reconciled)
- Reconciliation Tasks (All / Queued / Running / Completed)
- Financial Statements (Templates / Generated / Comparisons)

---

#### Accordion
**Purpose**: Collapsible sections for grouped content.

**Props**:
- `sections: Array<{id, title, content, defaultOpen?}>` - Sections
- `allowMultiple?: boolean` - Allow multiple open

**Where Used**:
- Reconciliation config forms (grouping: Filters, Weights, Tolerances)
- Financial statement template editor (grouping line items)
- Account tree view (expandable hierarchy)

---

#### Section
**Purpose**: Visual grouping of related content.

**Props**:
- `title?: string` - Section title
- `description?: string` - Section description
- `actions?: ReactNode` - Section-level actions
- `children: ReactNode` - Content

**Where Used**: Forms, detail pages, settings

---

### 3.2 Data Display & Tables

#### DataTable
**Purpose**: Main data table with sorting, filtering, pagination, column configuration.

**Props**:
- `columns: Array<Column>` - Column definitions
  - `id: string` - Column ID
  - `label: string` - Header label
  - `accessor: string | function` - Data accessor
  - `sortable?: boolean` - Enable sorting
  - `filterable?: boolean` - Enable filtering
  - `width?: string | number` - Column width
  - `render?: function` - Custom cell renderer
  - `align?: 'left' | 'center' | 'right'` - Text alignment
- `data: Array<Object>` - Row data
- `loading?: boolean` - Loading state
- `pagination?: {page, pageSize, total}` - Pagination config
- `sorting?: {field, direction}` - Current sort
- `filters?: Object` - Current filters
- `selectedRows?: Array<id>` - Selected row IDs
- `onRowClick?: (row) => void` - Row click handler
- `onSort?: (field, direction) => void` - Sort handler
- `onFilter?: (filters) => void` - Filter handler
- `onPageChange?: (page) => void` - Page change handler
- `onSelectionChange?: (ids) => void` - Selection handler
- `rowActions?: Array<Action>` - Row action menu items
- `bulkActions?: Array<Action>` - Bulk action menu items
- `emptyState?: ReactNode` - Empty state component
- `expandableRows?: boolean` - Enable expandable rows
- `renderExpandedRow?: (row) => ReactNode` - Expanded row content

**Events**:
- `onRowClick(row)` - Row clicked
- `onRowAction(action, row)` - Row action clicked
- `onBulkAction(action, rows)` - Bulk action clicked
- `onSort(field, direction)` - Sort changed
- `onFilter(filters)` - Filters changed
- `onPageChange(page)` - Page changed
- `onSelectionChange(ids)` - Selection changed

**Validation/Error States**:
- Show error message if data fetch fails
- Show empty state if no data
- Show loading skeleton while fetching

**Where Used**: 
- All list pages (Transactions, Bank Transactions, Journal Entries, Accounts, etc.)

---

#### NestedTable / MasterDetail
**Purpose**: Show related data in expandable rows or side panel.

**Props**:
- `masterData: Array` - Master rows
- `detailData: Object<masterId, Array>` - Detail rows by master ID
- `masterColumns: Array<Column>` - Master table columns
- `detailColumns: Array<Column>` - Detail table columns
- `renderDetail?: (masterRow) => ReactNode` - Custom detail renderer

**Where Used**:
- Transactions → Journal Entries (expandable rows)
- Reconciliation → Matched Bank/Journal items (tabs in drawer)
- Financial Statement → Line items (expandable hierarchy)

---

#### EmptyState
**Purpose**: Display when table/list is empty.

**Props**:
- `icon?: ReactNode` - Icon
- `title: string` - Title text
- `description?: string` - Description text
- `action?: {label, onClick}` - Primary action button

**Where Used**: All tables when empty

---

### 3.3 Forms & Inputs

#### TextInput
**Purpose**: Single-line text input.

**Props**:
- `label: string` - Field label
- `name: string` - Field name
- `value: string` - Current value
- `onChange: (value) => void` - Change handler
- `placeholder?: string` - Placeholder text
- `required?: boolean` - Required field
- `error?: string` - Error message
- `disabled?: boolean` - Disabled state
- `helperText?: string` - Helper text

**Validation**:
- Show error message below field
- Red border on error
- Required indicator (*)

---

#### NumberInput
**Purpose**: Numeric input with formatting.

**Props**:
- Same as TextInput, plus:
- `min?: number` - Minimum value
- `max?: number` - Maximum value
- `step?: number` - Step increment
- `format?: 'currency' | 'decimal' | 'integer'` - Format type
- `currency?: string` - Currency code (if format='currency')
- `decimals?: number` - Decimal places

**Where Used**: Amounts, percentages, weights

---

#### Select
**Purpose**: Single selection dropdown.

**Props**:
- `label: string` - Field label
- `name: string` - Field name
- `value: any` - Selected value
- `options: Array<{value, label}>` - Options
- `onChange: (value) => void` - Change handler
- `placeholder?: string` - Placeholder
- `searchable?: boolean` - Enable search
- `required?: boolean` - Required field
- `error?: string` - Error message
- `disabled?: boolean` - Disabled state

**Where Used**: Entity, Account, Currency, Status selections

---

#### MultiSelect
**Purpose**: Multiple selection dropdown.

**Props**:
- Same as Select, plus:
- `value: Array<any>` - Selected values
- `maxSelected?: number` - Max selections

**Where Used**: Account IDs, Bank Account IDs, Entity IDs in filters

---

#### DatePicker
**Purpose**: Date selection input.

**Props**:
- `label: string` - Field label
- `name: string` - Field name
- `value: Date | string` - Selected date
- `onChange: (date) => void` - Change handler
- `minDate?: Date` - Minimum date
- `maxDate?: Date` - Maximum date
- `required?: boolean` - Required field
- `error?: string` - Error message

**Where Used**: Transaction dates, date ranges, filters

---

#### DateRangePicker
**Purpose**: Date range selection.

**Props**:
- `label: string` - Field label
- `name: string` - Field name
- `value: {start, end}` - Selected range
- `onChange: (range) => void` - Change handler
- `presets?: Array<{label, range}>` - Quick select presets (e.g., "Last 30 days")

**Where Used**: Filters, financial statement date ranges

---

#### SearchBox
**Purpose**: Global or contextual search input.

**Props**:
- `placeholder?: string` - Placeholder text
- `value: string` - Search query
- `onChange: (query) => void` - Change handler
- `onSearch?: (query) => void` - Search handler (on Enter)
- `debounceMs?: number` - Debounce delay
- `suggestions?: Array<string>` - Autocomplete suggestions

**Where Used**: Transaction search, account search, bank transaction search

---

#### FormLayout
**Purpose**: Form container with layout options.

**Props**:
- `layout?: 'one-column' | 'two-column'` - Layout type
- `sections?: Array<{title, fields}>` - Grouped fields
- `children: ReactNode` - Form fields

**Where Used**: All forms

---

#### FormFieldGroup
**Purpose**: Visual grouping of related fields.

**Props**:
- `title?: string` - Group title
- `description?: string` - Group description
- `children: ReactNode` - Fields

**Where Used**: Complex forms (reconciliation configs, transaction forms)

---

### 3.4 Modals / Drawers / Popovers

#### Modal
**Purpose**: Overlay dialog for focused actions.

**Props**:
- `open: boolean` - Open state
- `onClose: () => void` - Close handler
- `title: string` - Modal title
- `children: ReactNode` - Content
- `size?: 'sm' | 'md' | 'lg' | 'xl'` - Modal size
- `footer?: ReactNode` - Footer actions
- `closeOnOverlayClick?: boolean` - Close on backdrop click
- `closeOnEscape?: boolean` - Close on Escape key

**Where Used**: 
- Create/Edit forms (Transactions, Accounts, Configs)
- Confirmation dialogs
- Quick actions

---

#### Drawer
**Purpose**: Side panel for detail views and complex forms.

**Props**:
- `open: boolean` - Open state
- `onClose: () => void` - Close handler
- `title: string` - Drawer title
- `children: ReactNode` - Content
- `side?: 'left' | 'right'` - Drawer side
- `width?: string` - Drawer width (default: 600px)
- `footer?: ReactNode` - Footer actions

**Where Used**:
- Transaction detail with journal entries
- Reconciliation detail with matched items
- Financial statement detail
- Complex multi-step forms

---

#### ConfirmationDialog
**Purpose**: Confirm destructive or important actions.

**Props**:
- `open: boolean` - Open state
- `onClose: () => void` - Close handler
- `onConfirm: () => void` - Confirm handler
- `title: string` - Dialog title
- `message: string` - Confirmation message
- `confirmLabel?: string` - Confirm button label (default: "Confirm")
- `cancelLabel?: string` - Cancel button label (default: "Cancel")
- `variant?: 'danger' | 'warning' | 'info'` - Dialog variant
- `loading?: boolean` - Loading state (disable buttons)

**Where Used**:
- Delete actions
- Post/unpost transactions
- Cancel reconciliation tasks
- Finalize financial statements

---

#### Popover
**Purpose**: Contextual information or actions.

**Props**:
- `open: boolean` - Open state
- `onClose: () => void` - Close handler
- `anchorEl: HTMLElement` - Anchor element
- `children: ReactNode` - Content
- `placement?: 'top' | 'bottom' | 'left' | 'right'` - Placement

**Where Used**:
- Row action menus
- Help tooltips
- Quick filters

---

### 3.5 Filters & Search

#### FilterBar
**Purpose**: Filter controls above tables.

**Props**:
- `filters: Object` - Current filter values
- `onFilterChange: (filters) => void` - Filter change handler
- `filterConfig: Array<FilterConfig>` - Filter definitions
  - `id: string` - Filter ID
  - `type: 'text' | 'select' | 'multiselect' | 'date' | 'daterange' | 'number' | 'numberrange'` - Filter type
  - `label: string` - Filter label
  - `options?: Array` - Options (for select/multiselect)
  - `placeholder?: string` - Placeholder
- `onClear?: () => void` - Clear all filters
- `savedFilters?: Array<{id, label, filters}>` - Saved filter presets
- `onSaveFilter?: (label, filters) => void` - Save current filters

**Where Used**: All table pages

---

#### FilterChips
**Purpose**: Display active filters as removable chips.

**Props**:
- `filters: Object` - Active filters
- `onRemove: (filterId) => void` - Remove filter handler
- `onClearAll: () => void` - Clear all handler

**Where Used**: Below FilterBar, shows active filters

---

### 3.6 Feedback & Status

#### Toast
**Purpose**: Temporary notification messages.

**Props**:
- `message: string` - Toast message
- `variant?: 'success' | 'error' | 'warning' | 'info'` - Toast type
- `duration?: number` - Auto-dismiss duration (ms)
- `action?: {label, onClick}` - Action button
- `onClose?: () => void` - Close handler

**Where Used**: All actions (create, update, delete, errors)

---

#### InlineError
**Purpose**: Inline error message below form fields.

**Props**:
- `message: string` - Error message
- `field?: string` - Field name (for accessibility)

**Where Used**: Form validation

---

#### LoadingSpinner
**Purpose**: Loading indicator.

**Props**:
- `size?: 'sm' | 'md' | 'lg'` - Spinner size
- `text?: string` - Loading text

**Where Used**: Button loading states, page loading

---

#### Skeleton
**Purpose**: Placeholder content while loading.

**Props**:
- `variant?: 'text' | 'table' | 'card'` - Skeleton type
- `rows?: number` - Number of rows (for table)

**Where Used**: Table loading, card loading

---

#### ProgressBar
**Purpose**: Progress indicator for long-running tasks.

**Props**:
- `progress: number` - Progress percentage (0-100)
- `label?: string` - Progress label
- `status?: string` - Status text (e.g., "Processing...")
- `indeterminate?: boolean` - Indeterminate progress

**Where Used**: 
- Reconciliation tasks
- Financial statement generation
- Embedding backfill tasks

---

### 3.7 Domain-Specific Components

#### ReconciliationSuggestionCard
**Purpose**: Display a reconciliation match suggestion.

**Props**:
- `suggestion: ReconciliationSuggestion` - Suggestion data
- `onAccept: () => void` - Accept handler
- `onReject: () => void` - Reject handler
- `onViewDetails: () => void` - View details handler

**Where Used**: Reconciliation task results, suggestion review

---

#### TransactionBalanceIndicator
**Purpose**: Visual indicator of transaction balance status.

**Props**:
- `transaction: Transaction` - Transaction object
- `isBalanced: boolean` - Balance status
- `discrepancy?: number` - Amount discrepancy

**Where Used**: Transaction list, transaction detail

---

#### AccountTree
**Purpose**: Hierarchical tree view of accounts.

**Props**:
- `accounts: Array<Account>` - Account tree data
- `onSelect: (account) => void` - Account selection handler
- `selectedId?: number` - Selected account ID
- `expandedIds?: Array<number>` - Expanded node IDs
- `onExpand: (id) => void` - Expand handler

**Where Used**: Account selection, account management

---

#### FinancialStatementLine
**Purpose**: Display a financial statement line item.

**Props**:
- `line: FinancialStatementLine` - Line data
- `indentLevel: number` - Indentation level
- `isBold?: boolean` - Bold formatting
- `showComparison?: boolean` - Show period comparison
- `comparison?: ComparisonData` - Comparison data

**Where Used**: Financial statement display

---

#### ReconciliationMatchPreview
**Purpose**: Preview matched bank and journal items.

**Props**:
- `bankTransactions: Array<BankTransaction>` - Bank transactions
- `journalEntries: Array<JournalEntry>` - Journal entries
- `confidenceScore: number` - Match confidence
- `discrepancy?: number` - Amount discrepancy

**Where Used**: Reconciliation suggestion review, match detail

---

## 4. Page-by-Page UI Schema

### 4.1 Transactions List Page

**Page ID**: `transactions-list`

**Route**: `/accounting/transactions`

**Title**: Transactions

**Purpose**: View, filter, and manage all accounting transactions. Users can create new transactions, view details, post/unpost, and filter by various criteria.

**User Roles**: All authenticated users (scoped to company)

**Main Components Used**:
- `DataTable` (with expandable rows for journal entries)
- `FilterBar` (date range, entity, status, amount range, description search)
- `PageHeader` (with "Create Transaction" button)
- `Modal` (for create/edit)
- `Drawer` (for transaction detail with journal entries)

**Data & API Dependencies**:
- `GET /api/transactions/` - List transactions
  - Query params: `date_from`, `date_to`, `entity`, `status`, `min_amount`, `max_amount`, `search`, `page`, `page_size`
- `POST /api/transactions/` - Create transaction
- `PUT /api/transactions/{id}/` - Update transaction
- `DELETE /api/transactions/{id}/` - Delete transaction
- `POST /api/transactions/{id}/post/` - Post transaction
- `POST /api/transactions/{id}/unpost/` - Unpost transaction
- `POST /api/transactions/{id}/cancel/` - Cancel transaction
- `POST /api/transactions/{id}/create_balancing_entry/` - Create balancing entry

**Key User Actions & Flows**:

1. **Create Transaction**
   - Click "Create Transaction" button → Opens modal
   - Modal form: Date, Entity, Description, Amount, Currency
   - After create → Opens drawer with transaction detail
   - In drawer: Add journal entries (Account, Debit/Credit, Description, Cost Center)
   - Save journal entries → Transaction balance validated
   - If unbalanced → Show warning, offer "Create Balancing Entry" button

2. **Edit Transaction**
   - Click row action menu → "Edit" → Opens modal (if pending) or drawer (if posted)
   - Pending: Can edit all fields
   - Posted: Read-only transaction, can only edit journal entries (creates adjustments)

3. **View Transaction Detail**
   - Click row → Opens drawer
   - Drawer tabs:
     - **Overview**: Transaction details, balance status, status badges
     - **Journal Entries**: Table of journal entries (expandable if many)
     - **Reconciliations**: Linked reconciliations (if any)
     - **History**: Audit trail

4. **Post/Unpost Transaction**
   - Row action menu → "Post" or "Unpost"
   - Confirmation dialog for unpost
   - Toast notification on success

5. **Filter Transactions**
   - FilterBar: Date range, Entity (multiselect), Status (select), Amount range, Description (search)
   - Active filters shown as chips below FilterBar
   - "Clear All" button

6. **Bulk Actions**
   - Select multiple rows → Bulk action menu appears
   - Actions: Post, Unpost, Delete (if pending), Export

**Interaction Patterns for Tables**:
- **Add**: Modal for transaction, then drawer for journal entries
- **Edit**: Modal (pending) or drawer (posted/complex)
- **View Details**: Drawer (keeps table context)
- **Related Data**: Expandable rows for journal entries, or tabs in drawer

**Edge Cases & Errors**:
- **Empty State**: "No transactions found. Create your first transaction."
- **Unbalanced Transaction**: Show warning badge, disable post, offer balancing entry
- **Permission Error**: Show toast, disable actions
- **Long-running Post**: Show progress indicator

**UX Improvement Suggestions**:
- Quick create: Inline form at top of table for simple transactions
- Batch import: Upload CSV/Excel for bulk creation
- Transaction templates: Save common transaction patterns

---

### 4.2 Bank Transactions List Page

**Page ID**: `bank-transactions-list`

**Route**: `/banking/bank-transactions`

**Title**: Bank Transactions

**Purpose**: View and manage bank transactions imported from bank statements. Filter unreconciled transactions, get ML suggestions, and create transactions from suggestions.

**User Roles**: All authenticated users (scoped to company)

**Main Components Used**:
- `DataTable`
- `FilterBar` (date range, bank account, entity, amount range, status, unreconciled filter)
- `Tabs` (All / Unreconciled / Reconciled)
- `PageHeader` (with "Import OFX" and "Get Suggestions" buttons)
- `Drawer` (for transaction detail and suggestions)
- `ReconciliationSuggestionCard` (in suggestions view)

**Data & API Dependencies**:
- `GET /api/bank-transactions/` - List bank transactions
  - Query params: `date_from`, `date_to`, `bank_account`, `entity`, `status`, `unreconciled`, `min_amount`, `max_amount`, `page`, `page_size`
- `GET /api/bank-transactions/unreconciled/` - Unreconciled transactions
- `POST /api/bank-transactions/suggest_matches/` - Get ML suggestions
- `POST /api/bank-transactions/create_suggestions/` - Create transactions from suggestions
- `POST /api/bank-transactions/finalize_reconciliation_matches/` - Finalize matches

**Key User Actions & Flows**:

1. **View Unreconciled Transactions**
   - Tab: "Unreconciled"
   - Shows transactions without reconciliation (status='matched' or 'approved')
   - Highlighted with badge or color

2. **Get Suggestions**
   - Select one or more unreconciled transactions
   - Click "Get Suggestions" → Calls API
   - Opens drawer with suggestions
   - Each suggestion shows:
     - Confidence score (progress bar)
     - Matched journal entries (if `use_existing_book`)
     - Proposed transaction + journal entries (if `create_new`)
     - Historical matches count
   - Actions: "Accept", "Reject", "View Details"

3. **Accept Suggestion**
   - Click "Accept" on suggestion card
   - Confirmation dialog
   - Creates transaction/journal entries/reconciliation
   - Toast notification
   - Refreshes table

4. **Create Transaction from Suggestion**
   - In suggestions drawer, review proposed transaction
   - Edit if needed (amount, description, accounts)
   - Click "Create Transaction"
   - Transaction created, reconciliation auto-created

5. **Manual Reconciliation**
   - Select bank transaction(s)
   - Row action → "Match Manually"
   - Opens drawer: Select journal entries
   - Shows balance/discrepancy
   - Click "Create Reconciliation"

6. **Bulk Finalize**
   - Select multiple bank transactions
   - Bulk action → "Finalize Matches"
   - Modal: Review matches, add reference/notes
   - Creates reconciliations in bulk

**Interaction Patterns**:
- **View Details**: Drawer with tabs (Overview, Suggestions, Reconciliations)
- **Get Suggestions**: Drawer opens with loading, then shows suggestion cards
- **Create from Suggestion**: Inline in drawer, or separate modal

**Edge Cases**:
- **No Suggestions**: Show empty state in suggestions drawer
- **Low Confidence**: Highlight suggestions below threshold
- **Import Error**: Toast with error details

---

### 4.3 Reconciliation Dashboard Page

**Page ID**: `reconciliation-dashboard`

**Route**: `/banking/reconciliation-dashboard`

**Title**: Reconciliation Dashboard

**Purpose**: Overview of unreconciled bank transactions and journal entries. Shows metrics, trends, and quick actions.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `PageHeader`
- Metric cards (count, total amount)
- Charts (daily trends)
- `DataTable` (recent unreconciled items)
- Quick action buttons

**Data & API Dependencies**:
- `GET /api/reconciliation-dashboard/` - Dashboard metrics
  - Returns: `bank_transactions: {overall: {count, total}, daily: Array}`, `journal_entries: {overall: {count, total}, daily: Array}`

**Key User Actions & Flows**:

1. **View Metrics**
   - Cards: Unreconciled Bank Transactions (count, total), Unreconciled Journal Entries (count, total)
   - Charts: Daily trend (line chart)

2. **Quick Actions**
   - "Run Reconciliation" button → Opens reconciliation task modal
   - "View Unreconciled Bank Transactions" → Links to bank transactions page (unreconciled tab)
   - "View Unreconciled Journal Entries" → Links to journal entries page (unreconciled filter)

3. **Recent Items Table**
   - Shows recent unreconciled items (bank + journal)
   - Click row → Opens detail drawer
   - Quick action: "Get Suggestions" or "Match Manually"

**Edge Cases**:
- **No Unreconciled Items**: Show success state, "All items reconciled"
- **Large Discrepancies**: Highlight in red, show warning

---

### 4.4 Reconciliation Tasks Page

**Page ID**: `reconciliation-tasks-list`

**Route**: `/banking/reconciliation-tasks`

**Title**: Reconciliation Tasks

**Purpose**: View and manage reconciliation task executions. Monitor running tasks, view results, and review suggestions.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `DataTable`
- `Tabs` (All / Queued / Running / Completed / Failed)
- `FilterBar` (date range, config, pipeline, status)
- `PageHeader` (with "Start Reconciliation" button)
- `Modal` (for starting reconciliation)
- `Drawer` (for task detail and suggestions)

**Data & API Dependencies**:
- `GET /api/reconciliation-tasks/` - List tasks
- `POST /api/reconciliation-tasks/start/` - Start reconciliation
  - Body: `{config_id?, pipeline_id?, bank_ids?, book_ids?, auto_match_100?}`
- `GET /api/reconciliation-tasks/{id}/` - Task detail
- `POST /api/reconciliation-tasks/{id}/cancel/` - Cancel task
- `GET /api/reconciliation-tasks/{id}/fresh-suggestions/` - Get fresh suggestions

**Key User Actions & Flows**:

1. **Start Reconciliation**
   - Click "Start Reconciliation" → Opens modal
   - Modal form:
     - Select Config or Pipeline (radio)
     - If Config: Select config (dropdown)
     - If Pipeline: Select pipeline (dropdown)
     - Optional: Select specific bank transactions (multiselect)
     - Optional: Select specific journal entries (multiselect)
     - Checkbox: "Auto-apply perfect matches (100%)"
   - Submit → Task created, status "queued"
   - Toast: "Reconciliation task started"
   - Table updates with new task

2. **Monitor Running Task**
   - Task row shows status badge (queued/running/completed/failed)
   - Running tasks show progress indicator
   - Auto-refresh every 5 seconds for running tasks
   - Click row → Opens drawer with task detail

3. **View Task Results**
   - Completed task → Click row → Opens drawer
   - Drawer tabs:
     - **Overview**: Task stats (candidates, suggestions, matches, duration)
     - **Suggestions**: Table of suggestions (sortable by confidence)
     - **Applied Matches**: Reconciliations created
   - In Suggestions tab:
     - Each row: Match type, confidence, bank IDs, journal IDs
     - Actions: "Accept", "Reject", "View Details"
     - Bulk actions: "Accept Selected", "Reject Selected"

4. **Accept/Reject Suggestions**
   - Select suggestion(s) → Click "Accept" or "Reject"
   - Accept → Creates reconciliation, marks suggestion as accepted
   - Reject → Marks suggestion as rejected
   - Toast notification

5. **Cancel Task**
   - Running task → Row action → "Cancel"
   - Confirmation dialog
   - Task status → "cancelled"

**Interaction Patterns**:
- **Start Task**: Modal form
- **View Results**: Drawer with tabs
- **Review Suggestions**: Table in drawer, inline actions

**Edge Cases**:
- **Task Failed**: Show error message in drawer, "Retry" button
- **Long-running Task**: Show progress, allow cancellation
- **No Suggestions**: Empty state in suggestions tab

---

### 4.5 Reconciliation Configs Page

**Page ID**: `reconciliation-configs-list`

**Route**: `/banking/reconciliation-configs`

**Title**: Reconciliation Configurations

**Purpose**: Create and manage reconciliation matching configurations. Define matching rules, weights, tolerances, and filters.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `DataTable`
- `PageHeader` (with "Create Config" button)
- `Modal` (for create/edit config)
- `Accordion` (for grouping config sections)
- `FormLayout` (two-column for config form)

**Data & API Dependencies**:
- `GET /api/reconciliation_configs/` - List configs
- `GET /api/reconciliation_configs/resolved/` - Get resolved configs (global + company + user)
- `POST /api/reconciliation_configs/` - Create config
- `PUT /api/reconciliation_configs/{id}/` - Update config
- `DELETE /api/reconciliation_configs/{id}/` - Delete config

**Key User Actions & Flows**:

1. **Create Config**
   - Click "Create Config" → Opens modal (large, ~800px width)
   - Form sections (accordions):
     - **Basic Info**: Name, Description, Scope (global/company/user/company_user), Is Default
     - **Scoring Weights**: Embedding, Amount, Currency, Date (must sum to 1.0)
       - Sliders or number inputs with sum validation
       - Show sum indicator (e.g., "Sum: 1.00 ✓")
     - **Tolerances**: Amount tolerance, Group span days, Avg date delta days
     - **Group Sizes**: Max group size (bank), Max group size (book)
     - **Thresholds**: Min confidence, Max suggestions, Max alternatives per match
     - **Filters**: Bank filters (JSON editor or form), Book filters (JSON editor or form)
     - **Advanced**: Soft time limit, Fee accounts, Duplicate window, Text similarity
   - Validation: Weights must sum to 1.0, scope requires company/user if needed
   - Save → Toast notification, table refresh

2. **Edit Config**
   - Row action → "Edit" → Opens modal with pre-filled form
   - Same form as create

3. **Duplicate Config**
   - Row action → "Duplicate" → Creates copy with "(Copy)" suffix
   - Opens edit modal for new config

4. **Set as Default**
   - Row action → "Set as Default" → Sets `is_default=True`, unsets others for same scope

5. **View Resolved Configs**
   - Toggle: "Show Resolved" → Shows all available configs (global + company + user)
   - Indicates source (badge: "Global", "Company", "User")

**Interaction Patterns**:
- **Create/Edit**: Large modal with accordions
- **Complex Forms**: Two-column layout for related fields

**Edge Cases**:
- **Weight Sum Error**: Show inline error, disable save
- **Scope Validation**: Show error if company/user missing

---

### 4.6 Reconciliation Pipelines Page

**Page ID**: `reconciliation-pipelines-list`

**Route**: `/banking/reconciliation-pipelines`

**Title**: Reconciliation Pipelines

**Purpose**: Create and manage multi-stage reconciliation pipelines. Define ordered sequences of configs with stage-specific overrides.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `DataTable`
- `PageHeader` (with "Create Pipeline" button)
- `Modal` (for create/edit pipeline)
- `Drawer` (for pipeline detail with stages)
- Drag-and-drop for stage reordering

**Data & API Dependencies**:
- `GET /api/reconciliation-pipelines/` - List pipelines
- `GET /api/reconciliation-pipelines/resolved/` - Get resolved pipelines
- `POST /api/reconciliation-pipelines/` - Create pipeline
- `PUT /api/reconciliation-pipelines/{id}/` - Update pipeline
- `DELETE /api/reconciliation-pipelines/{id}/` - Delete pipeline
- `POST /api/reconciliation-pipelines/{id}/stages/` - Add stage
- `PUT /api/reconciliation-pipelines/{id}/stages/{stage_id}/` - Update stage
- `DELETE /api/reconciliation-pipelines/{id}/stages/{stage_id}/` - Delete stage

**Key User Actions & Flows**:

1. **Create Pipeline**
   - Click "Create Pipeline" → Opens modal
   - Form: Name, Description, Scope, Auto-apply score, Max suggestions, Soft time limit
   - Save → Pipeline created, redirects to pipeline detail drawer

2. **Manage Stages**
   - Click pipeline row → Opens drawer
   - Drawer tabs:
     - **Overview**: Pipeline settings
     - **Stages**: List of stages (ordered)
   - In Stages tab:
     - "Add Stage" button → Modal: Select config, set order, optional overrides
     - Drag to reorder stages
     - Edit stage → Modal: Edit overrides
     - Delete stage → Confirmation dialog
     - Enable/disable toggle per stage

3. **Stage Overrides**
   - When adding/editing stage, show override fields (optional):
     - Max group sizes, Amount tolerance, Date knobs, Weights
     - Checkbox: "Override" per field
     - If unchecked, inherits from config

**Interaction Patterns**:
- **Create Pipeline**: Modal
- **Manage Stages**: Drawer with drag-and-drop list
- **Edit Stage**: Modal with override form

**Edge Cases**:
- **No Stages**: Show empty state, "Add your first stage"
- **Duplicate Order**: Auto-adjust order numbers

---

### 4.7 Financial Statements Templates Page

**Page ID**: `financial-statement-templates-list`

**Route**: `/financial-statements/templates`

**Title**: Financial Statement Templates

**Purpose**: Create and manage financial statement templates. Define report structures with line items, account mappings, and calculations.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `DataTable`
- `Tabs` (All / Balance Sheet / Income Statement / Cash Flow)
- `PageHeader` (with "Create Template" button)
- `Modal` (for create/edit template)
- `Drawer` (for template detail with line items editor)

**Data & API Dependencies**:
- `GET /api/financial-statement-templates/` - List templates
  - Query params: `report_type`, `is_active`
- `POST /api/financial-statement-templates/` - Create template
- `PUT /api/financial-statement-templates/{id}/` - Update template
- `DELETE /api/financial-statement-templates/{id}/` - Delete template
- `POST /api/financial-statement-templates/{id}/set_default/` - Set default
- `POST /api/financial-statement-templates/{id}/duplicate/` - Duplicate template

**Key User Actions & Flows**:

1. **Create Template**
   - Click "Create Template" → Opens modal
   - Form: Name, Report Type (select), Description, Is Active, Is Default
   - Save → Template created, redirects to template detail drawer

2. **Edit Line Items**
   - Click template row → Opens drawer
   - Drawer tabs:
     - **Overview**: Template settings
     - **Line Items**: List of line templates (ordered)
   - In Line Items tab:
     - "Add Line" button → Modal: Line form
     - Line form fields:
       - Line Number, Label, Line Type (header/account/subtotal/total/spacer)
       - Account Mapping (single account, account IDs, code prefix, path contains)
       - Calculation Type (sum/difference/balance/formula)
       - Formula (if calculation_type='formula', e.g., "L1 + L2")
       - Indent Level (0-4), Is Bold
       - Parent Line (for hierarchy)
     - Drag to reorder lines
     - Edit/Delete line actions

3. **Preview Template**
   - In template drawer, "Preview" button
   - Opens modal: Select date range, include pending
   - Shows preview of generated statement (read-only)

4. **Set as Default**
   - Row action → "Set as Default" → Sets default for report type

5. **Duplicate Template**
   - Row action → "Duplicate" → Creates copy with all line items

**Interaction Patterns**:
- **Create Template**: Modal
- **Edit Lines**: Drawer with drag-and-drop list
- **Add/Edit Line**: Modal form

**Edge Cases**:
- **Invalid Formula**: Show error, highlight line
- **Circular Formula**: Detect and show error

---

### 4.8 Financial Statements Generation Page

**Page ID**: `financial-statements-list`

**Route**: `/financial-statements/statements`

**Title**: Financial Statements

**Purpose**: Generate, view, and manage financial statements. Generate statements from templates, view time series, and compare periods.

**User Roles**: Accountants, Admins, Read-only users

**Main Components Used**:
- `DataTable`
- `FilterBar` (report type, status, date range)
- `PageHeader` (with "Generate Statement" button)
- `Modal` (for generation form)
- `Drawer` (for statement detail)
- `FinancialStatementLine` (for line display)

**Data & API Dependencies**:
- `GET /api/financial-statements/` - List statements
  - Query params: `report_type`, `status`, `start_date`, `end_date`
- `POST /api/financial-statements/generate/` - Generate statement
  - Body: `{template_id, start_date, end_date, as_of_date?, status?, include_pending?}`
  - Query params: `format` (json/markdown/html)
- `GET /api/financial-statements/{id}/` - Get statement
- `POST /api/financial-statements/{id}/finalize/` - Finalize statement
- `POST /api/financial-statements/{id}/archive/` - Archive statement
- `GET /api/financial-statements/{id}/export_excel/` - Export to Excel
- `POST /api/financial-statements/preview/` - Preview statement (no save)
- `POST /api/financial-statements/time_series/` - Generate time series
- `POST /api/financial-statements/with_comparisons/` - Generate with comparisons

**Key User Actions & Flows**:

1. **Generate Statement**
   - Click "Generate Statement" → Opens modal
   - Form:
     - Template (select, filtered by report type)
     - Start Date, End Date
     - As of Date (for balance sheet)
     - Include Pending (checkbox)
     - Status (draft/final)
   - Submit → Shows progress indicator
   - On completion → Toast, redirects to statement detail drawer

2. **View Statement**
   - Click statement row → Opens drawer
   - Drawer tabs:
     - **Overview**: Statement metadata, totals
     - **Lines**: Table of line items (hierarchical, with indentation)
     - **Export**: Export options (Excel, Markdown, HTML)
   - Lines table:
     - Columns: Line #, Label (indented), Debit, Credit, Balance
     - Expandable rows for parent/child relationships
     - Bold rows for headers/totals

3. **Generate Time Series**
   - In statement drawer, "Time Series" button
   - Modal: Select dimension (day/week/month/quarter/semester/year), line numbers (optional)
   - Generates time series data
   - Shows chart + table view

4. **Generate with Comparisons**
   - In statement drawer, "Compare Periods" button
   - Modal: Select comparison types (previous period, previous year, YTD, etc.), optional dimension
   - Generates comparison data
   - Shows statement with comparison columns (current, comparison, change, % change)

5. **Export Statement**
   - Row action → "Export" → Dropdown: Excel, Markdown, HTML
   - Downloads file

6. **Finalize/Archive**
   - Draft statement → Row action → "Finalize" → Confirmation dialog
   - Final statement → Row action → "Archive" → Confirmation dialog

**Interaction Patterns**:
- **Generate**: Modal form
- **View**: Drawer with tabs
- **Export**: Dropdown menu

**Edge Cases**:
- **Generation Error**: Show error in modal, allow retry
- **Long Generation**: Show progress, allow cancellation
- **Empty Statement**: Show empty state, check template

---

### 4.9 Chart of Accounts Page

**Page ID**: `accounts-list`

**Route**: `/accounting/accounts`

**Title**: Chart of Accounts

**Purpose**: Manage hierarchical chart of accounts. View account tree, balances, and account details.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `AccountTree` (hierarchical tree view)
- `DataTable` (flat list view, toggle)
- `FilterBar` (account code, name, entity, is_active)
- `PageHeader` (with "Create Account" button)
- `Modal` (for create/edit account)
- `Drawer` (for account detail with activity)

**Data & API Dependencies**:
- `GET /api/accounts/` - List accounts
  - Query params: `parent`, `entity`, `is_active`, `search`
- `POST /api/accounts/` - Create account
- `PUT /api/accounts/{id}/` - Update account
- `DELETE /api/accounts/{id}/` - Delete account
- `GET /api/account_summary/` - Account summary with balances
  - Query params: `company_id`, `entity_id`, `min_depth`, `include_pending`, `beginning_date`, `end_date`

**Key User Actions & Flows**:

1. **View Accounts**
   - Toggle: "Tree View" / "List View"
   - Tree View: Hierarchical tree, expandable nodes
   - List View: Flat table with parent column

2. **Create Account**
   - Click "Create Account" → Opens modal
   - Form:
     - Account Code, Name, Description
     - Parent Account (select, tree picker)
     - Account Direction (1 for debit normal, -1 for credit normal)
     - Currency, Bank Account (optional)
     - Is Active
   - Save → Account created, tree refreshes

3. **View Account Detail**
   - Click account → Opens drawer
   - Drawer tabs:
     - **Overview**: Account details, current balance, balance date
     - **Activity**: Journal entries for this account (table)
     - **Balance History**: Balance over time (chart)
   - Activity table: Filter by date range, transaction

4. **Account Summary**
   - "View Summary" button → Opens modal
   - Select: Entity (optional), Min Depth, Include Pending, Date Range
   - Shows table: Account Code, Name, Balance
   - Export to CSV

**Interaction Patterns**:
- **Create/Edit**: Modal
- **View Detail**: Drawer
- **Tree Navigation**: Expandable tree, click to select

**Edge Cases**:
- **Circular Parent**: Prevent in validation
- **Account with Children**: Warn before delete, or prevent delete

---

### 4.10 Journal Entries Page

**Page ID**: `journal-entries-list`

**Route**: `/accounting/journal-entries`

**Title**: Journal Entries

**Purpose**: View and manage all journal entries. Filter by account, transaction, reconciliation status.

**User Roles**: Accountants, Admins

**Main Components Used**:
- `DataTable`
- `FilterBar` (date range, account, transaction, cost center, state, is_reconciled, bank_designation_pending)
- `PageHeader`
- `Drawer` (for journal entry detail)

**Data & API Dependencies**:
- `GET /api/journal_entries/` - List journal entries
  - Query params: `date_from`, `date_to`, `account`, `transaction`, `cost_center`, `state`, `is_reconciled`, `bank_designation_pending`
- `PUT /api/journal_entries/{id}/` - Update journal entry
- `DELETE /api/journal_entries/{id}/` - Delete journal entry

**Key User Actions & Flows**:

1. **View Journal Entries**
   - Table columns: Date, Transaction, Account, Description, Debit, Credit, Cost Center, State, Reconciled
   - Filter by account, transaction, date range, state, reconciliation status

2. **Edit Journal Entry**
   - Pending entry → Row action → "Edit" → Opens modal
   - Can edit: Account, Debit/Credit, Description, Cost Center, Date
   - Posted entry → Read-only, or create adjustment entry

3. **View Detail**
   - Click row → Opens drawer
   - Shows: Journal entry details, linked transaction, reconciliations

4. **Filter Unreconciled**
   - Filter: "Is Reconciled" = false
   - Shows entries available for reconciliation

5. **Filter Bank Designation Pending**
   - Filter: "Bank Designation Pending" = true
   - Shows entries awaiting bank account assignment

**Interaction Patterns**:
- **Edit**: Modal (if pending)
- **View**: Drawer

**Edge Cases**:
- **Posted Entry**: Disable edit, show message

---

## 5. Tables + Modals + Nested UI

### 5.1 Main Tables/Grids

#### Transactions Table
**Key Columns** (default visible):
- Date
- Entity
- Description
- Amount
- Currency
- Status (badge: pending/posted/cancelled)
- Balance Status (badge: balanced/unbalanced)
- Actions (menu)

**Default Sort**: Date (descending)

**Filters**:
- Date range (date range picker)
- Entity (multiselect)
- Status (select)
- Amount range (number range)
- Description (search)

**Row Actions**:
- View (opens drawer)
- Edit (opens modal if pending, drawer if posted)
- Post (if pending)
- Unpost (if posted)
- Cancel (if pending)
- Delete (if pending)

**Bulk Actions**:
- Post Selected
- Unpost Selected
- Delete Selected
- Export

**Create Record UX**:
- Button: "Create Transaction" → Modal
- Modal form: Basic transaction fields
- After save → Opens drawer for journal entries
- In drawer: Add journal entries inline (table with add row)

**Edit Record UX**:
- Pending: Modal (quick edit)
- Posted: Drawer (read-only transaction, editable journal entries)

**Related Objects**:
- Journal Entries: Expandable rows in table, or tabs in drawer
- Reconciliations: Tab in drawer

---

#### Bank Transactions Table
**Key Columns**:
- Date
- Bank Account
- Description
- Amount
- Currency
- Status
- Reconciled (badge)
- Actions

**Default Sort**: Date (descending)

**Filters**:
- Date range
- Bank Account (multiselect)
- Entity (multiselect, via bank account)
- Amount range
- Status (select)
- Unreconciled (checkbox)

**Row Actions**:
- View (opens drawer)
- Get Suggestions (if unreconciled)
- Match Manually (if unreconciled)
- Delete (if pending)

**Bulk Actions**:
- Get Suggestions
- Finalize Matches
- Export

**Create Record UX**:
- Import OFX file → Bulk import
- Or: "Create Bank Transaction" → Modal (rare, usually imported)

**Edit Record UX**:
- Modal (if pending/unreconciled)

**Related Objects**:
- Suggestions: Tab in drawer
- Reconciliations: Tab in drawer

---

#### Journal Entries Table
**Key Columns**:
- Date
- Transaction (link)
- Account (link)
- Description
- Debit
- Credit
- Cost Center
- State
- Reconciled (badge)

**Default Sort**: Date (descending)

**Filters**:
- Date range
- Account (select)
- Transaction (select)
- Cost Center (select)
- State (select)
- Is Reconciled (checkbox)
- Bank Designation Pending (checkbox)

**Row Actions**:
- View (opens drawer)
- Edit (if pending)
- Delete (if pending)

**Create Record UX**:
- Usually created via Transaction form
- Can create standalone: Modal

**Edit Record UX**:
- Modal (if pending)

**Related Objects**:
- Transaction: Link to transaction detail
- Reconciliations: Tab in drawer

---

#### Accounts Table
**Key Columns**:
- Account Code
- Name
- Path (full hierarchy)
- Account Direction
- Current Balance
- Currency
- Is Active

**Default Sort**: Account Code (ascending)

**Filters**:
- Account Code (search)
- Name (search)
- Entity (multiselect)
- Is Active (checkbox)
- Parent (select)

**Row Actions**:
- View (opens drawer)
- Edit (opens modal)
- Delete (if no children/journal entries)

**Create Record UX**:
- Modal with parent selection (tree picker)

**Edit Record UX**:
- Modal

**Related Objects**:
- Children: Expandable in tree view
- Journal Entries: Tab in drawer
- Balance History: Chart in drawer

---

#### Reconciliation Tasks Table
**Key Columns**:
- Created At
- Config/Pipeline Name
- Status (badge: queued/running/completed/failed/cancelled)
- Bank Candidates
- Journal Candidates
- Suggestions Count
- Matched Count
- Duration
- Actions

**Default Sort**: Created At (descending)

**Filters**:
- Date range (created_at)
- Config (select)
- Pipeline (select)
- Status (select)

**Row Actions**:
- View (opens drawer)
- Cancel (if running)
- Retry (if failed)

**Create Record UX**:
- "Start Reconciliation" button → Modal
- Modal: Select config/pipeline, optional filters, auto-match option

**Edit Record UX**:
- Read-only (tasks are immutable)

**Related Objects**:
- Suggestions: Tab in drawer (table with accept/reject actions)
- Applied Matches: Tab in drawer

---

#### Financial Statements Table
**Key Columns**:
- Name
- Report Type (badge)
- Template Name
- Start Date
- End Date
- Status (badge: draft/final/archived)
- Generated At
- Actions

**Default Sort**: Generated At (descending)

**Filters**:
- Report Type (select)
- Status (select)
- Date Range (start_date/end_date)

**Row Actions**:
- View (opens drawer)
- Finalize (if draft)
- Archive (if final)
- Export (dropdown: Excel, Markdown, HTML)
- Delete (if draft)

**Create Record UX**:
- "Generate Statement" button → Modal
- Modal: Select template, date range, options

**Edit Record UX**:
- Read-only (regenerate to create new)

**Related Objects**:
- Lines: Tab in drawer (hierarchical table)
- Comparisons: Tab in drawer (if generated with comparisons)
- Time Series: Tab in drawer (if generated)

---

### 5.2 Nested UI Patterns

#### Pattern 1: Transaction → Journal Entries (Expandable Rows)
**Use Case**: View journal entries for a transaction without leaving the table.

**Implementation**:
- Table row has expand icon
- Click expand → Shows nested table below row
- Nested table: Journal entry columns (Account, Debit, Credit, Description)
- Can edit journal entries inline (if transaction pending)
- Collapse to hide

**Alternative**: Drawer with tabs (if many journal entries or need more space)

---

#### Pattern 2: Reconciliation Detail → Matched Items (Tabs in Drawer)
**Use Case**: View reconciliation with matched bank transactions and journal entries.

**Implementation**:
- Click reconciliation → Opens drawer
- Drawer tabs:
  - **Overview**: Reconciliation details, totals, discrepancy
  - **Bank Transactions**: Table of matched bank transactions
  - **Journal Entries**: Table of matched journal entries
  - **History**: Audit trail

**Why Tabs**: Two separate related lists, need to see both but not simultaneously

---

#### Pattern 3: Reconciliation Task → Suggestions (Table in Drawer)
**Use Case**: Review and accept/reject reconciliation suggestions.

**Implementation**:
- Click task → Opens drawer
- Tab: "Suggestions"
- Table: Suggestion rows (Match Type, Confidence, Bank IDs, Journal IDs)
- Row actions: Accept, Reject, View Details
- Bulk actions: Accept Selected, Reject Selected
- View Details: Opens modal with match preview (shows bank + journal items side-by-side)

**Why Table in Drawer**: Many suggestions, need to review and act on multiple

---

#### Pattern 4: Financial Statement → Line Items (Hierarchical Table)
**Use Case**: Display financial statement with indented line items.

**Implementation**:
- Statement drawer → Tab: "Lines"
- Table with indentation (padding-left based on indent_level)
- Parent rows: Expandable (if has children)
- Bold rows: If is_bold=true
- Columns: Line #, Label (indented), Debit, Credit, Balance
- If comparisons: Additional columns (Current, Comparison, Change, % Change)

**Why Hierarchical**: Natural structure of financial statements

---

#### Pattern 5: Account Tree → Account Detail (Side Panel)
**Use Case**: Navigate account tree and view account details.

**Implementation**:
- Left panel: Account tree (expandable)
- Right panel: Account detail (when selected)
- Detail panel tabs:
  - Overview
  - Activity (journal entries)
  - Balance History (chart)

**Why Side Panel**: Need to see tree context while viewing details

---

#### Pattern 6: Bank Transaction → Suggestions (Cards in Drawer)
**Use Case**: Review ML-generated suggestions for a bank transaction.

**Implementation**:
- Click bank transaction → Opens drawer
- Tab: "Suggestions"
- If suggestions exist: Cards (one per suggestion)
  - Card shows: Confidence score (progress bar), Match type, Proposed transaction/journal entries, Historical matches
  - Actions: Accept, Reject, View Details
- If no suggestions: Empty state, "Get Suggestions" button

**Why Cards**: Each suggestion is a distinct proposal, cards make comparison easier

---

## 6. Open Questions / Assumptions

### Assumptions Made

1. **User Roles**: Assumed standard roles (Superuser, Admin, Regular User) based on `ScopedQuerysetMixin` logic. Actual role system may be more complex.

2. **Permissions**: Assumed users can create/edit/delete within their scope. Actual permissions may be more granular (e.g., read-only financial statements).

3. **Multi-tenancy**: Assumed tenant switching via subdomain or header. UI should support tenant selector if user has access to multiple companies.

4. **Real-time Updates**: Assumed polling for long-running tasks (reconciliation, statement generation). WebSockets could be used instead.

5. **Mobile Support**: Assumed desktop-first design. Mobile responsiveness should be considered for key workflows.

6. **Export Formats**: Assumed Excel, Markdown, HTML exports. PDF export may be desired but not documented in APIs.

7. **Audit Trail**: Assumed audit trail exists (created_by, updated_by, created_at, updated_at). UI should show history where relevant.

8. **Bulk Operations**: Assumed bulk create/update/delete for efficiency. APIs support bulk operations via `generic_bulk_*` functions.

9. **Embedding/ML**: Assumed embedding service is external. UI should show embedding health/status.

10. **Date Handling**: Assumed all dates in user's timezone. Backend may store UTC.

### Open Questions

1. **User Onboarding**: What is the onboarding flow for new users? First-time setup wizard?

2. **Data Import**: What formats are supported for bulk import? CSV, Excel, OFX only?

3. **Notifications**: Should users receive notifications for reconciliation completions, statement generations? Email or in-app?

4. **Collaboration**: Can multiple users work on the same reconciliation task simultaneously? Locking mechanism?

5. **Versioning**: Are financial statements versioned? Can users revert to previous versions?

6. **Custom Fields**: Can users add custom fields to transactions, accounts, etc.?

7. **Workflow Approval**: Is there an approval workflow for transactions, reconciliations, statements?

8. **Reporting**: Are there custom report builders beyond financial statements?

9. **Integration**: What third-party integrations exist? Bank APIs, accounting software?

10. **Performance**: What are expected data volumes? Should pagination be infinite scroll or page-based?

11. **Accessibility**: What accessibility standards should be followed? WCAG 2.1 AA?

12. **Internationalization**: Is multi-language support required?

13. **Dark Mode**: Is dark mode a requirement?

14. **Offline Support**: Should the app work offline? PWA capabilities?

15. **Analytics**: Should user actions be tracked for analytics? What events?

---

## Summary

This documentation provides a comprehensive UI/UX schema for the NORD accounting system. The design emphasizes:

- **Modal-first** for quick add/edit actions
- **Drawer-based** detail views to preserve context
- **Table-centric** design for data-heavy pages
- **Nested UI** (expandable rows, tabs, side panels) for related data
- **Progressive disclosure** to reduce cognitive load
- **Clear feedback** via toasts, loading states, and error messages

The component library is framework-agnostic but React-oriented, with clear prop interfaces and usage patterns. Each page schema includes API dependencies, user flows, and edge cases.

This documentation should enable another LLM (or developer) to implement a consistent, user-friendly React frontend that integrates seamlessly with the existing Django REST API backend.

