import { api, unwrapList } from "@/lib/api-client"
import type {
  ApiDefinitionTestCallResult,
  ApiDefinitionValidateResult,
  DiscoveryCandidate,
  DiscoveryResult,
  ERPAPIDefinition,
  ERPAPIDefinitionWrite,
  ERPConnection,
  ERPSyncPipelineWrite,
  ImportDiscoveredResult,
  SandboxRequest,
  SandboxResult,
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

  runSandbox: (body: SandboxRequest) =>
    api.tenant.post<SandboxResult>("/api/pipeline-sandbox/", body),

  savePipeline: (body: ERPSyncPipelineWrite) =>
    api.tenant.post<{ id: number }>("/api/sync-pipelines/", body),
}
