/**
 * React Query hooks for the agent surface.
 *
 * Two clusters:
 *  * connection (superuser admin page) — status, start, revoke
 *  * chat (floating widget) — conversations CRUD + send-message
 *
 * Cache keys are intentionally short ("agent.*") so widget invalidations
 * don't accidentally bust unrelated queries.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { agentApi, type AgentMessage } from "./api"

const KEY_CONNECTION = ["agent", "connection"] as const
const KEY_TOOLS = ["agent", "tools"] as const
const KEY_CONVERSATIONS = ["agent", "conversations"] as const
const conversationKey = (id: number) => ["agent", "conversation", id] as const

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------
export function useAgentConnectionStatus(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: KEY_CONNECTION,
    queryFn: agentApi.getConnectionStatus,
    refetchInterval: 60_000,
    enabled: opts.enabled ?? true,
  })
}

export function useStartAgentConnection() {
  return useMutation({
    mutationFn: agentApi.startConnection,
  })
}

export function useRevokeAgentConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: agentApi.revokeConnection,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_CONNECTION }),
  })
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------
export function useAgentTools(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: KEY_TOOLS,
    queryFn: agentApi.listTools,
    staleTime: 5 * 60_000,
    enabled: opts.enabled ?? true,
  })
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------
export function useAgentConversations(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: KEY_CONVERSATIONS,
    queryFn: agentApi.listConversations,
    staleTime: 30_000,
    enabled: opts.enabled ?? true,
  })
}

export function useAgentConversation(id: number | null) {
  return useQuery({
    queryKey: id ? conversationKey(id) : ["agent", "conversation", "none"],
    queryFn: () => agentApi.getConversation(id as number),
    enabled: id != null,
  })
}

export function useCreateAgentConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title?: string) => agentApi.createConversation(title),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_CONVERSATIONS }),
  })
}

export function useDeleteAgentConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => agentApi.deleteConversation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_CONVERSATIONS })
    },
  })
}

/**
 * Send a message and append the resulting messages onto the cached
 * conversation detail so the chat widget renders them immediately
 * (no second roundtrip).
 */
export function useSendAgentMessage(conversationId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => agentApi.chat(conversationId, content),
    onSuccess: (data) => {
      qc.setQueryData(
        conversationKey(conversationId),
        (prev: { messages: AgentMessage[] } | undefined) => {
          if (!prev) return prev
          // The endpoint returns ALL messages produced by this turn — user +
          // any intermediate tool turns + the final assistant. Append all.
          const ids = new Set(prev.messages.map((m) => m.id))
          const fresh = data.messages.filter((m) => !ids.has(m.id))
          return { ...prev, messages: [...prev.messages, ...fresh] }
        },
      )
      qc.invalidateQueries({ queryKey: KEY_CONVERSATIONS })
    },
  })
}
