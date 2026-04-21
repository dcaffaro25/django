import { useState } from "react"
import { Link } from "react-router-dom"
import { ArrowLeft, GitBranch, RefreshCw, Timer, TrendingDown } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useActivityFunnels } from "@/features/admin/hooks"
import type { FunnelResult } from "@/features/admin/api"
import { cn } from "@/lib/utils"
import { formatDuration } from "./format"

const DAY_OPTIONS = [7, 14, 30, 60, 90] as const

/**
 * /admin/activity/funnels — workflow progression dashboard.
 *
 * For each declared funnel, we show:
 *   * an entered → completed % headline,
 *   * a stacked step breakdown with drop-off %,
 *   * inter-step p50/p95 times so the slow handoff jumps out.
 *
 * Funnels are hardcoded server-side (see ``core/services/activity_funnels.py``).
 * Step ids are stable — if a funnel's labels change, the id stays the same so
 * the UI keeps matching cached data on refresh.
 */
export function ActivityFunnelsPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(30)
  const { data, isLoading, isFetching, refetch } = useActivityFunnels(days)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Funis de workflow"
        subtitle="Quantas pessoas iniciam cada fluxo e quantas chegam ao fim."
        actions={
          <>
            <Link
              to="/admin/activity"
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Voltar
            </Link>
            <div className="inline-flex h-8 overflow-hidden rounded-md border border-border bg-background text-[11px]">
              {DAY_OPTIONS.map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={cn(
                    "h-full border-l border-border px-2 first:border-l-0",
                    d === days ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  {d}d
                </button>
              ))}
            </div>
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              Atualizar
            </button>
          </>
        }
      />

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-md bg-muted/40" />)}
        </div>
      ) : !data || data.funnels.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          {data.funnels.map((f) => <FunnelCard key={f.id} funnel={f} />)}
        </div>
      )}
    </div>
  )
}

function FunnelCard({ funnel }: { funnel: FunnelResult }) {
  const maxReached = funnel.steps.reduce((m, s) => Math.max(m, s.reached), 0)
  return (
    <div className="card-elevated rounded-md border border-border">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-3 py-2">
        <div>
          <div className="flex items-center gap-2 text-[13px] font-semibold">
            <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
            {funnel.label}
            <span className="font-mono text-[10px] text-muted-foreground">{funnel.id}</span>
          </div>
          <div className="text-[11px] text-muted-foreground">{funnel.description}</div>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <Kpi label="Entraram" value={funnel.entered} />
          <Kpi label="Concluíram" value={funnel.completed} />
          <Kpi
            label="Taxa"
            value={funnel.overall_pct == null ? "—" : `${funnel.overall_pct}%`}
            tone={funnel.overall_pct != null && funnel.overall_pct >= 50 ? "success" : "warning"}
          />
        </div>
      </div>
      <table className="w-full text-[12px]">
        <thead className="border-b border-border/60 bg-muted/10 text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="w-8 px-2 py-1.5 text-center">#</th>
            <th className="px-2 py-1.5 text-left">Passo</th>
            <th className="px-2 py-1.5 text-right">Sessões</th>
            <th className="px-2 py-1.5 text-right">Queda</th>
            <th className="px-2 py-1.5 text-left">Progresso</th>
            <th className="px-2 py-1.5 text-right">Tempo desde anterior (p50 / p95)</th>
          </tr>
        </thead>
        <tbody>
          {funnel.steps.map((s, i) => {
            const pct = maxReached > 0 ? (s.reached / maxReached) * 100 : 0
            const timing = s.timing_from_previous
            return (
              <tr key={s.id} className="border-b border-border/60 last:border-b-0">
                <td className="px-2 py-1.5 text-center text-[11px] text-muted-foreground">{i + 1}</td>
                <td className="px-2 py-1.5">{s.label}</td>
                <td className="px-2 py-1.5 text-right tabular-nums font-semibold">{s.reached}</td>
                <td className="px-2 py-1.5 text-right text-[11px]">
                  {s.dropoff_pct == null ? (
                    "—"
                  ) : (
                    <span
                      className={cn(
                        "inline-flex items-center gap-1",
                        s.dropoff_pct > 50 ? "text-warning" : "text-muted-foreground",
                      )}
                    >
                      <TrendingDown className="h-3 w-3" /> {s.dropoff_pct}%
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted/30">
                    <div
                      className="h-full rounded-full bg-primary/60"
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </div>
                </td>
                <td className="px-2 py-1.5 text-right text-[11px]">
                  {timing && timing.samples ? (
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <Timer className="h-3 w-3" />
                      {formatDuration(timing.p50_ms ?? 0)} / {formatDuration(timing.p95_ms ?? 0)}
                      <span className="opacity-60">(n={timing.samples})</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: number | string; tone?: "success" | "warning" }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-surface-3 px-2 py-1">
      <span className="uppercase tracking-wider text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-semibold tabular-nums",
          tone === "success" && "text-success",
          tone === "warning" && "text-warning",
        )}
      >
        {value}
      </span>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="card-elevated flex flex-col items-center gap-2 rounded-md border border-border p-10 text-center">
      <GitBranch className="h-6 w-6 text-muted-foreground" />
      <div className="text-[13px] font-semibold">Nenhum funil configurado ou sem dados</div>
      <div className="text-[12px] text-muted-foreground">
        Funis são definidos em <code>core/services/activity_funnels.py</code>.
      </div>
    </div>
  )
}
