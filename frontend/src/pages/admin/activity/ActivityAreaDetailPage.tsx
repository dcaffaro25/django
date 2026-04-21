import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useActivityAreaDetail } from "@/features/admin/hooks"
import { AREAS } from "@/lib/areas"
import { cn } from "@/lib/utils"
import { formatDateTime, formatDuration } from "./format"

const DAY_OPTIONS = [7, 14, 30, 60, 90] as const

/**
 * /admin/activity/areas/:area — per-area drill-down.
 *
 * Surfaces: who spends time here (top_users), what they do
 * (top_actions), and a raw recent-activity tail. Answer the
 * "what happens on this page?" question without the admin having to
 * scan the events endpoint manually.
 */
export function ActivityAreaDetailPage() {
  const { id } = useParams<{ id: string }>()
  const area = id ?? ""
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(30)
  const { data, isLoading, isFetching, refetch } = useActivityAreaDetail(area || null, days)

  const areaMeta = AREAS.find((a) => a.id === area)
  const title = areaMeta ? areaMeta.label : area
  const subtitle = areaMeta
    ? `${areaMeta.group} · ${area} · prefixo de rota: ${areaMeta.prefix}`
    : `${area} · área sem entrada canônica na taxonomia`

  return (
    <div className="space-y-4">
      <SectionHeader
        title={`Área · ${title}`}
        subtitle={subtitle}
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
        <div className="text-[12px] text-muted-foreground">Sem dados para essa área.</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
            <Stat label="Tempo focado" value={formatDuration(data.totals.focused_ms)} />
            <Stat label="Usuários distintos" value={data.totals.distinct_users} />
            <Stat label="Eventos" value={data.totals.events.toLocaleString("pt-BR")} />
            <Stat label="Janela" value={`${data.days}d`} />
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className="card-elevated rounded-md border border-border">
              <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Top usuários por tempo
              </div>
              {data.top_users.length === 0 ? (
                <div className="px-3 py-4 text-center text-[12px] text-muted-foreground">Nenhum usuário ainda.</div>
              ) : (
                <table className="w-full text-[12px]">
                  <tbody>
                    {data.top_users.map((u) => (
                      <tr key={u.user_id} className="border-b border-border/60 last:border-b-0">
                        <td className="px-3 py-1.5">
                          <Link to={`/admin/activity/users/${u.user_id}`} className="font-medium hover:text-primary hover:underline">
                            {u.user__username}
                          </Link>
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{u.events.toLocaleString("pt-BR")} ev</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                          {formatDuration(u.focused_ms)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card-elevated rounded-md border border-border">
              <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Top ações
              </div>
              {data.top_actions.length === 0 ? (
                <div className="px-3 py-4 text-center text-[12px] text-muted-foreground">
                  Nenhuma ação nomeada ainda — instrumente as mutações principais.
                </div>
              ) : (
                <table className="w-full text-[12px]">
                  <tbody>
                    {data.top_actions.map((a) => (
                      <tr key={a.action} className="border-b border-border/60 last:border-b-0">
                        <td className="px-3 py-1.5 font-mono text-[11px]">{a.action}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{a.events}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="card-elevated rounded-md border border-border">
            <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Atividade recente ({data.recent.length})
            </div>
            {data.recent.length === 0 ? (
              <div className="px-3 py-4 text-center text-[12px] text-muted-foreground">Sem eventos recentes.</div>
            ) : (
              <table className="w-full text-[12px]">
                <thead className="border-b border-border bg-muted/20 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Quando</th>
                    <th className="px-3 py-1.5 text-left">Usuário</th>
                    <th className="px-3 py-1.5 text-left">Tipo</th>
                    <th className="px-3 py-1.5 text-left">Ação</th>
                    <th className="px-3 py-1.5 text-right">Duração</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((e) => (
                    <tr key={e.id} className="border-b border-border/60 last:border-b-0">
                      <td className="px-3 py-1.5 text-[11px] text-muted-foreground">{formatDateTime(e.created_at)}</td>
                      <td className="px-3 py-1.5">
                        {e.user_id ? (
                          <Link to={`/admin/activity/users/${e.user_id}`} className="hover:text-primary hover:underline">
                            {e.user__username ?? `#${e.user_id}`}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[11px]">{e.kind}</td>
                      <td className="px-3 py-1.5">{e.action || "—"}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {e.duration_ms ? `${e.duration_ms}ms` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
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
