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
    return Promise.reject(error)
  },
)

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
