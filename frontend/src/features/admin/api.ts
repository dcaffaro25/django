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
  activityFunnels: (days: number = 30) =>
    api.get<ActivityFunnelsResponse>("/api/admin/activity/funnels/", { params: { days } }),
  activityFriction: (days: number = 30) =>
    api.get<ActivityFrictionResponse>("/api/admin/activity/friction/", { params: { days } }),
  /** GET /api/admin/integrity/ledger/ — how many Transactions have
   *  ΣDebit ≠ ΣCredit, broken down by company. Canary for PR 8's
   *  backfill ("missing cash legs") progress. */
  ledgerIntegrity: () =>
    api.get<LedgerIntegrityResponse>("/api/admin/integrity/ledger/"),

  /** POST /api/admin/activity/digest/run/ — run the weekly digest
   *  synchronously. ``dry_run=true`` returns stats without
   *  emailing; useful for "show me what would be sent". */
  runActivityDigest: (body: { days?: number; dry_run?: boolean; to?: string } = {}) =>
    api.post<{
      sent: boolean
      recipient?: string
      xlsx_bytes?: number
      subject?: string
      filename?: string
      reason?: string
    }>("/api/admin/activity/digest/run/", body),

  /* ---------------- Error reports ---------------- */
  listErrorReports: (params: {
    kind?: string
    resolved?: "true" | "false" | "any"
    days?: number
    order?: "last_seen" | "count"
    limit?: number
  } = {}) =>
    api.get<ErrorReportListResponse>("/api/admin/activity/errors/", { params }),
  getErrorReport: (id: number) =>
    api.get<ErrorReportDetailResponse>(`/api/admin/activity/errors/${id}/`),
  resolveErrorReport: (id: number, body: { resolved: boolean; note?: string }) =>
    api.post<{
      id: number
      is_resolved: boolean
      is_reopened: boolean
      resolved_at: string | null
      resolution_note: string
    }>(`/api/admin/activity/errors/${id}/`, body),
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

export interface FunnelStepResult {
  id: string
  label: string
  reached: number
  /** Null on the first step (nothing to drop-off from). */
  dropoff_pct: number | null
  timing_from_previous: {
    p50_ms?: number | null
    p95_ms?: number | null
    median_ms?: number
    samples?: number
  }
}
export interface FunnelResult {
  id: string
  label: string
  description: string
  entered: number
  completed: number
  overall_pct: number | null
  steps: FunnelStepResult[]
}
export interface ActivityFunnelsResponse {
  days: number
  since: string
  funnels: FunnelResult[]
}

export interface BackAndForthRow {
  from_area: string
  to_area: string
  count: number
  sample_users: Array<{ id: number; username: string }>
}
export interface LongDwellRow {
  session_id: number
  area: string
  user_id: number
  username: string
  focused_ms: number
}
export interface RepeatErrorRow {
  user_id: number
  username: string
  area: string
  errors: number
  first_at: string
  last_at: string
  sample_messages: Array<string | null>
}
export interface SlowActionRow {
  action: string
  area: string
  samples: number
  p50_ms: number | null
  p95_ms: number | null
  median_ms: number
  max_ms: number
}
export interface ActivityFrictionResponse {
  days: number
  since: string
  back_and_forth: BackAndForthRow[]
  long_dwell_no_action: LongDwellRow[]
  repeat_errors: RepeatErrorRow[]
  slow_actions: SlowActionRow[]
}

/* ---------------- Error reports ---------------- */

export type ErrorReportKind = "frontend" | "backend_drf" | "backend_django" | "celery"

export interface ErrorReport {
  id: number
  fingerprint: string
  kind: ErrorReportKind
  error_class: string
  message: string
  path: string
  method: string
  status_code: number | null
  count: number
  affected_users: number
  first_seen_at: string
  last_seen_at: string
  is_resolved: boolean
  is_reopened: boolean
  resolved_at: string | null
  resolution_note: string
}

export interface ErrorReportDetail extends ErrorReport {
  sample_stack: string
}

export interface ErrorReportListResponse {
  days: number
  count: number
  errors: ErrorReport[]
}

export interface ErrorOccurrence {
  id: number
  created_at: string
  user_id: number | null
  user__username: string | null
  path: string
  meta: {
    error_class?: string
    message?: string
    stack?: string
    status_code?: number | null
    method?: string
    breadcrumbs?: Array<{ ts: number; kind: string; area?: string; path?: string; action?: string }>
    [key: string]: unknown
  } | null
}

export interface ErrorReportDetailResponse {
  report: ErrorReportDetail
  recent_occurrences: ErrorOccurrence[]
  by_user: Array<{ user_id: number; user__username: string; n: number }>
}

export interface LedgerIntegrityRow {
  company_id: number
  company_name: string
  count: number
  imbalance_sum: string  // serialised Decimal
  sample_tx_ids: number[]
}
export interface LedgerIntegrityResponse {
  total: number
  imbalance_sum: string
  by_company: LedgerIntegrityRow[]
}
