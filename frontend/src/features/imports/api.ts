import { api, unwrapList } from "@/lib/api-client"
import type {
  EtlExecuteResponse,
  ImportTransformationRule,
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

export async function etlExecute(params: EtlExecuteParams): Promise<EtlExecuteResponse> {
  const fd = new FormData()
  fd.append("file", params.file)
  if (params.rowLimit != null) fd.append("row_limit", String(params.rowLimit))
  if (params.companyId != null) fd.append("company_id", String(params.companyId))
  if (params.autoCreateJournalEntries) {
    fd.append("auto_create_journal_entries", JSON.stringify(params.autoCreateJournalEntries))
  }
  return api.tenant.post<EtlExecuteResponse>("/api/core/etl/execute/", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
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

// ---- Import templates (ImportTransformationRule) -----------------------

export const importTemplatesApi = {
  list: () =>
    api.tenant
      .get<ImportTransformationRule[] | { results: ImportTransformationRule[] }>(
        "/api/core/etl/transformation-rules/",
      )
      .then(unwrapList<ImportTransformationRule>),
  get: (id: number) =>
    api.tenant.get<ImportTransformationRule>(`/api/core/etl/transformation-rules/${id}/`),
  create: (body: Partial<ImportTransformationRule>) =>
    api.tenant.post<ImportTransformationRule>("/api/core/etl/transformation-rules/", body),
  update: (id: number, body: Partial<ImportTransformationRule>) =>
    api.tenant.patch<ImportTransformationRule>(`/api/core/etl/transformation-rules/${id}/`, body),
  remove: (id: number) =>
    api.tenant.delete<void>(`/api/core/etl/transformation-rules/${id}/`),
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

export async function ofxImport(files: File[]): Promise<OfxImportResponse> {
  const payload: OfxImportFile[] = []
  for (const f of files) {
    payload.push({ name: f.name, base64Data: await readFileAsBase64(f) })
  }
  return api.tenant.post<OfxImportResponse>(
    "/api/bank_transactions/import_ofx_transactions/",
    { files: payload, policy: "records" },
  )
}

// ---- NFe ---------------------------------------------------------------

export async function nfeImport(files: File[]): Promise<NfeImportResponse> {
  const fd = new FormData()
  for (const f of files) fd.append("files", f)
  return api.tenant.post<NfeImportResponse>("/api/nfe/import/", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
}
