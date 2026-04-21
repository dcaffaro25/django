import { useState } from "react"
import { Link } from "react-router-dom"
import {
  AlertCircle, ArrowLeft, ArrowRight, Clock, RefreshCw, Rocket, RotateCcw, Timer,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useActivityFriction } from "@/features/admin/hooks"
import type {
  BackAndForthRow,
  LongDwellRow,
  RepeatErrorRow,
  SlowActionRow,
} from "@/features/admin/api"
import { AREAS } from "@/lib/areas"
import { cn } from "@/lib/utils"
import { formatDateTime, formatDuration } from "./format"

const DAY_OPTIONS = [7, 14, 30, 60, 90] as const

/**
 * /admin/activity/friction — four heuristics that surface workflow
 * pain without requiring the admin to dig through raw events:
 *
 *   * back-and-forth (A→B→A < 60s)
 *   * long dwell with zero actions (≥ 5 min focus, 0 actions)
 *   * repeat errors (≥ 3 in 5-min bucket on same user × area)
 *   * slow actions (top action labels by p95 duration_ms)
 *
 * Each card renders empty-state copy so the page is usable day 1.
 */
export function ActivityFrictionPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(30)
  const { data, isLoading, isFetching, refetch } = useActivityFriction(days)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Sinais de fricção"
        subtitle="Heurísticas para identificar onde os fluxos estão travando."
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
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-md bg-muted/40" />)}
        </div>
      ) : !data ? (
        <div className="text-[12px] text-muted-foreground">Sem dados.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <BackAndForthCard rows={data.back_and_forth} />
          <SlowActionsCard rows={data.slow_actions} />
          <RepeatErrorsCard rows={data.repeat_errors} />
          <LongDwellCard rows={data.long_dwell_no_action} />
        </div>
      )}
    </div>
  )
}

/* ---------------- individual cards ---------------- */

function FrictionCard({
  icon, title, subtitle, children,
}: {
  icon: React.ReactNode
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="card-elevated rounded-md border border-border">
      <div className="border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-[13px] font-semibold">
          {icon}
          {title}
        </div>
        <div className="text-[11px] text-muted-foreground">{subtitle}</div>
      </div>
      <div className="max-h-80 overflow-y-auto">{children}</div>
    </div>
  )
}

function EmptyRow({ label }: { label: string }) {
  return <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">{label}</div>
}

function areaLabel(id: string): string {
  return AREAS.find((a) => a.id === id)?.label ?? id
}

function BackAndForthCard({ rows }: { rows: BackAndForthRow[] }) {
  return (
    <FrictionCard
      icon={<RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />}
      title="Navegação cíclica (A → B → A)"
      subtitle="Sessões que voltaram para uma área até 60s depois de sair. Sugere que B não resolveu."
    >
      {rows.length === 0 ? <EmptyRow label="Sem ciclos recentes." /> : (
        <table className="w-full text-[12px]">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-border/60 last:border-b-0">
                <td className="px-3 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <Link to={`/admin/activity/areas/${encodeURIComponent(r.from_area)}`} className="hover:text-primary hover:underline">
                      {areaLabel(r.from_area)}
                    </Link>
                    <ArrowRight className="h-3 w-3 opacity-60" />
                    <Link to={`/admin/activity/areas/${encodeURIComponent(r.to_area)}`} className="hover:text-primary hover:underline">
                      {areaLabel(r.to_area)}
                    </Link>
                    <ArrowRight className="h-3 w-3 opacity-60" />
                    <span className="font-medium">{areaLabel(r.from_area)}</span>
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{r.count}×</td>
                <td className="px-3 py-1.5 text-right text-[11px] text-muted-foreground">
                  {r.sample_users.slice(0, 3).map((u) => u.username).join(", ")}
                  {r.sample_users.length > 3 ? ` +${r.sample_users.length - 3}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </FrictionCard>
  )
}

function SlowActionsCard({ rows }: { rows: SlowActionRow[] }) {
  return (
    <FrictionCard
      icon={<Rocket className="h-3.5 w-3.5 text-muted-foreground" />}
      title="Ações lentas (p95)"
      subtitle="Labels de ação ordenados pelo 95º percentil de duração. Mínimo 10 amostras."
    >
      {rows.length === 0 ? <EmptyRow label="Sem amostras suficientes ainda." /> : (
        <table className="w-full text-[12px]">
          <thead className="border-b border-border/60 bg-muted/10 text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-1.5 text-left">Ação</th>
              <th className="px-3 py-1.5 text-left">Área</th>
              <th className="px-3 py-1.5 text-right">n</th>
              <th className="px-3 py-1.5 text-right">p50</th>
              <th className="px-3 py-1.5 text-right">p95</th>
              <th className="px-3 py-1.5 text-right">máx</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.action}:${r.area}`} className="border-b border-border/60 last:border-b-0">
                <td className="px-3 py-1.5 font-mono text-[11px]">{r.action}</td>
                <td className="px-3 py-1.5 text-[11px] text-muted-foreground">{areaLabel(r.area)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{r.samples}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{r.p50_ms}ms</td>
                <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{r.p95_ms}ms</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{r.max_ms}ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </FrictionCard>
  )
}

function RepeatErrorsCard({ rows }: { rows: RepeatErrorRow[] }) {
  return (
    <FrictionCard
      icon={<AlertCircle className="h-3.5 w-3.5 text-warning" />}
      title="Cadeias de erro"
      subtitle="≥ 3 erros do mesmo usuário × área em 5 minutos. Provavelmente uma coisa quebrada que o usuário repetiu."
    >
      {rows.length === 0 ? <EmptyRow label="Nenhuma cadeia de erros detectada." /> : (
        <ul className="divide-y divide-border/60">
          {rows.map((r, i) => (
            <li key={i} className="px-3 py-2">
              <div className="flex items-center justify-between gap-2 text-[12px]">
                <div className="min-w-0 flex-1">
                  <span className="font-semibold">
                    <Link to={`/admin/activity/users/${r.user_id}`} className="hover:text-primary hover:underline">
                      {r.username}
                    </Link>
                  </span>
                  <span className="mx-1 text-muted-foreground">em</span>
                  <Link to={`/admin/activity/areas/${encodeURIComponent(r.area)}`} className="hover:text-primary hover:underline">
                    {areaLabel(r.area)}
                  </Link>
                </div>
                <div className="rounded-md bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning">
                  {r.errors} erros
                </div>
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                {formatDateTime(r.first_at)} → {formatDateTime(r.last_at)}
              </div>
              {r.sample_messages.filter(Boolean).slice(0, 2).map((m, k) => (
                <div key={k} className="mt-1 truncate font-mono text-[10px] text-muted-foreground" title={m ?? ""}>
                  · {m}
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
    </FrictionCard>
  )
}

function LongDwellCard({ rows }: { rows: LongDwellRow[] }) {
  return (
    <FrictionCard
      icon={<Clock className="h-3.5 w-3.5 text-muted-foreground" />}
      title="Travamento suspeito (muito tempo, zero ação)"
      subtitle="Sessões com ≥ 5 min focados e nenhuma ação/busca — possível ponto onde o usuário ficou perdido."
    >
      {rows.length === 0 ? <EmptyRow label="Nenhum caso encontrado." /> : (
        <table className="w-full text-[12px]">
          <thead className="border-b border-border/60 bg-muted/10 text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-1.5 text-left">Usuário</th>
              <th className="px-3 py-1.5 text-left">Área</th>
              <th className="px-3 py-1.5 text-right">Tempo focado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.session_id}:${r.area}`} className="border-b border-border/60 last:border-b-0">
                <td className="px-3 py-1.5">
                  <Link to={`/admin/activity/users/${r.user_id}`} className="hover:text-primary hover:underline">
                    {r.username}
                  </Link>
                </td>
                <td className="px-3 py-1.5">
                  <Link to={`/admin/activity/areas/${encodeURIComponent(r.area)}`} className="hover:text-primary hover:underline">
                    {areaLabel(r.area)}
                  </Link>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                  <span className="inline-flex items-center gap-1">
                    <Timer className="h-3 w-3 opacity-60" />
                    {formatDuration(r.focused_ms)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </FrictionCard>
  )
}
