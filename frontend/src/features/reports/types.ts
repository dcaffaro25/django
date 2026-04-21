// TypeScript mirror of accounting.reports.services.document_schema (pydantic).
// Keep hand-kept in sync with the backend. Schema validation lives in
// ./schema.ts as zod.

export type ReportType =
  | "balance_sheet"
  | "income_statement"
  | "cash_flow"
  | "trial_balance"
  | "general_ledger"
  | "custom"

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

export type BlockType =
  | "section"
  | "header"
  | "line"
  | "subtotal"
  | "total"
  | "spacer"

export interface AccountsSelector {
  account_ids?: number[]
  code_prefix?: string | null
  path_contains?: string | null
  include_descendants?: boolean
}

export interface BlockDefaults {
  calculation_method?: CalculationMethod | null
  sign_policy?: SignPolicy | null
  scale?: Scale | null
  decimal_places?: number | null
  show_zero?: boolean | null
  bold?: boolean | null
}

interface BlockBase {
  id: string
  label?: string | null
  bold?: boolean | null
  indent?: number | null
  ai_explanation?: string | null
}

export interface HeaderBlock extends BlockBase {
  type: "header"
}

export interface SpacerBlock {
  type: "spacer"
  id: string
}

export interface LineBlock extends BlockBase {
  type: "line"
  accounts?: AccountsSelector | null
  calculation_method?: CalculationMethod | null
  sign_policy?: SignPolicy | null
  scale?: Scale | null
  decimal_places?: number | null
  manual_value?: string | null
  show_zero?: boolean | null
}

export interface SubtotalBlock extends BlockBase {
  type: "subtotal"
  formula?: string | null
  accounts?: AccountsSelector | null
  calculation_method?: CalculationMethod | null
  sign_policy?: SignPolicy | null
  scale?: Scale | null
  decimal_places?: number | null
}

export interface TotalBlock extends BlockBase {
  type: "total"
  formula?: string | null
  sign_policy?: SignPolicy | null
  scale?: Scale | null
  decimal_places?: number | null
}

export interface SectionBlock extends BlockBase {
  type: "section"
  defaults?: BlockDefaults | null
  children: Block[]
}

export type Block =
  | SectionBlock
  | HeaderBlock
  | LineBlock
  | SubtotalBlock
  | TotalBlock
  | SpacerBlock

export interface TemplateDocument {
  version?: number
  name: string
  report_type: ReportType
  description?: string | null
  defaults?: BlockDefaults
  blocks: Block[]
}

// --- Templates (persistence) ----------------------------------------------

export interface ReportTemplate {
  id?: number
  name: string
  report_type: ReportType
  description?: string | null
  document: TemplateDocument
  is_active?: boolean
  is_default?: boolean
  created_at?: string
  updated_at?: string
}

// --- Periods ---------------------------------------------------------------

export type PeriodKind =
  | "range"
  | "as_of"
  | "variance_abs"
  | "variance_pct"
  | "variance_pp"

export interface Period {
  id: string
  label: string
  type: PeriodKind
  start?: string  // for range
  end?: string    // for range
  date?: string   // for as_of
  base?: string   // for variance*
  compare?: string // for variance*
}

export interface CalculateRequest {
  template?: TemplateDocument
  template_id?: number
  periods: Period[]
  options?: {
    include_pending?: boolean
    currency_id?: number
    cost_center_id?: number
  }
}

export interface LineValue {
  id: string
  type: BlockType
  label?: string | null
  depth: number
  indent: number
  bold: boolean
  parent_id?: string | null
  values: Record<string, number | null>
  memory?: Record<string, unknown>
}

export interface ReportResult {
  periods: Period[]
  template: TemplateDocument
  lines: LineValue[]
  warnings?: Array<{ level: string; block_id?: string | null; message: string }>
}

// --- Instances (saved reports) --------------------------------------------

export interface ReportInstance {
  id: number
  template?: number | null
  template_name?: string
  template_snapshot?: TemplateDocument
  name: string
  report_type: ReportType
  periods: Period[]
  result: ReportResult
  status: "draft" | "final" | "archived"
  generated_by?: number | null
  generated_by_name?: string
  generated_at: string
  notes?: string | null
}

export interface ReportInstanceListItem {
  id: number
  template?: number | null
  template_name?: string
  name: string
  report_type: ReportType
  status: "draft" | "final" | "archived"
  generated_by?: number | null
  generated_by_name?: string
  generated_at: string
  notes?: string | null
}

// --- Save request ----------------------------------------------------------

export interface SaveRequest {
  template?: TemplateDocument
  template_id?: number
  periods: Period[]
  options?: CalculateRequest["options"]
  result?: ReportResult
  name: string
  status?: "draft" | "final" | "archived"
  notes?: string | null
}
