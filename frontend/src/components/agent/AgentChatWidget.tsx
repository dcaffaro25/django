/**
 * Floating chat widget for the Sysnord internal agent.
 *
 * Mounted once at the AppShell level so it's available on every page.
 * Hidden when the user isn't authenticated. Renders three panels stacked
 * inside one floating card:
 *
 * 1. Conversation list (left rail when picking a thread).
 * 2. Active chat thread + composer.
 * 3. Settings drawer (model / reasoning / page-context toggle), reachable
 *    via the gear icon in the chat header.
 *
 * Three behaviours worth highlighting:
 *
 * * **Token metadata** — running totals in the header pill (input +
 *   output tokens for the active thread); per-assistant-message tokens
 *   in a small footer beneath each bubble.
 * * **Action buttons** — when an assistant message carries a
 *   ``request_user_choice`` / ``request_user_confirmation`` tool_call,
 *   we render the options as clickable buttons. Clicking one sends the
 *   chosen value as the next user message, so the LLM resumes with the
 *   answer in context.
 * * **Page context** — when the active conversation has the toggle on
 *   AND the current page has registered a context, we ship that blob
 *   alongside every chat call. The agent's system prompt explains what
 *   the user is looking at. Privacy-by-default: off until the user
 *   flips it inside settings.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import {
  ChevronLeft, Loader2, MessageCircle, Plus, Send, Settings, Sparkles, Trash2, Wrench, X,
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

function fmtPercent(used: number, total: number): string {
  if (!total) return "—"
  return `${Math.round((used / total) * 100)}%`
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
// Settings panel (model / reasoning / page-context)
// ---------------------------------------------------------------------------
function SettingsPanel(props: { conversation: AgentConversation; onBack: () => void }) {
  const { conversation } = props
  const models = useAgentModels()
  const patch = usePatchAgentConversation()

  const catalog = models.data
  const currentModel = conversation.model || catalog?.default_model || ""
  const currentEffort = conversation.reasoning_effort || ""
  const currentModelInfo = catalog?.models.find((m) => m.slug === currentModel)
  const supportsReasoning = currentModelInfo?.supports_reasoning ?? true

  const update = async (body: Parameters<typeof patch.mutateAsync>[0]["body"]) => {
    try {
      await patch.mutateAsync({ id: conversation.id, body })
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao salvar.")
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 text-sm font-medium dark:border-zinc-800">
        <button
          type="button" aria-label="Voltar"
          onClick={props.onBack}
          className="rounded p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <Settings className="h-4 w-4 text-primary" />
        Configurações da conversa
      </div>

      <div className="space-y-5 p-4 text-sm">
        {/* Model */}
        <div>
          <label className="mb-1 block font-medium">Modelo</label>
          {models.isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          ) : (
            <select
              value={currentModel}
              onChange={(e) => update({ model: e.target.value })}
              className="w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 dark:border-zinc-800 dark:bg-zinc-900"
            >
              {catalog?.models.map((m) => (
                <option key={m.slug} value={m.slug}>
                  {m.label}
                </option>
              ))}
            </select>
          )}
          {currentModelInfo && (
            <div className="mt-1 text-xs text-zinc-500">
              {currentModelInfo.description}
              {" · "}
              <span className="font-mono">~{Math.round(currentModelInfo.context_window / 1000)}k tokens</span>
            </div>
          )}
        </div>

        {/* Reasoning effort */}
        <div>
          <label className="mb-1 block font-medium">
            Esforço de raciocínio
            {!supportsReasoning && (
              <span className="ml-2 text-xs font-normal text-zinc-400">
                (modelo não suporta)
              </span>
            )}
          </label>
          <select
            value={currentEffort}
            onChange={(e) => update({ reasoning_effort: e.target.value as ReasoningEffort })}
            disabled={!supportsReasoning}
            className="w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900"
          >
            <option value="">Padrão</option>
            <option value="minimal">Minimal — respostas rápidas</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High — análises mais cuidadosas</option>
          </select>
          <div className="mt-1 text-xs text-zinc-500">
            Maior esforço = mais latência + mais tokens, mas melhor qualidade
            em perguntas analíticas.
          </div>
        </div>

        {/* Page context */}
        <div>
          <label className="flex items-start gap-2 font-medium">
            <input
              type="checkbox"
              checked={conversation.include_page_context}
              onChange={(e) => update({ include_page_context: e.target.checked })}
              className="mt-0.5"
            />
            <span>
              Considerar a tela atual
              <div className="font-normal text-xs text-zinc-500">
                Quando ligado, o agente recebe o contexto da página em que
                você está (rota, filtros, IDs selecionados). Off = só vê a
                identidade do tenant.
              </div>
            </span>
          </label>
        </div>

        {/* Token totals */}
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="font-medium text-zinc-700 dark:text-zinc-300">Tokens nesta conversa</div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-zinc-600 dark:text-zinc-400">
            <div>
              <div className="font-mono">{fmtTokens(conversation.total_input_tokens)}</div>
              <div>Entrada</div>
            </div>
            <div>
              <div className="font-mono">{fmtTokens(conversation.total_output_tokens)}</div>
              <div>Saída</div>
            </div>
            <div>
              <div className="font-mono">
                {fmtTokens((conversation.total_input_tokens ?? 0) + (conversation.total_output_tokens ?? 0))}
              </div>
              <div>Total</div>
            </div>
          </div>
          {currentModelInfo && (
            <div className="mt-2 text-zinc-500">
              ~{fmtPercent(
                conversation.total_input_tokens ?? 0,
                currentModelInfo.context_window,
              )} da janela do modelo.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Chat thread
// ---------------------------------------------------------------------------
function ChatThread(props: {
  conversationId: number
  onOpenSettings: () => void
}) {
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
      {/* Per-thread header bar (model + tokens hint + settings) */}
      <div className="flex items-center justify-between gap-2 border-b border-zinc-200 px-3 py-1.5 text-xs dark:border-zinc-800">
        <div className="flex items-center gap-2 text-zinc-500">
          {conv?.model ? (
            <span className="font-mono">{conv.model}</span>
          ) : (
            <span className="italic text-zinc-400">modelo padrão</span>
          )}
          {conv?.reasoning_effort && (
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">
              effort: {conv.reasoning_effort}
            </span>
          )}
          {includeContext && pageContext && (
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
              👁 {pageContext.title}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          {conv && (
            <span className="font-mono" title="Tokens nesta conversa (entrada + saída)">
              {fmtTokens((conv.total_input_tokens ?? 0) + (conv.total_output_tokens ?? 0))}
            </span>
          )}
          <button
            type="button"
            onClick={props.onOpenSettings}
            aria-label="Configurações"
            className="rounded p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

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
// Top-level widget
// ---------------------------------------------------------------------------
type Pane = "list" | "chat" | "settings"

export function AgentChatWidget() {
  const { isAuthenticated } = useAuth()
  const [open, setOpen] = useState(false)
  const [pane, setPane] = useState<Pane>("list")
  const [activeId, setActiveId] = useState<number | null>(null)
  const createMut = useCreateAgentConversation()

  const conversation = useAgentConversation(activeId)
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
          <ChatThread
            conversationId={activeId}
            onOpenSettings={() => setPane("settings")}
          />
        )}
        {pane === "settings" && conversation.data && (
          <SettingsPanel
            conversation={conversation.data}
            onBack={() => setPane("chat")}
          />
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
