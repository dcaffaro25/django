import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts"
import { AlertCircle, ArrowLeft, Monitor, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useActivityUserDetail } from "@/features/admin/hooks"
import { AREAS } from "@/lib/areas"
import { cn } from "@/lib/utils"
import { formatDateTime, formatDuration, shortUserAgent } from "./format"

const DAY_OPTIONS = [7, 14, 30, 60, 90] as const

/**
 * /admin/activity/users/:id — per-user deep dive.
 *
 * Three blocks:
 *   * Totals strip + day-over-day area chart (clearer than a pie for
 *     "is this user using the product more or less over time?").
 *   * Top areas table with click-through to the area detail page.
 *   * Timeline of recent actions + errors, capped at the last 40 /
 *     25 rows.
 *
 * Kept deliberately read-only: no edit affordances here, that's
 * /admin/users's job. This page is for answering "what's this user
 * doing?" questions.
 */
export function ActivityUserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const userId = id ? Number(id) : null
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(30)
  const { data, isLoading, isFetching, refetch } = useActivityUserDetail(userId, days)

  const dayChart = useMemo(
    () =>
      (data?.by_day ?? []).map((d) => ({
        date: d.date,
        minutes: Math.round(((d.focused_ms ?? 0) / 60_000) * 10) / 10,
      })),
    [data?.by_day],
  )

  const areaLabel = (id: string) => AREAS.find((a) => a.id === id)?.label ?? id

  return (
    <div className="space-y-4">
      <SectionHeader
        title={data ? `Atividade · ${data.user.username}` : "Atividade do usuário"}
        subtitle={data?.user.email || "Detalhamento do tempo focado, ações e erros recentes."}
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
      ) : !data ? (
        <div className="text-[12px] text-muted-foreground">Usuário não encontrado.</div>
      ) : (
        <>
          {/* Totals + day chart */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[260px_1fr]">
            <div className="card-elevated flex flex-col gap-2 rounded-md border border-border p-3">
              <KpiRow label="Tempo focado" value={formatDuration(data.totals.focused_ms)} />
              <KpiRow label="Eventos" value={data.totals.events.toLocaleString("pt-BR")} />
              <KpiRow label="Janela" value={`${data.days}d`} />
              <KpiRow label="Áreas tocadas" value={data.by_area.length} />
            </div>
            <div className="card-elevated rounded-md border border-border p-3">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Minutos focados por dia
              </div>
              <div className="h-40">
                {dayChart.length === 0 ? (
                  <EmptyChart />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={dayChart}>
                      <defs>
                        <linearGradient id="u-focus" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.45} />
                          <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} width={36} />
                      <Tooltip
                        contentStyle={{ fontSize: 11, background: "hsl(var(--surface-3))", border: "1px solid hsl(var(--border))" }}
                        formatter={(v: number) => [`${v} min`, "Foco"]}
                      />
                      <Area dataKey="minutes" stroke="hsl(var(--primary))" fill="url(#u-focus)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>

          {/* Top areas */}
          <div className="card-elevated rounded-md border border-border">
            <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Tempo por área
            </div>
            {data.by_area.length === 0 ? (
              <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">Nada registrado ainda.</div>
            ) : (
              <table className="w-full text-[12px]">
                <tbody>
                  {data.by_area.map((a) => (
                    <tr key={a.area} className="border-b border-border/60 last:border-b-0">
                      <td className="px-3 py-1.5">
                        <Link
                          to={`/admin/activity/areas/${encodeURIComponent(a.area)}`}
                          className="hover:text-primary hover:underline"
                        >
                          {areaLabel(a.area)}
                        </Link>
                        <span className="ml-2 font-mono text-[10px] text-muted-foreground">{a.area}</span>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{a.events.toLocaleString("pt-BR")} ev</td>
                      <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                        {formatDuration(a.focused_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Devices */}
          {data.devices.length > 0 && (
            <div className="card-elevated rounded-md border border-border">
              <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Dispositivos ({data.devices.length})
              </div>
              <table className="w-full text-[12px]">
                <tbody>
                  {data.devices.map((d, i) => (
                    <tr key={i} className="border-b border-border/60 last:border-b-0">
                      <td className="px-3 py-1.5">
                        <div className="flex items-center gap-2">
                          <Monitor className="h-3.5 w-3.5 text-muted-foreground" />
                          {shortUserAgent(d.user_agent)}
                          {d.viewport_width && (
                            <span className="text-[10px] text-muted-foreground">
                              {d.viewport_width}×{d.viewport_height}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{d.sessions} sessão(ões)</td>
                      <td className="px-3 py-1.5 text-right text-[11px] text-muted-foreground">
                        visto {formatDateTime(d.last_seen)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Recent actions + errors side-by-side on desktop */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <ActionList title="Ações recentes" events={data.recent_actions} />
            <ErrorList errors={data.recent_errors} />
          </div>
        </>
      )}
    </div>
  )
}

function KpiRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums font-semibold">{value}</span>
    </div>
  )
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center text-[11px] text-muted-foreground">
      Sem heartbeats na janela selecionada.
    </div>
  )
}

function ActionList({ title, events }: { title: string; events: Array<{ id: number; created_at: string; kind: string; area: string; action?: string; duration_ms?: number | null; meta?: Record<string, unknown> | null }> }) {
  const areaLabel = (id: string) => AREAS.find((a) => a.id === id)?.label ?? id
  return (
    <div className="card-elevated rounded-md border border-border">
      <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title} ({events.length})
      </div>
      {events.length === 0 ? (
        <div className="px-3 py-4 text-center text-[12px] text-muted-foreground">Sem ações registradas.</div>
      ) : (
        <ul className="divide-y divide-border/60">
          {events.map((e) => (
            <li key={e.id} className="flex items-start justify-between gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[12px]">
                  <span className="rounded-md border border-border bg-surface-3 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {e.kind}
                  </span>
                  <span className="truncate font-medium">{e.action || "—"}</span>
                </div>
                <div className="truncate text-[10px] text-muted-foreground">
                  {areaLabel(e.area)} · {formatDateTime(e.created_at)}
                  {e.duration_ms ? ` · ${e.duration_ms}ms` : ""}
                </div>
                {e.meta && Object.keys(e.meta).length > 0 && (
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground" title={JSON.stringify(e.meta)}>
                    {JSON.stringify(e.meta)}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ErrorList({ errors }: { errors: Array<{ id: number; created_at: string; area: string; meta?: Record<string, unknown> | null }> }) {
  const areaLabel = (id: string) => AREAS.find((a) => a.id === id)?.label ?? id
  return (
    <div className="card-elevated rounded-md border border-border">
      <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Erros ({errors.length})
      </div>
      {errors.length === 0 ? (
        <div className="px-3 py-4 text-center text-[12px] text-muted-foreground">Nenhum erro na janela.</div>
      ) : (
        <ul className="divide-y divide-border/60">
          {errors.map((e) => (
            <li key={e.id} className="flex items-start gap-2 px-3 py-2">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] font-medium">
                  {(e.meta?.["message"] as string) ?? "Erro sem mensagem"}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {areaLabel(e.area)} · {formatDateTime(e.created_at)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
