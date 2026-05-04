/**
 * Typed API client for the Sysnord agent endpoints.
 *
 * All routes live under ``/api/agent/`` (no tenant prefix — the connection
 * surface is platform-wide and the chat surface scopes by ``request.tenant``
 * server-side via the multitenancy middleware).
 */
import { api } from "@/lib/api-client"

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
}

export interface AgentConversationDetail extends AgentConversation {
  messages: AgentMessage[]
}

export interface AgentChatResponse {
  iterations: number
  truncated: boolean
  messages: AgentMessage[]
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

  // -- platform (read-only, any authenticated user)
  listTools: () => api.get<{ count: number; tools: AgentTool[] }>("/api/agent/tools/"),
  listModels: () => api.get<AgentModelsCatalog>("/api/agent/models/"),
}
