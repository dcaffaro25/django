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
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import {
  AlertCircle, CheckCircle2, ChevronLeft, Eye, FileText, Image as ImageIcon, Loader2,
  MessageCircle, Paperclip, Plus, Send, Sparkles, Trash2, Wrench, X,
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
  useUploadAgentAttachment,
} from "@/features/agent/hooks"
import {
  type AgentAttachment,
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

function parseInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const tokenRe = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = tokenRe.exec(text)) != null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    const token = match[0]
    const key = `${keyPrefix}-${match.index}`
    if (token.startsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-black/5 px-1 py-0.5 font-mono text-[0.92em] dark:bg-white/10">
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>)
    }
    lastIndex = match.index + token.length
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function isMarkdownTable(lines: string[], index: number): boolean {
  const header = lines[index]?.trim() ?? ""
  const divider = lines[index + 1]?.trim() ?? ""
  return header.startsWith("|") && header.endsWith("|") && /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(divider)
}

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim())
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n")
  const blocks: ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i] ?? ""

    if (!line.trim()) {
      i += 1
      continue
    }

    if (line.trim().startsWith("```")) {
      const codeLines: string[] = []
      i += 1
      while (i < lines.length && !(lines[i] ?? "").trim().startsWith("```")) {
        codeLines.push(lines[i] ?? "")
        i += 1
      }
      if (i < lines.length) i += 1
      blocks.push(
        <pre key={`code-${i}`} className="my-1 max-w-full overflow-auto rounded-md bg-black/5 px-2.5 py-2 font-mono text-xs leading-relaxed dark:bg-white/10">
          {codeLines.join("\n")}
        </pre>,
      )
      continue
    }

    if (isMarkdownTable(lines, i)) {
      const headers = splitTableRow(lines[i] ?? "")
      i += 2
      const rows: string[][] = []
      while (i < lines.length && (lines[i] ?? "").trim().startsWith("|")) {
        rows.push(splitTableRow(lines[i] ?? ""))
        i += 1
      }
      blocks.push(
        <div key={`table-${i}`} className="my-1 max-w-full overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-700">
          <table className="w-full min-w-max border-collapse text-left text-xs">
            <thead className="bg-black/5 dark:bg-white/10">
              <tr>
                {headers.map((h, idx) => (
                  <th key={`${h}-${idx}`} className="border-b border-zinc-200 px-2 py-1.5 font-semibold dark:border-zinc-700">
                    {parseInlineMarkdown(h, `th-${i}-${idx}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => (
                <tr key={`row-${rowIdx}`} className="border-t border-zinc-100 dark:border-zinc-800">
                  {headers.map((_, cellIdx) => (
                    <td key={`cell-${rowIdx}-${cellIdx}`} className="px-2 py-1.5 align-top">
                      {parseInlineMarkdown(row[cellIdx] ?? "", `td-${i}-${rowIdx}-${cellIdx}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*[-*]\s+/, ""))
        i += 1
      }
      blocks.push(
        <ul key={`ul-${i}`} className="my-1 list-disc space-y-1 pl-5">
          {items.map((item, idx) => (
            <li key={`${idx}-${item.slice(0, 12)}`}>{parseInlineMarkdown(item, `li-${i}-${idx}`)}</li>
          ))}
        </ul>,
      )
      continue
    }

    const paragraph: string[] = [line]
    i += 1
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !(lines[i] ?? "").trim().startsWith("```") &&
      !isMarkdownTable(lines, i) &&
      !/^\s*[-*]\s+/.test(lines[i] ?? "")
    ) {
      paragraph.push(lines[i] ?? "")
      i += 1
    }
    blocks.push(
      <p key={`p-${i}`} className="my-1">
        {parseInlineMarkdown(paragraph.join(" "), `p-${i}`)}
      </p>,
    )
  }

  return <>{blocks.length ? blocks : <span className="text-zinc-400">...</span>}</>
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
// Tool-call sidecar
//
// For "calling" rows: just the tool name pill (the agent's about to run it).
// For "result" rows: parse the tool's JSON response and surface a
// domain-aware chip — write tools get a "X applied · undo" affordance,
// reads stay as the simple pill.
// ---------------------------------------------------------------------------

/** Pull the tool result blob out of a ROLE_TOOL message. The runtime
 *  stores it as a JSON string in ``content``; bad JSON falls back to
 *  null. */
function parseToolResult(msg: AgentMessage): Record<string, unknown> | null {
  if (msg.role !== "tool") return null
  const raw = msg.content || ""
  if (!raw.trim().startsWith("{")) return null
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return null
  }
}

/** Detect a "write tool result" by the audit_id field the runtime
 *  attaches. Used to choose the rich chip vs the simple one. */
function isWriteToolResult(parsed: Record<string, unknown> | null): boolean {
  return !!parsed && typeof parsed["audit_id"] === "number"
}

function fmtCounter(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("pt-BR")
  return String(value ?? "?")
}

function compactToolValue(value: unknown): string {
  if (value == null) return ""
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function summarizeToolResult(parsed: Record<string, unknown> | null, raw: string): string {
  if (!parsed) {
    const trimmed = raw.trim()
    return trimmed ? trimmed.slice(0, 120) : "Sem conteúdo retornado"
  }

  const error = parsed["error"] || parsed["detail"] || parsed["message"]
  if (error) return compactToolValue(error).slice(0, 120)

  const counters = parsed["counters"]
  if (counters && typeof counters === "object") {
    const pairs = Object.entries(counters as Record<string, unknown>)
      .slice(0, 3)
      .map(([key, value]) => `${key}: ${fmtCounter(value)}`)
    if (pairs.length > 0) return pairs.join(" · ")
  }

  if (Array.isArray(parsed["rows"])) return `${parsed["rows"].length.toLocaleString("pt-BR")} linha(s)`
  if (Array.isArray(parsed["results"])) return `${parsed["results"].length.toLocaleString("pt-BR")} resultado(s)`
  if (typeof parsed["count"] === "number") return `${parsed["count"].toLocaleString("pt-BR")} item(ns)`
  if (typeof parsed["ok"] === "boolean") return parsed["ok"] ? "Concluído" : "Retornou erro"

  const keys = Object.keys(parsed).slice(0, 4)
  return keys.length > 0 ? keys.join(" · ") : "Resultado recebido"
}

function ToolOutputPreview({ msg, parsed }: { msg: AgentMessage; parsed: Record<string, unknown> | null }) {
  const raw = msg.content || ""
  if (!raw.trim()) return null
  const pretty = parsed ? compactToolValue(parsed) : raw

  return (
    <details className="mt-1 w-full min-w-0 max-w-full overflow-hidden rounded-md border border-zinc-200 bg-white/70 dark:border-zinc-800 dark:bg-zinc-950/60">
      <summary className="cursor-pointer select-none px-2.5 py-1 text-[11px] font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
        Ver saída da ferramenta
      </summary>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words border-t border-zinc-200 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
        {pretty}
      </pre>
    </details>
  )
}

function WriteResultChip({ msg, parsed }: { msg: AgentMessage; parsed: Record<string, unknown> }) {
  const tool = msg.tool_name
  const ok = parsed["ok"] !== false
  const dryRun = !!parsed["dry_run_effective"]
  const blocked = !!parsed["blocked_by_policy"]
  const auditId = parsed["audit_id"] as number | null
  const undoToken = parsed["undo_token"] as string | null
  const counters = (parsed["counters"] || {}) as Record<string, unknown>
  const errorStr = (parsed["error"] || "") as string

  // Domain-specific summary line.
  let summary = ""
  if (tool === "run_reconciliation_agent") {
    const auto = counters["n_auto_accepted"] ?? 0
    const amb = counters["n_ambiguous"] ?? 0
    const cand = counters["n_candidates"] ?? 0
    summary = `${fmtCounter(auto)} aceitos · ${fmtCounter(amb)} ambíguos · ${fmtCounter(cand)} candidatos`
  } else if (tool === "apply_document_mapping") {
    const inv = parsed["invoice_id"] as number | null
    const lines = ((parsed["line_ids"] as unknown[]) || []).length
    summary = inv ? `Invoice #${inv} criada · ${lines} linha(s)` : `${lines} linha(s) propostas`
  } else if (tool === "accept_recon_decision") {
    const reconId = parsed["reconciliation_id"] as number | null
    summary = reconId ? `Reconciliation #${reconId} criada` : "decisão aceita (proposta)"
  } else if (tool === "reject_recon_decision") {
    summary = "rejeição registrada"
  } else if (tool === "undo_via_audit") {
    summary = "reversão executada"
  }

  const tone =
    !ok          ? "border-red-300 bg-red-50 text-red-800 dark:border-red-800/50 dark:bg-red-900/30 dark:text-red-200"
    : blocked    ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800/50 dark:bg-amber-900/30 dark:text-amber-200"
    : dryRun     ? "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
    : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800/50 dark:bg-emerald-900/30 dark:text-emerald-200"

  const Icon = !ok ? AlertCircle : (dryRun || blocked) ? Eye : CheckCircle2

  return (
    <div className={cn("my-1 flex w-fit max-w-full min-w-0 items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs", tone)}>
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 truncate font-mono text-[11px]" title={tool}>{tool}</span>
      {summary && <span>· {summary}</span>}
      {dryRun && !blocked && <span className="text-[10px] uppercase opacity-70">· dry-run</span>}
      {blocked && <span className="text-[10px] uppercase opacity-70">· bloqueado</span>}
      {!ok && errorStr && (
        <span className="truncate text-[10px] opacity-80" title={errorStr}>· {errorStr.slice(0, 60)}</span>
      )}
      {auditId != null && (
        <span className="ml-auto text-[10px] opacity-50" title={undoToken ? `undo_token: ${undoToken}` : undefined}>
          audit #{auditId}{undoToken ? " · ↶" : ""}
        </span>
      )}
    </div>
  )
}

function ToolPill({ msg, isResult }: { msg: AgentMessage; isResult: boolean }) {
  const calls = msg.tool_calls ?? []
  const label = isResult ? msg.tool_name : calls[0]?.function?.name ?? "tool"
  const labels = isResult ? [label] : calls.map((call) => call.function?.name).filter(Boolean)

  // For result rows on write tools, render the rich chip.
  if (isResult) {
    const parsed = parseToolResult(msg)
    if (isWriteToolResult(parsed)) {
      return <WriteResultChip msg={msg} parsed={parsed!} />
    }
  }

  return (
    <div className="my-1 flex max-w-full min-w-0 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300">
      <Wrench className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      <span className="min-w-0 truncate font-mono" title={labels.join(", ")}>
        {labels.length > 1 ? labels.join(", ") : label}
      </span>
      <span className="text-zinc-400">{isResult ? "→ resultado" : "chamando"}</span>
    </div>
  )
}

function ToolResultRow({ msg }: { msg: AgentMessage }) {
  const parsed = parseToolResult(msg)
  const summary = summarizeToolResult(parsed, msg.content || "")

  return (
    <div className="my-1 max-w-full min-w-0">
      <ToolPill msg={msg} isResult={true} />
      {summary && (
        <div className="mt-1 max-w-full truncate pl-1 text-[11px] text-zinc-500 dark:text-zinc-400" title={summary}>
          {summary}
        </div>
      )}
      <ToolOutputPreview msg={msg} parsed={parsed} />
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
    return <ToolResultRow msg={msg} />
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
  const attachments = msg.attachments ?? []
  return (
    <div className={cn("flex w-full min-w-0", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[85%] min-w-0 flex-col gap-1", isUser ? "items-end" : "items-start")}>
        {attachments.length > 0 && (
          <div className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
            {attachments.map((a) => {
              const Icon = a.kind === "image" ? ImageIcon : FileText
              const summary = a.summary?.trim()
              return (
                <div
                  key={a.id}
                  className="flex max-w-[280px] flex-col gap-0.5 rounded-md border border-zinc-200 bg-white px-2 py-1 text-[11px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-200"
                  title={`${a.filename} (${a.kind})`}
                >
                  <div className="flex items-center gap-1.5">
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate font-medium">{a.filename}</span>
                    <span className="text-[10px] opacity-60">· {fmtBytes(a.size_bytes)}</span>
                  </div>
                  {summary && (
                    <div className="ml-5 truncate text-[10px] text-zinc-500 dark:text-zinc-400" title={summary}>
                      {summary}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
        <div
          className={cn(
            "max-w-full break-words rounded-2xl px-3.5 py-2 text-sm shadow-sm",
            isUser && "whitespace-pre-wrap",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100",
          )}
        >
          {msg.content ? <MarkdownMessage content={msg.content} /> : <span className="text-zinc-400">...</span>}
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
// ---------------------------------------------------------------------------
// Attachment chip — shown below the textarea while files are pending or being
// uploaded. ``status`` distinguishes the in-flight pre-upload state from the
// "ready to send" state where ``id`` is populated.
// ---------------------------------------------------------------------------
type PendingAttachment =
  | { localId: string; status: "uploading"; file: File; progress: number }
  | { localId: string; status: "ready"; file: File; attachment: AgentAttachment }
  | { localId: string; status: "error"; file: File; error: string }

function attachmentIcon(att: PendingAttachment) {
  const kind = att.status === "ready" ? att.attachment.kind : null
  if (kind === "image") return <ImageIcon className="h-3.5 w-3.5 shrink-0" />
  return <FileText className="h-3.5 w-3.5 shrink-0" />
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

function AttachmentChip(props: { att: PendingAttachment; onRemove: () => void }) {
  const { att } = props
  const tone =
    att.status === "uploading" ? "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
    : att.status === "ready"   ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800/50 dark:bg-emerald-900/30 dark:text-emerald-200"
    : "border-red-300 bg-red-50 text-red-800 dark:border-red-800/50 dark:bg-red-900/30 dark:text-red-200"
  return (
    <div className={cn(
      "relative flex max-w-[220px] items-center gap-1.5 overflow-hidden rounded-md border px-2 py-1 text-[11px]",
      tone,
    )}>
      {att.status === "uploading"
        ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
        : attachmentIcon(att)}
      <span className="truncate font-medium" title={att.file.name}>{att.file.name}</span>
      <span className="text-[10px] opacity-70">
        {att.status === "uploading"
          ? `· ${att.progress}%`
          : `· ${fmtBytes(att.file.size)}`}
      </span>
      <button
        type="button"
        onClick={props.onRemove}
        className="ml-1 -mr-1 rounded p-0.5 opacity-60 hover:opacity-100"
        aria-label={`Remover ${att.file.name}`}
      >
        <X className="h-3 w-3" />
      </button>
      {/* Progress fill — narrow strip at the bottom of the chip while uploading */}
      {att.status === "uploading" && (
        <div
          className="absolute bottom-0 left-0 h-[2px] bg-primary/70 transition-all"
          style={{ width: `${att.progress}%` }}
        />
      )}
    </div>
  )
}


function ChatThread(props: { conversationId: number }) {
  const conversation = useAgentConversation(props.conversationId)
  const sendMut = useSendAgentMessage(props.conversationId)
  const uploadMut = useUploadAgentAttachment(props.conversationId)
  const [draft, setDraft] = useState("")
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [dragOver, setDragOver] = useState(false)
  const dragCounter = useRef(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const pageContext = usePageContextStore((s) => s.context)

  useEffect(() => {
    if (!scroller.current) return
    scroller.current.scrollTop = scroller.current.scrollHeight
  }, [conversation.data?.messages.length, sendMut.isPending])

  const conv = conversation.data
  const includeContext = conv?.include_page_context ?? false

  // Upload one file. Adds an "uploading" chip immediately, then transitions
  // to "ready" or "error" once the server replies. Progress events update
  // the chip's strip in real time.
  const uploadFile = async (file: File) => {
    const localId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setAttachments((prev) => [...prev, { localId, status: "uploading", file, progress: 0 }])
    const onProgress = (pct: number) => {
      setAttachments((prev) =>
        prev.map((a) =>
          a.localId === localId && a.status === "uploading"
            ? { ...a, progress: pct }
            : a,
        ),
      )
    }
    try {
      const attachment = await uploadMut.mutateAsync({ file, onProgress })
      setAttachments((prev) =>
        prev.map((a) =>
          a.localId === localId
            ? { localId, status: "ready", file, attachment }
            : a,
        ),
      )
    } catch (e) {
      const msg = extractApiErrorMessage(e) ?? "Falha ao subir o arquivo."
      setAttachments((prev) =>
        prev.map((a) =>
          a.localId === localId
            ? { localId, status: "error", file, error: msg }
            : a,
        ),
      )
      toast.error(`${file.name}: ${msg}`)
    }
  }

  const handleFiles = (fileList: FileList | File[] | null) => {
    if (!fileList) return
    const arr = Array.from(fileList)
    for (const f of arr) void uploadFile(f)
  }

  // Drag-and-drop overlay state. We need a counter (not a flag) because the
  // browser fires dragenter/dragleave for every nested element — without
  // counting, hovering over a child element flickers the overlay off.
  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.types.includes("Files")) {
      dragCounter.current += 1
      setDragOver(true)
    }
  }
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    dragCounter.current = Math.max(0, dragCounter.current - 1)
    if (dragCounter.current === 0) setDragOver(false)
  }
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.types.includes("Files")) {
      e.dataTransfer.dropEffect = "copy"
    }
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    dragCounter.current = 0
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  const removeAttachment = (localId: string) => {
    setAttachments((prev) => prev.filter((a) => a.localId !== localId))
  }

  const sendMessage = async (content: string) => {
    if (sendMut.isPending) return
    const ready = attachments.filter((a) => a.status === "ready")
    if (!content.trim() && ready.length === 0) return
    try {
      await sendMut.mutateAsync({
        content: content.trim(),
        page_context: includeContext && pageContext ? pageContext : undefined,
        attachment_ids: ready.map((a) => (a as { attachment: AgentAttachment }).attachment.id),
      })
      // Clear pending attachments after a successful send. Errored chips
      // are also cleared — they're not worth re-trying without the user
      // re-attaching the file.
      setAttachments([])
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao falar com o agente.")
    }
  }

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const content = draft.trim()
    setDraft("")
    await sendMessage(content)
  }

  const messages = conv?.messages ?? []
  const hasReadyAttachment = attachments.some((a) => a.status === "ready")
  const isUploading = attachments.some((a) => a.status === "uploading")

  return (
    <div
      className="relative flex h-full min-h-0 flex-col"
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {/* Drop-zone overlay — visible only while a file is being dragged. */}
      {dragOver && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-primary/5 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-primary/60 bg-white/90 px-6 py-4 text-sm font-medium text-primary shadow-sm dark:bg-zinc-900/90">
            <Paperclip className="h-5 w-5" />
            Solte os arquivos para anexar
          </div>
        </div>
      )}

      <div ref={scroller} className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3">
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
              conciliação e demonstrativos do tenant atual. Anexe NF-e XML,
              OFX, PDFs ou imagens para que eu analise junto.
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

      <form onSubmit={handleSubmit} className="shrink-0 border-t border-zinc-200 px-2 pt-2 dark:border-zinc-800">
        {attachments.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1.5">
            {attachments.map((att) => (
              <AttachmentChip
                key={att.localId}
                att={att}
                onRemove={() => removeAttachment(att.localId)}
              />
            ))}
          </div>
        )}
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
            placeholder={
              attachments.length > 0
                ? "Adicione uma instrução ou aperte Enter para enviar…"
                : "Pergunte algo sobre seus dados…"
            }
            rows={2}
            className="flex-1 resize-none rounded-md border border-zinc-200 bg-white px-2.5 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-primary dark:border-zinc-800 dark:bg-zinc-900"
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".xml,.ofx,.pdf,image/*,application/xml,text/xml,application/pdf"
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files)
              // Reset so re-selecting the same file fires onChange again.
              e.target.value = ""
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={sendMut.isPending}
            onClick={() => fileInputRef.current?.click()}
            title="Anexar arquivo"
            aria-label="Anexar arquivo"
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          <Button
            type="submit"
            size="sm"
            disabled={
              sendMut.isPending
              || isUploading
              || (!draft.trim() && !hasReadyAttachment)
            }
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </form>

      {/* Config + metadata toolbar — always visible. */}
      {conv && (
        <div className="shrink-0">
        <ComposerToolbar
          conversation={conv}
          pageTitle={pageContext?.title ?? null}
        />
        </div>
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

      <div className="grid min-h-0 flex-1 overflow-hidden">
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
