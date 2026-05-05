/**
 * Typed API client for the Sysnord agent endpoints.
 *
 * All routes live under ``/api/agent/`` (no tenant prefix — the connection
 * surface is platform-wide and the chat surface scopes by ``request.tenant``
 * server-side via the multitenancy middleware).
 */
import { api, getStoredTenant, getStoredToken } from "@/lib/api-client"

const FETCH_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"

// ---------------------------------------------------------------------------
// Connection (superuser-only)
// ---------------------------------------------------------------------------
export interface AgentConnectionStatus {
  is_connected: boolean
  is_expired: boolean
  account_email: string
  account_subject: string
  chatgpt_account_id: string
  scopes: string
  connected_by_username: string | null
  connected_at: string | null
  last_refreshed_at: string | null
  expires_at: string | null
  last_error: string
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
export type AgentRole = "user" | "assistant" | "tool" | "system"

export interface AgentMessage {
  id: number
  role: AgentRole
  content: string
  tool_calls: Array<{
    id: string
    type: string
    function: { name: string; arguments: string }
  }>
  tool_call_id: string
  tool_name: string
  model_used: string
  prompt_tokens: number | null
  completion_tokens: number | null
  created_at: string
  attachments?: Array<{
    id: number
    kind: "nfe_xml" | "ofx" | "pdf" | "image" | "other"
    filename: string
    content_type: string
    size_bytes: number
    created_at: string
    summary?: string
  }>
}

export type ReasoningEffort = "" | "minimal" | "low" | "medium" | "high"

export interface AgentConversation {
  id: number
  title: string
  is_archived: boolean
  model: string
  reasoning_effort: ReasoningEffort
  include_page_context: boolean
  created_at: string
  updated_at: string
  last_message_at: string
  message_count: number
  total_input_tokens: number
  total_output_tokens: number
}

export interface AgentConversationPatch {
  title?: string
  model?: string
  reasoning_effort?: ReasoningEffort
  include_page_context?: boolean
  is_archived?: boolean
}

export interface AgentModelInfo {
  slug: string
  label: string
  description: string
  supports_reasoning: boolean
  context_window: number
}

export interface AgentModelsCatalog {
  default_model: string
  reasoning_efforts: ReasoningEffort[]
  models: AgentModelInfo[]
}

export interface PageContextPayload {
  route: string
  title: string
  summary?: string
  data?: Record<string, unknown>
}

export interface ChatRequestBody {
  content: string
  model?: string
  reasoning_effort?: ReasoningEffort
  include_page_context?: boolean
  page_context?: PageContextPayload
  attachment_ids?: number[]
}

/** Returned by ``POST /conversations/{id}/attachments/`` — Phase 2. */
export interface AgentAttachment {
  id: number
  kind: "nfe_xml" | "ofx" | "pdf" | "image" | "other"
  filename: string
  content_type: string
  size_bytes: number
}

/** Audit-log row from ``/audit/tool-calls/`` — Phase 0. */
export interface AgentToolCallLogRow {
  id: number
  tool_name: string
  tool_domain: string
  status: "ok" | "warn" | "error" | "rejected"
  args_summary: string
  error_type: string
  error_message: string
  latency_ms: number | null
  response_size_bytes: number | null
  iteration: number | null
  conversation_id: number | null
  user_id: number | null
  created_at: string
}

/** Audit-log row from ``/audit/writes/`` — Phase 1. */
export interface AgentWriteAuditRow {
  id: number
  tool_name: string
  target_model: string
  target_ids: (number | string)[]
  args_summary: string
  before_state: Record<string, unknown>
  after_state: Record<string, unknown>
  status: "dry_run" | "proposed" | "applied" | "rejected" | "failed" | "undone"
  error_type: string
  error_message: string
  undo_token: string
  conversation_id: number | null
  user_id: number | null
  created_at: string
}

export interface AuditFilters {
  conversation?: number
  tool?: string
  status?: string
  since?: string
  limit?: number
}

export interface AgentConversationDetail extends AgentConversation {
  messages: AgentMessage[]
}

export interface AgentChatResponse {
  iterations: number
  truncated: boolean
  messages: AgentMessage[]
}

/** Server-Sent Event payloads emitted by ``/conversations/{id}/chat/stream/``.
 *  Each is a discriminated-union variant on ``type``. */
export type AgentStreamEvent =
  | { type: "started"; user_message: AgentMessage }
  | { type: "iteration"; n: number }
  | { type: "message"; message: AgentMessage }
  | { type: "final"; iterations: number; truncated: boolean }
  | { type: "error"; detail: string }

export interface AgentStreamHandlers {
  onEvent: (event: AgentStreamEvent) => void
  signal?: AbortSignal
}

export interface AgentTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------
export const agentApi = {
  // -- connection
  getConnectionStatus: () =>
    api.get<AgentConnectionStatus>("/api/agent/connection/"),
  revokeConnection: () =>
    api.delete<{ detail: string }>("/api/agent/connection/"),

  // -- chat (tenant-scoped — server mounts these under /<tenant>/api/agent/
  // and the api.tenant.* helpers prepend the active tenant subdomain)
  listConversations: () =>
    api.tenant.get<AgentConversation[] | { results: AgentConversation[] }>(
      "/api/agent/conversations/",
    ),
  getConversation: (id: number) =>
    api.tenant.get<AgentConversationDetail>(`/api/agent/conversations/${id}/`),
  createConversation: (title?: string) =>
    api.tenant.post<AgentConversation>("/api/agent/conversations/", { title: title ?? "" }),
  patchConversation: (id: number, body: AgentConversationPatch) =>
    api.tenant.patch<AgentConversation>(`/api/agent/conversations/${id}/`, body),
  deleteConversation: (id: number) =>
    api.tenant.delete<void>(`/api/agent/conversations/${id}/`),
  chat: (id: number, body: ChatRequestBody) =>
    api.tenant.post<AgentChatResponse>(`/api/agent/conversations/${id}/chat/`, body),

  /**
   * Streaming variant of ``chat``. Uses ``fetch`` (not axios) because
   * axios doesn't expose the body as a ``ReadableStream`` in the
   * browser. The server emits SSE-framed events; we parse them line by
   * line and call ``onEvent`` for each one. The promise resolves once
   * the server closes the stream (or rejects if the network fails).
   *
   * Falls through to the caller's ``onEvent`` for the ``error`` SSE
   * event -- the caller decides whether to toast/log/abort. The promise
   * itself only rejects on transport-level failures.
   */
  chatStream: async (
    id: number,
    body: ChatRequestBody,
    handlers: AgentStreamHandlers,
  ): Promise<void> => {
    const tenant = getStoredTenant()
    if (!tenant) throw new Error("No tenant selected. Set one via TenantProvider.")
    const token = getStoredToken()
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    }
    if (token) headers["Authorization"] = `Token ${token}`
    const url = `${FETCH_BASE_URL}/${tenant}/api/agent/conversations/${id}/chat/stream/`

    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: handlers.signal,
      credentials: "include",
    })

    if (!res.ok || !res.body) {
      // Best-effort error parse: the server emits JSON DRF errors for
      // pre-stream failures (auth, validation). Only after we start
      // yielding SSE does the connection switch to text/event-stream.
      let detail = `Falha ao iniciar streaming (HTTP ${res.status}).`
      try {
        const data = await res.json()
        if (typeof data?.detail === "string") detail = data.detail
      } catch {
        // body was not JSON; keep the generic message.
      }
      handlers.onEvent({ type: "error", detail })
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder("utf-8")
    let buffer = ""

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE: events are separated by blank lines (``\n\n``). Each event
      // is one or more ``data: <json>`` lines; we only emit a single
      // ``data:`` line per event, so the parser is intentionally
      // simple. Anything else (comments, retry hints) is ignored.
      let sepIdx = buffer.indexOf("\n\n")
      while (sepIdx !== -1) {
        const raw = buffer.slice(0, sepIdx).trim()
        buffer = buffer.slice(sepIdx + 2)
        if (raw.startsWith("data:")) {
          const json = raw.slice(5).trim()
          if (json) {
            try {
              const parsed = JSON.parse(json) as AgentStreamEvent
              handlers.onEvent(parsed)
            } catch (err) {
              // A malformed event shouldn't break the rest of the
              // stream — log it and keep reading.
              // eslint-disable-next-line no-console
              console.warn("agent.stream.parse_failed", err, json)
            }
          }
        }
        sepIdx = buffer.indexOf("\n\n")
      }
    }
  },

  /** Upload a single file as a chat attachment — Phase 2. The conversation
   * scopes the file to the right tenant; the chat endpoint then references
   * the returned ID via ``attachment_ids: [...]``.
   *
   * Optional ``onProgress`` callback receives a number 0..100 each time
   * Axios fires its upload-progress event — used by the chip UI to show
   * a real percentage instead of an indeterminate spinner. */
  uploadAttachment: (
    conversationId: number,
    file: File,
    opts?: { onProgress?: (pct: number) => void },
  ) => {
    const fd = new FormData()
    fd.append("file", file)
    return api.tenant.post<AgentAttachment>(
      `/api/agent/conversations/${conversationId}/attachments/`,
      fd,
      {
        // Let the browser set the multipart boundary by removing the
        // default JSON Content-Type the api-client interceptor stamps.
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (event) => {
          if (!opts?.onProgress || !event.total) return
          opts.onProgress(Math.round((event.loaded / event.total) * 100))
        },
      },
    )
  },

  // -- platform (read-only, any authenticated user)
  listTools: () => api.get<{ count: number; tools: AgentTool[] }>("/api/agent/tools/"),
  listModels: () => api.get<AgentModelsCatalog>("/api/agent/models/"),

  // -- audit (tenant-scoped, read-only)
  listToolCallLog: (filters: AuditFilters = {}) =>
    api.tenant.get<{ count: number; tool_calls: AgentToolCallLogRow[] }>(
      "/api/agent/audit/tool-calls/", { params: filters as Record<string, unknown> },
    ),
  listWriteAudit: (filters: AuditFilters = {}) =>
    api.tenant.get<{ count: number; writes: AgentWriteAuditRow[] }>(
      "/api/agent/audit/writes/", { params: filters as Record<string, unknown> },
    ),
}
