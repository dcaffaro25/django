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

import {
  agentApi,
  type AgentConversationPatch,
  type AgentMessage,
  type ChatRequestBody,
} from "./api"

const KEY_CONNECTION = ["agent", "connection"] as const
const KEY_TOOLS = ["agent", "tools"] as const
const KEY_MODELS = ["agent", "models"] as const
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

/** Curated model catalog (gpt-5.5 / gpt-5.4 / mini / codex…). Cached
 *  for an hour because it's a static config endpoint. */
export function useAgentModels(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: KEY_MODELS,
    queryFn: agentApi.listModels,
    staleTime: 60 * 60_000,
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

/** Patch the per-conversation agent config (model / reasoning / page-context
 *  toggle / title / archived). Optimistic-updates both the list cache and
 *  the detail cache so the widget reflects the change without a refetch. */
export function usePatchAgentConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AgentConversationPatch }) =>
      agentApi.patchConversation(id, body),
    onSuccess: (data, vars) => {
      qc.setQueryData(conversationKey(vars.id), (prev: { messages: AgentMessage[] } | undefined) => {
        if (!prev) return data
        return { ...prev, ...data }
      })
      qc.invalidateQueries({ queryKey: KEY_CONVERSATIONS })
    },
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
    mutationFn: (body: ChatRequestBody) => agentApi.chat(conversationId, body),
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


/**
 * Upload one file to an agent conversation — Phase 2. Returns the new
 * attachment row's metadata; the caller then passes ``attachment.id``
 * to ``useSendAgentMessage`` via ``attachment_ids: [...]``.
 *
 * The ``onProgress`` callback fires with 0..100 as bytes are sent —
 * the widget surfaces it as a real percentage on the attachment chip.
 *
 * No cache invalidation here — attachments are referenced by message,
 * not surfaced as a top-level list.
 */
export function useUploadAgentAttachment(conversationId: number) {
  return useMutation({
    mutationFn: ({ file, onProgress }: {
      file: File
      onProgress?: (pct: number) => void
    }) => agentApi.uploadAttachment(conversationId, file, { onProgress }),
  })
}


/** Audit-log readers — Phase 0/1 visibility surface. Tenant-scoped via
 *  the api.tenant.* helpers. Refetches every 15s by default since the
 *  audit log is append-only and operators usually want fresh data. */
export function useAgentToolCallLog(
  filters: import("./api").AuditFilters = {},
  options: { enabled?: boolean; refetchIntervalMs?: number } = {},
) {
  return useQuery({
    queryKey: ["agent", "audit", "tool-calls", filters] as const,
    queryFn: () => agentApi.listToolCallLog(filters),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchIntervalMs ?? 15_000,
  })
}

export function useAgentWriteAudit(
  filters: import("./api").AuditFilters = {},
  options: { enabled?: boolean; refetchIntervalMs?: number } = {},
) {
  return useQuery({
    queryKey: ["agent", "audit", "writes", filters] as const,
    queryFn: () => agentApi.listWriteAudit(filters),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchIntervalMs ?? 15_000,
  })
}
