// Reconciliation API endpoints
import { apiClient } from "@/lib/api-client"
import type {
  ReconciliationTask,
  ReconciliationConfig,
  ReconciliationPipeline,
  ReconciliationDashboard,
  ReconciliationSummaryRow,
  ReconciliationRecordTagBulkPayload,
  ReconciliationRecordTagBulkResponse,
  BankBookDailyBalancesResponse,
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

/**
 * GET /api/reconciliation/summaries/?status=matched,approved (default) or e.g. open,pending,review
 * Response is a raw list unless pagination query params are used (then DRF returns count/next/previous/results).
 */
export async function getReconciliationSummaries(
  tenant: string,
  params?: Record<string, unknown>
): Promise<ReconciliationSummaryRow[] | PaginatedResponse<ReconciliationSummaryRow>> {
  return apiClient.get<ReconciliationSummaryRow[] | PaginatedResponse<ReconciliationSummaryRow>>(
    "/api/reconciliation/summaries/",
    params
  )
}

/** Bulk-set the same tag on journal lines and/or bank lines */
export async function setReconciliationRecordTags(
  tenant: string,
  data: ReconciliationRecordTagBulkPayload
): Promise<ReconciliationRecordTagBulkResponse> {
  return apiClient.post<ReconciliationRecordTagBulkResponse>(
    "/api/reconciliation-record-tags/",
    data
  )
}

/** GET /api/bank-book-daily-balances/ — bank statement vs GL running balance per day */
export async function getBankBookDailyBalances(
  tenant: string,
  params: {
    bank_account_id: number
    date_from: string
    date_to: string
    include_pending_book?: boolean
    company_id?: number
  }
): Promise<BankBookDailyBalancesResponse> {
  const q: Record<string, unknown> = {
    bank_account_id: params.bank_account_id,
    date_from: params.date_from,
    date_to: params.date_to,
  }
  if (params.include_pending_book !== undefined) {
    q.include_pending_book = params.include_pending_book
  }
  if (params.company_id !== undefined) {
    q.company_id = params.company_id
  }
  return apiClient.get<BankBookDailyBalancesResponse>("/api/bank-book-daily-balances/", q)
}

