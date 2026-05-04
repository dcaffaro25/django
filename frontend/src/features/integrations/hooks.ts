import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { integrationsApi } from "./api"
import { useTenant } from "@/providers/TenantProvider"

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

export function useErpConnections() {
  const sub = useSub()
  return useQuery({
    queryKey: ["integrations", sub, "connections"],
    queryFn: integrationsApi.listConnections,
    enabled: !!sub,
    staleTime: 60 * 1000,
  })
}

export function useErpApiDefinitions(
  providerOrParams?: number | { provider?: number; include_inactive?: boolean },
) {
  const sub = useSub()
  // Backward-compat: existing callers pass a bare provider id; new
  // callers pass an options object so they can opt-in to include_inactive.
  const params = typeof providerOrParams === "number"
    ? { provider: providerOrParams }
    : providerOrParams
  return useQuery({
    queryKey: ["integrations", sub, "api-definitions", params?.provider ?? null, params?.include_inactive ?? false],
    queryFn: () => integrationsApi.listApiDefinitions(params),
    enabled: !!sub,
    staleTime: 5 * 60 * 1000,
  })
}

export function useErpApiDefinition(id: number | null) {
  const sub = useSub()
  return useQuery({
    queryKey: ["integrations", sub, "api-definition", id],
    queryFn: () => integrationsApi.getApiDefinition(id as number),
    enabled: !!sub && id != null,
    staleTime: 60 * 1000,
  })
}

export function useSaveApiDefinition() {
  const sub = useSub()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (args: {
      id?: number
      body: Parameters<typeof integrationsApi.createApiDefinition>[0]
    }) =>
      args.id
        ? integrationsApi.updateApiDefinition(args.id, args.body)
        : integrationsApi.createApiDefinition(args.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations", sub, "api-definitions"] })
      qc.invalidateQueries({ queryKey: ["integrations", sub, "api-definition"] })
    },
  })
}

export function useDeleteApiDefinition() {
  const sub = useSub()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: integrationsApi.deleteApiDefinition,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations", sub, "api-definitions"] })
    },
  })
}

export function useValidateApiDefinition() {
  return useMutation({
    mutationFn: integrationsApi.validateApiDefinition,
  })
}

export function useTestCallApiDefinition() {
  const sub = useSub()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      id: number
      body: Parameters<typeof integrationsApi.testCallApiDefinition>[1]
    }) => integrationsApi.testCallApiDefinition(args.id, args.body),
    onSuccess: () => {
      // The test-call updates last_tested_at on the definition; refetch.
      qc.invalidateQueries({ queryKey: ["integrations", sub, "api-definition"] })
      qc.invalidateQueries({ queryKey: ["integrations", sub, "api-definitions"] })
    },
  })
}

export function useRunSandbox() {
  return useMutation({
    mutationFn: integrationsApi.runSandbox,
  })
}

export function useSavePipeline() {
  return useMutation({
    mutationFn: integrationsApi.savePipeline,
  })
}
