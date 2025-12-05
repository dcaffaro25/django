// Base types
export interface BaseModel {
  id: number
  created_at?: string
  updated_at?: string
  created_by?: number
  updated_by?: number
}

export interface Company extends BaseModel {
  name: string
}

export interface Entity extends BaseModel {
  name: string
  company: number
  parent?: number
  level?: number
  path?: string
  path_ids?: number[]
}

export interface Currency extends BaseModel {
  code: string
  name: string
  symbol: string
}

export interface Bank extends BaseModel {
  name: string
  bank_code: string
}

export interface BankAccount extends BaseModel {
  name: string
  company: number
  entity: number
  bank: number
  currency: number
  account_number?: string
  current_balance?: number
}

export interface Account extends BaseModel {
  account_code: string
  name: string
  description?: string
  company: number
  parent?: number
  parent_id?: number
  level?: number
  path?: string
  path_ids?: number[]
  account_direction: number
  balance: number
  balance_date: string
  currency: number
  bank_account?: number
  is_active: boolean
  current_balance?: number
}

export interface CostCenter extends BaseModel {
  name: string
  company: number
  entity?: number
  type: "cost" | "profit"
  current_balance?: number
}

export interface JournalEntry extends BaseModel {
  company: number
  transaction: number
  account: number
  cost_center?: number
  description: string
  debit_amount?: number
  credit_amount?: number
  state: "pending" | "posted" | "cancelled"
  date: string
  bank_designation_pending?: boolean
  has_designated_bank?: boolean
}

export interface Transaction extends BaseModel {
  date: string
  entity: number
  description: string
  amount: number
  currency: number
  state: "pending" | "posted" | "cancelled"
  balance?: number
  journal_entries?: JournalEntry[]
  journal_entries_count?: number
  journal_entries_summary?: string[]
  journal_entries_bank_accounts?: number[]
  reconciliation_status?: "pending" | "matched" | "mixed"
  bank_date?: string
}

export interface BankTransaction extends BaseModel {
  company: number
  bank_account: number
  entity?: number
  entity_name?: string
  date: string
  amount: number
  description: string
  currency: number
  status: string
  reconciliation_status?: "pending" | "matched" | "mixed"
}

export interface Reconciliation extends BaseModel {
  company: number
  bank_transactions: number[]
  journal_entries: number[]
  status: "pending" | "matched" | "approved" | "rejected"
  reference?: string
  notes?: string
  discrepancy?: number
}

export interface ReconciliationConfig extends BaseModel {
  name: string
  description?: string
  scope: "global" | "company" | "user" | "company_user"
  company?: number
  user?: number
  company_name?: string
  user_name?: string
  is_default?: boolean
  
  // Scoring weights (must sum to 1.0)
  weight_embedding?: number
  weight_amount?: number
  weight_currency?: number
  weight_date?: number
  
  // Tolerances
  amount_tolerance?: number
  group_span_days?: number
  avg_date_delta_days?: number
  
  // Group sizes
  max_group_size_bank?: number
  max_group_size_book?: number
  
  // Thresholds
  min_confidence?: number
  max_suggestions?: number
  max_alternatives_per_match?: number
  
  // Filters
  bank_filters?: Record<string, unknown>
  book_filters?: Record<string, unknown>
  
  // Advanced
  soft_time_limit?: number
  fee_accounts?: number[]
  duplicate_window?: number
  text_similarity?: number
}

export interface ReconciliationPipeline extends BaseModel {
  name: string
  description?: string
  scope: "global" | "company" | "user" | "company_user"
  company?: number
  user?: number
  auto_apply_score?: number
  max_suggestions?: number
  soft_time_limit?: number
  stages?: ReconciliationPipelineStage[]
}

export interface ReconciliationPipelineStage extends BaseModel {
  pipeline: number
  config: number
  order: number
  enabled: boolean
  overrides?: Record<string, unknown>
}

export interface ReconciliationTask extends BaseModel {
  task_id: string
  status: "queued" | "running" | "completed" | "failed" | "cancelled"
  tenant_id?: number
  config?: number
  config_name?: string
  pipeline?: number
  pipeline_name?: string
  parameters?: Record<string, unknown>
  result?: Record<string, unknown>
  error_message?: string
  bank_candidates?: number
  journal_candidates?: number
  suggestion_count?: number
  matched_bank_transactions?: number
  matched_journal_entries?: number
  auto_match_enabled?: boolean
  auto_match_applied?: number
  auto_match_skipped?: number
  duration_seconds?: number
  stats?: Record<string, unknown>
}

export interface ReconciliationSuggestion {
  id?: number
  match_type: "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many"
  confidence: number
  bank_transaction_ids: number[]
  journal_entry_ids: number[]
  discrepancy?: number
  use_existing_book?: boolean
  create_new?: boolean
  proposed_transaction?: Transaction
  proposed_journal_entries?: JournalEntry[]
  historical_matches_count?: number
}

export interface FinancialStatementTemplate extends BaseModel {
  name: string
  report_type: "balance_sheet" | "income_statement" | "cash_flow"
  description?: string
  is_active: boolean
  is_default?: boolean
  line_templates?: FinancialStatementLineTemplate[]
}

export interface FinancialStatementLineTemplate extends BaseModel {
  template: number
  line_number: number
  label: string
  line_type: "header" | "account" | "subtotal" | "total" | "spacer"
  account_mapping_type?: "single" | "ids" | "code_prefix" | "path_contains"
  account_id?: number
  account_ids?: number[]
  account_code_prefix?: string
  account_path_contains?: string
  calculation_type?: "sum" | "difference" | "balance" | "formula"
  formula?: string
  indent_level: number
  is_bold: boolean
  parent_line?: number
}

export interface FinancialStatement extends BaseModel {
  name: string
  template: number
  template_name?: string
  report_type: "balance_sheet" | "income_statement" | "cash_flow"
  start_date: string
  end_date: string
  as_of_date?: string
  status: "draft" | "final" | "archived"
  include_pending?: boolean
  lines?: FinancialStatementLine[]
}

export interface FinancialStatementLine extends BaseModel {
  statement: number
  line_number: number
  label: string
  debit?: number
  credit?: number
  balance: number
  indent_level: number
  is_bold: boolean
}

export interface ReconciliationDashboard {
  bank_transactions: {
    overall: {
      count: number
      total: number
    }
    daily: Array<{
      date: string
      count: number
      total: number
    }>
  }
  journal_entries: {
    overall: {
      count: number
      total: number
    }
    daily: Array<{
      date: string
      count: number
      total: number
    }>
  }
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Billing Module Types
export interface BusinessPartnerCategory extends BaseModel {
  name: string
  company: number
  description?: string
}

export interface BusinessPartner extends BaseModel {
  name: string
  company: number
  category?: number
  category_name?: string
  tax_id?: string
  email?: string
  phone?: string
  address?: string
  is_customer: boolean
  is_vendor: boolean
  is_supplier: boolean
}

export interface ProductServiceCategory extends BaseModel {
  name: string
  company: number
  description?: string
}

export interface ProductService extends BaseModel {
  name: string
  company: number
  category?: number
  category_name?: string
  description?: string
  unit_price?: number
  currency?: number
  is_product: boolean
  is_service: boolean
}

export interface Contract extends BaseModel {
  name: string
  company: number
  business_partner: number
  business_partner_name?: string
  start_date: string
  end_date?: string
  value?: number
  currency?: number
  status: "draft" | "active" | "expired" | "cancelled"
  terms?: string
}

// HR Module Types
export interface Employee extends BaseModel {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  employee_id?: string
  company: number
  position?: number
  position_name?: string
  hire_date?: string
  termination_date?: string
  status: "active" | "inactive" | "terminated"
  salary?: number
  currency?: number
}

export interface Position extends BaseModel {
  name: string
  company: number
  description?: string
  department?: string
  is_active: boolean
}

export interface TimeTracking extends BaseModel {
  employee: number
  employee_name?: string
  date: string
  hours: number
  description?: string
  project?: string
  status: "pending" | "approved" | "rejected"
  approved_by?: number
  approved_at?: string
}

export interface Payroll extends BaseModel {
  employee: number
  employee_name?: string
  period_start: string
  period_end: string
  gross_salary: number
  deductions: number
  net_salary: number
  currency: number
  status: "draft" | "final" | "paid"
  payment_date?: string
}

export interface RecurringAdjustment extends BaseModel {
  employee: number
  employee_name?: string
  name: string
  amount: number
  type: "addition" | "deduction"
  frequency: "monthly" | "biweekly" | "weekly"
  start_date: string
  end_date?: string
  is_active: boolean
}

// Settings/Configuration Types
export interface IntegrationRule extends BaseModel {
  name: string
  description?: string
  company: number
  trigger_event: string
  rule: string // JavaScript/Python code
  filter_conditions?: string // JSON string
  is_active: boolean
  priority?: number
}

export interface SubstitutionRule extends BaseModel {
  name: string
  description?: string
  company: number
  pattern: string
  replacement: string
  is_active: boolean
  priority?: number
}

export interface ApiError {
  message: string
  detail?: string
  errors?: Record<string, string[]>
}

