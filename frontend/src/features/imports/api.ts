import { api, unwrapList } from "@/lib/api-client"
import type {
  BulkImportResponse,
  EtlExecuteResponse,
  ImportResolutionInput,
  ImportSession,
  ImportSessionRunningCount,
  ImportSessionSummary,
  ImportTransformationRuleSummary,
  NfeImportResponse,
  OfxImportFile,
  OfxImportResponse,
  Paginated,
  SubstitutionRule,
} from "./types"

// ---- ETL ---------------------------------------------------------------

export interface EtlExecuteParams {
  file: File
  rowLimit?: number
  companyId?: number
  autoCreateJournalEntries?: Record<string, unknown>
}

function buildEtlFormData(params: EtlExecuteParams): FormData {
  const fd = new FormData()
  fd.append("file", params.file)
  if (params.rowLimit != null) fd.append("row_limit", String(params.rowLimit))
  if (params.companyId != null) fd.append("company_id", String(params.companyId))
  if (params.autoCreateJournalEntries) {
    fd.append("auto_create_journal_entries", JSON.stringify(params.autoCreateJournalEntries))
  }
  return fd
}

export async function etlExecute(params: EtlExecuteParams): Promise<EtlExecuteResponse> {
  return api.tenant.post<EtlExecuteResponse>("/api/core/etl/execute/", buildEtlFormData(params), {
    headers: { "Content-Type": "multipart/form-data" },
  })
}

/** Dry-run: same payload as execute, but the backend rolls back instead of committing. */
export async function etlPreview(params: EtlExecuteParams): Promise<EtlExecuteResponse> {
  return api.tenant.post<EtlExecuteResponse>("/api/core/etl/preview/", buildEtlFormData(params), {
    headers: { "Content-Type": "multipart/form-data" },
    // 4xx is expected when validation fails — surface the body rather than throwing.
    validateStatus: (s) => s < 500,
  })
}

// ---- Bulk-import (Excel workbook with many models) ---------------------

/**
 * Multi-model Excel bulk import. The backend reads every sheet in the
 * workbook, resolves *_fk references via ``__row_id`` tokens, and returns a
 * per-sheet report. With ``commit=false`` the whole thing runs inside a
 * transaction that gets rolled back — ideal for a preview step.
 */
export async function bulkImport(
  file: File,
  opts: { commit?: boolean } = {},
): Promise<BulkImportResponse> {
  const fd = new FormData()
  fd.append("file", file)
  fd.append("commit", opts.commit ? "true" : "false")
  return api.tenant.post<BulkImportResponse>("/api/core/bulk-import/", fd, {
    headers: { "Content-Type": "multipart/form-data" },
    validateStatus: (s) => s < 500,
  })
}

/**
 * Download the canonical workbook template (headers for every supported
 * model, with an ImportHelp sheet describing __row_id / __erp_id / *_fk).
 * Uses axios + blob so the Authorization header flows through.
 */
export async function downloadBulkImportTemplate(): Promise<void> {
  const blob = await api.tenant.get<Blob>("/api/core/bulk-import-template/", {
    responseType: "blob",
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)
  a.download = `bulk_import_template_${stamp}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

// ---- v2 interactive import ---------------------------------------------
//
// Two parallel URL namespaces share one ``ImportSession`` on the backend:
//
//   * ``/api/core/imports/v2/*``   → template flow (no transformation rule)
//   * ``/api/core/etl/v2/*``       → ETL flow (with transformation rule)
//
// The ``commit`` / ``sessions/<id>`` / ``resolve`` endpoints are identical
// across both namespaces (mode-dispatched on the server). We keep them in
// two objects anyway so call sites read naturally — ``importsV2.template
// .analyze(...)`` vs ``importsV2.etl.analyze(...)``.

export interface ImportsV2AnalyzeTemplateParams {
  file: File
  companyId?: number
  erpDuplicateBehavior?: "update" | "skip" | "error"
}

export interface ImportsV2AnalyzeEtlParams {
  file: File
  transformationRuleId: number
  companyId?: number
  rowLimit?: number
  autoCreateJournalEntries?: Record<string, unknown>
}

export interface ImportsV2ResolvePayload {
  resolutions: ImportResolutionInput[]
}

function buildTemplateAnalyzeFormData(p: ImportsV2AnalyzeTemplateParams): FormData {
  const fd = new FormData()
  fd.append("file", p.file)
  if (p.companyId != null) fd.append("company_id", String(p.companyId))
  if (p.erpDuplicateBehavior)
    fd.append("erp_duplicate_behavior", p.erpDuplicateBehavior)
  return fd
}

function buildEtlAnalyzeFormData(p: ImportsV2AnalyzeEtlParams): FormData {
  const fd = new FormData()
  fd.append("file", p.file)
  fd.append("transformation_rule_id", String(p.transformationRuleId))
  if (p.companyId != null) fd.append("company_id", String(p.companyId))
  if (p.rowLimit != null) fd.append("row_limit", String(p.rowLimit))
  if (p.autoCreateJournalEntries)
    fd.append(
      "auto_create_journal_entries",
      JSON.stringify(p.autoCreateJournalEntries),
    )
  return fd
}

export interface ImportsV2ListParams {
  /** Comma-separated whitelist. Empty / undefined → backend returns
   *  all statuses (including terminals). */
  status?: string
  mode?: "template" | "etl"
  page?: number
  pageSize?: number
}

// Shared endpoints — factored as free helpers so both namespace objects
// below can reference them without duplicating logic. The URL prefix is
// the only thing that differs between namespaces.
function makeSharedOps(prefix: string) {
  return {
    getSession: async (id: number): Promise<ImportSession> =>
      api.tenant.get<ImportSession>(`${prefix}/sessions/${id}/`),

    discardSession: async (id: number): Promise<ImportSession> =>
      api.tenant.delete<ImportSession>(`${prefix}/sessions/${id}/`),

    /** Paginated lightweight list — drives the queue panel. */
    listSessions: async (
      params: ImportsV2ListParams = {},
    ): Promise<Paginated<ImportSessionSummary>> => {
      const qs = new URLSearchParams()
      if (params.status) qs.set("status", params.status)
      if (params.mode) qs.set("mode", params.mode)
      if (params.page) qs.set("page", String(params.page))
      if (params.pageSize) qs.set("page_size", String(params.pageSize))
      const suffix = qs.toString() ? `?${qs.toString()}` : ""
      return api.tenant.get<Paginated<ImportSessionSummary>>(
        `${prefix}/sessions/${suffix}`,
      )
    },

    /** Cheap aggregate for the sidebar badge. */
    runningCount: async (): Promise<ImportSessionRunningCount> =>
      api.tenant.get<ImportSessionRunningCount>(
        `${prefix}/sessions/running-count/`,
      ),

    // Resolve returns the freshly-serialised session with mutated
    // open_issues / resolutions / status. A session that cleared all
    // its blocking issues will have is_committable === true.
    resolve: async (
      id: number,
      payload: ImportsV2ResolvePayload,
    ): Promise<ImportSession> =>
      api.tenant.post<ImportSession>(`${prefix}/resolve/${id}/`, payload, {
        // 409 / 400 are expected responses when the session can't
        // accept the resolution batch — surface the body, don't throw.
        validateStatus: (s) => s < 500,
      }),

    // Commit writes through to the DB. Server wraps the write in an
    // atomic transaction + materialises any staged_substitution_rules
    // with ``source=import_session`` + ``source_session=FK``.
    commit: async (id: number): Promise<ImportSession> =>
      api.tenant.post<ImportSession>(`${prefix}/commit/${id}/`, null, {
        validateStatus: (s) => s < 500,
      }),

    /**
     * Download the full per-row dry-run results as a multi-sheet xlsx.
     * Streams via ``GET ${prefix}/sessions/<id>/preview.xlsx``. We
     * fetch as ``blob`` (responseType) so axios doesn't try to JSON-
     * parse the binary body, then trigger a save dialog by creating a
     * temporary anchor with a blob URL. Returns nothing useful — the
     * side effect IS the operator's download.
     *
     * Throws on 404 (no preview data — session was discarded, file
     * was above the dry-run row threshold, or analyze didn't get far
     * enough). Caller should catch + surface a friendly message.
     */
    downloadPreviewXlsx: async (
      id: number,
      filename?: string,
    ): Promise<void> => {
      const blob = await api.tenant.get<Blob>(
        `${prefix}/sessions/${id}/preview.xlsx`,
        { responseType: "blob" },
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename ?? `session-${id}-preview.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      // Defer revoke so Safari has time to start the download.
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  }
}

/** Read-only view of the operator's transformation rules. Used by the
 *  ETL v2 rule picker; the legacy CRUD (create/edit/delete) still
 *  happens via ``/api/core/etl/transformation-rules/`` + a future
 *  dedicated rule-manager page. */
export const transformationRulesApi = {
  list: () =>
    api.tenant
      .get<
        | ImportTransformationRuleSummary[]
        | { results: ImportTransformationRuleSummary[] }
      >("/api/core/etl/transformation-rules/")
      .then(unwrapList<ImportTransformationRuleSummary>),

  get: (id: number) =>
    api.tenant.get<ImportTransformationRuleSummary>(
      `/api/core/etl/transformation-rules/${id}/`,
    ),
}

export const importsV2 = {
  template: {
    analyze: async (
      p: ImportsV2AnalyzeTemplateParams,
    ): Promise<ImportSession> =>
      api.tenant.post<ImportSession>(
        "/api/core/imports/v2/analyze/",
        buildTemplateAnalyzeFormData(p),
        { headers: { "Content-Type": "multipart/form-data" } },
      ),
    ...makeSharedOps("/api/core/imports/v2"),
  },
  etl: {
    analyze: async (p: ImportsV2AnalyzeEtlParams): Promise<ImportSession> =>
      api.tenant.post<ImportSession>(
        "/api/core/etl/v2/analyze/",
        buildEtlAnalyzeFormData(p),
        { headers: { "Content-Type": "multipart/form-data" } },
      ),
    ...makeSharedOps("/api/core/etl/v2"),
  },
}

// ---- Substitution rules ------------------------------------------------

export const substitutionRulesApi = {
  list: () =>
    api.tenant
      .get<SubstitutionRule[] | { results: SubstitutionRule[] }>("/api/core/substitution-rules/")
      .then(unwrapList<SubstitutionRule>),
  create: (body: Partial<SubstitutionRule>) =>
    api.tenant.post<SubstitutionRule>("/api/core/substitution-rules/", body),
  update: (id: number, body: Partial<SubstitutionRule>) =>
    api.tenant.patch<SubstitutionRule>(`/api/core/substitution-rules/${id}/`, body),
  remove: (id: number) => api.tenant.delete<void>(`/api/core/substitution-rules/${id}/`),
}

// ---- OFX ---------------------------------------------------------------

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error("read failed"))
    reader.onload = () => {
      const result = reader.result as string
      // strip "data:...;base64,"
      const comma = result.indexOf(",")
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.readAsDataURL(file)
  })
}

async function buildOfxPayload(files: File[]): Promise<OfxImportFile[]> {
  const out: OfxImportFile[] = []
  for (const f of files) {
    out.push({ name: f.name, base64Data: await readFileAsBase64(f) })
  }
  return out
}

export async function ofxImport(
  files: File[],
  policy: "records" | "files" = "records",
): Promise<OfxImportResponse> {
  const payload = await buildOfxPayload(files)
  return api.tenant.post<OfxImportResponse>(
    "/api/bank_transactions/import_ofx_transactions/",
    { files: payload, policy },
  )
}

/** Scan-only: classify each tx as duplicate/pending without writing to the DB. */
export async function ofxScan(files: File[]): Promise<OfxImportResponse> {
  const payload = await buildOfxPayload(files)
  return api.tenant.post<OfxImportResponse>(
    "/api/bank_transactions/import_ofx/",
    { files: payload },
  )
}

// ---- NFe ---------------------------------------------------------------

export async function nfeImport(
  files: File[],
  opts?: { dryRun?: boolean },
): Promise<NfeImportResponse> {
  const fd = new FormData()
  for (const f of files) fd.append("files", f)
  if (opts?.dryRun) fd.append("dry_run", "true")
  return api.tenant.post<NfeImportResponse>("/api/nfe/import/", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
}
