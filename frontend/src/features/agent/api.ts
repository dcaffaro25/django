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

export interface AgentConversation {
  id: number
  title: string
  is_archived: boolean
  created_at: string
  updated_at: string
  last_message_at: string
  message_count: number
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
  deleteConversation: (id: number) =>
    api.tenant.delete<void>(`/api/agent/conversations/${id}/`),
  chat: (id: number, content: string) =>
    api.tenant.post<AgentChatResponse>(
      `/api/agent/conversations/${id}/chat/`, { content },
    ),

  // -- catalog (informational; widget uses it for "what can the agent do")
  listTools: () => api.get<{ count: number; tools: AgentTool[] }>("/api/agent/tools/"),
}
