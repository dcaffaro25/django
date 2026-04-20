import { useMutation, useQuery } from "@tanstack/react-query"
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

export function useErpApiDefinitions(provider?: number) {
  const sub = useSub()
  return useQuery({
    queryKey: ["integrations", sub, "api-definitions", provider ?? null],
    queryFn: () => integrationsApi.listApiDefinitions(provider),
    enabled: !!sub,
    staleTime: 5 * 60 * 1000,
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
