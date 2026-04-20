import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { api, getStoredTenant, setStoredTenant, unwrapList } from "@/lib/api-client"
import { useAuth } from "./AuthProvider"

export interface Tenant {
  id: number
  name: string
  subdomain: string
}

interface TenantContextType {
  tenant: Tenant | null
  tenants: Tenant[]
  isLoading: boolean
  setTenant: (t: Tenant | null) => void
  switchTenant: (subdomain: string) => void
}

const TenantContext = createContext<TenantContextType | undefined>(undefined)

export function TenantProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const [tenant, setTenantState] = useState<Tenant | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["core", "companies"],
    queryFn: () => api.get<Tenant[] | { results: Tenant[] }>("/api/core/companies/").then(unwrapList<Tenant>),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  })

  const tenants = data ?? []

  // On first load (or when tenants arrive), hydrate selection from storage or default.
  useEffect(() => {
    if (tenant || tenants.length === 0) return
    const storedSub = getStoredTenant()
    const found = (storedSub && tenants.find((t) => t.subdomain === storedSub)) ?? tenants[0]
    if (found) {
      setTenantState(found)
      setStoredTenant(found.subdomain)
    }
  }, [tenants, tenant])

  const setTenant = useCallback((next: Tenant | null) => {
    setTenantState(next)
    setStoredTenant(next?.subdomain ?? null)
  }, [])

  const switchTenant = useCallback((subdomain: string) => {
    const found = tenants.find((t) => t.subdomain === subdomain)
    if (found) setTenant(found)
  }, [tenants, setTenant])

  const value = useMemo<TenantContextType>(() => ({
    tenant, tenants, isLoading, setTenant, switchTenant,
  }), [tenant, tenants, isLoading, setTenant, switchTenant])

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenant() {
  const ctx = useContext(TenantContext)
  if (!ctx) throw new Error("useTenant must be used within TenantProvider")
  return ctx
}
