export type ReportType =
  | "balance_sheet"
  | "income_statement"
  | "cash_flow"
  | "trial_balance"
  | "general_ledger"
  | "custom"

export type LineType = "header" | "account" | "subtotal" | "total" | "spacer"

export type CalculationMethod =
  | "ending_balance"
  | "opening_balance"
  | "net_movement"
  | "debit_total"
  | "credit_total"
  | "change_in_balance"
  | "rollup_children"
  | "formula"
  | "manual_input"

export type SignPolicy = "natural" | "invert" | "absolute"

export type Scale = "none" | "K" | "M" | "B"

export interface LineTemplate {
  id?: number
  line_number: number
  label: string
  line_type: LineType
  account?: number | null
  account_code_prefix?: string | null
  account_path_contains?: string | null
  account_ids?: number[]
  include_descendants?: boolean
  calculation_method?: CalculationMethod | null
  sign_policy?: SignPolicy
  formula?: string | null
  manual_value?: string | null
  indent_level?: number
  is_bold?: boolean
  show_negative_in_parentheses?: boolean
  scale?: Scale
  decimal_places?: number
  parent_line?: number | null
}

export interface StatementTemplate {
  id?: number
  name: string
  report_type: ReportType
  description?: string | null
  is_active?: boolean
  is_default?: boolean
  show_zero_balances?: boolean
  show_account_codes?: boolean
  show_percentages?: boolean
  group_by_cost_center?: boolean
  line_templates?: LineTemplate[]
  created_at?: string
  updated_at?: string
}

export interface GenerateStatementInput {
  template_id: number
  start_date: string
  end_date: string
  as_of_date?: string | null
  currency_id?: number | null
  include_pending?: boolean
  notes?: string | null
  persist?: boolean
}

export interface PreviewLine {
  line_number: number
  label: string
  line_type: LineType
  balance: number | string
  debit_amount?: number | string
  credit_amount?: number | string
  indent_level?: number
  is_bold?: boolean
  account_ids?: number[]
}

export interface PreviewStatementResponse {
  name: string
  report_type: ReportType
  start_date: string
  end_date: string
  lines: PreviewLine[]
  formatted?: {
    markdown?: string
    html?: string
  }
}

export interface GeneratedStatement {
  id: number
  name: string
  report_type: ReportType
  start_date: string
  end_date: string
  template: number
  status: "draft" | "final" | "archived"
  formatted?: {
    markdown?: string
    html?: string
  }
}
