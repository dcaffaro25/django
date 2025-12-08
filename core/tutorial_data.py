"""
Tutorial data for NORD Accounting System.

This module contains the complete tutorial content organized as steps
for both end-users (non-programmers) and developers.
"""

TUTORIAL_STEPS = [
    # ========== USER TUTORIAL ==========
    {
        "audience": "user",
        "id": "getting-started",
        "title": "Getting Started with NORD",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="getting-started">
          <h2>Welcome to NORD Accounting System</h2>
          <p>NORD is a comprehensive multi-tenant accounting and financial management system designed to help you manage your complete accounting lifecycle.</p>
          
          <h3>What You Can Do</h3>
          <ul>
            <li><strong>Manage Transactions</strong> - Create and track all your accounting transactions with double-entry bookkeeping</li>
            <li><strong>Bank Reconciliation</strong> - Automatically match bank transactions with your journal entries using AI-powered matching</li>
            <li><strong>Financial Statements</strong> - Generate Balance Sheets, Income Statements, and Cash Flow statements</li>
            <li><strong>Chart of Accounts</strong> - Organize your accounts in a hierarchical structure</li>
            <li><strong>Multi-Entity Management</strong> - Manage multiple entities within your organization</li>
          </ul>
          
          <h3>First Steps</h3>
          <ol>
            <li>Log in using your username and password</li>
            <li>If you have access to multiple companies, select your company from the tenant dropdown in the sidebar</li>
            <li>Start by exploring the <strong>Transactions</strong> section to see your existing transactions</li>
          </ol>
          
          <p><strong>Tip:</strong> The sidebar on the left contains all main sections. Click any item to navigate to that section.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "navigation-overview",
        "title": "Understanding the Navigation",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="navigation-overview">
          <h2>How to Navigate NORD</h2>
          <p>The application is organized into <strong>5 main sections</strong> accessible from the left sidebar:</p>
          
          <h3>1. Accounting (Core)</h3>
          <ul>
            <li><strong>Transactions</strong> - View and manage all accounting transactions</li>
            <li><strong>Journal Entries</strong> - See individual journal entries that make up transactions</li>
            <li><strong>Chart of Accounts</strong> - Manage your account hierarchy</li>
          </ul>
          
          <h3>2. Banking & Reconciliation</h3>
          <ul>
            <li><strong>Bank Transactions</strong> - View imported bank statement transactions</li>
            <li><strong>Reconciliation Dashboard</strong> - Overview of unreconciled items</li>
            <li><strong>Reconciliation Tasks</strong> - Run and monitor automated reconciliation</li>
            <li><strong>Reconciliation Configs</strong> - Configure matching rules</li>
          </ul>
          
          <h3>3. Financial Statements</h3>
          <ul>
            <li><strong>Statements</strong> - Generate and view financial statements</li>
            <li><strong>Templates</strong> - Create and manage statement templates</li>
          </ul>
          
          <h3>4. Other Sections</h3>
          <ul>
            <li><strong>Billing</strong> - Manage business partners, products, and contracts</li>
            <li><strong>HR</strong> - Employee management, time tracking, and payroll</li>
            <li><strong>Settings</strong> - System configuration and rules</li>
          </ul>
          
          <p><strong>Tip:</strong> Use the breadcrumbs at the top of each page to see where you are and navigate back.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "transactions-basics",
        "title": "Working with Transactions",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="transactions-basics">
          <h2>Creating and Managing Transactions</h2>
          <p>Transactions are the foundation of your accounting system. Each transaction contains one or more journal entries that must balance (debits = credits).</p>
          
          <h3>Creating a New Transaction</h3>
          <ol>
            <li>Go to the <strong>Transactions</strong> section from the left sidebar</li>
            <li>Click the <strong>"Create Transaction"</strong> button at the top right</li>
            <li>Fill in the basic information:
              <ul>
                <li><strong>Date</strong> - The transaction date</li>
                <li><strong>Entity</strong> - Select which entity this transaction belongs to</li>
                <li><strong>Description</strong> - A clear description of the transaction</li>
                <li><strong>Currency</strong> - The currency for this transaction</li>
              </ul>
            </li>
            <li>After saving, you'll see a drawer open where you can add <strong>Journal Entries</strong></li>
            <li>For each journal entry, specify:
              <ul>
                <li><strong>Account</strong> - The account to debit or credit</li>
                <li><strong>Debit</strong> or <strong>Credit</strong> amount</li>
                <li><strong>Description</strong> - Entry description</li>
                <li><strong>Cost Center</strong> (optional) - For cost tracking</li>
              </ul>
            </li>
            <li>The system will show you if the transaction is balanced. If not, you can click <strong>"Create Balancing Entry"</strong> to automatically balance it</li>
          </ol>
          
          <h3>Posting Transactions</h3>
          <p>Transactions start in <strong>"Pending"</strong> status. To finalize them:</p>
          <ol>
            <li>Find the transaction in the table</li>
            <li>Click the row action menu (three dots) → <strong>"Post"</strong></li>
            <li>Once posted, the transaction affects your account balances</li>
          </ol>
          
          <p><strong>Tip:</strong> You can expand any transaction row to see its journal entries without leaving the table. Look for the expand icon on the left side of each row.</p>
          <p><strong>Common Pitfall:</strong> Make sure your transaction balances before posting. The system will warn you if debits don't equal credits.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "bank-reconciliation-overview",
        "title": "Bank Reconciliation Overview",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="bank-reconciliation-overview">
          <h2>Understanding Bank Reconciliation</h2>
          <p>Bank reconciliation matches your bank statement transactions with your accounting journal entries. NORD uses AI-powered matching to suggest matches automatically.</p>
          
          <h3>The Reconciliation Process</h3>
          <ol>
            <li><strong>Import Bank Transactions</strong> - Upload OFX files from your bank</li>
            <li><strong>View Unreconciled Items</strong> - See which bank transactions and journal entries need matching</li>
            <li><strong>Run Automated Reconciliation</strong> - Let the system suggest matches</li>
            <li><strong>Review and Accept</strong> - Review suggestions and accept or reject them</li>
            <li><strong>Manual Matching</strong> - For items that need manual attention</li>
          </ol>
          
          <h3>Key Pages</h3>
          <ul>
            <li><strong>Bank Transactions</strong> - Shows all imported bank transactions with reconciliation status</li>
            <li><strong>Reconciliation Dashboard</strong> - Overview showing counts and totals of unreconciled items</li>
            <li><strong>Reconciliation Tasks</strong> - Where you start automated reconciliation runs</li>
          </ul>
          
          <p><strong>Tip:</strong> Start with the Reconciliation Dashboard to get an overview of what needs attention. The dashboard shows metrics and recent unreconciled items.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "importing-bank-transactions",
        "title": "Importing Bank Transactions",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="importing-bank-transactions">
          <h2>How to Import Bank Transactions</h2>
          <p>Before you can reconcile, you need to import your bank statement transactions.</p>
          
          <h3>Step-by-Step Import</h3>
          <ol>
            <li>Go to <strong>Banking & Reconciliation → Bank Transactions</strong> from the sidebar</li>
            <li>Click the <strong>"Import OFX"</strong> button at the top</li>
            <li>In the modal that opens:
              <ul>
                <li>Select the <strong>Bank Account</strong> you're importing for</li>
                <li>Choose the <strong>OFX file</strong> from your computer (download from your bank's website)</li>
                <li>Click <strong>"Upload"</strong></li>
              </ul>
            </li>
            <li>The system will parse the file and show you a preview of transactions to import</li>
            <li>Review the preview and click <strong>"Finalize Import"</strong> to complete the import</li>
          </ol>
          
          <h3>After Import</h3>
          <ul>
            <li>Imported transactions appear in the Bank Transactions table</li>
            <li>They start as <strong>"Unreconciled"</strong> until matched with journal entries</li>
            <li>Use the <strong>"Unreconciled"</strong> tab to filter and see only unmatched transactions</li>
          </ul>
          
          <p><strong>Tip:</strong> Most banks allow you to download OFX files from their online banking portal. Look for "Export" or "Download" options in your bank's transaction history.</p>
          <p><strong>Common Pitfall:</strong> Make sure you select the correct bank account when importing. Each bank account should be linked to a specific account in your Chart of Accounts.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "running-reconciliation",
        "title": "Running Automated Reconciliation",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="running-reconciliation">
          <h2>Running Automated Reconciliation</h2>
          <p>NORD can automatically suggest matches between bank transactions and journal entries using AI-powered matching algorithms.</p>
          
          <h3>Starting a Reconciliation Task</h3>
          <ol>
            <li>Go to <strong>Banking & Reconciliation → Reconciliation Tasks</strong></li>
            <li>Click <strong>"Start Reconciliation"</strong> button</li>
            <li>In the modal:
              <ul>
                <li>Choose either a <strong>Config</strong> or <strong>Pipeline</strong>:
                  <ul>
                    <li><strong>Config</strong> - A single set of matching rules</li>
                    <li><strong>Pipeline</strong> - Multiple configs run in sequence (more powerful)</li>
                  </ul>
                </li>
                <li>(Optional) Select specific bank transactions to match</li>
                <li>(Optional) Select specific journal entries to match</li>
                <li>Check <strong>"Auto-apply perfect matches (100%)"</strong> if you want perfect matches applied automatically</li>
              </ul>
            </li>
            <li>Click <strong>"Start"</strong> to begin the task</li>
          </ol>
          
          <h3>Monitoring the Task</h3>
          <ul>
            <li>The task appears in the table with status: <strong>Queued</strong> → <strong>Running</strong> → <strong>Completed</strong></li>
            <li>Click on a running task to see progress details</li>
            <li>For completed tasks, click to view results and suggestions</li>
          </ul>
          
          <h3>Reviewing Suggestions</h3>
          <ol>
            <li>Open a completed task</li>
            <li>Go to the <strong>"Suggestions"</strong> tab</li>
            <li>Review each suggestion showing:
              <ul>
                <li><strong>Confidence Score</strong> - How confident the match is (0-100%)</li>
                <li><strong>Matched Items</strong> - Which bank transactions and journal entries are matched</li>
                <li><strong>Amount Discrepancy</strong> - Any difference in amounts</li>
              </ul>
            </li>
            <li>Click <strong>"Accept"</strong> to create the reconciliation, or <strong>"Reject"</strong> to dismiss it</li>
            <li>You can select multiple suggestions and use bulk actions</li>
          </ol>
          
          <p><strong>Tip:</strong> Start with a Pipeline if you have one configured. Pipelines run multiple matching strategies in sequence, often finding more matches than a single config.</p>
          <p><strong>Common Pitfall:</strong> Don't accept suggestions with low confidence scores (below 70%) without reviewing them carefully. Check the matched items to ensure they make sense.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "manual-reconciliation",
        "title": "Manual Reconciliation",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="manual-reconciliation">
          <h2>Manual Reconciliation</h2>
          <p>Sometimes you need to manually match bank transactions with journal entries, especially for complex cases or when automated matching doesn't find a match.</p>
          
          <h3>Manual Matching from Bank Transactions</h3>
          <ol>
            <li>Go to <strong>Bank Transactions</strong> and find an unreconciled transaction</li>
            <li>Click the row action menu → <strong>"Match Manually"</strong></li>
            <li>In the drawer that opens:
              <ul>
                <li>You'll see the bank transaction details</li>
                <li>Below, you can search and select journal entries to match</li>
                <li>The system shows the balance/discrepancy as you select items</li>
              </ul>
            </li>
            <li>Select the journal entries that correspond to this bank transaction</li>
            <li>Review the total - it should match the bank transaction amount</li>
            <li>Click <strong>"Create Reconciliation"</strong> to finalize</li>
          </ol>
          
          <h3>Getting Suggestions for a Single Transaction</h3>
          <ol>
            <li>Select one or more bank transactions in the table</li>
            <li>Click <strong>"Get Suggestions"</strong> button</li>
            <li>A drawer opens showing AI-generated suggestions for those specific transactions</li>
            <li>Review each suggestion card showing confidence, matched items, and proposed transaction</li>
            <li>Click <strong>"Accept"</strong> on a suggestion to create the reconciliation</li>
          </ol>
          
          <p><strong>Tip:</strong> Use "Get Suggestions" before manual matching - it's faster and often finds good matches. Only use manual matching when suggestions aren't available or don't match correctly.</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "chart-of-accounts",
        "title": "Managing Your Chart of Accounts",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="chart-of-accounts">
          <h2>Chart of Accounts Management</h2>
          <p>Your Chart of Accounts is the foundation of your accounting system. It organizes all accounts in a hierarchical structure.</p>
          
          <h3>Viewing Accounts</h3>
          <ol>
            <li>Go to <strong>Accounting → Chart of Accounts</strong></li>
            <li>You can toggle between <strong>"Tree View"</strong> and <strong>"List View"</strong>:
              <ul>
                <li><strong>Tree View</strong> - Shows the hierarchical structure with expandable nodes</li>
                <li><strong>List View</strong> - Shows a flat table with parent relationships</li>
              </ul>
            </li>
            <li>Click any account to see its details in a drawer</li>
          </ol>
          
          <h3>Creating a New Account</h3>
          <ol>
            <li>Click <strong>"Create Account"</strong> button</li>
            <li>Fill in the form:
              <ul>
                <li><strong>Account Code</strong> - Unique identifier (e.g., "1000", "4000")</li>
                <li><strong>Name</strong> - Account name (e.g., "Cash", "Revenue")</li>
                <li><strong>Parent Account</strong> - Select a parent to create a hierarchy</li>
                <li><strong>Account Direction</strong> - 1 for debit normal (assets), -1 for credit normal (liabilities, equity, revenue)</li>
                <li><strong>Currency</strong> - The currency for this account</li>
                <li><strong>Bank Account</strong> (optional) - Link to a bank account if applicable</li>
              </ul>
            </li>
            <li>Click <strong>"Save"</strong></li>
          </ol>
          
          <h3>Viewing Account Activity</h3>
          <ol>
            <li>Click on any account to open its detail drawer</li>
            <li>In the <strong>"Activity"</strong> tab, you'll see all journal entries for this account</li>
            <li>Use filters to see activity for specific date ranges</li>
            <li>The <strong>"Balance History"</strong> tab shows how the balance changed over time</li>
          </ol>
          
          <p><strong>Tip:</strong> Organize your accounts hierarchically. For example, "Assets" as a parent, with "Current Assets" and "Fixed Assets" as children, and specific accounts under those.</p>
          <p><strong>Common Pitfall:</strong> Make sure to set the correct Account Direction. Assets and Expenses are debit normal (1), while Liabilities, Equity, and Revenue are credit normal (-1).</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "financial-statements",
        "title": "Generating Financial Statements",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="financial-statements">
          <h2>Generating Financial Statements</h2>
          <p>NORD can generate Balance Sheets, Income Statements, and Cash Flow statements from your accounting data.</p>
          
          <h3>Before You Start</h3>
          <p>You need a <strong>Financial Statement Template</strong> configured. Templates define the structure and line items for each type of statement.</p>
          
          <h3>Generating a Statement</h3>
          <ol>
            <li>Go to <strong>Financial Statements → Statements</strong></li>
            <li>Click <strong>"Generate Statement"</strong> button</li>
            <li>In the modal:
              <ul>
                <li>Select a <strong>Template</strong> (filtered by report type)</li>
                <li>Set the <strong>Start Date</strong> and <strong>End Date</strong> for the period</li>
                <li>For Balance Sheets, set the <strong>As of Date</strong></li>
                <li>Check <strong>"Include Pending"</strong> if you want to include unposted transactions</li>
                <li>Set the <strong>Status</strong> (Draft or Final)</li>
              </ul>
            </li>
            <li>Click <strong>"Generate"</strong> and wait for processing</li>
            <li>Once complete, the statement appears in the table</li>
          </ol>
          
          <h3>Viewing a Statement</h3>
          <ol>
            <li>Click on any statement in the table</li>
            <li>A drawer opens with tabs:
              <ul>
                <li><strong>Overview</strong> - Statement metadata and totals</li>
                <li><strong>Lines</strong> - The actual statement with line items (hierarchically indented)</li>
                <li><strong>Export</strong> - Options to export to Excel, Markdown, or HTML</li>
              </ul>
            </li>
          </ol>
          
          <h3>Comparing Periods</h3>
          <ol>
            <li>In a statement drawer, click <strong>"Compare Periods"</strong></li>
            <li>Select comparison types (Previous Period, Previous Year, YTD, etc.)</li>
            <li>The statement will show additional columns with comparisons and percentage changes</li>
          </ol>
          
          <p><strong>Tip:</strong> Start with Draft status, review the statement, then Finalize it when you're satisfied. Finalized statements can be archived but not edited.</p>
          <p><strong>Common Pitfall:</strong> Make sure your date range matches the period you want to report on. For Income Statements, use the full period (e.g., Jan 1 - Dec 31 for annual).</p>
        </div>
        """
    },
    {
        "audience": "user",
        "id": "filtering-and-search",
        "title": "Filtering and Searching",
        "html": """
        <div class="wizard-step" data-audience="user" data-step-id="filtering-and-search">
          <h2>Filtering and Searching Data</h2>
          <p>Most pages in NORD have powerful filtering and search capabilities to help you find exactly what you need.</p>
          
          <h3>Using Filters</h3>
          <ol>
            <li>Look for the <strong>Filter Bar</strong> above most tables</li>
            <li>Common filters include:
              <ul>
                <li><strong>Date Range</strong> - Filter by transaction date, creation date, etc.</li>
                <li><strong>Entity</strong> - Filter by specific entities (multiselect)</li>
                <li><strong>Status</strong> - Filter by status (Pending, Posted, etc.)</li>
                <li><strong>Amount Range</strong> - Filter by minimum/maximum amounts</li>
                <li><strong>Search</strong> - Text search across descriptions, names, etc.</li>
              </ul>
            </li>
            <li>Active filters appear as <strong>chips</strong> below the filter bar</li>
            <li>Click the X on a chip to remove that filter, or <strong>"Clear All"</strong> to remove all</li>
          </ol>
          
          <h3>Using Tabs</h3>
          <p>Many pages use tabs to show different views:</p>
          <ul>
            <li><strong>Bank Transactions</strong> - "All", "Unreconciled", "Reconciled"</li>
            <li><strong>Reconciliation Tasks</strong> - "All", "Queued", "Running", "Completed", "Failed"</li>
            <li><strong>Financial Statements</strong> - "Templates", "Generated", "Comparisons"</li>
          </ul>
          
          <h3>Table Features</h3>
          <ul>
            <li><strong>Sorting</strong> - Click column headers to sort</li>
            <li><strong>Pagination</strong> - Use page numbers or next/previous buttons</li>
            <li><strong>Column Visibility</strong> - Some tables allow you to show/hide columns</li>
            <li><strong>Row Selection</strong> - Checkboxes to select rows for bulk actions</li>
          </ul>
          
          <p><strong>Tip:</strong> Combine multiple filters to narrow down results. For example, filter by date range AND entity AND status to find specific transactions.</p>
          <p><strong>Common Pitfall:</strong> Remember to clear filters when switching between different views, or you might wonder why you're not seeing expected data.</p>
        </div>
        """
    },
    
    # ========== DEVELOPER TUTORIAL ==========
    {
        "audience": "developer",
        "id": "api-authentication",
        "title": "API Authentication",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-authentication">
          <h2>API Authentication</h2>
          <p>NORD uses <strong>Django REST Framework Token Authentication</strong> (not JWT). All authenticated requests require a token in the Authorization header.</p>
          
          <h3>Login Endpoint</h3>
          <pre><code>POST /login/
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "password123"
}</code></pre>
          
          <h3>Response</h3>
          <pre><code>{
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
}</code></pre>
          
          <h3>Authenticated Requests</h3>
          <p>Include the token in all subsequent requests:</p>
          <pre><code>Authorization: Token {token}</code></pre>
          
          <p><strong>Important:</strong> Use <code>Token</code> (not <code>Bearer</code>) in the Authorization header.</p>
          
          <h3>Multi-Tenancy</h3>
          <p>Tenants are identified via URL path prefix:</p>
          <pre><code>GET /{tenant_subdomain}/api/transactions/</code></pre>
          <p>Example: <code>GET /acme-corp/api/transactions/</code></p>
          
          <p>The <code>TenantMiddleware</code> automatically extracts the tenant from the URL and scopes all queries to that tenant.</p>
        </div>
        """
    },
    {
        "audience": "developer",
        "id": "api-transactions",
        "title": "Transactions API",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-transactions">
          <h2>Transactions API</h2>
          <p>Transactions are the core of the accounting system. Each transaction contains one or more journal entries.</p>
          
          <h3>List Transactions</h3>
          <pre><code>GET /{tenant}/api/transactions/
Query Parameters:
  - date_from: Filter from date
  - date_to: Filter to date
  - entity: Filter by entity ID
  - status: Filter by status (pending, posted, cancelled)
  - min_amount, max_amount: Amount range
  - search: Text search in description
  - page, page_size: Pagination</code></pre>
          
          <h3>Create Transaction</h3>
          <pre><code>POST /{tenant}/api/transactions/
Content-Type: application/json

{
  "date": "2025-01-15",
  "entity": 1,
  "description": "Payment to vendor",
  "currency": 1,
  "status": "pending"
}</code></pre>
          
          <h3>Post Transaction</h3>
          <pre><code>POST /{tenant}/api/transactions/{id}/post/</code></pre>
          <p>Moves transaction from "pending" to "posted" status. Once posted, it affects account balances.</p>
          
          <h3>Create Balancing Entry</h3>
          <pre><code>POST /{tenant}/api/transactions/{id}/create_balancing_entry/</code></pre>
          <p>Automatically creates a journal entry to balance the transaction if debits ≠ credits.</p>
          
          <h3>Related Endpoints</h3>
          <ul>
            <li><code>PUT /{tenant}/api/transactions/{id}/</code> - Update transaction</li>
            <li><code>DELETE /{tenant}/api/transactions/{id}/</code> - Delete transaction</li>
            <li><code>POST /{tenant}/api/transactions/{id}/unpost/</code> - Unpost transaction</li>
            <li><code>POST /{tenant}/api/transactions/{id}/cancel/</code> - Cancel transaction</li>
          </ul>
          
          <p><strong>User Workflow Link:</strong> When a user creates a transaction in the UI (see "Working with Transactions" step), the frontend calls <code>POST /{tenant}/api/transactions/</code> and then allows adding journal entries.</p>
        </div>
        """
    },
    {
        "audience": "developer",
        "id": "api-bank-reconciliation",
        "title": "Bank Reconciliation API",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-bank-reconciliation">
          <h2>Bank Reconciliation API</h2>
          <p>The reconciliation API handles matching bank transactions with journal entries using AI-powered algorithms.</p>
          
          <h3>Import OFX File</h3>
          <pre><code>POST /{tenant}/api/bank_transactions/import_ofx/
Content-Type: multipart/form-data

{
  "bank_account": 1,
  "ofx_file": &lt;file&gt;
}</code></pre>
          
          <h3>Get Suggestions</h3>
          <pre><code>POST /{tenant}/api/bank_transactions/suggest_matches/
Content-Type: application/json

{
  "bank_transaction_ids": [1, 2, 3],
  "use_existing_book": true,
  "create_new": true,
  "config_id": 1  // optional
}</code></pre>
          
          <h3>Start Reconciliation Task</h3>
          <pre><code>POST /{tenant}/api/reconciliation-tasks/start/
Content-Type: application/json

{
  "config_id": 1,  // or "pipeline_id": 1
  "bank_ids": [1, 2],  // optional
  "book_ids": [10, 11],  // optional
  "auto_match_100": true  // optional
}</code></pre>
          
          <h3>Get Task Status</h3>
          <pre><code>GET /{tenant}/api/reconciliation-tasks/{id}/status/</code></pre>
          
          <h3>Get Fresh Suggestions</h3>
          <pre><code>GET /{tenant}/api/reconciliation-tasks/{id}/fresh-suggestions/?limit=50</code></pre>
          
          <h3>Finalize Matches</h3>
          <pre><code>POST /{tenant}/api/bank_transactions/finalize_reconciliation_matches/
Content-Type: application/json

{
  "matches": [
    {
      "bank_transaction_ids": [1],
      "journal_entry_ids": [10, 11],
      "reference": "Invoice #123",
      "notes": "Monthly payment"
    }
  ]
}</code></pre>
          
          <h3>Reconciliation Dashboard</h3>
          <pre><code>GET /{tenant}/api/reconciliation-dashboard/</code></pre>
          <p>Returns metrics about unreconciled items:</p>
          <pre><code>{
  "bank_transactions": {
    "overall": {"count": 50, "total": 15000.00},
    "daily": [...]
  },
  "journal_entries": {
    "overall": {"count": 30, "total": 12000.00},
    "daily": [...]
  }
}</code></pre>
          
          <p><strong>User Workflow Link:</strong> When a user runs automated reconciliation (see "Running Automated Reconciliation" step), the frontend calls <code>POST /{tenant}/api/reconciliation-tasks/start/</code> and polls <code>GET /{tenant}/api/reconciliation-tasks/{id}/status/</code> for updates.</p>
        </div>
        """
    },
    {
        "audience": "developer",
        "id": "api-financial-statements",
        "title": "Financial Statements API",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-financial-statements">
          <h2>Financial Statements API</h2>
          <p>Generate financial statements from templates and accounting data.</p>
          
          <h3>List Statements</h3>
          <pre><code>GET /{tenant}/api/financial-statements/
Query Parameters:
  - report_type: balance_sheet, income_statement, cash_flow
  - status: draft, final, archived
  - start_date, end_date: Date range</code></pre>
          
          <h3>Generate Statement</h3>
          <pre><code>POST /{tenant}/api/financial-statements/
Content-Type: application/json

{
  "template_id": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "as_of_date": "2025-03-31",  // for balance sheet
  "include_pending": true,
  "status": "draft"
}</code></pre>
          
          <h3>Generate with Comparisons</h3>
          <pre><code>POST /{tenant}/api/financial-statements/with_comparisons/?preview=true
Content-Type: application/json

{
  "template_id": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_period", "previous_year"],
  "dimension": "month",
  "include_pending": true
}</code></pre>
          
          <h3>Generate Time Series</h3>
          <pre><code>POST /{tenant}/api/financial-statements/time_series/?preview=true&include_metadata=true
Content-Type: application/json

{
  "template_id": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimension": "month",  // day, week, month, quarter, semester, year
  "line_numbers": [1, 5, 10],  // optional: specific lines
  "include_pending": true
}</code></pre>
          
          <h3>Export Statement</h3>
          <pre><code>GET /{tenant}/api/financial-statements/{id}/export_excel/</code></pre>
          
          <h3>Template Management</h3>
          <ul>
            <li><code>GET /{tenant}/api/financial-statement-templates/</code> - List templates</li>
            <li><code>POST /{tenant}/api/financial-statement-templates/</code> - Create template</li>
            <li><code>PUT /{tenant}/api/financial-statement-templates/{id}/</code> - Update template</li>
          </ul>
          
          <p><strong>User Workflow Link:</strong> When a user generates a statement (see "Generating Financial Statements" step), the frontend calls <code>POST /{tenant}/api/financial-statements/</code> and displays the result in a drawer.</p>
        </div>
        """
    },
    {
        "audience": "developer",
        "id": "api-common-patterns",
        "title": "Common API Patterns",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-common-patterns">
          <h2>Common API Patterns</h2>
          <p>Understanding these patterns will help you work with all NORD APIs.</p>
          
          <h3>Pagination</h3>
          <p>Most list endpoints support pagination:</p>
          <pre><code>GET /{tenant}/api/transactions/?page=1&page_size=50</code></pre>
          <p>Response format:</p>
          <pre><code>{
  "count": 100,
  "next": "http://api.example.com/api/transactions/?page=2",
  "previous": null,
  "results": [...]
}</code></pre>
          
          <h3>Filtering</h3>
          <p>Django Filter Backend supports various filter types:</p>
          <ul>
            <li><code>?field=value</code> - Exact match</li>
            <li><code>?field__gte=value</code> - Greater than or equal</li>
            <li><code>?field__lte=value</code> - Less than or equal</li>
            <li><code>?field__contains=value</code> - Contains (case-sensitive)</li>
            <li><code>?field__icontains=value</code> - Contains (case-insensitive)</li>
            <li><code>?search=term</code> - Search across multiple fields</li>
          </ul>
          
          <h3>Ordering</h3>
          <pre><code>GET /{tenant}/api/transactions/?ordering=date
GET /{tenant}/api/transactions/?ordering=-date  // descending
GET /{tenant}/api/transactions/?ordering=date,-amount  // multiple fields</code></pre>
          
          <h3>Error Responses</h3>
          <p>Standard error format:</p>
          <pre><code>{
  "detail": "Error message",
  "errors": {
    "field_name": ["Error message 1", "Error message 2"]
  }
}</code></pre>
          
          <h3>HTTP Status Codes</h3>
          <ul>
            <li><code>200 OK</code> - Success</li>
            <li><code>201 Created</code> - Resource created</li>
            <li><code>400 Bad Request</code> - Validation error</li>
            <li><code>401 Unauthorized</code> - Authentication required</li>
            <li><code>403 Forbidden</code> - Permission denied</li>
            <li><code>404 Not Found</code> - Resource not found</li>
            <li><code>500 Internal Server Error</code> - Server error</li>
          </ul>
          
          <h3>Multi-Tenancy</h3>
          <p>All tenant-aware endpoints automatically filter by:</p>
          <ul>
            <li>Current user's tenant (if not superuser)</li>
            <li>Selected tenant (if superuser)</li>
          </ul>
          <p>The tenant is extracted from the URL path: <code>/{tenant_subdomain}/api/...</code></p>
        </div>
        """
    },
    {
        "audience": "developer",
        "id": "api-accounts-journal",
        "title": "Accounts and Journal Entries API",
        "html": """
        <div class="wizard-step" data-audience="developer" data-step-id="api-accounts-journal">
          <h2>Accounts and Journal Entries API</h2>
          
          <h3>Accounts (Chart of Accounts)</h3>
          <pre><code>GET /{tenant}/api/accounts/
Query Parameters:
  - parent: Filter by parent account ID
  - entity: Filter by entity ID
  - is_active: Filter active/inactive accounts
  - search: Search in code or name</code></pre>
          
          <h3>Account Summary</h3>
          <pre><code>GET /{tenant}/api/account_summary/
Query Parameters:
  - company_id: Company ID
  - entity_id: Entity ID (optional)
  - min_depth: Minimum account depth
  - include_pending: Include unposted transactions
  - beginning_date, end_date: Date range</code></pre>
          
          <h3>Journal Entries</h3>
          <pre><code>GET /{tenant}/api/journal_entries/
Query Parameters:
  - date_from, date_to: Date range
  - account: Filter by account ID
  - transaction: Filter by transaction ID
  - cost_center: Filter by cost center ID
  - state: Filter by state (pending, posted)
  - is_reconciled: Filter reconciled/unreconciled
  - bank_designation_pending: Filter entries needing bank assignment</code></pre>
          
          <h3>Create Journal Entry</h3>
          <pre><code>POST /{tenant}/api/journal_entries/
Content-Type: application/json

{
  "transaction": 1,
  "account": 10,
  "debit": 1000.00,
  "credit": 0.00,
  "description": "Payment received",
  "cost_center": 1,  // optional
  "date": "2025-01-15"
}</code></pre>
          
          <h3>Unreconciled Journal Entries</h3>
          <pre><code>GET /{tenant}/api/journal_entries/?unreconciled=true</code></pre>
          
          <p><strong>User Workflow Link:</strong> When a user views the Chart of Accounts (see "Managing Your Chart of Accounts" step), the frontend calls <code>GET /{tenant}/api/accounts/</code> and displays the hierarchical structure.</p>
        </div>
        """
    },
]

def get_tutorial_steps(audience=None):
    """
    Get tutorial steps, optionally filtered by audience.
    
    Args:
        audience: 'user', 'developer', or None for all
        
    Returns:
        List of tutorial step dictionaries
    """
    if audience:
        return [step for step in TUTORIAL_STEPS if step['audience'] == audience]
    return TUTORIAL_STEPS

def get_tutorial_step(step_id):
    """
    Get a specific tutorial step by ID.
    
    Args:
        step_id: The step ID to retrieve
        
    Returns:
        Tutorial step dictionary or None if not found
    """
    for step in TUTORIAL_STEPS:
        if step['id'] == step_id:
            return step
    return None

