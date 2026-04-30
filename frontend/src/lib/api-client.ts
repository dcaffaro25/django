import axios, { AxiosInstance, AxiosRequestConfig } from "axios"

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"

const TOKEN_KEY = "nord.auth.token"
const TENANT_KEY = "nord.tenant.subdomain"

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) ?? (import.meta.env.VITE_DEV_TOKEN as string | undefined) ?? null
}

export function setStoredToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getStoredTenant(): string | null {
  return localStorage.getItem(TENANT_KEY) ?? (import.meta.env.VITE_DEFAULT_TENANT as string | undefined) ?? null
}

export function setStoredTenant(subdomain: string | null) {
  if (subdomain) localStorage.setItem(TENANT_KEY, subdomain)
  else localStorage.removeItem(TENANT_KEY)
}

const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 60_000,
})

http.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers ?? {}
    ;(config.headers as Record<string, string>).Authorization = `Token ${token}`
  }
  return config
})

// Track the last 403-role-block toast so a burst of write attempts
// (e.g. a form that accidentally calls a mutation twice) doesn't
// stack 5 identical toasts. 3-second debounce is enough for a real
// click-then-click sequence to surface fresh feedback.
let _lastRoleBlockToastAt = 0
let _last5xxToastAt = 0
let _lastTenant404ToastAt = 0

/**
 * Pull a human-readable error string out of an Axios error response
 * if the server gave us anything useful. Walks the common DRF shapes:
 *
 *   * ``{detail: "..."}``                       — APIException default
 *   * ``{field: ["msg", "..."]}``               — serializer errors
 *   * ``{non_field_errors: ["msg"]}``
 *
 * Falls back to ``null`` when the body isn't a structured error
 * (e.g. Django's debug HTML page on 500). Callers can substitute
 * their own copy in that case.
 */
export function extractApiErrorMessage(error: unknown): string | null {
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (!data) return null
  if (typeof data === "string") {
    // HTML responses (Django debug pages) are useless to operators.
    return data.startsWith("<") ? null : data
  }
  if (typeof data !== "object") return null
  const obj = data as Record<string, unknown>
  if (typeof obj.detail === "string") return obj.detail
  if (Array.isArray(obj.non_field_errors) && typeof obj.non_field_errors[0] === "string") {
    return obj.non_field_errors[0] as string
  }
  // First field-level error wins. Format as ``field: message`` so
  // the operator can tell which input failed validation.
  for (const [key, value] of Object.entries(obj)) {
    if (Array.isArray(value) && typeof value[0] === "string") return `${key}: ${value[0]}`
    if (typeof value === "string") return `${key}: ${value}`
  }
  return null
}

http.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401) {
      // Clear only if it was not a dev token (avoid blowing away env token)
      if (localStorage.getItem(TOKEN_KEY)) setStoredToken(null)
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.href = "/login"
      }
    }
    if (error?.response?.status === 403) {
      // The viewer-write gate in TenantMiddleware emits this exact
      // detail; surface a friendly toast instead of letting each
      // call site reinvent the message. Other 403s (per-viewset
      // permissions) get a generic toast — at worst a duplicate
      // with a less-specific copy, never silent failure.
      const detail = error.response?.data?.detail || ""
      const isRoleBlock = typeof detail === "string" && detail.includes("Read-only access")
      const now = Date.now()
      if (now - _lastRoleBlockToastAt > 3000) {
        _lastRoleBlockToastAt = now
        // Lazy import so the api-client doesn't depend on sonner at
        // module-load (sonner pulls React internals).
        void import("sonner").then(({ toast }) => {
          if (isRoleBlock) {
            toast.error("Apenas operadores podem fazer alterações nesta tela.")
          } else {
            toast.error("Sem permissão para esta ação.")
          }
        })
      }
    }
    // Tenant-scoped 404s usually mean the user has no
    // ``UserCompanyMembership`` for the URL's tenant — the middleware
    // 404s the whole prefix to avoid leaking which tenants exist.
    // Without a toast the workbench just looks empty, so surface a
    // hint pointing operators at the right fix.
    if (error?.response?.status === 404) {
      const url: string = error.response?.config?.url || error.config?.url || ""
      const tenantSub = getStoredTenant()
      const looksTenantScoped =
        !!tenantSub && (url.startsWith(`/${tenantSub}/`) || url.includes(`/${tenantSub}/`))
      const detail = error.response?.data?.detail || ""
      const isCompanyNotFound =
        typeof detail === "string" && detail.toLowerCase().includes("company not found")
      if (looksTenantScoped && (isCompanyNotFound || detail === "")) {
        const now = Date.now()
        if (now - _lastTenant404ToastAt > 5000) {
          _lastTenant404ToastAt = now
          void import("sonner").then(({ toast }) => {
            toast.error(
              `Sem acesso a esta empresa (${tenantSub}). Peça a um administrador para vincular seu usuário ao tenant.`,
            )
          })
        }
      }
    }
    if (error?.response?.status >= 500 && error.response.status < 600) {
      // Server-side crashes used to surface as a generic "Erro ao
      // salvar" in the calling component, which hid the underlying
      // cause (most commonly: a migration that hasn't been applied
      // on the deploy box). Toast a short version + log the full
      // body so the next time it happens, operators can act on it.
      const detail = extractApiErrorMessage(error)
      const now = Date.now()
      if (now - _last5xxToastAt > 3000) {
        _last5xxToastAt = now
        void import("sonner").then(({ toast }) => {
          toast.error(
            detail
              ? `Erro do servidor: ${detail}`
              : "Erro do servidor (500). Verifique se as migrações estão aplicadas e se o servidor foi reiniciado.",
          )
        })
      }
    }
    return Promise.reject(error)
  },
)

// Tap the response pipeline for error telemetry. Kept in a separate
// module so the interceptor can be unit-tested in isolation and so
// this file doesn't import from the telemetry layer (which already
// imports from here).
try {
  // Lazy import to avoid a circular init sequence at module load.
  void import("@/lib/error-capture").then(({ attachAxiosErrorCapture }) =>
    attachAxiosErrorCapture(http),
  )
} catch {
  /* telemetry is best-effort */
}

function tenantPrefixed(path: string): string {
  const tenant = getStoredTenant()
  if (!tenant) throw new Error("No tenant selected. Set one via TenantProvider.")
  const clean = path.startsWith("/") ? path : `/${path}`
  return `/${tenant}${clean}`
}

/** GET a tenant-scoped endpoint, e.g. `api.tenant.get("/api/reconciliation-tasks/")`. */
export const api = {
  /** Global (non-tenant) endpoints, e.g. `/api/core/companies/`, `/api/meta/...`. */
  get: <T = unknown>(path: string, config?: AxiosRequestConfig) => http.get<T>(path, config).then((r) => r.data),
  post: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.post<T>(path, body, config).then((r) => r.data),
  put: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.put<T>(path, body, config).then((r) => r.data),
  patch: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.patch<T>(path, body, config).then((r) => r.data),
  delete: <T = unknown>(path: string, config?: AxiosRequestConfig) => http.delete<T>(path, config).then((r) => r.data),

  /** Tenant-scoped variants — prepend the current tenant slug automatically. */
  tenant: {
    get: <T = unknown>(path: string, config?: AxiosRequestConfig) =>
      http.get<T>(tenantPrefixed(path), config).then((r) => r.data),
    post: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
      http.post<T>(tenantPrefixed(path), body, config).then((r) => r.data),
    put: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
      http.put<T>(tenantPrefixed(path), body, config).then((r) => r.data),
    patch: <T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig) =>
      http.patch<T>(tenantPrefixed(path), body, config).then((r) => r.data),
    delete: <T = unknown>(path: string, config?: AxiosRequestConfig) =>
      http.delete<T>(tenantPrefixed(path), config).then((r) => r.data),
  },
}

/** DRF paginated list — many endpoints return plain arrays, some return `{count, results}`. */
export function unwrapList<T>(data: T[] | { results: T[] } | undefined | null): T[] {
  if (!data) return []
  if (Array.isArray(data)) return data
  if (typeof data === "object" && "results" in data && Array.isArray((data as { results: T[] }).results)) {
    return (data as { results: T[] }).results
  }
  return []
}
