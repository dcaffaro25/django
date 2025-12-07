// Transaction API endpoints
import { apiClient } from "@/lib/api-client"
import type { Transaction, PaginatedResponse } from "@/types"

export async function getTransactions(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Transaction>> {
  console.log("getTransactions - Called with tenant:", tenant, "params:", params)
  try {
    const result = await apiClient.get<PaginatedResponse<Transaction>>("/api/transactions/", params)
    console.log("getTransactions - Success:", result)
    return result
  } catch (error) {
    console.error("getTransactions - Error:", error)
    throw error
  }
}

export async function getTransaction(tenant: string, id: number): Promise<Transaction> {
  return apiClient.get<Transaction>(`/api/transactions/${id}/`)
}

export async function createTransaction(
  tenant: string,
  data: Partial<Transaction>
): Promise<Transaction> {
  return apiClient.post<Transaction>("/api/transactions/", data)
}

export async function updateTransaction(
  tenant: string,
  id: number,
  data: Partial<Transaction>
): Promise<Transaction> {
  return apiClient.put<Transaction>(`/api/transactions/${id}/`, data)
}

export async function postTransaction(tenant: string, id: number): Promise<void> {
  return apiClient.post(`/api/transactions/${id}/post/`)
}

export async function unpostTransaction(tenant: string, id: number): Promise<void> {
  return apiClient.post(`/api/transactions/${id}/unpost/`)
}

export async function cancelTransaction(tenant: string, id: number): Promise<void> {
  return apiClient.post(`/api/transactions/${id}/cancel/`)
}

