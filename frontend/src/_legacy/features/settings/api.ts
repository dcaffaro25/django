// Settings API endpoints
import { apiClient } from "@/lib/api-client"
import type {
  IntegrationRule,
  SubstitutionRule,
  PaginatedResponse,
} from "@/types"

// Integration Rules
export async function getIntegrationRules(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<IntegrationRule>> {
  return apiClient.get<PaginatedResponse<IntegrationRule>>(
    "/api/core/integration-rules/",
    params
  )
}

export async function createIntegrationRule(
  tenant: string,
  data: Partial<IntegrationRule>
): Promise<IntegrationRule> {
  return apiClient.post<IntegrationRule>("/api/core/integration-rules/", data)
}

export async function updateIntegrationRule(
  tenant: string,
  id: number,
  data: Partial<IntegrationRule>
): Promise<IntegrationRule> {
  return apiClient.put<IntegrationRule>(`/api/core/integration-rules/${id}/`, data)
}

export async function deleteIntegrationRule(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/core/integration-rules/${id}/`)
}

export async function validateRule(
  tenant: string,
  data: {
    trigger_event: string
    rule: string
    filter_conditions?: string
    num_records?: number
  }
): Promise<{
  setup_data: string
  mock_payload: string
  mock_filtered_payload: string
  validation_errors?: string[]
}> {
  return apiClient.post("/api/core/validate-rule/", data)
}

export async function testRule(
  tenant: string,
  data: {
    setup_data: string
    payload: string
    rule: string
  }
): Promise<unknown> {
  return apiClient.post("/api/core/test-rule/", data)
}

// Substitution Rules
export async function getSubstitutionRules(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<SubstitutionRule>> {
  return apiClient.get<PaginatedResponse<SubstitutionRule>>(
    "/api/core/substitution-rules/",
    params
  )
}

export async function createSubstitutionRule(
  tenant: string,
  data: Partial<SubstitutionRule>
): Promise<SubstitutionRule> {
  return apiClient.post<SubstitutionRule>("/api/core/substitution-rules/", data)
}

export async function updateSubstitutionRule(
  tenant: string,
  id: number,
  data: Partial<SubstitutionRule>
): Promise<SubstitutionRule> {
  return apiClient.put<SubstitutionRule>(`/api/core/substitution-rules/${id}/`, data)
}

export async function deleteSubstitutionRule(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/core/substitution-rules/${id}/`)
}

