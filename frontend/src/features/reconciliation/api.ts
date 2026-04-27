import { api, unwrapList } from "@/lib/api-client"
import type {
  BankAccountFull,
  BankBookBalancesAggregate,
  BankTransaction,
  BankTransactionLite,
  EmbeddingBackfillAck,
  EmbeddingBackfillInput,
  EmbeddingHealth,
  EmbeddingJob,
  EmbeddingMissingCounts,
  EmbeddingTaskState,
  FilterColumnDef,
  FilterStack,
  FinalizeMatchesInput,
  FreshSuggestionsResponse,
  JournalEntry,
  PreviewCountsInput,
  PreviewCountsResponse,
  Reconciliation,
  ReconciliationConfig,
  ReconciliationConfigLite,
  ReconciliationPipelineLite,
  ReconciliationSummary,
  ReconciliationTask,
  ReconStatus,
  SuggestMatchInput,
  SuggestMatchResponse,
} from "./types"

export const reconApi = {
  listTasks: (params?: { status?: string; ordering?: string; page?: number }) =>
    api.tenant
      .get<ReconciliationTask[] | { results: ReconciliationTask[] }>("/api/reconciliation-tasks/", { params })
      .then(unwrapList<ReconciliationTask>),

  getTask: (id: number) => api.tenant.get<ReconciliationTask>(`/api/reconciliation-tasks/${id}/`),

  queuedTasks: () =>
    api.tenant
      .get<ReconciliationTask[] | { results: ReconciliationTask[] }>("/api/reconciliation-tasks/queued/")
      .then(unwrapList<ReconciliationTask>),

  startTask: (body: {
    config_id?: number
    pipeline_id?: number
    bank_ids?: number[]
    book_ids?: number[]
    bank_filter_overrides?: FilterStack | null
    book_filter_overrides?: FilterStack | null
    override_mode?: "append" | "replace" | "intersect"
    merge_config_filters?: boolean
    auto_match_100?: boolean
    fast?: boolean
  }) => api.tenant.post<ReconciliationTask>("/api/reconciliation-tasks/start/", body),

  // Filter-stack helpers
  filterColumns: (kind?: "bank_transaction" | "journal_entry") =>
    api.tenant.get<
      | { kind: string; columns: FilterColumnDef[] }
      | { bank_transaction: FilterColumnDef[]; journal_entry: FilterColumnDef[] }
    >("/api/reconciliation-filter-columns/", { params: kind ? { kind } : undefined }),

  previewCounts: (body: PreviewCountsInput) =>
    api.tenant.post<PreviewCountsResponse>("/api/reconciliation-preview-counts/", body),

  cancelTask: (id: number, reason?: string) =>
    api.tenant.post<ReconciliationTask>(`/api/reconciliation-tasks/${id}/cancel/`, { reason }),

  deleteTask: (id: number) => api.tenant.delete<void>(`/api/reconciliation-tasks/${id}/`),

  /**
   * Return persisted suggestions for a past task. Backend endpoint:
   * GET /api/reconciliation-tasks/{id}/fresh-suggestions/. Response shape:
   * `{ count, suggestions: SuggestionPayload[] }` where each payload is the
   * raw suggestion dict stored when the task ran. We regroup these by bank
   * transaction on the client to match SuggestMatchResponse shape used by
   * the Sugestões page renderer.
   */
  freshSuggestions: (
    taskId: number,
    params?: { min_confidence?: number; limit?: number },
  ) =>
    api.tenant.get<FreshSuggestionsResponse>(
      `/api/reconciliation-tasks/${taskId}/fresh-suggestions/`,
      { params },
    ),

  listConfigs: () =>
    api.tenant
      .get<ReconciliationConfigLite[] | { results: ReconciliationConfigLite[] }>("/api/reconciliation_configs/")
      .then(unwrapList<ReconciliationConfigLite>),

  listPipelines: () =>
    api.tenant
      .get<ReconciliationPipelineLite[] | { results: ReconciliationPipelineLite[] }>("/api/reconciliation-pipelines/")
      .then(unwrapList<ReconciliationPipelineLite>),

  unreconciledBank: (params?: {
    bank_account?: number
    start_date?: string
    end_date?: string
    min_amount?: number
    max_amount?: number
  }) =>
    api.tenant
      .get<BankTransactionLite[] | { results: BankTransactionLite[] }>(
        "/api/bank_transactions/unreconciled/",
        { params },
      )
      .then(unwrapList<BankTransactionLite>),

  dailyBalances: (params: {
    date_from: string
    date_to: string
    bank_account_id?: number
    /** When true, the book line includes JEs in ``state="pending"`` —
     *  the only state most operators see in the workbench, since
     *  pending IS the meaningful reconciliation state (posted JEs
     *  have already been finalized in the GL). Defaults to ``true``
     *  on the dashboard call site so a tenant whose JEs are
     *  exclusively pending (e.g. Evolat) doesn't see a flat book
     *  line. The backend default is still ``false`` to preserve
     *  behavior for any other client. */
    include_pending_book?: boolean
  }) =>
    api.tenant.get<BankBookBalancesAggregate>("/api/bank-book-daily-balances/", { params }),

  getKPIs: (params?: { date_from?: string; date_to?: string; lookback_days?: number; trend_days?: number }) =>
    api.tenant.get<import("./types").ReconKPIs>("/api/reconciliation-kpis/", { params }),

  getNotifications: (params?: { since?: string; limit?: number }) =>
    api.tenant.get<{
      as_of: string
      items: Array<{
        key: string
        type: string
        title: string
        subtitle?: string
        created_at: string | null
        url: string
      }>
    }>("/api/notifications/", { params }),

  search: (q: string, limit = 8) =>
    api.tenant.get<{
      q: string
      total: number
      groups: Array<{
        type: string
        label: string
        items: Array<{ id: number; title: string; subtitle?: string; url: string; state?: string }>
      }>
    }>("/api/search/", { params: { q, limit } }),

  // Transactions CRUD
  listTransactions: (params?: {
    state?: string
    date_after?: string
    date_before?: string
    entity?: number
    ordering?: string
    page_size?: number
    search?: string
  }) =>
    api.tenant
      .get<import("./types").Transaction[] | { results: import("./types").Transaction[] }>("/api/transactions/", { params })
      .then(unwrapList<import("./types").Transaction>),
  getTransaction: (id: number) => api.tenant.get<import("./types").Transaction>(`/api/transactions/${id}/`),
  createTransaction: (body: import("./types").TransactionWrite) =>
    api.tenant.post<import("./types").Transaction>("/api/transactions/", body),
  updateTransaction: (id: number, body: Partial<import("./types").TransactionWrite>) =>
    api.tenant.patch<import("./types").Transaction>(`/api/transactions/${id}/`, body),
  deleteTransaction: (id: number) => api.tenant.delete<void>(`/api/transactions/${id}/`),
  postTransaction: (id: number) => api.tenant.post<import("./types").Transaction>(`/transactions/${id}/post/`, {}),
  unpostTransaction: (id: number) => api.tenant.post<import("./types").Transaction>(`/transactions/${id}/unpost/`, {}),
  cancelTransaction: (id: number) => api.tenant.post<import("./types").Transaction>(`/transactions/${id}/cancel/`, {}),

  // Journal entries CRUD
  getJournalEntry: (id: number) => api.tenant.get<JournalEntry>(`/api/journal_entries/${id}/`),
  createJournalEntry: (body: Partial<JournalEntry>) =>
    api.tenant.post<JournalEntry>("/api/journal_entries/", body),
  updateJournalEntry: (id: number, body: Partial<JournalEntry>) =>
    api.tenant.patch<JournalEntry>(`/api/journal_entries/${id}/`, body),
  deleteJournalEntry: (id: number) => api.tenant.delete<void>(`/api/journal_entries/${id}/`),

  /**
   * Create one or more new JEs on the same Transaction as the template.
   * Used by the Bancada book-row "Ajustar" action — operators add a
   * balanced debit/credit pair without touching the existing entries.
   * Backed by JournalEntryViewSet.derive_from.
   */
  deriveJournalEntries: (body: {
    template_journal_entry_id: number
    entries: Array<{
      account_id: number
      debit_amount?: string | number | null
      credit_amount?: string | number | null
      description?: string
      date?: string
      cost_center_id?: number | null
      state?: "pending" | "posted" | "canceled"
    }>
  }) =>
    api.tenant.post<{ transaction_id: number; journal_entries: JournalEntry[] }>(
      "/api/journal_entries/derive_from/",
      body,
    ),

  /**
   * JEs attached to a single transaction. One query per expanded row;
   * backed by TransactionViewSet.journal_entries @action. Returns the
   * detail-serializer shape (id, account, debit/credit, state, …).
   */
  listTransactionJournalEntries: (txId: number) =>
    api.tenant.get<Array<import("./types").TransactionJournalEntry>>(
      `/api/transactions/${txId}/journal_entries/`,
    ),

  listBankTransactions: (params?: {
    /**
     * Preferred "not matched" switch — maps to BankTransactionFilter.filter_unreconciled
     * (excludes rows with any matched/approved Reconciliation). The Workbench bank pane
     * uses this as its equivalent of /api/journal_entries/unmatched/.
     */
    unreconciled?: boolean
    reconciliation_status?: string
    bank_account?: number
    date_after?: string
    date_before?: string
    ordering?: string
    limit?: number
    /** Forwarded to DRF pagination if enabled; harmless otherwise. */
    page_size?: number
    /** Comma-separated list of ids (maps to BankTransactionFilter.id__in). */
    id__in?: string
  }) =>
    api.tenant
      .get<BankTransaction[] | { results: BankTransaction[] }>("/api/bank_transactions/", { params })
      .then(unwrapList<BankTransaction>),

  listJournalEntries: (params?: {
    reconciliation_status?: string
    bank_account?: number
    transaction_date_after?: string
    transaction_date_before?: string
    ordering?: string
    limit?: number
    page_size?: number
    /** Comma-separated list of ids (maps to JournalEntryFilter.id__in). */
    id__in?: string
  }) =>
    api.tenant
      .get<JournalEntry[] | { results: JournalEntry[] }>("/api/journal_entries/", { params })
      .then(unwrapList<JournalEntry>),

  /**
   * Dedicated "unmatched" endpoint (bank-linked JEs with no matched/approved
   * reconciliation). Mirrors the Retool pattern and avoids the FilterSet
   * fallbacks. Params filter server-side on JE.date (not transaction.date).
   */
  listUnmatchedJournalEntries: (params?: {
    date_from?: string
    date_to?: string
    bank_account?: number
    tag?: string
  }) =>
    api.tenant
      .get<JournalEntry[] | { results: JournalEntry[] }>(
        "/api/journal_entries/unmatched/",
        { params },
      )
      .then(unwrapList<JournalEntry>),

  listBankAccounts: () =>
    api.tenant
      .get<BankAccountFull[] | { results: BankAccountFull[] }>("/api/bank_accounts/")
      .then(unwrapList<BankAccountFull>),

  createBankAccount: (body: import("./types").BankAccountWrite) =>
    api.tenant.post<BankAccountFull>("/api/bank_accounts/", body),
  updateBankAccount: (id: number, body: Partial<import("./types").BankAccountWrite>) =>
    api.tenant.patch<BankAccountFull>(`/api/bank_accounts/${id}/`, body),
  deleteBankAccount: (id: number) => api.tenant.delete<void>(`/api/bank_accounts/${id}/`),

  listBanks: () =>
    api.tenant
      .get<import("./types").BankLite[] | { results: import("./types").BankLite[] }>("/api/banks/")
      .then(unwrapList<import("./types").BankLite>),

  listCurrencies: () =>
    api.tenant
      .get<import("./types").CurrencyLite[] | { results: import("./types").CurrencyLite[] }>("/api/currencies/")
      .then(unwrapList<import("./types").CurrencyLite>),

  listEntities: () =>
    api.tenant
      .get<import("./types").Entity[] | { results: import("./types").Entity[] }>("/api/entities-mini/")
      .then(unwrapList<import("./types").Entity>),

  createEntity: (body: Partial<import("./types").Entity> & { company?: number }) =>
    api.tenant.post<import("./types").Entity>("/api/entities/", body),
  updateEntity: (id: number, body: Partial<import("./types").Entity>) =>
    api.tenant.patch<import("./types").Entity>(`/api/entities/${id}/`, body),
  deleteEntity: (id: number) => api.tenant.delete<void>(`/api/entities/${id}/`),

  listAccounts: (params?: { is_active?: boolean }) =>
    api.tenant
      .get<import("./types").AccountLite[] | { results: import("./types").AccountLite[] }>("/api/accounts/", { params })
      .then(unwrapList<import("./types").AccountLite>),

  createAccount: (body: Partial<import("./types").AccountLite> & { company?: number; parent?: number | null }) =>
    api.tenant.post<import("./types").AccountLite>("/api/accounts/", body),
  updateAccount: (id: number, body: Partial<import("./types").AccountLite>) =>
    api.tenant.patch<import("./types").AccountLite>(`/api/accounts/${id}/`, body),
  deleteAccount: (id: number) => api.tenant.delete<void>(`/api/accounts/${id}/`),

  // NOTE: backend router registers the viewset as `bank_transactions` (with
  // underscore) in accounting/urls.py. Earlier these paths used hyphens which
  // silently 404'd — the suggest button looked broken because the POST never
  // reached the view. Keep these in sync with accounting/urls.py.
  suggestMatches: (body: SuggestMatchInput) =>
    api.tenant.post<SuggestMatchResponse>("/api/bank_transactions/suggest_matches/", body),

  createSuggestions: (body: { suggestions: unknown[] }) =>
    api.tenant.post<{ created_transactions: unknown[]; created_reconciliations: unknown[]; errors: unknown[] }>(
      "/api/bank_transactions/create_suggestions/",
      body,
    ),

  finalizeMatches: (body: FinalizeMatchesInput) =>
    api.tenant.post<{ created: unknown[]; problems: unknown[] }>(
      "/api/bank_transactions/finalize_reconciliation_matches/",
      body,
    ),

  // Pipeline CRUD
  listPipelinesFull: () =>
    api.tenant
      .get<import("./types").ReconciliationPipeline[] | { results: import("./types").ReconciliationPipeline[] }>(
        "/api/reconciliation-pipelines/",
      )
      .then(unwrapList<import("./types").ReconciliationPipeline>),
  getPipeline: (id: number) =>
    api.tenant.get<import("./types").ReconciliationPipeline>(`/api/reconciliation-pipelines/${id}/`),
  createPipeline: (body: Partial<import("./types").ReconciliationPipeline>) =>
    api.tenant.post<import("./types").ReconciliationPipeline>("/api/reconciliation-pipelines/", body),
  updatePipeline: (id: number, body: Partial<import("./types").ReconciliationPipeline>) =>
    api.tenant.patch<import("./types").ReconciliationPipeline>(`/api/reconciliation-pipelines/${id}/`, body),
  deletePipeline: (id: number) => api.tenant.delete<void>(`/api/reconciliation-pipelines/${id}/`),

  // ---- Reconciliation records (the matches themselves) ----
  /** Raw list (ReconciliationSerializer). Mostly for detail/edit. */
  listReconciliations: (params?: {
    status?: string
    ordering?: string
    page?: number
    page_size?: number
  }) =>
    api.tenant
      .get<Reconciliation[] | { results: Reconciliation[] }>("/api/reconciliation/", { params })
      .then(unwrapList<Reconciliation>),

  /**
   * Compact, aggregated view used by the Reconciliations management page.
   * ?status defaults to "matched,approved" server-side. Pass "all" or a
   * comma-separated subset to widen.
   */
  listReconciliationSummaries: (params?: {
    status?: string
    ordering?: string
  }) =>
    api.tenant
      .get<ReconciliationSummary[] | { results: ReconciliationSummary[] }>(
        "/api/reconciliation/summaries/",
        { params },
      )
      .then(unwrapList<ReconciliationSummary>),

  getReconciliation: (id: number) =>
    api.tenant.get<Reconciliation>(`/api/reconciliation/${id}/`),

  /** Undo a reconciliation. Passing {delete:true} soft-deletes the record. */
  unmatchReconciliation: (id: number, body?: { reason?: string; delete?: boolean }) =>
    api.tenant.post<{
      id: number
      status: string
      is_deleted: boolean
      released_bank_transactions: number[]
      released_journal_entries: number[]
    }>(`/api/reconciliation/${id}/unmatch/`, body ?? {}),

  /** PATCH for inline edits (status, reference, notes). */
  updateReconciliation: (
    id: number,
    body: Partial<Pick<Reconciliation, "status" | "reference" | "notes">> & { status?: ReconStatus },
  ) => api.tenant.patch<Reconciliation>(`/api/reconciliation/${id}/`, body),

  deleteReconciliation: (id: number) =>
    api.tenant.delete<void>(`/api/reconciliation/${id}/`),

  /** Enqueue a Celery task that recomputes is_balanced/is_reconciled on all unposted transactions. */
  recalcUnpostedFlags: () =>
    api.tenant.post<{ task_id: string; status: string }>(
      "/api/transactions/recalc-unposted-flags-task/",
      {},
    ),

  // Config CRUD
  getConfig: (id: number) => api.tenant.get<ReconciliationConfig>(`/api/reconciliation_configs/${id}/`),
  createConfig: (body: Partial<ReconciliationConfig>) =>
    api.tenant.post<ReconciliationConfig>("/api/reconciliation_configs/", body),
  updateConfig: (id: number, body: Partial<ReconciliationConfig>) =>
    api.tenant.patch<ReconciliationConfig>(`/api/reconciliation_configs/${id}/`, body),
  deleteConfig: (id: number) => api.tenant.delete<void>(`/api/reconciliation_configs/${id}/`),
  listConfigsFull: () =>
    api.tenant
      .get<ReconciliationConfig[] | { results: ReconciliationConfig[] }>("/api/reconciliation_configs/")
      .then(unwrapList<ReconciliationConfig>),

  // ---- Embeddings ----
  /**
   * Describes what endpoints back each call:
   *   health         -> GET  /<tenant>/embeddings/health/
   *   missingCounts  -> GET  /<tenant>/embeddings/missing-counts/
   *   backfill       -> POST /<tenant>/embeddings/backfill/         (202 async)
   *   task           -> GET  /<tenant>/embeddings/tasks/<task_id>/
   *   jobs           -> GET  /<tenant>/embeddings/jobs/
   *
   * IMPORTANT: These live at `/<tenant>/embeddings/...` (no `/api/`). The
   * router-based resources in `accounting/urls.py` are nested under an
   * `^api/` include, but the embeddings views are registered at the root
   * of `accounting/urls.py`, so the `api/` segment is absent here.
   */
  embeddingsHealth: () =>
    api.tenant.get<EmbeddingHealth>("/embeddings/health/"),

  embeddingsMissingCounts: () =>
    api.tenant.get<EmbeddingMissingCounts>("/embeddings/missing-counts/"),

  embeddingsBackfill: (body: EmbeddingBackfillInput) =>
    api.tenant.post<EmbeddingBackfillAck>("/embeddings/backfill/", body),

  embeddingsTask: (taskId: string) =>
    api.tenant.get<EmbeddingTaskState>(`/embeddings/tasks/${taskId}/`),

  embeddingsJobs: (params?: {
    limit?: number
    status?: string
    kind?: string
    include_active?: 0 | 1
  }) =>
    api.tenant
      .get<EmbeddingJob[] | { results: EmbeddingJob[] }>("/embeddings/jobs/", { params })
      .then(unwrapList<EmbeddingJob>),
}

// Export named so other files can import BankTransactionLite typing
export type { BankTransactionLite }
