import { api, unwrapList } from "@/lib/api-client"
import type {
  GenerateStatementInput,
  GeneratedStatement,
  PreviewStatementResponse,
  StatementTemplate,
} from "./types"

export const statementsApi = {
  listTemplates: (params?: { report_type?: string; is_active?: boolean }) =>
    api.tenant
      .get<StatementTemplate[] | { results: StatementTemplate[] }>(
        "/api/financial-statement-templates/",
        { params },
      )
      .then(unwrapList<StatementTemplate>),

  getTemplate: (id: number) =>
    api.tenant.get<StatementTemplate>(`/api/financial-statement-templates/${id}/`),

  createTemplate: (body: StatementTemplate) =>
    api.tenant.post<StatementTemplate>("/api/financial-statement-templates/", body),

  updateTemplate: (id: number, body: Partial<StatementTemplate>) =>
    api.tenant.patch<StatementTemplate>(`/api/financial-statement-templates/${id}/`, body),

  deleteTemplate: (id: number) =>
    api.tenant.delete<void>(`/api/financial-statement-templates/${id}/`),

  duplicateTemplate: (id: number) =>
    api.tenant.post<StatementTemplate>(
      `/api/financial-statement-templates/${id}/duplicate/`,
    ),

  generate: (body: GenerateStatementInput) =>
    api.tenant.post<PreviewStatementResponse | GeneratedStatement>(
      "/api/financial-statements/generate/",
      body,
    ),

  /**
   * Fetches Excel export as a Blob (returned as base64 or raw bytes by backend).
   * Caller is responsible for triggering download.
   */
  exportExcel: (statementId: number) =>
    api.tenant.get<Blob>(`/api/financial-statements/${statementId}/export_excel/`, {
      responseType: "blob",
    }),
}
