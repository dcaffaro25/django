// Accounts API endpoints
import { apiClient } from "@/lib/api-client"
import type { Account, PaginatedResponse } from "@/types"

export async function getAccounts(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Account>> {
  return apiClient.get<PaginatedResponse<Account>>("/api/accounts/", params)
}

export async function getAccount(tenant: string, id: number): Promise<Account> {
  return apiClient.get<Account>(`/api/accounts/${id}/`)
}

export async function createAccount(
  tenant: string,
  data: Partial<Account>
): Promise<Account> {
  return apiClient.post<Account>("/api/accounts/", data)
}

export async function updateAccount(
  tenant: string,
  id: number,
  data: Partial<Account>
): Promise<Account> {
  return apiClient.put<Account>(`/api/accounts/${id}/`, data)
}

export async function deleteAccount(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/accounts/${id}/`)
}

