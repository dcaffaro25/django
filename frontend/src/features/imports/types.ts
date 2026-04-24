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

// ---- v2 interactive import -----------------------------------------------
//
// These types mirror the backend payloads documented in
// ``docs/manual/11-etl-importacao.md`` §11.10c. The session is the root
// object everything else hangs off — analyze returns it, resolve mutates
// it in place, commit finalises it.
//
// Every field is optional-ish: the backend will never send a partial
// session, but a session in ``STATUS_ERROR`` may be missing
// ``parsed_payload`` / ``open_issues``, and a fresh ``STATUS_READY``
// session won't have a ``result`` yet.

export type ImportSessionMode = "template" | "etl"

export type ImportSessionStatus =
  | "analyzing"
  | "awaiting_resolve"
  | "ready"
  | "committing"
  | "committed"
  | "error"
  | "discarded"

export type ImportIssueType =
  | "erp_id_conflict"
  | "unmatched_reference"
  | "je_balance_mismatch"
  | "bad_date_format"
  | "negative_amount"
  | "fk_ambiguous"
  | "missing_etl_parameter"

export type ImportIssueSeverity = "error" | "warning"

/**
 * An action name the v2 resolve endpoint accepts. Each issue type exposes
 * a subset in ``proposed_actions``; the frontend picks the matching card
 * renderer off ``issue.type`` and only renders buttons whose action name
 * appears in ``proposed_actions``.
 */
export type ImportResolveAction =
  | "pick_row"
  | "skip_group"
  | "abort"
  | "map_to_existing"
  | "edit_value"
  | "ignore_row"

/**
 * The issue payload is intentionally loose on the wire — backend dicts,
 * not a tagged union — so callers can handle unknown types gracefully.
 * ``context`` and ``location`` carry per-type fields; renderers pick
 * them apart.
 */
export interface ImportIssue {
  issue_id: string
  type: ImportIssueType | string // tolerate unknown types
  severity: ImportIssueSeverity
  location: Record<string, unknown>
  context: Record<string, unknown>
  proposed_actions: string[]
  message?: string | null
}

/** One "badge" in the "Substituições aplicadas" panel: X → Y on field F. */
export interface SubstitutionApplied {
  field?: string
  from?: unknown
  to?: unknown
  [k: string]: unknown // backend may attach model/rule_id/etc.
}

/** Staged SubstitutionRule shown in the pre-commit editable summary. */
export interface StagedSubstitutionRule {
  model_name: string
  field_name: string
  match_type: "exact" | "regex" | "caseless" | string
  match_value: string
  substitution_value: string
  filter_conditions?: Record<string, unknown> | null
  title?: string | null
  /** Derived/source: which issue_id staged this rule. */
  source_issue_id?: string | null
}

/**
 * Compact view of how the parsed rows cluster by ``__erp_id``. Populated
 * server-side by the serializer (keeps ``parsed_payload`` internal) so
 * the UI can render the ETL v2 "Grupos de erp_id" panel without another
 * round-trip.
 */
export interface ImportTransactionGroup {
  erp_id: string | null
  row_count: number
  has_conflict: boolean
  rows: Record<string, unknown>[]
}

/**
 * Saved transformation rule (subset of ``ImportTransformationRule``
 * fields the UI needs). Used by the ETL v2 rule picker.
 */
export interface ImportTransformationRuleSummary {
  id: number
  name: string
  description?: string | null
  source_sheet_name: string
  target_model: string
  /** Present in detail-level fetches; list endpoints may omit. */
  column_mappings?: Record<string, string>
  erp_duplicate_behavior?: "update" | "skip" | "error"
  is_active?: boolean
}

/**
 * Compact preview of what commit would write. Populated by the
 * backend at analyze time for ETL sessions (stops dropping
 * ``would_create`` / ``would_fail`` from ``ETLPipelineService.execute
 * (commit=False)``). Template sessions leave it empty until we wire
 * a ``commit=False`` dry-run in a follow-up commit.
 */
export interface ImportPreview {
  /** Per-model expected-create counts. Example: {"Transaction": 12}. */
  would_create?: Record<string, number>
  /** Per-model expected-update counts (when the pipeline knows). */
  would_update?: Record<string, number>
  /** Per-model rows that would fail with a reason. */
  would_fail?: Record<string, number>
  /** Total rows that would be imported across all models. */
  total_rows?: number
  /** Anything else the write backend surfaces; forward-compatible. */
  [k: string]: unknown
}

export interface ImportSession {
  id: number
  company: number
  mode: ImportSessionMode
  status: ImportSessionStatus
  file_name: string
  file_hash?: string | null
  created_at?: string
  updated_at?: string
  expires_at?: string | null
  committed_at?: string | null
  open_issues: ImportIssue[]
  resolutions: unknown[]
  staged_substitution_rules: StagedSubstitutionRule[]
  result: Record<string, unknown>
  summary: { sheets?: Record<string, number> }
  issue_counts: Partial<Record<ImportIssueType, number>>
  is_committable: boolean
  is_terminal: boolean
  substitutions_applied: SubstitutionApplied[]
  transaction_groups: ImportTransactionGroup[]
  /** Dry-run preview: what commit would write. Empty for template
   *  sessions until the follow-up dry-run commit ships. */
  preview: ImportPreview
}

/** Request body for POST /v2/resolve/<id>/. Each resolution targets one
 *  issue by id, picks an action, and supplies per-action params. */
export interface ImportResolutionInput {
  issue_id: string
  action: ImportResolveAction | string
  params?: Record<string, unknown>
}

/**
 * Lightweight session row returned by GET /v2/sessions/ (Phase 6.z-b).
 * Backend's ImportSessionListSerializer deliberately omits
 * parsed_payload / open_issues / result — the queue table only needs
 * identification + a status chip + the operator name. Clicking a
 * row to expand it fetches the full ImportSession via the detail
 * endpoint.
 */
export interface ImportSessionSummary {
  id: number
  mode: ImportSessionMode
  status: ImportSessionStatus
  file_name: string
  file_hash: string | null
  created_at: string
  updated_at: string
  committed_at: string | null
  operator_name: string | null
  open_issue_count: number
  is_terminal: boolean
  transformation_rule_name: string | null
}

/** DRF PageNumberPagination shape. */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/**
 * Counts of non-terminal sessions, driving the sidebar badge. ``total``
 * is the sum of the three buckets — exposed separately so the frontend
 * can switch the dot colour (red when any ``awaiting_resolve`` wants
 * attention, amber when only background work is in flight).
 */
export interface ImportSessionRunningCount {
  analyzing: number
  committing: number
  awaiting_resolve: number
  total: number
}
