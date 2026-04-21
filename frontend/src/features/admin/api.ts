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

  /* ---------------- Activity dashboards ---------------- */
  activitySummary: (days: number = 7) =>
    api.get<ActivitySummaryResponse>("/api/admin/activity/summary/", { params: { days } }),
  activityUserDetail: (userId: number, days: number = 30) =>
    api.get<ActivityUserDetail>(`/api/admin/activity/users/${userId}/`, { params: { days } }),
  activityAreaDetail: (area: string, days: number = 30) =>
    api.get<ActivityAreaDetail>(`/api/admin/activity/areas/${encodeURIComponent(area)}/`, { params: { days } }),
  activityEvents: (params: { user?: number; area?: string; kind?: string; limit?: number; before_id?: number } = {}) =>
    api.get<ActivityEventList>("/api/admin/activity/events/", { params }),
}

/* ---------------- Activity payload types ---------------- */

export interface ActivitySummaryRow {
  user_id: number
  user__username: string
  area: string
  total_ms: number | null
  events: number
}
export interface ActivitySummaryResponse {
  since: string
  days: number
  rows: ActivitySummaryRow[]
}

export interface ActivityByDay {
  date: string
  focused_ms: number | null
  events: number
}
export interface ActivityByArea {
  area: string
  focused_ms: number | null
  events: number
}
export interface ActivityDevice {
  user_agent: string
  viewport_width: number | null
  viewport_height: number | null
  last_seen: string
  sessions: number
}
export interface ActivityRawEvent {
  id: number
  created_at: string
  kind: string
  area: string
  path: string
  action?: string
  target_model?: string
  target_id?: string
  duration_ms?: number | null
  meta?: Record<string, unknown> | null
  user_id?: number
  user__username?: string
  company_id?: number | null
}
export interface ActivityUserDetail {
  user: { id: number; username: string; email?: string; is_superuser?: boolean }
  since: string
  days: number
  totals: { focused_ms: number | null; events: number }
  by_day: ActivityByDay[]
  by_area: ActivityByArea[]
  devices: ActivityDevice[]
  recent_actions: ActivityRawEvent[]
  recent_errors: ActivityRawEvent[]
}
export interface ActivityAreaDetail {
  area: string
  since: string
  days: number
  totals: { focused_ms: number; events: number; distinct_users: number }
  top_users: Array<{ user_id: number; user__username: string; focused_ms: number | null; events: number }>
  top_actions: Array<{ action: string; events: number; avg_duration_ms?: number | null }>
  recent: ActivityRawEvent[]
}
export interface ActivityEventList {
  events: ActivityRawEvent[]
  count: number
}
