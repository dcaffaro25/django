import { api, unwrapList } from "@/lib/api-client"
import type {
  ApiDefinitionTestCallResult,
  ApiDefinitionValidateResult,
  DiscoveryCandidate,
  DiscoveryResult,
  ERPAPIDefinition,
  ERPAPIDefinitionWrite,
  ERPConnection,
  ERPSyncPipeline,
  ERPSyncPipelineWrite,
  ImportDiscoveredResult,
  PipelineRunHistoryRow,
  SandboxRequest,
  SandboxResult,
  ScheduledRunOutcome,
} from "./types"

export const integrationsApi = {
  listConnections: () =>
    api.tenant
      .get<ERPConnection[] | { results: ERPConnection[] }>("/api/connections/")
      .then(unwrapList<ERPConnection>),

  listApiDefinitions: (params?: { provider?: number; include_inactive?: boolean }) =>
    api.tenant
      .get<ERPAPIDefinition[] | { results: ERPAPIDefinition[] }>("/api/api-definitions/", {
        params: {
          provider: params?.provider ?? undefined,
          include_inactive: params?.include_inactive ? 1 : undefined,
        },
      })
      .then(unwrapList<ERPAPIDefinition>),

  getApiDefinition: (id: number) =>
    api.tenant.get<ERPAPIDefinition>(`/api/api-definitions/${id}/`),

  createApiDefinition: (body: ERPAPIDefinitionWrite) =>
    api.tenant.post<ERPAPIDefinition>("/api/api-definitions/", body),

  updateApiDefinition: (id: number, body: Partial<ERPAPIDefinitionWrite>) =>
    api.tenant.patch<ERPAPIDefinition>(`/api/api-definitions/${id}/`, body),

  deleteApiDefinition: (id: number) =>
    api.tenant.delete<void>(`/api/api-definitions/${id}/`),

  validateApiDefinition: (body: Partial<ERPAPIDefinitionWrite>) =>
    api.tenant.post<ApiDefinitionValidateResult>("/api/api-definitions/validate/", body),

  testCallApiDefinition: (id: number, body: {
    connection_id: number
    param_values?: Record<string, unknown>
    max_pages?: number
  }) =>
    api.tenant.post<ApiDefinitionTestCallResult>(`/api/api-definitions/${id}/test-call/`, body),

  // Phase-2: discovery
  discoverApis: (body: { url: string; allow_llm?: boolean }) =>
    api.tenant.post<DiscoveryResult>("/api/api-definitions/discover/", body),

  importDiscovered: (body: { provider: number; candidates: DiscoveryCandidate[] }) =>
    api.tenant.post<ImportDiscoveredResult>("/api/api-definitions/import-discovered/", body),

  // Phase-4: scheduled routines
  listPipelines: (params?: { connection?: number }) =>
    api.tenant
      .get<ERPSyncPipeline[] | { results: ERPSyncPipeline[] }>("/api/sync-pipelines/", {
        params,
      })
      .then(unwrapList<ERPSyncPipeline>),

  getPipeline: (id: number) =>
    api.tenant.get<ERPSyncPipeline>(`/api/sync-pipelines/${id}/`),

  updatePipeline: (id: number, body: Partial<ERPSyncPipeline>) =>
    api.tenant.patch<ERPSyncPipeline>(`/api/sync-pipelines/${id}/`, body),

  pausePipeline: (id: number) =>
    api.tenant.post<{ is_paused: boolean }>(`/api/sync-pipelines/${id}/pause/`, {}),

  resumePipeline: (id: number) =>
    api.tenant.post<{ is_paused: boolean }>(`/api/sync-pipelines/${id}/resume/`, {}),

  runPipelineNow: (id: number, body?: {
    force_full_dump?: boolean
    window_start?: string
    window_end?: string
  }) =>
    api.tenant.post<ScheduledRunOutcome>(`/api/sync-pipelines/${id}/run-now/`, body ?? {}),

  pipelineHistory: (id: number) =>
    api.tenant.get<PipelineRunHistoryRow[]>(`/api/sync-pipelines/${id}/history/`),

  runSandbox: (body: SandboxRequest) =>
    api.tenant.post<SandboxResult>("/api/pipeline-sandbox/", body),

  savePipeline: (body: ERPSyncPipelineWrite) =>
    api.tenant.post<{ id: number }>("/api/sync-pipelines/", body),
}
