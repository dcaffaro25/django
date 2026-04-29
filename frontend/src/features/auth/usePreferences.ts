import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useTenant } from "@/providers/TenantProvider"

interface PreferencesPayload {
  use_tenant_theme?: boolean
  prefer_dark_mode?: boolean
}

interface PreferencesResponse {
  use_tenant_theme: boolean
  prefer_dark_mode: boolean
}

/**
 * PATCH ``/api/core/me/preferences/`` — updates the user's display
 * prefs (system-vs-tenant theme + light/dark). Invalidates the
 * ``["core", "me"]`` query so ``useUserRole`` re-renders with the
 * new values; the ThemeBridge picks them up on the next tick.
 */
export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  const { tenant } = useTenant()
  return useMutation({
    mutationFn: (body: PreferencesPayload) =>
      api.tenant.patch<PreferencesResponse>("/api/core/me/preferences/", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["core", "me", tenant?.subdomain ?? null] })
    },
  })
}
