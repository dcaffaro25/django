import { api, unwrapList } from "@/lib/api-client"
import type {
  CalculateRequest,
  ReportInstance,
  ReportInstanceListItem,
  ReportResult,
  ReportTemplate,
  SaveRequest,
} from "./types"

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
}
