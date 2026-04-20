export interface EtlExecuteResponse {
  success: boolean
  summary?: {
    sheets_found?: string[]
    sheets_processed?: string[]
    committed?: boolean
    [k: string]: unknown
  }
  import_result?: Record<string, unknown>
  errors_organized?: {
    all_errors?: unknown[]
    python_errors?: unknown[]
    database_errors?: unknown[]
    validation_errors?: unknown[]
    [k: string]: unknown
  }
  warnings?: unknown[]
  error?: string
  detail?: string
}

export interface SubstitutionRule {
  id: number
  name: string
  description?: string | null
  source_value?: string
  target_value?: string
  rule_type?: string
  company?: number
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

export interface ImportTransformationRule {
  id: number
  name: string
  description?: string | null
  model_name?: string
  mapping_config?: Record<string, unknown>
  company?: number
  is_active?: boolean
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

export interface OfxImportResponse {
  import_results: Array<{
    filename: string
    bank?: string
    account?: string
    inserted: number
    duplicates: number
    duplicate_ratio?: number
    transactions?: OfxImportedTx[]
  }>
}

export interface NfeImportResponse {
  nfe_count?: number
  evento_count?: number
  inutilizacao_count?: number
  nfe_results?: Array<{
    filename: string
    action?: string
    status?: string
    data?: Record<string, unknown>
  }>
  errors?: Array<{ filename: string; error_message: string }>
}
