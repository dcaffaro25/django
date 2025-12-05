// Reconciliation API endpoints
import { apiClient } from "@/lib/api-client"
import type {
  ReconciliationTask,
  ReconciliationConfig,
  ReconciliationPipeline,
  ReconciliationDashboard,
  PaginatedResponse,
} from "@/types"

export async function getReconciliationTasks(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ReconciliationTask>> {
  return apiClient.get<PaginatedResponse<ReconciliationTask>>(
    "/api/reconciliation-tasks/",
    params
  )
}

export async function getReconciliationTask(
  tenant: string,
  id: number
): Promise<ReconciliationTask> {
  return apiClient.get<ReconciliationTask>(`/api/reconciliation-tasks/${id}/`)
}

export async function getReconciliationDashboard(
  tenant: string
): Promise<ReconciliationDashboard> {
  return apiClient.get<ReconciliationDashboard>("/api/reconciliation-dashboard/")
}

export async function getReconciliationConfigs(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ReconciliationConfig>> {
  return apiClient.get<PaginatedResponse<ReconciliationConfig>>(
    "/api/reconciliation_configs/",
    params
  )
}

export async function createReconciliationConfig(
  tenant: string,
  data: Partial<ReconciliationConfig>
): Promise<ReconciliationConfig> {
  return apiClient.post<ReconciliationConfig>("/api/reconciliation_configs/", data)
}

export async function updateReconciliationConfig(
  tenant: string,
  id: number,
  data: Partial<ReconciliationConfig>
): Promise<ReconciliationConfig> {
  return apiClient.put<ReconciliationConfig>(`/api/reconciliation_configs/${id}/`, data)
}

export async function deleteReconciliationConfig(
  tenant: string,
  id: number
): Promise<void> {
  return apiClient.delete(`/api/reconciliation_configs/${id}/`)
}

export async function startReconciliation(
  tenant: string,
  data: {
    config_id?: number
    pipeline_id?: number
    bank_ids?: number[]
    book_ids?: number[]
    auto_match_100?: boolean
  }
): Promise<ReconciliationTask> {
  return apiClient.post<ReconciliationTask>("/api/reconciliation-tasks/start/", data)
}

export async function cancelReconciliationTask(
  tenant: string,
  id: number
): Promise<void> {
  return apiClient.post(`/api/reconciliation-tasks/${id}/cancel/`)
}

export async function getReconciliationTaskStatus(
  tenant: string,
  id: number
): Promise<ReconciliationTask> {
  return apiClient.get<ReconciliationTask>(`/api/reconciliation-tasks/${id}/status/`)
}

