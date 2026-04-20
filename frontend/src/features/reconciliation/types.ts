export type ReconTaskStatus = "queued" | "running" | "completed" | "failed" | "cancelled"

export interface ReconciliationTask {
  id: number
  status: ReconTaskStatus
  task_id?: string | null
  tenant_id?: string | null
  config?: number | null
  pipeline?: number | null
  config_name?: string | null
  pipeline_name?: string | null
  parameters?: Record<string, unknown>
  result?: Record<string, unknown> | null
  error_message?: string | null
  bank_candidates?: number
  journal_candidates?: number
  suggestion_count?: number
  matched_bank_transactions?: number
  matched_journal_entries?: number
  auto_match_enabled?: boolean
  auto_match_applied?: number
  auto_match_skipped?: number
  duration_seconds?: number | null
  created_at?: string
  updated_at?: string
}

export type ReconStatus = "pending" | "open" | "matched" | "unmatched" | "review" | "approved"

export interface BankAccountLite {
  id: number
  name: string
  currency: string
}

export interface DailyBalanceRow {
  date: string
  bank_balance: number
  book_balance: number
  difference: number
}

export interface BalanceLinePoint {
  date: string
  movement: number
  balance: number
}

export interface DifferenceLinePoint {
  date: string
  bank_minus_book: number
}

/**
 * Emitted by the daily-balances service when a bank account has no leaf GL
 * account linked (`bank_account=ba`). In that case the backend returns a
 * zero-opening, zero-movement book line for that account — which then makes
 * the aggregated book series look flat in the dashboard chart.
 *
 * Possible warning codes:
 *   - "no_leaf_gl_linked_to_bank_account": no leaf Account has this bank
 *     account as `bank_account`. The only fix is linking one in Accounting.
 */
export type BookDailyWarningCode = "no_leaf_gl_linked_to_bank_account" | (string & {})

export interface BookDailyWarning {
  bank_account_id: number
  warning: BookDailyWarningCode
}

export interface BookCurrencyMismatch {
  bank_account_id: number
  currency_mismatch: string
}

export interface CurrencyAggregate {
  currency_id: number
  bank_accounts_count: number
  bank: { opening_balance: number; line: BalanceLinePoint[] }
  book: {
    opening_balance: number
    line: BalanceLinePoint[]
    warnings?: BookDailyWarning[]
    currency_mismatches?: BookCurrencyMismatch[]
  }
  difference: { line: DifferenceLinePoint[] }
}

export interface BankBookBalancesAggregate {
  company_id: number
  date_from: string
  date_to: string
  include_pending_book: boolean
  bank_accounts: Array<{
    id: number
    name: string
    entity_id?: number
    entity_name?: string
    bank_id?: number
    bank_name?: string
    currency_id: number
    balance: number
    balance_date?: string
  }>
  aggregate: {
    by_currency: Record<string, CurrencyAggregate>
    totals: { bank_accounts: number; currencies: number }
  }
}

export interface BankTransactionLite {
  id: number
  date: string
  amount: string | number
  description?: string | null
  bank_account?: number | null
  currency?: number | null
  is_reconciled?: boolean
}

export interface ReconciliationConfigLite {
  id: number
  name: string
  scope?: string
  is_default?: boolean
}

export interface ReconciliationPipelineLite {
  id: number
  name: string
  scope?: string
  is_default?: boolean
}

export interface Transaction {
  id: number
  company: number
  date: string
  entity: number
  entity_name?: string
  description: string
  amount: string
  currency: number
  currency_code?: string
  state: string
  is_balanced?: boolean
  is_reconciled?: boolean
  is_posted?: boolean
  erp_id?: string | null
  due_date?: string | null
  nf_number?: string | null
  numero_boleto?: string | null
  cnpj?: string | null
  created_at?: string
  updated_at?: string
}

export interface TransactionWrite {
  id?: number
  date: string
  entity: number
  description: string
  amount: string
  currency: number
  state?: string
}

export interface BankTransaction {
  id: number
  company: number
  bank_account: number | null
  entity?: number | null
  entity_name?: string | null
  currency: number
  date: string
  description: string
  amount: string
  status?: string
  reconciliation_status: ReconStatus
  tag?: string
  numeros_boleto?: string[]
  cnpj?: string | null
  erp_id?: string | null
}

export interface JournalEntry {
  id: number
  transaction_id: number
  company: number
  description: string
  bank_date?: string | null
  balance: number
  transaction_date: string
  transaction_description?: string
  transaction_value: number
  bank_account?: { id: number; name: string } | null
  reconciliation_status: ReconStatus
  tag?: string
  numero_boleto?: string | null
  cnpj?: string | null
  due_date?: string | null
  nf_number?: string | null
  erp_id?: string | null
}

/**
 * Shape returned by GET /api/transactions/{id}/journal_entries/ — matches
 * the detail JournalEntrySerializer. account/cost_center may come back as
 * nested dicts or as PKs depending on the serializer's resolution; we
 * accept both and render defensively.
 */
export interface TransactionJournalEntry {
  id: number
  transaction: number
  erp_id?: string | null
  description?: string | null
  account?: { id: number; name: string; account_code?: string | null } | number | null
  cost_center?: { id: number; name: string } | number | null
  debit_amount: string | number
  credit_amount: string | number
  state?: string
  date?: string
  bank_designation_pending?: boolean
  has_designated_bank?: boolean
  notes?: string | null
  tag?: string | null
}

export interface BankAccountFull {
  id: number
  name: string
  account_number?: string
  branch_id?: string
  current_balance?: number
  balance?: string
  balance_date?: string
  account_type?: string
  bank?: { id: number; name: string; bank_code?: string } | null
  currency?: { id: number; code: string; name: string } | null
  entity?: { id: number; name: string } | null
  company?: { id: number; name: string; subdomain: string } | null
}

/** Write shape for bank account (flat FK IDs). */
export interface BankAccountWrite {
  id?: number
  name: string
  bank: number
  entity: number
  currency: number
  account_number?: string
  branch_id?: string
  balance?: string
  balance_date?: string | null
  account_type?: string
}

export interface BankLite {
  id: number
  name: string
  bank_code?: string | null
}

export interface CurrencyLite {
  id: number
  code: string
  name: string
}

export interface ReconciliationPipelineStage {
  id?: number
  pipeline?: number
  config: number
  config_name?: string
  order: number
  enabled: boolean
  max_group_size_bank?: number | null
  max_group_size_book?: number | null
  amount_tolerance?: string | null
  group_span_days?: number | null
  avg_date_delta_days?: number | null
  embedding_weight?: string | null
  amount_weight?: string | null
  currency_weight?: string | null
  date_weight?: string | null
}

export interface ReconciliationPipeline {
  id: number
  scope: "global" | "company" | "user" | "company_user"
  name: string
  description?: string
  auto_apply_score: string
  max_suggestions: number
  soft_time_limit_seconds?: number | null
  is_default: boolean
  company: number | null
  user: number | null
  stages?: ReconciliationPipelineStage[]
  created_at?: string
  updated_at?: string
}

/** One leaf of a filter stack. */
export interface FilterStackRow {
  column_id: string
  operator: string
  value: unknown
  disabled?: boolean
}

/** The filter stack shape the backend expects for bank_filters/book_filters and overrides. */
export interface FilterStack {
  operator: "and" | "or"
  filters: Array<FilterStackRow | FilterStack>
}

export interface FilterColumnDef {
  id: string
  label: string
  type: "string" | "number" | "date" | "datetime" | "bool" | "fk" | "enum" | "array"
  operators: string[]
  enum?: string[]
  fk_model?: string
}

export interface PreviewCountsInput {
  bank_filters?: FilterStack | null
  book_filters?: FilterStack | null
  bank_ids?: number[]
  book_ids?: number[]
  override_mode?: "append" | "replace" | "intersect"
  merge_config_filters?: boolean
  config_id?: number
}

export interface PreviewCountsResponse {
  bank: { total: number; sample_ids: number[] }
  book: { total: number; sample_ids: number[] }
  warnings: string[]
  override_mode: "append" | "replace" | "intersect"
}

export interface ReconciliationConfig {
  id: number
  scope: "global" | "company" | "user" | "company_user"
  name: string
  description?: string
  bank_filters: FilterStack
  book_filters: FilterStack
  embedding_weight: string
  amount_weight: string
  currency_weight: string
  date_weight: string
  amount_tolerance: string
  group_span_days: number
  avg_date_delta_days: number
  max_group_size_bank: number
  max_group_size_book: number
  allow_mixed_signs: boolean
  require_cnpj_match?: boolean
  min_confidence: string
  max_suggestions: number
  soft_time_limit_seconds?: number
  max_alternatives_per_match: number
  fee_accounts: number[]
  duplicate_window_days: number
  text_similarity?: Record<string, unknown>
  is_default: boolean
  company: number | null
  user: number | null
  created_at?: string
  updated_at?: string
}

export interface SuggestMatchInput {
  bank_transaction_ids: number[]
  max_suggestions_per_bank?: number
  min_confidence?: number
  min_match_count?: number
}

export interface SuggestedJournalEntry {
  account_id: number
  account_code?: string
  account_name?: string
  debit_amount?: string | null
  credit_amount?: string | null
  description?: string
  cost_center_id?: number | null
  date?: string
}

export interface SuggestionItem {
  suggestion_type: "use_existing_book" | "create_new"
  confidence_score: number
  similarity?: number
  amount_match_score?: number
  match_count?: number
  pattern?: string
  amount_difference?: string
  existing_journal_entry?: {
    id: number
    transaction_id?: number
    account_id?: number
    account_code?: string
    account_name?: string
    debit_amount?: string | null
    credit_amount?: string | null
    description?: string
    date?: string
  }
  complementing_journal_entries?: SuggestedJournalEntry[]
  transaction?: {
    date: string
    entity_id?: number | null
    description: string
    amount: string
    currency_id?: number | null
    state?: string
  }
  journal_entries?: SuggestedJournalEntry[]
  historical_matches?: Array<{ bank_transaction_id: number; transaction_id: number; similarity: number }>
}

export interface SuggestMatchResponse {
  suggestions: Array<{
    bank_transaction_id: number
    bank_transaction: {
      id: number
      date: string
      amount: string
      description: string
      bank_account_id?: number
      entity_id?: number | null
      currency_id?: number
    }
    suggestions: SuggestionItem[]
  }>
  errors: unknown[]
}

/**
 * Raw suggestion payload as persisted by the engine (see
 * `reconciliation_service1.format_suggestion_output` and
 * `tasks.on_suggestion`). Used by the Sugestões page when viewing the
 * suggestions for a past reconciliation task.
 */
export interface TaskSuggestionBankDetail {
  id: number
  date: string | null
  amount: number | null
  description?: string | null
  tx_hash?: string | null
  bank_account?: { id: number; name: string } | null
  entity?: number | null
  currency?: number | null
}

export interface TaskSuggestionBookDetail {
  id: number
  date: string | null
  amount: number | null
  description?: string | null
  account?: { id: number; account_code?: string; name?: string } | null
  transaction?: {
    id: number
    entity?: { id: number; name: string } | null
    description?: string
    date?: string | null
  } | null
}

/** Aggregate stats emitted by the newer fuzzy engines alongside `bank_lines`
 *  / `book_lines` summary strings. Superset of what `sum_bank`/`sum_book`
 *  used to carry. */
export interface SideStats {
  count?: number
  sum_amount?: number
  min_date?: string | null
  max_date?: string | null
  weighted_avg_date?: string | null
}

export interface TaskSuggestionPayload {
  suggestion_id?: number
  match_type?: string
  "N bank"?: number
  "N book"?: number
  bank_ids: number[]
  journal_entries_ids: number[]
  /** Legacy service1 shape — arrays of already-inlined row details. */
  bank_transaction_details?: TaskSuggestionBankDetail[]
  journal_entry_details?: TaskSuggestionBookDetail[]
  /** Service1 also emitted pre-concatenated human-readable summaries. */
  bank_transaction_summary?: string
  journal_entries_summary?: string
  /** Newer fuzzy engine emits pipe-delimited lines instead of detail objects:
   *    "BANK#<id> | <date> | <amount> | <description>"
   *    "BOOK#<id> | <date> | <amount> | <code> | <branch> | <bank> | <entity> | <cnpj> | <account>"
   *  Multi-line matches concatenate rows with "\n". */
  bank_lines?: string
  book_lines?: string
  /** Newer engine stats (mirrors `bank_stats.count` / `bank_stats.sum_amount` etc). */
  bank_stats?: SideStats
  book_stats?: SideStats
  sum_bank?: number
  sum_book?: number
  difference?: number
  avg_date_diff?: number
  confidence_score: number
  abs_amount_diff?: number
  /** Newer engine dumps aux telemetry here (amount_diff, embed_similarity, etc). */
  extra?: {
    amount_diff?: number
    avg_date_delta_days_measured?: number
    currency_match?: number
    embed_similarity?: number
    [k: string]: unknown
  }
  component_scores?: Record<string, number>
  confidence_weights?: Record<string, number>
  match_parameters?: Record<string, number | string | boolean>
}

export interface FreshSuggestionsResponse {
  count: number
  suggestions: TaskSuggestionPayload[]
}

export interface FinalizeMatch {
  bank_transaction_ids: number[]
  journal_entry_ids: number[]
  adjustment_side?: "bank" | "journal" | "none"
}

export interface FinalizeMatchesInput {
  matches: FinalizeMatch[]
  adjustment_side?: "bank" | "journal" | "none"
  reference?: string
  notes?: string
}

export interface Entity {
  id: number
  level: number
  parent_id: number | null
  name: string
  path: string
  inherit_accounts?: boolean
  inherit_cost_centers?: boolean
}

export interface ReconKPIs {
  as_of: string
  unreconciled: {
    count: number
    amount_abs: string
    oldest_age_days: number | null
    oldest_date: string | null
  }
  tasks_30d: {
    completed: number
    failed: number
    running: number
    suggestion_count: number
    auto_match_applied: number
    automatch_rate: number | null
  }
  trend_14d: Array<{ date: string; new_bank_tx: number; reconciled: number }>
}

/* ---------------- Embeddings ---------------- */

/** GET /embeddings/health/ */
export interface EmbeddingHealth {
  ok: boolean
  dim?: number
  latency_ms?: number
  endpoint?: string
  model?: string
  used_internal?: boolean
  error?: string
}

/** GET /embeddings/missing-counts/ */
export interface EmbeddingMissingCounts {
  transactions_missing: number
  bank_transactions_missing: number
  accounts_missing: number
  total_missing: number
}

/** POST /embeddings/backfill/ — immediate response */
export interface EmbeddingBackfillInput {
  per_model_limit?: number
  client_opts?: Record<string, unknown>
}

export interface EmbeddingBackfillAck {
  task_id: string
  state: string
  mode: "async"
}

/**
 * GET /embeddings/tasks/<task_id>/ — progress breakdown. The backend
 * reports per-category `done/total` counters; shape is consistent across
 * categories but the set of keys can vary based on which job kicked off.
 */
export interface EmbeddingCategoryProgress {
  done: number
  total: number
}

export interface EmbeddingTaskState {
  task_id: string
  state: string
  progress?: {
    transactions?: EmbeddingCategoryProgress
    bank_transactions?: EmbeddingCategoryProgress
    accounts?: EmbeddingCategoryProgress
    [k: string]: EmbeddingCategoryProgress | undefined
  }
  error?: string | null
  result?: Record<string, unknown> | null
  updated_at?: string
}

/** GET /embeddings/jobs/ — one row per past/active embedding run. */
export interface EmbeddingJob {
  id?: number
  task_id: string
  kind?: string
  status: string
  created_at?: string
  updated_at?: string
  finished_at?: string | null
  progress?: EmbeddingTaskState["progress"]
  error?: string | null
}

export interface AccountLite {
  id: number
  name: string
  parent?: number | null
  level: number
  path: string
  account_code?: string | null
  is_active?: boolean
  currency?: { id: number; code: string; name: string } | null
  bank_account?: number | null
  current_balance?: number
  // Extended writable fields exposed by AccountSerializer (write-side only
  // cares about these; list/detail responses include them too).
  description?: string | null
  erp_id?: string | null
  account_direction?: number | null  // 1 = debit, -1 = credit
  balance?: number | string | null
  balance_date?: string | null
  key_words?: string | null
  examples?: string | null
}

/**
 * Full Reconciliation record as returned by ReconciliationSerializer
 * (/api/reconciliation/ and /api/reconciliation/{id}/).
 */
export interface Reconciliation {
  id: number
  status: ReconStatus
  reference?: string | null
  notes?: string | null
  journal_entries: number[]
  bank_transactions: number[]
  same_company?: boolean
  same_entity?: boolean
  created_at?: string
  updated_at?: string
  is_deleted?: boolean
  company?: number | null
}

/**
 * Compact row returned by /api/reconciliation/summaries/ — aggregated
 * totals + preformatted bank/book descriptions for the management page.
 */
export interface ReconciliationSummary {
  reconciliation_id: number
  status: ReconStatus
  is_closed: boolean
  bank_ids: number[]
  book_ids: number[]
  bank_description: string
  book_description: string
  bank_sum_value: number
  book_sum_value: number
  difference: number
  bank_amounts: number[]
  book_amounts: number[]
  bank_avg_date: string | null
  book_avg_date: string | null
  min_date: string | null
  max_date: string | null
  reference: string | null
  notes: string | null
  same_company: boolean
  same_entity: boolean
}
