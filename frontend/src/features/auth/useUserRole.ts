import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useAuth } from "@/providers/AuthProvider"
import { useTenant } from "@/providers/TenantProvider"

/** Tenant role values the backend returns. ``superuser`` is the
 *  string literal sent for Django superusers; all others come from
 *  ``UserCompanyMembership.ROLE_CHOICES``. ``null`` means the user
 *  isn't a member of the active tenant (the middleware would have
 *  404'd the request, but the hook still has to type the loading /
 *  no-tenant state). */
export type TenantRole = "viewer" | "operator" | "manager" | "owner" | "superuser" | null

const ROLE_RANK: Record<Exclude<TenantRole, null>, number> = {
  viewer: 1,
  operator: 2,
  manager: 3,
  owner: 4,
  // Treat superuser as effectively above every tenant role -- the
  // backend already grants them access globally; this rank just
  // makes ``isAtLeast(...)`` always return true for superusers.
  superuser: 99,
}

/** Brand palette tokens (CSS variable equivalents). Open shape so
 *  the design system can grow without a TS bump. Keys mirror the
 *  Tailwind / shadcn surface vocabulary (background / foreground /
 *  primary / accent / muted / border / ring / good / warn / bad). */
export type BrandPalette = Record<string, string>

/** Category palette is an ordered list -- chart series cycle
 *  through it. 14 colours by convention but the type is open. */
export type CategoryPalette = string[]

export interface TenantThemePayload {
  id: number
  company: number
  brand_palette_light: BrandPalette
  brand_palette_dark: BrandPalette
  category_palette_light: CategoryPalette
  category_palette_dark: CategoryPalette
  logo_url: string | null
  logo_dark_url: string | null
  favicon_url: string | null
  updated_at: string
}

export interface MeUser {
  id: number
  username: string
  email?: string | null
  first_name?: string
  last_name?: string
  is_superuser: boolean
  use_tenant_theme: boolean
  prefer_dark_mode: boolean
}

export interface MeCompany {
  id: number
  name: string
  subdomain: string
  nome_fantasia?: string | null
  cnpj?: string | null
  default_currency?: string
  default_locale?: string
  default_timezone?: string
}

interface MePayload {
  user: MeUser
  role: TenantRole
  company: MeCompany | null
  theme: TenantThemePayload | null
}

/**
 * Per-tenant role of the active user. Drives role-aware UI:
 *   * ``isViewer`` — true when the user is a read-only viewer; hide
 *     write buttons + write-heavy sections in the sidebar.
 *   * ``canWrite`` — alias for "role above viewer" (operator+).
 *   * ``isAtLeast(min)`` — gate finer-grained sections (e.g.
 *     manager-only tenant config).
 *
 * Backed by ``GET /api/core/me/`` which the ``TenantMiddleware``
 * annotates per request. Cached for 60s; invalidated automatically
 * when the active tenant changes (the queryKey includes the
 * subdomain).
 */
export function useUserRole() {
  const { isAuthenticated } = useAuth()
  const { tenant } = useTenant()

  const { data, isLoading } = useQuery({
    queryKey: ["core", "me", tenant?.subdomain ?? null],
    queryFn: () => api.tenant.get<MePayload>("/api/core/me/"),
    enabled: isAuthenticated && !!tenant,
    staleTime: 60 * 1000,
  })

  const role: TenantRole = data?.role ?? null

  const isAtLeast = (min: Exclude<TenantRole, null | "superuser">) => {
    if (!role) return false
    return ROLE_RANK[role] >= ROLE_RANK[min]
  }

  return {
    role,
    me: data?.user ?? null,
    company: data?.company ?? null,
    theme: data?.theme ?? null,
    isLoading,
    /** True when the user can ONLY read. Hide every write button on
     *  the page if this is true. */
    isViewer: role === "viewer",
    /** Negation of ``isViewer`` for code paths that read better as
     *  "is the operator allowed to mutate?". Superusers always pass. */
    canWrite: role != null && role !== "viewer",
    /** Manager-or-above gate (e.g. tenant config edit, user management). */
    isManager: role != null && (role === "manager" || role === "owner" || role === "superuser"),
    /** Owner-or-above gate (e.g. dangerous deletes, billing changes). */
    isOwner: role != null && (role === "owner" || role === "superuser"),
    isSuperuser: role === "superuser",
    isAtLeast,
  }
}
