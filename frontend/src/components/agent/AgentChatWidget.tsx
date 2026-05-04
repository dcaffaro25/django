/**
 * Floating chat widget for the Sysnord internal agent.
 *
 * Mounted once at the AppShell level so it's available on every page.
 * Renders nothing when the user isn't authenticated; collapsed (just a
 * bubble) by default; expands into a side panel with conversation list +
 * active thread + input.
 *
 * The agent loop runs server-side (synchronous request/response) — no
 * streaming yet. Intermediate ``tool`` messages from the loop are
 * shown as compact "running tool X" cards so the user sees what the
 * agent did, not just the final answer.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import {
  ChevronLeft, Loader2, MessageCircle, Plus, Send, Sparkles, Trash2, Wrench, X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { extractApiErrorMessage } from "@/lib/api-client"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"
import {
  useAgentConversation,
  useAgentConversations,
  useCreateAgentConversation,
  useDeleteAgentConversation,
  useSendAgentMessage,
} from "@/features/agent/hooks"
import {
  type AgentConversation,
  type AgentMessage,
} from "@/features/agent/api"


// ---------------------------------------------------------------------------
// Tool-call sidecar — compact card for the tool turns
// ---------------------------------------------------------------------------
function ToolCallCard({ msg }: { msg: AgentMessage }) {
  const isToolResult = msg.role === "tool"
  const calls = msg.tool_calls ?? []
  const label = isToolResult ? msg.tool_name : calls[0]?.function?.name ?? "tool"
  return (
    <div className="my-1 flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300">
      <Wrench className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      <span className="font-mono">{label}</span>
      <span className="text-zinc-400">{isToolResult ? "→ resultado" : "chamando"}</span>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Bubble (assistant or user content)
// ---------------------------------------------------------------------------
function MessageBubble({ msg }: { msg: AgentMessage }) {
  if (msg.role === "tool" || (msg.role === "assistant" && (msg.tool_calls?.length ?? 0) > 0)) {
    return <ToolCallCard msg={msg} />
  }

  const isUser = msg.role === "user"
  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100",
        )}
      >
        {msg.content || <span className="text-zinc-400">…</span>}
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Conversation list (left rail of the panel)
// ---------------------------------------------------------------------------
function ConversationsList(props: {
  active: number | null
  onPick: (id: number) => void
  onNew: () => void
}) {
  const conversations = useAgentConversations()
  const deleteMut = useDeleteAgentConversation()

  const list = useMemo<AgentConversation[]>(() => {
    const data = conversations.data
    if (!data) return []
    return Array.isArray(data) ? data : data.results ?? []
  }, [conversations.data])

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteMut.mutateAsync(id)
      if (props.active === id) props.onPick(0)  // 0 = no selection sentinel
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao excluir.")
    }
  }

  return (
    <div className="flex h-full flex-col border-r border-zinc-200 dark:border-zinc-800">
      <div className="border-b border-zinc-200 p-2 dark:border-zinc-800">
        <Button variant="default" size="sm" className="w-full" onClick={props.onNew}>
          <Plus className="mr-1.5 h-4 w-4" /> Nova conversa
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {conversations.isLoading ? (
          <div className="flex items-center justify-center p-6">
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          </div>
        ) : list.length === 0 ? (
          <div className="p-3 text-xs text-zinc-500">Nenhuma conversa ainda.</div>
        ) : (
          list.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => props.onPick(c.id)}
              className={cn(
                "group flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition",
                props.active === c.id
                  ? "bg-zinc-100 dark:bg-zinc-800"
                  : "hover:bg-zinc-50 dark:hover:bg-zinc-900",
              )}
            >
              <span className="truncate">
                {c.title || "Sem título"}
              </span>
              <span
                role="button"
                tabIndex={0}
                aria-label="Excluir conversa"
                onClick={(e) => handleDelete(c.id, e)}
                className="opacity-0 transition group-hover:opacity-60 hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Chat thread (right side of the panel)
// ---------------------------------------------------------------------------
function ChatThread({ conversationId }: { conversationId: number }) {
  const conversation = useAgentConversation(conversationId)
  const sendMut = useSendAgentMessage(conversationId)
  const [draft, setDraft] = useState("")
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Scroll to bottom whenever new messages land.
    if (!scroller.current) return
    scroller.current.scrollTop = scroller.current.scrollHeight
  }, [conversation.data?.messages.length, sendMut.isPending])

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const content = draft.trim()
    if (!content || sendMut.isPending) return
    setDraft("")
    try {
      await sendMut.mutateAsync(content)
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao falar com o agente.")
    }
  }

  const messages = conversation.data?.messages ?? []

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="flex-1 space-y-2 overflow-y-auto p-3">
        {conversation.isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-zinc-500">
            <Sparkles className="h-6 w-6 text-zinc-400" />
            <div className="font-medium text-zinc-700 dark:text-zinc-300">
              Olá! Sou o assistente Sysnord.
            </div>
            <div className="text-xs">
              Posso consultar contas, transações, NFs, faturas, sugestões de
              conciliação e demonstrativos do tenant atual. Não realizo
              alterações nesta versão.
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
        {sendMut.isPending && (
          <div className="flex items-center gap-2 px-1 py-1 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Pensando…
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-zinc-200 p-2 dark:border-zinc-800">
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void handleSubmit()
              }
            }}
            placeholder="Pergunte algo sobre seus dados…"
            rows={2}
            className="flex-1 resize-none rounded-md border border-zinc-200 bg-white px-2.5 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-primary dark:border-zinc-800 dark:bg-zinc-900"
          />
          <Button type="submit" size="sm" disabled={sendMut.isPending || !draft.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Top-level widget (bubble + side panel)
// ---------------------------------------------------------------------------
export function AgentChatWidget() {
  const { isAuthenticated } = useAuth()
  const [open, setOpen] = useState(false)
  const [showList, setShowList] = useState(true)
  const [activeId, setActiveId] = useState<number | null>(null)
  const createMut = useCreateAgentConversation()

  // Auto-open the most recent thread when the panel opens.
  const conversations = useAgentConversations({ enabled: open && activeId == null })
  useEffect(() => {
    if (!open || activeId != null) return
    const data = conversations.data
    const list = data ? (Array.isArray(data) ? data : data.results ?? []) : []
    if (list.length > 0) setActiveId(list[0].id)
  }, [open, activeId, conversations.data])

  if (!isAuthenticated) return null

  const handleNew = async () => {
    try {
      const conv = await createMut.mutateAsync(undefined)
      setActiveId(conv.id)
      setShowList(false)
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao criar conversa.")
    }
  }

  const handlePick = (id: number) => {
    if (id === 0) {
      setActiveId(null)
      return
    }
    setActiveId(id)
    setShowList(false)
  }

  if (!open) {
    return (
      <button
        type="button"
        aria-label="Abrir agente Sysnord"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:opacity-90"
      >
        <MessageCircle className="h-5 w-5" />
      </button>
    )
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex h-[600px] max-h-[85vh] w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl dark:border-zinc-800 dark:bg-zinc-950">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <div className="flex items-center gap-2 text-sm font-medium">
          {!showList && (
            <button
              type="button"
              aria-label="Voltar para lista"
              onClick={() => setShowList(true)}
              className="rounded p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
          <Sparkles className="h-4 w-4 text-primary" />
          Agente Sysnord
        </div>
        <button
          type="button"
          aria-label="Fechar agente"
          onClick={() => setOpen(false)}
          className="rounded p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="grid flex-1 overflow-hidden" style={{ gridTemplateColumns: showList ? "1fr" : "1fr" }}>
        {showList ? (
          <ConversationsList
            active={activeId}
            onPick={handlePick}
            onNew={handleNew}
          />
        ) : activeId ? (
          <ChatThread conversationId={activeId} />
        ) : (
          <div className="flex flex-1 items-center justify-center p-6 text-sm text-zinc-500">
            Selecione uma conversa ou crie uma nova.
          </div>
        )}
      </div>
    </div>
  )
}
