/**
 * Floating chat widget for the Sysnord internal agent.
 *
 * Mounted once at the AppShell level so it's available on every page.
 * Hidden when the user isn't authenticated. Two panes:
 *
 * 1. **Conversation list** (left rail when picking a thread).
 * 2. **Active chat thread + composer** with a config/metadata toolbar
 *    pinned beneath the textarea.
 *
 * Three behaviours worth highlighting:
 *
 * * **Composer toolbar** — model picker, reasoning effort, page-context
 *   toggle and running token tally are all permanently visible right
 *   under the input. No hidden settings drawer; everything that affects
 *   the next turn is one click away.
 * * **Action buttons** — when an assistant message carries a
 *   ``request_user_choice`` / ``request_user_confirmation`` tool_call,
 *   we render the options as clickable buttons. Clicking one sends the
 *   chosen value as the next user message so the LLM resumes with the
 *   answer in context.
 * * **Page context** — when the active conversation has the toggle on
 *   AND the current page has registered a context (via
 *   ``stores/page-context-store.ts``), we ship that blob alongside the
 *   chat call. Privacy-by-default: off until the user flips it.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import {
  ChevronLeft, Eye, Loader2, MessageCircle, Plus, Send, Sparkles, Trash2, Wrench, X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { extractApiErrorMessage } from "@/lib/api-client"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"
import { usePageContextStore } from "@/stores/page-context-store"
import {
  useAgentConversation,
  useAgentConversations,
  useAgentModels,
  useCreateAgentConversation,
  useDeleteAgentConversation,
  usePatchAgentConversation,
  useSendAgentMessage,
} from "@/features/agent/hooks"
import {
  type AgentConversation,
  type AgentMessage,
  type AgentModelInfo,
  type ReasoningEffort,
} from "@/features/agent/api"


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtTokens(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}



// ---------------------------------------------------------------------------
// Action buttons (request_user_choice / request_user_confirmation)
// ---------------------------------------------------------------------------
type ChoiceOption = { label: string; value: string; description?: string; variant?: string }

function parseUiToolCall(msg: AgentMessage): null | {
  kind: "choice" | "confirmation"
  question: string
  options: ChoiceOption[]
} {
  if (msg.role !== "assistant") return null
  for (const call of msg.tool_calls ?? []) {
    const name = call.function?.name
    if (name !== "request_user_choice" && name !== "request_user_confirmation") continue
    let args: Record<string, unknown> = {}
    try {
      args = JSON.parse(call.function?.arguments ?? "{}")
    } catch {
      continue
    }
    if (name === "request_user_choice") {
      const opts = Array.isArray(args.options) ? (args.options as ChoiceOption[]) : []
      if (opts.length < 2) continue
      return { kind: "choice", question: String(args.question ?? ""), options: opts }
    }
    // confirmation
    const action = String(args.action ?? "Prosseguir?")
    return {
      kind: "confirmation",
      question: action,
      options: [
        { label: String(args.confirm_label ?? "Sim, prosseguir"), value: "confirm", variant: "primary" },
        { label: String(args.cancel_label ?? "Não"), value: "cancel", variant: "secondary" },
      ],
    }
  }
  return null
}


function ActionButtons(props: {
  question: string
  options: ChoiceOption[]
  onPick: (label: string) => void
  disabled: boolean
  alreadyAnswered: string | null
}) {
  return (
    <div className="my-1 max-w-[90%] space-y-2 rounded-2xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 text-sm dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="text-zinc-900 dark:text-zinc-100">{props.question}</div>
      <div className="flex flex-wrap gap-1.5">
        {props.options.map((opt) => {
          const variant: "default" | "secondary" | "destructive" = (
            opt.variant === "primary" ? "default"
            : opt.variant === "destructive" ? "destructive"
            : "secondary"
          )
          const wasPicked = props.alreadyAnswered != null && props.alreadyAnswered === opt.label
          return (
            <Button
              key={opt.value}
              type="button"
              size="sm"
              variant={variant}
              disabled={props.disabled || props.alreadyAnswered != null}
              onClick={() => props.onPick(opt.label)}
              className={cn(wasPicked && "ring-2 ring-primary")}
              title={opt.description}
            >
              {opt.label}
            </Button>
          )
        })}
      </div>
      {props.alreadyAnswered && (
        <div className="text-xs text-zinc-500">
          Você escolheu: <strong>{props.alreadyAnswered}</strong>
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Tool-call sidecar (non-UI tools: just a "running tool X" pill)
// ---------------------------------------------------------------------------
function ToolPill({ msg, isResult }: { msg: AgentMessage; isResult: boolean }) {
  const calls = msg.tool_calls ?? []
  const label = isResult ? msg.tool_name : calls[0]?.function?.name ?? "tool"
  return (
    <div className="my-1 flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300">
      <Wrench className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      <span className="font-mono">{label}</span>
      <span className="text-zinc-400">{isResult ? "→ resultado" : "chamando"}</span>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Per-message metadata (model + tokens, only for assistant messages)
// ---------------------------------------------------------------------------
function MessageMeta({ msg }: { msg: AgentMessage }) {
  if (msg.role !== "assistant") return null
  const total = (msg.prompt_tokens ?? 0) + (msg.completion_tokens ?? 0)
  if (!msg.model_used && !total) return null
  return (
    <div className="ml-1 mt-0.5 text-[10px] text-zinc-400">
      {msg.model_used && <span className="font-mono">{msg.model_used}</span>}
      {msg.model_used && total > 0 && <span> · </span>}
      {total > 0 && (
        <span>
          {fmtTokens(msg.prompt_tokens)} in · {fmtTokens(msg.completion_tokens)} out
        </span>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Bubble dispatcher
// ---------------------------------------------------------------------------
function MessageRow(props: {
  msg: AgentMessage
  allMessages: AgentMessage[]
  onPickChoice: (label: string) => void
  isSending: boolean
}) {
  const { msg, allMessages, onPickChoice, isSending } = props
  const ui = parseUiToolCall(msg)

  // Tool-call assistants without UI tools → small pill
  if (msg.role === "assistant" && (msg.tool_calls?.length ?? 0) > 0 && !ui) {
    return <ToolPill msg={msg} isResult={false} />
  }
  if (msg.role === "tool") {
    return <ToolPill msg={msg} isResult={true} />
  }

  if (ui) {
    // The "next user message" after this assistant turn is the answer
    // (if it exists). Detect it so we can disable buttons + show "you
    // chose X" — robust to thread navigation.
    const idx = allMessages.findIndex((m) => m.id === msg.id)
    const next = allMessages.slice(idx + 1).find((m) => m.role === "user")
    const alreadyAnswered = next?.content ?? null
    return (
      <div className="flex flex-col gap-1">
        <ActionButtons
          question={ui.question}
          options={ui.options}
          onPick={onPickChoice}
          disabled={isSending}
          alreadyAnswered={alreadyAnswered}
        />
        <MessageMeta msg={msg} />
      </div>
    )
  }

  const isUser = msg.role === "user"
  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div className="flex max-w-[85%] flex-col">
        <div
          className={cn(
            "whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm shadow-sm",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100",
          )}
        >
          {msg.content || <span className="text-zinc-400">…</span>}
        </div>
        <MessageMeta msg={msg} />
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Conversation list
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
      if (props.active === id) props.onPick(0)
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao excluir.")
    }
  }

  return (
    <div className="flex h-full flex-col">
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
              <span className="truncate">{c.title || "Sem título"}</span>
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
// Config + metadata toolbar (under the composer, always visible)
// ---------------------------------------------------------------------------
/** Compact strip shown right beneath the textarea. Holds:
 *
 *  * model picker (compact dropdown — full label in option list, just the
 *    slug as the trigger so it fits in the widget width)
 *  * reasoning effort picker (compact; auto-disabled on models that
 *    don't accept the param)
 *  * page-context toggle (label = registered page title or "—")
 *  * token tally (right-aligned: total + % of context window)
 *
 *  Settings drawer was removed in favour of this — everything that
 *  matters is now visible at a glance instead of behind a gear icon. */
function ComposerToolbar(props: {
  conversation: AgentConversation
  pageTitle: string | null
}) {
  const { conversation, pageTitle } = props
  const models = useAgentModels()
  const patch = usePatchAgentConversation()

  const catalog = models.data
  const currentModel = conversation.model || catalog?.default_model || ""
  const currentEffort = conversation.reasoning_effort || ""
  const currentModelInfo: AgentModelInfo | undefined = catalog?.models.find(
    (m) => m.slug === currentModel,
  )
  const supportsReasoning = currentModelInfo?.supports_reasoning ?? true

  const update = async (body: Parameters<typeof patch.mutateAsync>[0]["body"]) => {
    try {
      await patch.mutateAsync({ id: conversation.id, body })
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao salvar.")
    }
  }

  const totalTokens =
    (conversation.total_input_tokens ?? 0) + (conversation.total_output_tokens ?? 0)
  const window = currentModelInfo?.context_window ?? 0
  const usagePct = window
    ? Math.round(((conversation.total_input_tokens ?? 0) / window) * 100)
    : null

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-zinc-200 px-2 py-1.5 text-[11px] dark:border-zinc-800">
      {/* Model */}
      <select
        value={currentModel}
        onChange={(e) => update({ model: e.target.value })}
        title={
          currentModelInfo
            ? `${currentModelInfo.label} — ${currentModelInfo.description}`
            : "Selecione o modelo"
        }
        className="cursor-pointer rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[11px] hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
      >
        {models.isLoading && <option value="">…</option>}
        {catalog?.models.map((m) => (
          <option key={m.slug} value={m.slug}>
            {m.label}
          </option>
        ))}
      </select>

      {/* Reasoning effort */}
      <select
        value={currentEffort}
        onChange={(e) => update({ reasoning_effort: e.target.value as ReasoningEffort })}
        disabled={!supportsReasoning}
        title={
          supportsReasoning
            ? "Esforço de raciocínio. Maior = mais latência + tokens, mas melhor qualidade analítica."
            : "Modelo selecionado não suporta esforço de raciocínio."
        }
        className="cursor-pointer rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
      >
        <option value="">effort: padrão</option>
        <option value="minimal">effort: minimal</option>
        <option value="low">effort: low</option>
        <option value="medium">effort: medium</option>
        <option value="high">effort: high</option>
      </select>

      {/* Page context toggle */}
      <button
        type="button"
        onClick={() => update({ include_page_context: !conversation.include_page_context })}
        title={
          conversation.include_page_context
            ? "Agente vê o contexto da página atual. Clique para desligar."
            : "Agente NÃO vê a página atual. Clique para ligar."
        }
        className={cn(
          "flex items-center gap-1 rounded border px-1.5 py-0.5 transition",
          conversation.include_page_context
            ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 dark:border-emerald-800/60 dark:bg-emerald-900/30 dark:text-emerald-300"
            : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800",
        )}
      >
        <Eye className="h-3 w-3" />
        <span className="max-w-[120px] truncate">
          {conversation.include_page_context
            ? `tela: ${pageTitle ?? "(sem contexto)"}`
            : "tela: off"}
        </span>
      </button>

      {/* Token tally — right-aligned */}
      <div
        className="ml-auto flex items-center gap-1.5 font-mono text-zinc-500"
        title={
          window
            ? `${conversation.total_input_tokens ?? 0} entrada / ${conversation.total_output_tokens ?? 0} saída · ~${usagePct}% da janela (${window.toLocaleString()} tokens)`
            : `${conversation.total_input_tokens ?? 0} entrada / ${conversation.total_output_tokens ?? 0} saída`
        }
      >
        <span>{fmtTokens(totalTokens)}</span>
        {usagePct != null && (
          <span className={cn(
            "rounded px-1 py-0.5 text-[10px]",
            usagePct >= 80 ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
            : usagePct >= 50 ? "bg-zinc-100 dark:bg-zinc-800"
            : "bg-zinc-50 dark:bg-zinc-900",
          )}>
            {usagePct}%
          </span>
        )}
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Chat thread
// ---------------------------------------------------------------------------
function ChatThread(props: { conversationId: number }) {
  const conversation = useAgentConversation(props.conversationId)
  const sendMut = useSendAgentMessage(props.conversationId)
  const [draft, setDraft] = useState("")
  const scroller = useRef<HTMLDivElement>(null)
  const pageContext = usePageContextStore((s) => s.context)

  useEffect(() => {
    if (!scroller.current) return
    scroller.current.scrollTop = scroller.current.scrollHeight
  }, [conversation.data?.messages.length, sendMut.isPending])

  const conv = conversation.data
  const includeContext = conv?.include_page_context ?? false

  const sendMessage = async (content: string) => {
    if (!content.trim() || sendMut.isPending) return
    try {
      await sendMut.mutateAsync({
        content: content.trim(),
        page_context: includeContext && pageContext ? pageContext : undefined,
      })
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao falar com o agente.")
    }
  }

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const content = draft.trim()
    if (!content) return
    setDraft("")
    await sendMessage(content)
  }

  const messages = conv?.messages ?? []

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
              conciliação e demonstrativos do tenant atual. Ainda não realizo
              alterações nesta versão.
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <MessageRow
              key={m.id}
              msg={m}
              allMessages={messages}
              onPickChoice={sendMessage}
              isSending={sendMut.isPending}
            />
          ))
        )}
        {sendMut.isPending && (
          <div className="flex items-center gap-2 px-1 py-1 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Pensando…
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-zinc-200 px-2 pt-2 dark:border-zinc-800">
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

      {/* Config + metadata toolbar — always visible. */}
      {conv && (
        <ComposerToolbar
          conversation={conv}
          pageTitle={pageContext?.title ?? null}
        />
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Top-level widget
// ---------------------------------------------------------------------------
type Pane = "list" | "chat"

export function AgentChatWidget() {
  const { isAuthenticated } = useAuth()
  const [open, setOpen] = useState(false)
  const [pane, setPane] = useState<Pane>("list")
  const [activeId, setActiveId] = useState<number | null>(null)
  const createMut = useCreateAgentConversation()

  const conversations = useAgentConversations({ enabled: open && activeId == null })

  // Auto-open the most recent thread when the panel opens.
  useEffect(() => {
    if (!open || activeId != null) return
    const data = conversations.data
    const list = data ? (Array.isArray(data) ? data : data.results ?? []) : []
    if (list.length > 0) {
      setActiveId(list[0].id)
      setPane("chat")
    }
  }, [open, activeId, conversations.data])

  if (!isAuthenticated) return null

  const handleNew = async () => {
    try {
      const conv = await createMut.mutateAsync(undefined)
      setActiveId(conv.id)
      setPane("chat")
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao criar conversa.")
    }
  }

  const handlePick = (id: number) => {
    if (id === 0) {
      setActiveId(null)
      setPane("list")
      return
    }
    setActiveId(id)
    setPane("chat")
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

  const showBack = pane !== "list"

  return (
    <div className="fixed bottom-5 right-5 z-40 flex h-[640px] max-h-[85vh] w-[440px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <div className="flex items-center gap-2 text-sm font-medium">
          {showBack && (
            <button
              type="button"
              aria-label="Voltar para lista"
              onClick={() => setPane("list")}
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

      <div className="grid flex-1 overflow-hidden">
        {pane === "list" && (
          <ConversationsList
            active={activeId}
            onPick={handlePick}
            onNew={handleNew}
          />
        )}
        {pane === "chat" && activeId && (
          <ChatThread conversationId={activeId} />
        )}
        {pane === "chat" && !activeId && (
          <div className="flex flex-1 items-center justify-center p-6 text-sm text-zinc-500">
            Selecione uma conversa ou crie uma nova.
          </div>
        )}
      </div>
    </div>
  )
}
