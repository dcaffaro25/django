import { api, unwrapList } from "@/lib/api-client"
import type {
  CalculateRequest,
  ReportInstance,
  ReportInstanceListItem,
  ReportResult,
  ReportTemplate,
  ReportType,
  SaveRequest,
  TemplateDocument,
} from "./types"

export interface AiGenerateTemplateRequest {
  report_type: ReportType
  preferences?: string
  provider?: "openai" | "anthropic"
  model?: string
}
export interface AiGenerateTemplateResponse {
  document: TemplateDocument
}

export type AiRefineAction =
  | "normalize_labels"
  | "translate_en"
  | "translate_pt"
  | "suggest_subtotals"
  | "add_missing_accounts"

export interface AiRefineRequest {
  action: AiRefineAction
  document: TemplateDocument
  provider?: "openai" | "anthropic"
  model?: string
}

export interface AiRefineSummary {
  added_ids: string[]
  removed_ids: string[]
  renamed: Array<{ id: string; from: string; to: string }>
  old_count: number
  new_count: number
}

export interface AiRefineResponse {
  document: TemplateDocument
  summary: AiRefineSummary
}

export const reportsApi = {
  // --- Templates ---------------------------------------------------------
  listTemplates: (params?: { report_type?: string; is_active?: boolean }) =>
    api.tenant
      .get<ReportTemplate[] | { results: ReportTemplate[] }>(
        "/api/reports/templates/",
        { params },
      )
      .then(unwrapList<ReportTemplate>),

  getTemplate: (id: number) =>
    api.tenant.get<ReportTemplate>(`/api/reports/templates/${id}/`),

  createTemplate: (body: ReportTemplate) =>
    api.tenant.post<ReportTemplate>("/api/reports/templates/", body),

  updateTemplate: (id: number, body: Partial<ReportTemplate>) =>
    api.tenant.patch<ReportTemplate>(`/api/reports/templates/${id}/`, body),

  deleteTemplate: (id: number) =>
    api.tenant.delete<void>(`/api/reports/templates/${id}/`),

  duplicateTemplate: (id: number) =>
    api.tenant.post<ReportTemplate>(`/api/reports/templates/${id}/duplicate/`),

  setDefaultTemplate: (id: number) =>
    api.tenant.post<{ status: string }>(`/api/reports/templates/${id}/set_default/`),

  // --- Stateless calculate ----------------------------------------------
  calculate: (body: CalculateRequest) =>
    api.tenant.post<ReportResult>("/api/reports/calculate/", body),

  // --- Save -------------------------------------------------------------
  save: (body: SaveRequest) =>
    api.tenant.post<ReportInstance>("/api/reports/save/", body),

  // --- Instances (list / detail / metadata update / delete) ------------
  listInstances: (params?: {
    report_type?: string
    status?: string
    template?: number
  }) =>
    api.tenant
      .get<ReportInstanceListItem[] | { results: ReportInstanceListItem[] }>(
        "/api/reports/instances/",
        { params },
      )
      .then(unwrapList<ReportInstanceListItem>),

  getInstance: (id: number) =>
    api.tenant.get<ReportInstance>(`/api/reports/instances/${id}/`),

  updateInstance: (id: number, body: Partial<Pick<ReportInstance, "status" | "notes">>) =>
    api.tenant.patch<ReportInstance>(`/api/reports/instances/${id}/`, body),

  deleteInstance: (id: number) =>
    api.tenant.delete<void>(`/api/reports/instances/${id}/`),

  // --- Exports (both stateless and instance-driven) ---------------------
  exportXlsx: (body: { result?: ReportResult; instance_id?: number; name?: string }) =>
    api.tenant.post<Blob>("/api/reports/export/xlsx/", body, { responseType: "blob" }),

  exportPdf: (body: { result?: ReportResult; instance_id?: number; name?: string }) =>
    api.tenant.post<Blob>("/api/reports/export/pdf/", body, { responseType: "blob" }),

  // --- AI --------------------------------------------------------------
  aiGenerateTemplate: (body: AiGenerateTemplateRequest) =>
    api.tenant.post<AiGenerateTemplateResponse>("/api/reports/ai/generate-template/", body),

  aiRefine: (body: AiRefineRequest) =>
    api.tenant.post<AiRefineResponse>("/api/reports/ai/refine/", body),
}
