import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useTenant } from "@/providers/TenantProvider"
import type { TenantThemePayload } from "@/features/auth/useUserRole"

/**
 * GET ``/api/core/tenant-theme/``. Returns the active tenant's
 * brand palette + category palette + logo URLs. The same payload
 * is also bundled into ``/api/core/me/`` for the boot-time paint;
 * use this hook on the editor screen where you want a stand-alone
 * fetch with its own loading state.
 */
export function useTenantTheme() {
  const { tenant } = useTenant()
  return useQuery({
    queryKey: ["tenant-theme", tenant?.subdomain ?? null],
    queryFn: () => api.tenant.get<TenantThemePayload>("/api/core/tenant-theme/"),
    enabled: !!tenant,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * PATCH ``/api/core/tenant-theme/`` (manager+ gate enforced
 * server-side). Invalidates both the standalone theme query and
 * the bundled ``/api/core/me/`` so the live preview matches the
 * persisted value once the round-trip completes.
 */
export function useUpdateTenantTheme() {
  const queryClient = useQueryClient()
  const { tenant } = useTenant()
  return useMutation({
    mutationFn: (body: Partial<TenantThemePayload>) =>
      api.tenant.patch<TenantThemePayload>("/api/core/tenant-theme/", body),
    onSuccess: () => {
      const key = tenant?.subdomain ?? null
      queryClient.invalidateQueries({ queryKey: ["tenant-theme", key] })
      queryClient.invalidateQueries({ queryKey: ["core", "me", key] })
    },
  })
}
