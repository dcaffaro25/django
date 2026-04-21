import { useState } from "react"
import { Link } from "react-router-dom"
import { Drawer } from "vaul"
import { toast } from "sonner"
import {
  AlertCircle, AlertTriangle, ArrowLeft, Bug, Check, ChevronRight, RefreshCw,
  RotateCcw, ServerCrash, ShieldAlert, X,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useErrorReportDetail,
  useErrorReports,
  useResolveErrorReport,
} from "@/features/admin/hooks"
import type {
  ErrorReport,
  ErrorReportKind,
  ErrorReportDetailResponse,
} from "@/features/admin/api"
import { AREAS } from "@/lib/areas"
import { cn } from "@/lib/utils"
import { formatDateTime } from "./format"

const DAY_OPTIONS = [1, 7, 14, 30, 90] as const

const KIND_LABEL: Record<ErrorReportKind, string> = {
  frontend: "Frontend",
  backend_drf: "Backend · DRF",
  backend_django: "Backend · Django",
  celery: "Celery",
}

const KIND_ICON: Record<ErrorReportKind, React.ComponentType<{ className?: string }>> = {
  frontend: Bug,
  backend_drf: ServerCrash,
  backend_django: ServerCrash,
  celery: AlertTriangle,
}

/**
 * /admin/activity/errors — issue tracker for the app.
 *
 * Left: sortable/filterable list of error groups. Right: a detail
 * drawer with stack, affected users, recent occurrences, and the
 * crucial breadcrumb timeline (what the user was doing right before
 * it fired).
 *
 * A group is one row per ``fingerprint`` in ``ErrorReport``. Every
 * backend exception handler + the frontend beacon upsert into the
 * same table so every error — render crash, promise rejection,
 * 500 response, Celery task failure — shows up here.
 */
export function ErrorsPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(7)
  const [kind, setKind] = useState<ErrorReportKind | "">("")
  const [resolved, setResolved] = useState<"true" | "false" | "any">("false")
  const [order, setOrder] = useState<"last_seen" | "count">("last_seen")
  const [activeId, setActiveId] = useState<number | null>(null)

  const { data, isLoading, isFetching, refetch } = useErrorReports({
    days, kind: kind || undefined, resolved, order, limit: 200,
  })
  const errors = data?.errors ?? []

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Erros da aplicação"
        subtitle="Agrupados por assinatura. Clique para ver stack, usuários afetados e o que o usuário estava fazendo."
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

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="text-muted-foreground">Tipo:</span>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as ErrorReportKind | "")}
          className="h-7 rounded-md border border-border bg-background px-2"
        >
          <option value="">Todos</option>
          <option value="frontend">Frontend</option>
          <option value="backend_drf">Backend · DRF</option>
          <option value="backend_django">Backend · Django</option>
          <option value="celery">Celery</option>
        </select>

        <span className="ml-2 text-muted-foreground">Resolução:</span>
        <select
          value={resolved}
          onChange={(e) => setResolved(e.target.value as "true" | "false" | "any")}
          className="h-7 rounded-md border border-border bg-background px-2"
        >
          <option value="false">Abertos</option>
          <option value="true">Resolvidos</option>
          <option value="any">Todos</option>
        </select>

        <span className="ml-2 text-muted-foreground">Ordenar:</span>
        <select
          value={order}
          onChange={(e) => setOrder(e.target.value as "last_seen" | "count")}
          className="h-7 rounded-md border border-border bg-background px-2"
        >
          <option value="last_seen">Mais recentes</option>
          <option value="count">Mais frequentes</option>
        </select>

        <span className="ml-auto text-[11px] text-muted-foreground">
          {errors.length} {errors.length === 1 ? "grupo" : "grupos"}
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-16 animate-pulse rounded-md bg-muted/40" />)}
        </div>
      ) : errors.length === 0 ? (
        <EmptyState days={days} />
      ) : (
        <div className="card-elevated overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="border-b border-border bg-muted/20 text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="w-8 px-2 py-2"></th>
                <th className="px-2 py-2 text-left">Erro</th>
                <th className="px-2 py-2 text-left">Onde</th>
                <th className="px-2 py-2 text-right">Ocorrências</th>
                <th className="px-2 py-2 text-right">Usuários</th>
                <th className="px-2 py-2 text-right">Visto em</th>
                <th className="w-8 px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {errors.map((e) => <ErrorRow key={e.id} row={e} onOpen={() => setActiveId(e.id)} />)}
            </tbody>
          </table>
        </div>
      )}

      <ErrorDetailDrawer id={activeId} onClose={() => setActiveId(null)} />
    </div>
  )
}

function ErrorRow({ row, onOpen }: { row: ErrorReport; onOpen: () => void }) {
  const Icon = KIND_ICON[row.kind] ?? Bug
  return (
    <tr
      onClick={onOpen}
      className={cn(
        "cursor-pointer border-b border-border/60 hover:bg-accent/40",
        row.is_reopened && "bg-warning/5",
      )}
    >
      <td className="px-2 py-1.5 text-center">
        <Icon className={cn("h-3.5 w-3.5", row.is_resolved ? "text-muted-foreground" : "text-danger")} />
      </td>
      <td className="px-2 py-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] font-semibold text-foreground">{row.error_class || "Error"}</span>
          {row.status_code != null && (
            <span className="rounded-md border border-border bg-surface-3 px-1.5 py-0.5 text-[10px]">
              {row.status_code}
            </span>
          )}
          <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground">
            {KIND_LABEL[row.kind]}
          </span>
          {row.is_reopened && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">
              <RotateCcw className="h-3 w-3" /> reaberto
            </span>
          )}
          {row.is_resolved && (
            <span className="inline-flex items-center gap-1 rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
              <Check className="h-3 w-3" /> resolvido
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground" title={row.message}>
          {row.message || "(sem mensagem)"}
        </div>
      </td>
      <td className="px-2 py-1.5 text-[11px] text-muted-foreground">
        {row.method && <span className="mr-1 font-mono">{row.method}</span>}
        <span className="font-mono">{row.path || "—"}</span>
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">{row.count}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{row.affected_users}</td>
      <td className="px-2 py-1.5 text-right text-[11px] text-muted-foreground">
        {formatDateTime(row.last_seen_at)}
      </td>
      <td className="px-2 py-1.5 text-center">
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
      </td>
    </tr>
  )
}

function EmptyState({ days }: { days: number }) {
  return (
    <div className="card-elevated flex flex-col items-center gap-2 rounded-md border border-border p-10 text-center">
      <ShieldAlert className="h-6 w-6 text-muted-foreground" />
      <div className="text-[13px] font-semibold">Nenhum erro no período</div>
      <div className="text-[12px] text-muted-foreground">
        Nenhum grupo de erro nos últimos {days} {days === 1 ? "dia" : "dias"} com esses filtros.
      </div>
    </div>
  )
}

/* ---------------- Detail drawer ---------------- */

function ErrorDetailDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data, isLoading } = useErrorReportDetail(id)
  const resolveMut = useResolveErrorReport()
  const [note, setNote] = useState("")

  const onResolve = (resolved: boolean) => {
    if (!id) return
    resolveMut.mutate(
      { id, resolved, note },
      {
        onSuccess: () => {
          toast.success(resolved ? "Marcado como resolvido" : "Reaberto")
          setNote("")
          onClose()
        },
        onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={id != null} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[840px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="text-[13px] font-semibold">Detalhe do erro</Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            {isLoading || !data ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-md bg-muted/40" />)}
              </div>
            ) : (
              <ErrorDetailBody data={data} />
            )}
          </div>

          <div className="hairline flex shrink-0 flex-col gap-2 border-t p-3">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anotação opcional (ex.: commit que corrige, link de PR, mudança necessária)..."
              className="h-16 w-full resize-none rounded-md border border-border bg-background px-2 py-1 text-[12px] outline-none focus:border-ring"
            />
            <div className="flex items-center justify-end gap-2">
              {data?.report.is_resolved && !data.report.is_reopened && (
                <button
                  onClick={() => onResolve(false)}
                  disabled={resolveMut.isPending}
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reabrir
                </button>
              )}
              {(!data?.report.is_resolved || data?.report.is_reopened) && (
                <button
                  onClick={() => onResolve(true)}
                  disabled={resolveMut.isPending}
                  className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5" />
                  Marcar resolvido
                </button>
              )}
            </div>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function ErrorDetailBody({ data }: { data: ErrorReportDetailResponse }) {
  const r = data.report
  const Icon = KIND_ICON[r.kind] ?? Bug
  return (
    <>
      <section>
        <div className="flex flex-wrap items-center gap-2">
          <Icon className={cn("h-4 w-4", r.is_resolved ? "text-muted-foreground" : "text-danger")} />
          <span className="font-mono text-[13px] font-semibold">{r.error_class || "Error"}</span>
          {r.status_code != null && (
            <span className="rounded-md border border-border bg-surface-3 px-1.5 py-0.5 text-[10px]">{r.status_code}</span>
          )}
          <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground">
            {KIND_LABEL[r.kind]}
          </span>
          {r.is_reopened && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">
              <RotateCcw className="h-3 w-3" /> reaberto
            </span>
          )}
          {r.is_resolved && !r.is_reopened && (
            <span className="inline-flex items-center gap-1 rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
              <Check className="h-3 w-3" /> resolvido
            </span>
          )}
        </div>
        <div className="mt-2 whitespace-pre-wrap rounded-md border border-border bg-surface-3 p-2 text-[12px]" title={r.message}>
          {r.message || "(sem mensagem)"}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground md:grid-cols-4">
          <Kv label="Ocorrências" value={r.count} />
          <Kv label="Usuários afetados" value={r.affected_users} />
          <Kv label="Primeira vez" value={formatDateTime(r.first_seen_at)} />
          <Kv label="Última vez" value={formatDateTime(r.last_seen_at)} />
          {r.path && <Kv label="Caminho" value={<span className="font-mono">{r.method ? `${r.method} ` : ""}{r.path}</span>} />}
          <Kv label="Fingerprint" value={<span className="font-mono text-[10px]">{r.fingerprint.slice(0, 12)}…</span>} />
        </div>
        {r.resolution_note && (
          <div className="mt-2 rounded-md border border-border bg-muted/20 p-2 text-[11px]">
            <div className="mb-0.5 font-semibold uppercase tracking-wider text-muted-foreground">Nota</div>
            <div className="whitespace-pre-wrap">{r.resolution_note}</div>
          </div>
        )}
      </section>

      {r.sample_stack && (
        <section>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Stack mais recente</div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-surface-3 p-2 text-[10px] text-muted-foreground">
            {r.sample_stack}
          </pre>
        </section>
      )}

      {/* Breadcrumbs of the most recent occurrence — the killer feature. */}
      <section>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          O que o usuário estava fazendo antes
        </div>
        {data.recent_occurrences.length === 0 ? (
          <div className="rounded-md border border-border bg-muted/10 p-3 text-[11px] text-muted-foreground">
            Sem registros de ocorrência com breadcrumbs (pode ser um erro só-backend).
          </div>
        ) : (
          <Breadcrumbs occ={data.recent_occurrences[0]!} />
        )}
      </section>

      <section>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Usuários afetados (top)
        </div>
        {data.by_user.length === 0 ? (
          <div className="text-[11px] text-muted-foreground">Sem usuários identificados.</div>
        ) : (
          <ul className="rounded-md border border-border divide-y divide-border/60">
            {data.by_user.map((u) => (
              <li key={u.user_id} className="flex items-center justify-between px-3 py-1.5 text-[12px]">
                <Link to={`/admin/activity/users/${u.user_id}`} className="hover:text-primary hover:underline">
                  {u.user__username}
                </Link>
                <span className="tabular-nums text-muted-foreground">{u.n} ocorrência{u.n === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Últimas ocorrências ({data.recent_occurrences.length})
        </div>
        <ul className="divide-y divide-border/60 rounded-md border border-border">
          {data.recent_occurrences.map((o) => (
            <li key={o.id} className="flex items-start gap-2 px-3 py-2 text-[11px]">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-danger/70" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono">{o.path || "(sem path)"}</div>
                <div className="text-[10px] text-muted-foreground">
                  {o.user__username ?? `user #${o.user_id ?? "?"}`} · {formatDateTime(o.created_at)}
                </div>
                {o.meta?.message && (
                  <div className="mt-0.5 truncate text-muted-foreground" title={String(o.meta.message)}>
                    {String(o.meta.message)}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

function Breadcrumbs({ occ }: { occ: NonNullable<ErrorReportDetailResponse["recent_occurrences"][number]> }) {
  const crumbs = (occ.meta?.breadcrumbs ?? []) as Array<{ ts: number; kind: string; area?: string; path?: string; action?: string }>
  if (!crumbs.length) {
    return (
      <div className="rounded-md border border-border bg-muted/10 p-3 text-[11px] text-muted-foreground">
        Sem breadcrumbs nesta ocorrência.
      </div>
    )
  }
  const areaLabel = (id?: string) => (id && AREAS.find((a) => a.id === id)?.label) || id || "—"
  return (
    <ol className="relative space-y-1 rounded-md border border-border bg-surface-3 p-2">
      {crumbs.map((c, i) => (
        <li key={i} className="flex items-center gap-2 text-[11px]">
          <span className="w-12 shrink-0 font-mono text-[10px] text-muted-foreground">
            {relativeFromNow(c.ts, occ.created_at)}
          </span>
          <span className="rounded-md border border-border bg-background px-1.5 py-0.5 font-mono text-[10px]">
            {c.kind}
          </span>
          <span className="truncate">
            {c.action ? <span className="font-semibold">{c.action}</span> : null}
            {c.action && c.area ? " · " : null}
            {c.area ? areaLabel(c.area) : c.path || "—"}
          </span>
        </li>
      ))}
      <li className="flex items-center gap-2 border-t border-border pt-1 text-[11px] font-semibold text-danger">
        <span className="w-12 shrink-0 font-mono text-[10px]">0s</span>
        <span className="rounded-md border border-danger/40 bg-danger/10 px-1.5 py-0.5 font-mono text-[10px] text-danger">error</span>
        <span>{occ.path || "(erro)"}</span>
      </li>
    </ol>
  )
}

function relativeFromNow(ts: number, refIso: string): string {
  try {
    const ref = new Date(refIso).getTime()
    const diff = (ref - ts) / 1000
    if (diff < 60) return `-${Math.round(diff)}s`
    return `-${Math.round(diff / 60)}m`
  } catch {
    return ""
  }
}

function Kv({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-border bg-surface-3 px-2 py-1">
      <span className="uppercase tracking-wider">{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  )
}
