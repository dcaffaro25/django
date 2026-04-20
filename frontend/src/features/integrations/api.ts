import { api, unwrapList } from "@/lib/api-client"
import type {
  ERPAPIDefinition,
  ERPConnection,
  ERPSyncPipelineWrite,
  SandboxRequest,
  SandboxResult,
} from "./types"

export const integrationsApi = {
  listConnections: () =>
    api.tenant
      .get<ERPConnection[] | { results: ERPConnection[] }>("/api/connections/")
      .then(unwrapList<ERPConnection>),

  listApiDefinitions: (provider?: number) =>
    api.tenant
      .get<ERPAPIDefinition[] | { results: ERPAPIDefinition[] }>("/api/api-definitions/", {
        params: provider != null ? { provider } : undefined,
      })
      .then(unwrapList<ERPAPIDefinition>),

  runSandbox: (body: SandboxRequest) =>
    api.tenant.post<SandboxResult>("/api/pipeline-sandbox/", body),

  savePipeline: (body: ERPSyncPipelineWrite) =>
    api.tenant.post<{ id: number }>("/api/sync-pipelines/", body),
}
