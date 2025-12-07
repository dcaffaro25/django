import { createContext, useContext, useState, useEffect, ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import type { Company } from "@/types"

interface TenantContextType {
  tenant: Company | null
  tenants: Company[]
  isLoading: boolean
  setTenant: (tenant: Company | null) => void
  switchTenant: (tenantSubdomain: string) => void
}

const TenantContext = createContext<TenantContextType | undefined>(undefined)

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenant, setTenantState] = useState<Company | null>(null)

  // Fetch available tenants (companies)
  // Only fetch if user is authenticated
  const { data: tenantsData, isLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: async () => {
      const response = await apiClient.get<Company[] | { results: Company[] }>("/api/core/companies/")
      // Handle both array and paginated response formats
      if (Array.isArray(response)) {
        return response
      }
      // If it's a paginated response, extract the results
      if (response && typeof response === 'object' && 'results' in response) {
        return (response as { results: Company[] }).results
      }
      return []
    },
    enabled: !!localStorage.getItem("auth_token"), // Only fetch if authenticated
    retry: false, // Don't retry on failure
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  })
  
  // Ensure tenants is always an array
  const tenants = Array.isArray(tenantsData) ? tenantsData : []

  // Load tenant from localStorage on mount
  useEffect(() => {
    const storedTenant = localStorage.getItem("selected_tenant")
    if (storedTenant) {
      try {
        const parsed = JSON.parse(storedTenant)
        setTenantState(parsed)
        apiClient.setTenantId(parsed.subdomain)
      } catch (error) {
        console.error("Failed to parse tenant from localStorage", error)
        localStorage.removeItem("selected_tenant")
      }
    }
  }, [])

  const setTenant = (newTenant: Company | null) => {
    setTenantState(newTenant)
    if (newTenant) {
      localStorage.setItem("selected_tenant", JSON.stringify(newTenant))
      apiClient.setTenantId(newTenant.subdomain)
    } else {
      localStorage.removeItem("selected_tenant")
      apiClient.setTenantId(null)
    }
  }

  const switchTenant = (tenantSubdomain: string) => {
    const foundTenant = tenants.find((t) => t.subdomain === tenantSubdomain)
    if (foundTenant) {
      setTenant(foundTenant)
    } else {
      console.error(`Tenant with subdomain ${tenantSubdomain} not found`)
    }
  }

  const value: TenantContextType = {
    tenant,
    tenants,
    isLoading,
    setTenant,
    switchTenant,
  }

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenant() {
  const context = useContext(TenantContext)
  if (context === undefined) {
    throw new Error("useTenant must be used within a TenantProvider")
  }
  return context
}

