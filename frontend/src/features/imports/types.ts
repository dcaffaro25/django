/**
 * Common shape for every error dict the ETL service appends to its three
 * buckets. All fields beyond `type`/`message` are optional because different
 * error types populate different subsets (substitution errors carry
 * `field`/`value`/`account_path`; python errors carry `traceback`; etc.).
 */
export interface EtlError {
  type: string
  message: string
  stage?: string
  timestamp?: string
  model?: string
  record_id?: number | string
  sheet?: string
  row?: number | string
  field?: string
  value?: string | number | null
  account_path?: string
  exception_type?: string
  traceback?: string
  [k: string]: unknown
}

export interface EtlWarning {
  type: string
  message: string
  [k: string]: unknown
}

export interface EtlExecuteResponse {
  success: boolean
  summary?: {
    sheets_found?: string[]
    sheets_processed?: string[]
    sheets_skipped?: string[]
    sheets_failed?: string[]
    committed?: boolean
    [k: string]: unknown
  }
  data?: Record<string, { row_count?: number; rows?: unknown[]; sample_columns?: string[] } | unknown>
  import_result?: Record<string, unknown>
  errors?: EtlError[]
  errors_organized?: {
    all_errors?: EtlError[]
    python_errors?: EtlError[]
    database_errors?: EtlError[]
    substitution_errors?: EtlError[]
    warnings?: EtlWarning[]
    error_report_text?: string | null
    [k: string]: unknown
  }
  warnings?: EtlWarning[]
  error?: string
  detail?: string
}

// Matches SubstitutionRule fields exposed by the backend serializer:
// during ETL, a cell value `match_value` in `field_name` of `model_name`
// gets replaced with `substitution_value` according to `match_type`.
// Earlier this type claimed {name, source_value, target_value, rule_type}
// which didn't match anything the backend returns — rows rendered blank.
export type SubstitutionMatchType =
  | "exact"
  | "prefix"
  | "suffix"
  | "contains"
  | "regex"

export interface SubstitutionRule {
  id: number
  company?: number
  model_name: string
  field_name: string
  match_type: SubstitutionMatchType | string
  match_value: string
  substitution_value: string
  is_deleted?: boolean
  created_at?: string
  updated_at?: string
}

/**
 * One row in a sheet, as reported back by execute_import_job().
 * ``status`` is usually "success" | "error" | "skipped"; ``action`` is
 * "create" | "update" | "delete" | "upsert" | "noop", but both are
 * free-form strings on the backend so we keep them loose.
 */
export interface BulkImportRowResult {
  __row_id?: string | number | null
  status?: string
  action?: string | null
  data?: Record<string, unknown>
  message?: string
  observations?: string[]
  external_id?: string | number | null
  [k: string]: unknown
}

export interface BulkImportSheetResult {
  model: string
  result: BulkImportRowResult[]
}

export interface BulkImportResponse {
  committed: boolean
  reason?: string | null
  imports: BulkImportSheetResult[]
  /** Top-level error when the request fails outside the per-row loop. */
  error?: string
  detail?: string
}

export interface OfxImportFile {
  name?: string
  ofx_text?: string
  base64Data?: string
}

export interface OfxImportedTx {
  tx_hash: string
  amount: number
  date: string
  status: "duplicate" | "pending" | "inserted"
  [k: string]: unknown
}

export interface OfxLookupInfo {
  result?: "Success" | "Error"
  message?: string
  value?: unknown
}

export interface OfxImportResult {
  filename: string
  /** On scan: object with lookup info. On older import responses: plain string. */
  bank?: OfxLookupInfo | string
  account?: OfxLookupInfo | string
  inserted: number
  duplicates: number
  duplicate_ratio?: number
  warning?: string | null
  transactions?: OfxImportedTx[]
}

export interface OfxImportResponse {
  import_results: OfxImportResult[]
}

export interface NfeImportadaItem {
  chave?: string
  id?: number
  numero?: string | number
  [k: string]: unknown
}

export interface NfeEventoItem {
  chave_nfe?: string
  id?: number
  tipo_evento?: string
  n_seq_evento?: number
  [k: string]: unknown
}

export interface NfeInutilizacaoItem {
  ano?: number
  serie?: number
  n_nf_ini?: number
  n_nf_fin?: number
  id?: number
  [k: string]: unknown
}

export interface NfeErrorItem {
  /** Backend uses ``arquivo`` (pt-BR). */
  arquivo?: string
  erro?: string
  /** Legacy fields for robustness. */
  filename?: string
  error_message?: string
  [k: string]: unknown
}

export interface NfeImportResponse {
  importadas: NfeImportadaItem[]
  importados: NfeEventoItem[]
  importados_inut: NfeInutilizacaoItem[]
  duplicadas: unknown[]
  erros: NfeErrorItem[]
  inventory_triggered?: boolean
  dry_run?: boolean
}
