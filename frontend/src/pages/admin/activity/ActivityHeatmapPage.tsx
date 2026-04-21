import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Activity, ChevronRight, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useActivitySummary } from "@/features/admin/hooks"
import { AREAS } from "@/lib/areas"
import { cn } from "@/lib/utils"
import { formatDuration, heatmapFill } from "./format"

const DAY_OPTIONS = [1, 7, 14, 30, 60] as const

/**
 * Landing dashboard at /admin/activity.
 *
 * A user × area matrix coloured by focused time. Sorts users by
 * total time descending so the most-engaged rows surface first;
 * columns are the ``AREAS`` list intersected with whatever actually
 * has data in the window (empty areas are hidden to keep the table
 * scannable).
 *
 * Raw heartbeats are aggregated server-side; the client only slices
 * into a pivoted grid here. Click a row's username or a cell's area
 * label to drill into the per-user or per-area detail pages.
 */
export function ActivityHeatmapPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(7)
  const { data, isLoading, isFetching, refetch } = useActivitySummary(days)

  // Pivot the flat rows into a {user → {area → ms}} grid.
  const { users, areas, grid, rowTotals, max, total } = useMemo(() => {
    const rows = data?.rows ?? []
    const userMap = new Map<number, { user_id: number; username: string; total: number }>()
    const areaSet = new Set<string>()
    const grid: Record<number, Record<string, { ms: number; events: number }>> = {}
    for (const r of rows) {
      const ms = r.total_ms ?? 0
      if (!userMap.has(r.user_id)) {
        userMap.set(r.user_id, { user_id: r.user_id, username: r.user__username, total: 0 })
      }
      const u = userMap.get(r.user_id)!
      u.total += ms
      areaSet.add(r.area)
      grid[r.user_id] ??= {}
      grid[r.user_id]![r.area] = { ms, events: r.events }
    }
    // Sort areas: known ones in AREAS order, unknown stragglers last.
    const known = AREAS.map((a) => a.id).filter((id) => areaSet.has(id))
    const unknown = [...areaSet].filter((a) => !known.includes(a)).sort()
    const areas = [...known, ...unknown]
    const users = [...userMap.values()].sort((a, b) => b.total - a.total)
    const rowTotals = new Map(users.map((u) => [u.user_id, u.total]))
    let max = 0
    for (const u of users) {
      for (const a of areas) {
        const v = grid[u.user_id]?.[a]?.ms ?? 0
        if (v > max) max = v
      }
    }
    const total = users.reduce((s, u) => s + u.total, 0)
    return { users, areas, grid, rowTotals, max, total }
  }, [data])

  const areaLabel = (id: string) => AREAS.find((a) => a.id === id)?.label ?? id

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Atividade por usuário"
        subtitle="Tempo focado em cada área. Dados a partir do beacon por aba."
        actions={
          <>
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
                  {d === 1 ? "Hoje" : `${d}d`}
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

      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <Stat label="Período" value={`${days}d`} />
        <Stat label="Usuários com atividade" value={users.length} />
        <Stat label="Áreas tocadas" value={areas.length} />
        <Stat label="Tempo total focado" value={formatDuration(total)} />
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-muted/40" />
          ))}
        </div>
      ) : users.length === 0 || areas.length === 0 ? (
        <div className="card-elevated flex flex-col items-center gap-2 rounded-md border border-border p-10 text-center">
          <Activity className="h-6 w-6 text-muted-foreground" />
          <div className="text-[13px] font-semibold">Ainda não há atividade suficiente</div>
          <div className="text-[12px] text-muted-foreground">
            O beacon começa a contar tempo a partir do próximo login. Tente
            ampliar a janela para {DAY_OPTIONS[DAY_OPTIONS.length - 1]}d ou
            volte em algumas horas.
          </div>
        </div>
      ) : (
        <div className="card-elevated overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead className="border-b border-border bg-muted/20 text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="sticky left-0 z-10 min-w-[180px] bg-muted/20 px-2 py-2 text-left">Usuário</th>
                {areas.map((a) => (
                  <th key={a} className="min-w-[96px] px-2 py-2 text-right">
                    <Link
                      to={`/admin/activity/areas/${encodeURIComponent(a)}`}
                      className="hover:text-foreground hover:underline"
                      title={a}
                    >
                      {areaLabel(a)}
                    </Link>
                  </th>
                ))}
                <th className="min-w-[80px] px-2 py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-b border-border/60">
                  <td className="sticky left-0 z-10 bg-surface-2 px-2 py-1.5 font-medium">
                    <Link
                      to={`/admin/activity/users/${u.user_id}`}
                      className="inline-flex items-center gap-1 hover:text-primary hover:underline"
                    >
                      {u.username}
                      <ChevronRight className="h-3 w-3 opacity-60" />
                    </Link>
                  </td>
                  {areas.map((a) => {
                    const cell = grid[u.user_id]?.[a]
                    const ms = cell?.ms ?? 0
                    return (
                      <td
                        key={a}
                        className="px-1 py-1 text-right"
                        title={cell ? `${areaLabel(a)} — ${formatDuration(ms)} · ${cell.events} eventos` : ""}
                      >
                        <div
                          className="inline-flex w-full items-center justify-end rounded-md px-2 py-1 tabular-nums"
                          style={{ backgroundColor: heatmapFill(ms, max) }}
                        >
                          {ms > 0 ? formatDuration(ms) : <span className="opacity-30">—</span>}
                        </div>
                      </td>
                    )
                  })}
                  <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
                    {formatDuration(rowTotals.get(u.user_id) ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-surface-3 px-2 py-1">
      <span className="uppercase tracking-wider">{label}:</span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  )
}
