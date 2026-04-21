import { useEffect, useState } from "react"
import { Sparkles, X, Loader2 } from "lucide-react"
import { useAiExplain } from "@/features/reports"
import type { ReportResult, TemplateDocument } from "@/features/reports"

/**
 * Tooltip-style popover explaining a single preview cell. Fires the
 * explain API call the first time it opens for a given (block, period)
 * pair and caches the result for the rest of the session.
 *
 * Anchored to the caller's cursor / DOM position via `anchor`. No focus
 * trap — clicking outside closes.
 */
export function ExplainPopover({
  open,
  document,
  result,
  blockId,
  periodId,
  onClose,
  anchorRect,
}: {
  open: boolean
  document: TemplateDocument | null
  result: ReportResult | null
  blockId: string | null
  periodId: string | null
  onClose: () => void
  anchorRect: DOMRect | null
}) {
  const explain = useAiExplain()
  const [data, setData] = useState<{ text: string; accounts: unknown[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !document || !result || !blockId || !periodId) return
    setData(null)
    setError(null)
    explain
      .mutateAsync({ document, result, block_id: blockId, period_id: periodId })
      .then((res) => setData({ text: res.text, accounts: res.accounts ?? [] }))
      .catch((err: unknown) => {
        const resp = (err as { response?: { data?: { error?: string } } })?.response?.data
        setError(resp?.error ?? (err instanceof Error ? err.message : "Falha ao explicar"))
      })
    // Only refire when the target changes, not on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, blockId, periodId])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (target.closest("[data-explain-popover]")) return
      onClose()
    }
    window.addEventListener("mousedown", handler)
    return () => window.removeEventListener("mousedown", handler)
  }, [open, onClose])

  if (!open) return null

  // Position near the anchor (cell center, but clamped to viewport).
  const top = anchorRect ? Math.min(anchorRect.top + anchorRect.height + 6, window.innerHeight - 260) : 120
  const left = anchorRect ? Math.min(anchorRect.left, window.innerWidth - 340) : 120

  return (
    <div
      data-explain-popover
      style={{ top, left }}
      className="fixed z-50 w-[320px] rounded-lg border border-border bg-popover p-3 text-[11px] shadow-lg"
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold">
          <Sparkles className="h-3 w-3 text-amber-500" />
          Explicação
        </div>
        <button
          onClick={onClose}
          className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:bg-accent"
        >
          <X className="h-2.5 w-2.5" />
        </button>
      </div>

      {error ? (
        <div className="text-red-600">{error}</div>
      ) : !data ? (
        <div className="flex items-center gap-1 text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Gerando...
        </div>
      ) : (
        <div className="space-y-2">
          <p className="whitespace-pre-wrap text-foreground">{data.text}</p>
          {Array.isArray(data.accounts) && data.accounts.length > 0 && (
            <details className="rounded border border-border/70 p-1.5">
              <summary className="cursor-pointer select-none text-[10px] text-muted-foreground">
                {data.accounts.length} conta(s) contribuíram
              </summary>
              <ul className="mt-1 space-y-0.5 font-mono text-[10px]">
                {(data.accounts as Array<{ account_code?: string; name: string }>).map(
                  (a, i) => (
                    <li key={i}>
                      <span className="text-muted-foreground">{a.account_code ?? "—"}</span>{" "}
                      {a.name}
                    </li>
                  ),
                )}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
