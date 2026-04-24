import { useMemo } from "react"
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Trash2,
  XCircle,
  type LucideIcon,
} from "lucide-react"
import { useImportSessionsList } from "@/features/imports"
import type {
  ImportSessionStatus,
  ImportSessionSummary,
} from "@/features/imports/types"
import { ProgressStrip } from "./ProgressStrip"
import { cn } from "@/lib/utils"

/**
 * Queue panel rendered on the Imports hub (Phase 6.z-b). Shows the
 * last N sessions for the current tenant with a live status chip,
 * auto-refreshes every 3s while anything is still running. Clicking
 * a row is wired via ``onSelectSession`` — the hub decides whether
 * that expands the row inline or navigates to a detail route
 * (Phase 6.z-c lands the inline expansion).
 *
 * OFX / NF-e imports don't use ``ImportSession`` yet and therefore
 * don't appear here. The panel covers the v2 template + ETL flows.
 *
 * Keep this component purely presentational — the only side effect
 * it owns is the list query (via the hook). Upstream state (upload
 * form, selection) lives on the hub.
 */

// Status ordering for the chip — matches how operators tend to
// scan the queue: blocking red first, work-in-flight amber, then
// terminal greys.
const STATUS_META: Record<
  ImportSessionStatus,
  {
    label: string
    icon: LucideIcon
    // Tailwind utility pair: text color for icon/label, optional bg.
    className: string
  }
> = {
  analyzing: {
    label: "Analisando",
    icon: Loader2,
    className: "text-blue-500",
  },
  committing: {
    label: "Importando",
    icon: Loader2,
    className: "text-blue-500",
  },
  awaiting_resolve: {
    label: "Aguarda resolução",
    icon: AlertCircle,
    className: "text-amber-600",
  },
  ready: {
    label: "Pronto",
    icon: CheckCircle2,
    className: "text-emerald-600",
  },
  committed: {
    label: "Importado",
    icon: CheckCircle2,
    className: "text-emerald-600",
  },
  error: {
    label: "Erro",
    icon: XCircle,
    className: "text-destructive",
  },
  discarded: {
    label: "Descartado",
    icon: Trash2,
    className: "text-muted-foreground",
  },
}

/**
 * "Há 3s", "há 2min", "ontem" style relative time. Keeps the queue
 * compact vs a full ISO timestamp — hover-title shows the full
 * date for operators who need the exact time.
 */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const deltaMs = Date.now() - then
  const deltaS = Math.max(0, Math.round(deltaMs / 1000))
  if (deltaS < 5) return "agora"
  if (deltaS < 60) return `há ${deltaS}s`
  const deltaMin = Math.round(deltaS / 60)
  if (deltaMin < 60) return `há ${deltaMin}min`
  const deltaH = Math.round(deltaMin / 60)
  if (deltaH < 24) return `há ${deltaH}h`
  const deltaD = Math.round(deltaH / 24)
  if (deltaD === 1) return "ontem"
  if (deltaD < 7) return `há ${deltaD} dias`
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  })
}

function StatusChip({ status }: { status: ImportSessionStatus }) {
  const meta = STATUS_META[status]
  if (!meta) return <span className="text-[11px]">{status}</span>
  const Icon = meta.icon
  const spinning = status === "analyzing" || status === "committing"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-medium",
        meta.className,
      )}
    >
      <Icon className={cn("h-3 w-3", spinning && "animate-spin")} />
      {meta.label}
    </span>
  )
}

export function ImportQueuePanel({
  selectedSessionId,
  onSelectSession,
  pageSize = 10,
}: {
  /** The row currently expanded (or null). Row click toggles. */
  selectedSessionId?: number | null
  onSelectSession?: (id: number | null) => void
  pageSize?: number
}) {
  const { data, isLoading, isError } = useImportSessionsList({ pageSize })

  const rows = useMemo<ImportSessionSummary[]>(
    () => data?.results ?? [],
    [data],
  )

  const runningCount = rows.filter(
    (r) => r.status === "analyzing" || r.status === "committing",
  ).length

  return (
    <section className="card-elevated overflow-hidden">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-semibold text-foreground">
            Fila de importações
          </h3>
          <span className="text-[11px] text-muted-foreground">
            {data?.count != null ? `${data.count} total` : ""}
          </span>
        </div>
        {runningCount > 0 && (
          <span className="inline-flex items-center gap-1 text-[11px] text-blue-600">
            <Loader2 className="h-3 w-3 animate-spin" />
            {runningCount} em execução
          </span>
        )}
      </header>

      {isLoading && (
        <div className="flex items-center gap-2 px-3 py-4 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Carregando sessões…
        </div>
      )}

      {isError && (
        <div className="px-3 py-4 text-[12px] text-destructive">
          Falha ao carregar a fila. Recarregue a página.
        </div>
      )}

      {!isLoading && !isError && rows.length === 0 && (
        <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
          Nenhuma sessão de importação ainda. Envie um arquivo acima para
          começar.
        </div>
      )}

      {rows.length > 0 && (
        <ul className="divide-y divide-border">
          {rows.map((r) => {
            const isSelected = selectedSessionId === r.id
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() =>
                    onSelectSession?.(isSelected ? null : r.id)
                  }
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-2 text-left text-[12px] hover:bg-accent/30",
                    isSelected && "bg-accent/40",
                  )}
                >
                  <ChevronRight
                    className={cn(
                      "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                      isSelected && "rotate-90",
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate font-medium text-foreground"
                        title={r.file_name}
                      >
                        {r.file_name}
                      </span>
                      <span className="inline-flex shrink-0 rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {r.mode}
                      </span>
                      {r.transformation_rule_name && (
                        <span
                          className="truncate text-[11px] text-muted-foreground"
                          title={r.transformation_rule_name}
                        >
                          · {r.transformation_rule_name}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span title={new Date(r.created_at).toLocaleString("pt-BR")}>
                        {relativeTime(r.created_at)}
                      </span>
                      {r.operator_name && <span>· {r.operator_name}</span>}
                      {r.open_issue_count > 0 && (
                        <span className="text-amber-600">
                          · {r.open_issue_count} pendência
                          {r.open_issue_count === 1 ? "" : "s"}
                        </span>
                      )}
                      {/* Phase 6.z-e: inline progress percentage for
                          running rows. ProgressStrip renders null on
                          terminal sessions so the badge disappears
                          once the worker finishes. */}
                      <ProgressStrip progress={r.progress} variant="inline" />
                    </div>
                  </div>
                  <StatusChip status={r.status} />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
