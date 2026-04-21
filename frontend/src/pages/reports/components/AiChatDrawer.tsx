import { useEffect, useRef, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import {
  Sparkles, Send, X, Check, XCircle, Loader2, MessageSquare, Plus, Pencil, Trash2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  applyOperation,
  describeOperation,
  useAiChat,
} from "@/features/reports"
import type {
  ChatOperation,
  AiChatMessage,
  ReportResult,
  TemplateDocument,
  PeriodPreset,
} from "@/features/reports"

interface ChatTurn {
  id: string
  role: "user" | "assistant"
  content: string
  operations?: ChatOperation[]
  /** Which operations have already been accepted/rejected (by index). */
  opStatus?: Record<number, "accepted" | "rejected">
}

/**
 * Right-side chat drawer. Each assistant turn may come with a list of
 * proposed operations that appear as diff cards the user accepts or rejects
 * individually. The chat itself doesn't mutate the editor — onOperation
 * bubbles the accepted operation up.
 */
export function AiChatDrawer({
  open,
  onClose,
  doc,
  preview,
  onDocChange,
  onPeriodPreset,
}: {
  open: boolean
  onClose: () => void
  doc: TemplateDocument
  preview: ReportResult | null
  onDocChange: (next: TemplateDocument) => void
  onPeriodPreset: (preset: PeriodPreset) => void
}) {
  const chat = useAiChat()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState("")
  const scrollerRef = useRef<HTMLDivElement>(null)

  // Keep scroll pinned to the latest turn when it updates.
  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight
    }
  }, [turns, chat.isPending])

  const send = async () => {
    const text = input.trim()
    if (!text) return
    const userTurn: ChatTurn = {
      id: mkId(),
      role: "user",
      content: text,
    }
    const nextTurns = [...turns, userTurn]
    setTurns(nextTurns)
    setInput("")

    // Backend wants the full conversation (last 10 turns are kept
    // server-side too, but we can send more for context).
    const messages: AiChatMessage[] = nextTurns.map((t) => ({
      role: t.role,
      content: t.content,
    }))

    try {
      const res = await chat.mutateAsync({
        messages,
        document: doc,
        preview_result: preview ?? undefined,
      })
      setTurns((t) => [
        ...t,
        {
          id: mkId(),
          role: "assistant",
          content: res.assistant_message || "(sem resposta)",
          operations: res.operations,
          opStatus: {},
        },
      ])
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { error?: string } } })?.response?.data
      const msg = resp?.error ?? (err instanceof Error ? err.message : "Falha na IA")
      setTurns((t) => [
        ...t,
        { id: mkId(), role: "assistant", content: `❌ ${msg}` },
      ])
    }
  }

  const handleAccept = (turnId: string, idx: number, op: ChatOperation) => {
    if (op.op === "set_period_preset") {
      onPeriodPreset(op.preset)
      markOp(turnId, idx, "accepted")
      toast.success("Predefinição aplicada")
      return
    }
    const res = applyOperation(doc, op)
    if (!res.applied) {
      toast.error(res.reason ?? "Não foi possível aplicar")
      markOp(turnId, idx, "rejected")
      return
    }
    onDocChange(res.doc)
    markOp(turnId, idx, "accepted")
    toast.success("Aplicado")
  }

  const handleReject = (turnId: string, idx: number) => {
    markOp(turnId, idx, "rejected")
  }

  const markOp = (turnId: string, idx: number, status: "accepted" | "rejected") => {
    setTurns((list) =>
      list.map((t) =>
        t.id === turnId
          ? { ...t, opStatus: { ...(t.opStatus ?? {}), [idx]: status } }
          : t,
      ),
    )
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      send()
    }
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Sparkles className="h-4 w-4 text-amber-500" />
              Chat com a IA
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div ref={scrollerRef} className="flex-1 space-y-3 overflow-y-auto p-3 text-[12px]">
            {turns.length === 0 && (
              <EmptyState />
            )}
            {turns.map((turn) => (
              <div key={turn.id} className={cn("space-y-2", turn.role === "user" && "items-end")}>
                <div
                  className={cn(
                    "rounded-lg px-3 py-2 text-[12px]",
                    turn.role === "user"
                      ? "ml-8 bg-primary/10 text-right"
                      : "mr-8 bg-muted/50",
                  )}
                >
                  <div className="whitespace-pre-wrap">{turn.content}</div>
                </div>
                {turn.operations && turn.operations.length > 0 && (
                  <div className="mr-8 space-y-1">
                    {turn.operations.map((op, idx) => (
                      <OperationCard
                        key={idx}
                        op={op}
                        status={turn.opStatus?.[idx]}
                        onAccept={() => handleAccept(turn.id, idx, op)}
                        onReject={() => handleReject(turn.id, idx)}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
            {chat.isPending && (
              <div className="mr-8 flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span className="text-[11px]">Pensando...</span>
              </div>
            )}
          </div>

          <div className="hairline shrink-0 border-t border-border p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder='ex. "adicione uma linha de IRPJ antes do lucro líquido"'
                rows={2}
                disabled={chat.isPending}
                className="flex-1 resize-none rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none focus:border-ring disabled:opacity-60"
              />
              <button
                onClick={send}
                disabled={chat.isPending || !input.trim()}
                className="inline-flex h-8 items-center gap-1 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {chat.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                Enviar
              </button>
            </div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              ⌘/Ctrl + Enter para enviar
            </div>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function OperationCard({
  op,
  status,
  onAccept,
  onReject,
}: {
  op: ChatOperation
  status?: "accepted" | "rejected"
  onAccept: () => void
  onReject: () => void
}) {
  const accent =
    op.op === "add_block"
      ? { bg: "bg-emerald-500/10", border: "border-emerald-500/40", icon: <Plus className="h-3 w-3" /> }
      : op.op === "update_block"
        ? { bg: "bg-amber-500/10", border: "border-amber-500/40", icon: <Pencil className="h-3 w-3" /> }
        : op.op === "remove_block"
          ? { bg: "bg-red-500/10", border: "border-red-500/40", icon: <Trash2 className="h-3 w-3" /> }
          : { bg: "bg-blue-500/10", border: "border-blue-500/40", icon: <MessageSquare className="h-3 w-3" /> }

  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border p-2 text-[11px]",
        accent.bg,
        accent.border,
        status === "accepted" && "opacity-60",
        status === "rejected" && "opacity-40 line-through",
      )}
    >
      <div className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md bg-background/70">
        {accent.icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-medium">{describeOperation(op)}</div>
        <details className="mt-0.5 text-[10px] text-muted-foreground">
          <summary className="cursor-pointer select-none">detalhes</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-background/50 p-1.5 font-mono text-[10px]">
            {JSON.stringify(op, null, 2)}
          </pre>
        </details>
      </div>
      {status ? (
        <span
          className={cn(
            "ml-auto self-start rounded-md px-1.5 py-0.5 text-[10px] font-medium",
            status === "accepted"
              ? "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300"
              : "bg-muted text-muted-foreground",
          )}
        >
          {status === "accepted" ? "aplicado" : "rejeitado"}
        </span>
      ) : (
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <button
            onClick={onAccept}
            title="Aplicar"
            className="grid h-6 w-6 place-items-center rounded-md bg-emerald-600/80 text-white hover:bg-emerald-600"
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            onClick={onReject}
            title="Rejeitar"
            className="grid h-6 w-6 place-items-center rounded-md border border-border hover:bg-accent"
          >
            <XCircle className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 p-6 text-center text-muted-foreground">
      <Sparkles className="h-8 w-8 opacity-40" />
      <p className="text-[12px]">
        Peça o que quiser: adicionar linhas, renomear, aplicar presets de
        período... Cada ação aparece como um cartão separado que você aprova.
      </p>
      <div className="flex flex-col gap-1.5 text-[10px]">
        {[
          '"adicione uma linha de IRPJ antes do lucro líquido"',
          '"agrupe receitas por tipo de cliente"',
          '"aplique a predefinição yoy de períodos"',
        ].map((s) => (
          <span key={s} className="rounded bg-muted/50 px-2 py-1 italic">
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

function mkId(): string {
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}
