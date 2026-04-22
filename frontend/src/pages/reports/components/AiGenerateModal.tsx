import { useEffect, useRef, useState } from "react"
import { Sparkles, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ReportType, TemplateDocument } from "@/features/reports"
import { useAiGenerateTemplate } from "@/features/reports"

const REPORT_TYPE_OPTIONS: { value: ReportType; label: string; hint: string }[] = [
  { value: "income_statement", label: "DRE", hint: "Receitas, custos, despesas, resultado" },
  { value: "balance_sheet",    label: "Balanço Patrimonial", hint: "Ativo, passivo, patrimônio líquido" },
  { value: "cash_flow",        label: "Fluxo de Caixa", hint: "Operacional, investimento, financiamento" },
]

export function AiGenerateModal({
  open,
  onClose,
  onGenerated,
}: {
  open: boolean
  onClose: () => void
  onGenerated: (doc: TemplateDocument) => void
}) {
  const [reportType, setReportType] = useState<ReportType>("income_statement")
  const [preferences, setPreferences] = useState("")
  const [provider, setProvider] = useState<"openai" | "anthropic">("openai")
  const [error, setError] = useState<string | null>(null)
  // Elapsed-seconds counter while the LLM is grinding. 1-second tick
  // is cheap, and a running number prevents the "is this hung?"
  // anxiety during 30-60s AI calls.
  const [elapsed, setElapsed] = useState(0)
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const generate = useAiGenerateTemplate()

  useEffect(() => {
    if (!generate.isPending) {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current)
        elapsedTimerRef.current = null
      }
      setElapsed(0)
      return
    }
    const startedAt = Date.now()
    elapsedTimerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)
    return () => {
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current)
    }
  }, [generate.isPending])

  if (!open) return null

  const onSubmit = async () => {
    setError(null)
    try {
      const res = await generate.mutateAsync({
        report_type: reportType,
        preferences: preferences.trim() || undefined,
        provider,
      })
      onGenerated(res.document)
      onClose()
    } catch (err: unknown) {
      // The client sets a 180s timeout on this endpoint (see
      // ``features/reports/api.ts``). Axios surfaces timeouts as
      // ``code === "ECONNABORTED"`` with a message starting with
      // "timeout of". Rewrite that into actionable operator copy
      // instead of the raw axios string.
      const code = (err as { code?: string })?.code
      const raw = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? (err instanceof Error ? err.message : "")
      const isTimeout = code === "ECONNABORTED" || /timeout of/i.test(raw || "")
      const msg = isTimeout
        ? "A IA demorou mais do que o esperado (>3 min). Tente novamente com preferências mais enxutas ou o outro provedor."
        : raw || "Falha na IA"
      setError(msg)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-[520px] rounded-lg border border-border bg-surface-1 shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Gerar modelo com IA
          </h2>
          <button
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="space-y-3 p-4 text-[12px]">
          <div className="rounded-md bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
            A IA analisa seu plano de contas e propõe uma estrutura. Cada linha gerada inclui
            uma explicação clicável. Nada é salvo automaticamente — você pode revisar antes.
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Tipo de relatório
            </label>
            <div className="grid grid-cols-3 gap-1.5">
              {REPORT_TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setReportType(opt.value)}
                  className={cn(
                    "flex flex-col items-start gap-0.5 rounded-md border p-2 text-left transition-colors",
                    reportType === opt.value
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background hover:bg-accent",
                  )}
                >
                  <span className="text-[12px] font-semibold">{opt.label}</span>
                  <span className="text-[10px] text-muted-foreground">{opt.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Preferências (opcional)
            </label>
            <textarea
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              placeholder="ex. 3 níveis de receita, OPEX em 1 nível, separar receita de produtos e serviços"
              rows={3}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none focus:border-ring"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Provedor
            </label>
            <div className="flex gap-1.5">
              {(["openai", "anthropic"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setProvider(p)}
                  className={cn(
                    "h-7 rounded-md border px-2 text-[11px] font-medium",
                    provider === p
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background hover:bg-accent",
                  )}
                >
                  {p === "openai" ? "OpenAI" : "Anthropic"}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-700 dark:text-red-300">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          <button
            onClick={onClose}
            className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            Cancelar
          </button>
          <button
            onClick={onSubmit}
            disabled={generate.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {generate.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {generate.isPending
              ? `Gerando${elapsed > 0 ? ` · ${elapsed}s` : "..."}`
              : "Gerar"}
          </button>
        </div>
      </div>
    </div>
  )
}
