import { Loader2 } from "lucide-react"
import type { ImportProgress } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Live progress strip shown at the top of the diagnostics panel while
 * the worker is still chewing (Phase 6.z-e).
 *
 * Pulls its state from ``session.progress`` — a JSON snapshot the
 * worker writes at stage boundaries. The polling hook picks up the
 * new snapshot every ~2s, so the strip updates without any
 * WebSocket plumbing.
 *
 * Reads the ``stage`` key to label the current step; if
 * ``sheets_total`` is present, renders a percentage bar; if
 * ``errors_so_far`` is non-zero, surfaces the count in amber.
 *
 * **Honesty note:** per-row progress during the commit write loop
 * isn't observable today because the loop runs inside a single
 * ``transaction.atomic()`` block — any session.save from inside
 * won't be visible to the polling frontend until the block commits.
 * So the bar jumps from "writing" → "done" without intermediate
 * row-level progress. Analyze's detector phase DOES update per
 * sheet (not wrapped in atomic). Follow-up with a separate DB
 * connection or Redis progress store can close this gap.
 */

const STAGE_LABELS: Record<string, string> = {
  parsing: "Analisando planilha…",
  detecting: "Detectando pendências…",
  dry_run: "Executando prévia (dry-run)…",
  materializing_rules: "Materializando regras…",
  writing: "Escrevendo no banco…",
  done: "Concluído",
}

export function ProgressStrip({
  progress,
  variant = "card",
}: {
  progress: ImportProgress | undefined
  /** ``card`` renders a full-width card row (used in DiagnosticsPanel).
   *  ``inline`` is a single-line badge for the queue. */
  variant?: "card" | "inline"
}) {
  if (!progress || !progress.stage || progress.stage === "done") return null

  const label = STAGE_LABELS[progress.stage] ?? progress.stage
  const total = progress.sheets_total ?? 0
  const done = progress.sheets_done ?? 0
  const hasBar = total > 0
  const pct = hasBar ? Math.min(100, Math.round((done / total) * 100)) : null
  const errors = progress.errors_so_far ?? 0

  const sheetCaption = (() => {
    if (!hasBar) return null
    if (progress.current_sheet) {
      return `${progress.current_sheet} · ${done} / ${total} abas`
    }
    return `${done} / ${total} abas`
  })()

  if (variant === "inline") {
    // Compact — queue row badge form. Fits next to the status chip.
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-blue-600"
        title={label + (sheetCaption ? ` · ${sheetCaption}` : "")}
      >
        <Loader2 className="h-3 w-3 animate-spin" />
        {hasBar ? `${pct}%` : label}
      </span>
    )
  }

  return (
    <div className="card-elevated flex items-center gap-3 border-l-4 border-l-blue-500 px-4 py-2">
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-500" />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-semibold text-foreground">
            {label}
          </span>
          {sheetCaption && (
            <span className="text-[11px] text-muted-foreground">
              {sheetCaption}
            </span>
          )}
        </div>
        {hasBar && (
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
            <div
              className={cn(
                "h-full rounded-full bg-blue-500 transition-[width] duration-500 ease-out",
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          {progress.updated_at && (
            <span>
              Atualizado {relativeTime(progress.updated_at)}
            </span>
          )}
          {errors > 0 && (
            <span className="text-amber-600">
              · {errors} erro{errors === 1 ? "" : "s"} detectado{errors === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const deltaS = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (deltaS < 5) return "agora"
  if (deltaS < 60) return `há ${deltaS}s`
  const deltaMin = Math.round(deltaS / 60)
  return `há ${deltaMin}min`
}
