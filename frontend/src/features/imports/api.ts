import { api, unwrapList } from "@/lib/api-client"
import type {
  BulkImportResponse,
  EtlExecuteResponse,
  NfeImportResponse,
  OfxImportFile,
  OfxImportResponse,
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
