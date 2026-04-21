import { api } from "@/lib/api-client"

// These endpoints are cross-tenant and gated by backend IsSuperUser —
// use the non-tenant ``api.*`` helpers, not ``api.tenant.*``.

export interface AdminCompany {
  id: number
  name: string
  subdomain: string
}

export interface AdminUserMembership {
  id: number
  company: number
  company_name: string
  company_subdomain: string
  role: "owner" | "manager" | "operator" | "viewer"
  is_primary: boolean
}

export interface AdminUser {
  id: number
  username: string
  email: string | null
  first_name: string
  last_name: string
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
  last_login: string | null
  date_joined: string
  must_change_password: boolean
  companies: AdminUserMembership[]
}

export interface AdminUserWritable {
  username?: string
  email?: string | null
  first_name?: string
  last_name?: string
  is_active?: boolean
  is_staff?: boolean
  is_superuser?: boolean
  password?: string
  set_companies?: Array<{ company: number; role?: string; is_primary?: boolean }>
}

/** DRF paginated (or not, per viewset). Admin endpoints currently use
 *  page-number pagination with ``results``; we unwrap to an array here. */
function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === "object" && "results" in data) {
    return (data as { results: T[] }).results
  }
  return []
}

export const adminApi = {
  listUsers: (q?: string) =>
    api.get<AdminUser[] | { results: AdminUser[] }>(
      "/api/admin/users/",
      q ? { params: { q } } : undefined,
    ).then(unwrap<AdminUser>),
  getUser: (id: number) => api.get<AdminUser>(`/api/admin/users/${id}/`),
  createUser: (body: AdminUserWritable) => api.post<AdminUser>("/api/admin/users/", body),
  updateUser: (id: number, body: AdminUserWritable) =>
    api.patch<AdminUser>(`/api/admin/users/${id}/`, body),
  deactivateUser: (id: number) => api.delete<void>(`/api/admin/users/${id}/`),
  setActive: (id: number, isActive: boolean) =>
    api.post<{ id: number; is_active: boolean }>(
      `/api/admin/users/${id}/set_active/`,
      { is_active: isActive },
    ),
  resetPassword: (id: number) =>
    api.post<{
      user_id: number
      username: string
      temporary_password: string
      must_change_password: boolean
    }>(`/api/admin/users/${id}/reset_password/`),

  listCompanies: () => api.get<AdminCompany[]>("/api/admin/companies/"),
}
