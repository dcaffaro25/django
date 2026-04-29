import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useTenant } from "@/providers/TenantProvider"

/**
 * Full Company shape returned by ``GET /api/core/companies/<id>/``.
 * Phase E2 added 20 nullable fields on top of name/subdomain --
 * this type lists them as optional so existing tenants whose rows
 * pre-date the migration still parse cleanly.
 */
export interface Company {
  id: number
  name: string
  subdomain: string
  cnpj?: string | null
  razao_social?: string | null
  nome_fantasia?: string | null
  inscricao_estadual?: string | null
  inscricao_municipal?: string | null
  cnae_principal?: string | null
  regime_tributario?: string | null
  endereco_logradouro?: string | null
  endereco_numero?: string | null
  endereco_complemento?: string | null
  endereco_bairro?: string | null
  endereco_cidade?: string | null
  endereco_uf?: string | null
  endereco_cep?: string | null
  email?: string | null
  telefone?: string | null
  website?: string | null
  default_currency?: string
  default_locale?: string
  default_timezone?: string
  created_at?: string
  updated_at?: string
}

/**
 * GET ``/api/core/companies/<id>/`` for the active tenant. Returns
 * the full Company row including all the Phase E2 fiscal fields.
 * The TenantProvider already lists every Company the user belongs
 * to, but for the edit drawer we want the live, full record.
 */
export function useActiveCompany() {
  const { tenant } = useTenant()
  return useQuery({
    queryKey: ["core", "companies", tenant?.id ?? null],
    queryFn: () => api.get<Company>(`/api/core/companies/${tenant?.id}/`),
    enabled: !!tenant?.id,
    staleTime: 60 * 1000,
  })
}

/**
 * PATCH ``/api/core/companies/<id>/``. Manager+ on the server side
 * (the global write-method gate enforces this -- viewers get a
 * friendly toast via the api-client interceptor).
 *
 * Invalidates both the standalone Company query and the bundled
 * ``/api/core/me/`` payload so the topbar / sidebar pick up name,
 * logo, and currency changes immediately after save.
 */
export function useUpdateCompany() {
  const queryClient = useQueryClient()
  const { tenant } = useTenant()
  return useMutation({
    mutationFn: (body: Partial<Company>) =>
      api.patch<Company>(`/api/core/companies/${tenant?.id}/`, body),
    onSuccess: () => {
      const id = tenant?.id ?? null
      queryClient.invalidateQueries({ queryKey: ["core", "companies", id] })
      queryClient.invalidateQueries({ queryKey: ["core", "companies"] })
      queryClient.invalidateQueries({ queryKey: ["core", "me", tenant?.subdomain ?? null] })
    },
  })
}
