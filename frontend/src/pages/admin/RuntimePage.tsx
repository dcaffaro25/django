import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  AlertTriangle, Database, Layers, Loader2, RefreshCw, Server,
  Settings2, TerminalSquare,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { adminApi, type RuntimeConfigResponse } from "@/features/admin/api"
import { cn } from "@/lib/utils"

/**
 * Runtime Config page (Phase 6.z-h+).
 *
 * Reads ``GET /api/admin/runtime/`` and renders what the web
 * service + every live Celery worker picked up at boot. Primary
 * use case: confirming a Railway deploy ``startCommand`` matches
 * intent without opening a shell.
 *
 * Layout — six cards:
 *   1. Process (web) — argv, parent_argv, hostname, versions.
 *   2. Django settings snapshot — critical knobs.
 *   3. Celery app.conf (web) — reliability flags.
 *   4. Celery workers — per-worker queues / pool / prefetch.
 *   5. Beat schedule — definition (not liveness).
 *   6. Redis / stale sessions — queue depth + stuck v2 imports.
 *
 * The page is read-only. Emergency actions (purge / revoke) live
 * in the management commands; wiring them as HTTP actions is a
 * separate decision (destructive tools behind shell-only access
 * is generally safer).
 */
export function RuntimePage() {
  const [data, setData] = useState<RuntimeConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await adminApi.runtimeConfig({
        queues: ["celery", "recon_legacy", "recon_fast"],
      })
      setData(res)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Falha ao carregar"
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // Auto-refresh every 15s — gives a live feel without hammering.
    const id = window.setInterval(() => { void load() }, 15_000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Runtime config"
        subtitle="O que os serviços carregaram ao subir. Atualiza a cada 15s."
        actions={
          <button
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-60"
          >
            {loading
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : <RefreshCw className="h-3.5 w-3.5" />}
            Atualizar
          </button>
        }
      />

      {error && (
        <div className="card-elevated rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive">
          {error}
        </div>
      )}

      {!data && loading && (
        <div className="card-elevated flex items-center gap-2 rounded-md p-3 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Carregando snapshot do runtime…
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <ProcessCard data={data} />
          <CeleryWorkersCard data={data} />
          <DjangoCard data={data} />
          <CeleryLocalCard data={data} />
          <BeatScheduleCard data={data} />
          <RedisAndStaleCard data={data} />
        </div>
      )}
    </div>
  )
}

// ---- cards ---------------------------------------------------------------

function Card({
  icon, title, hint, children,
}: {
  icon: React.ReactNode
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <section className="card-elevated rounded-md border border-border p-3">
      <header className="mb-2 flex items-start gap-2">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold">{title}</div>
          {hint && (
            <div className="text-[11px] text-muted-foreground">{hint}</div>
          )}
        </div>
      </header>
      <div className="space-y-1 text-[12px]">{children}</div>
    </section>
  )
}

function KV({
  k, v, mono = true, wrap = false,
}: {
  k: string
  v: React.ReactNode
  mono?: boolean
  wrap?: boolean
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="shrink-0 text-muted-foreground">{k}:</span>
      <span
        className={cn(
          "min-w-0 flex-1 text-foreground",
          mono && "font-mono text-[11px]",
          wrap ? "break-words" : "truncate",
        )}
        title={typeof v === "string" ? v : undefined}
      >
        {v}
      </span>
    </div>
  )
}

function ProcessCard({ data }: { data: RuntimeConfigResponse }) {
  const p = data.process
  return (
    <Card
      icon={<Server className="h-4 w-4" />}
      title="Web process"
      hint="Quem atendeu ESTE request."
    >
      <KV k="hostname" v={p.hostname} />
      <KV k="pid" v={String(p.pid)} />
      <KV k="python" v={p.python_version} />
      <KV k="django" v={p.django_version} />
      <KV k="celery" v={p.celery_version ?? "—"} />
      <div className="pt-1" />
      <KV k="argv" v={p.argv.join(" ")} wrap />
      {p.parent_argv && p.parent_argv.length > 0 && (
        <KV k="parent_argv" v={p.parent_argv.join(" ")} wrap />
      )}
      {!p.parent_argv && (
        <KV k="parent_argv" v={<em className="not-italic text-muted-foreground">—</em>} mono={false} />
      )}
      {Object.keys(p.env || {}).length > 0 && (
        <>
          <div className="pt-1 text-[11px] font-semibold text-muted-foreground">env</div>
          {Object.entries(p.env).map(([k, v]) => (
            <KV key={k} k={k} v={v} />
          ))}
        </>
      )}
    </Card>
  )
}

function DjangoCard({ data }: { data: RuntimeConfigResponse }) {
  const d = data.django
  return (
    <Card
      icon={<Settings2 className="h-4 w-4" />}
      title="Django settings"
      hint="Snapshot curado."
    >
      <KV k="settings_module" v={d.settings_module ?? "—"} />
      <KV k="DEBUG" v={String(d.DEBUG)} />
      <KV k="TZ" v={d.TIME_ZONE ?? "—"} />
      <KV k="USE_TZ" v={String(d.USE_TZ)} />
      <KV k="ALLOWED_HOSTS" v={d.ALLOWED_HOSTS.join(", ") || "—"} />
      <KV k="LANGUAGE_CODE" v={d.LANGUAGE_CODE ?? "—"} />
      <div className="pt-1" />
      <KV k="CELERY_BROKER_URL" v={d.CELERY_BROKER_URL} />
      <KV k="CELERY_RESULT_BACKEND" v={d.CELERY_RESULT_BACKEND} />
      <KV
        k="CELERY_TASK_TIME_LIMIT"
        v={
          d.CELERY_TASK_TIME_LIMIT != null
            ? `${d.CELERY_TASK_TIME_LIMIT}s (soft=${d.CELERY_TASK_SOFT_TIME_LIMIT ?? "—"}s)`
            : "—"
        }
      />
      <KV k="CELERY_TASK_ALWAYS_EAGER" v={String(d.CELERY_TASK_ALWAYS_EAGER)} />
      {Object.keys(d.DATABASES || {}).length > 0 && (
        <>
          <div className="pt-1 text-[11px] font-semibold text-muted-foreground">databases</div>
          {Object.entries(d.DATABASES).map(([alias, cfg]) => (
            <KV
              key={alias}
              k={alias}
              v={`${cfg.ENGINE ?? "?"} @ ${cfg.HOST ?? "?"}:${cfg.PORT ?? "?"} / ${cfg.NAME ?? "?"}`}
            />
          ))}
        </>
      )}
    </Card>
  )
}

function CeleryLocalCard({ data }: { data: RuntimeConfigResponse }) {
  const c = data.celery_local
  const entries = Object.entries(c)
  return (
    <Card
      icon={<Settings2 className="h-4 w-4" />}
      title="Celery app.conf (web)"
      hint="O que ESTE processo carregou de app.conf."
    >
      {entries.length === 0 && (
        <div className="text-muted-foreground">— vazio</div>
      )}
      {entries.map(([k, v]) => (
        <KV
          key={k}
          k={k}
          v={typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}
        />
      ))}
    </Card>
  )
}

function CeleryWorkersCard({ data }: { data: RuntimeConfigResponse }) {
  const cw = data.celery_workers
  const workers = Object.entries(cw.workers || {})
  return (
    <Card
      icon={<Layers className="h-4 w-4" />}
      title={`Celery workers (${workers.length})`}
      hint="Remote-inspect dos workers vivos — confirma -Q, --autoscale, prefetch."
    >
      {workers.length === 0 && (
        <div className="text-muted-foreground">
          Nenhum worker respondeu dentro do timeout.
        </div>
      )}
      {workers.map(([name, info]) => (
        <div
          key={name}
          className="mb-2 rounded-md border border-border bg-surface-2 p-2 last:mb-0"
        >
          <div className="font-mono text-[11px] font-semibold">{name}</div>
          <div className="mt-1 space-y-0.5">
            <KV
              k="queues"
              v={info.queues_subscribed?.join(", ") || "—"}
              wrap
            />
            <KV
              k="pool_max"
              v={info.pool_processes != null ? String(info.pool_processes) : "—"}
            />
            <KV
              k="prefetch"
              v={
                info.prefetch_count != null
                  ? `${info.prefetch_count} (= multiplier × pool)`
                  : "—"
              }
            />
            <KV
              k="uptime_s"
              v={info.uptime_seconds != null ? formatUptime(info.uptime_seconds) : "—"}
            />
            <KV k="total_tasks" v={formatTotalTasks(info.total_tasks)} wrap />
          </div>
        </div>
      ))}
      {(cw.warnings || []).map((w, i) => (
        <div
          key={i}
          className="mt-1 flex items-start gap-1 text-[11px] text-amber-600"
        >
          <AlertTriangle className="h-3 w-3 shrink-0 translate-y-[2px]" />
          <span>{w}</span>
        </div>
      ))}
      {cw.error && (
        <div className="mt-1 text-[11px] text-destructive">! {cw.error}</div>
      )}
    </Card>
  )
}

function BeatScheduleCard({ data }: { data: RuntimeConfigResponse }) {
  const entries = Object.entries(data.beat_schedule || {})
  return (
    <Card
      icon={<TerminalSquare className="h-4 w-4" />}
      title={`Beat schedule (${entries.length})`}
      hint="Definição. Não garante que o serviço beat esteja vivo."
    >
      {entries.length === 0 && (
        <div className="text-muted-foreground">— nenhum agendamento</div>
      )}
      {entries.map(([name, e]) => (
        <div
          key={name}
          className="mb-2 rounded-md border border-border bg-surface-2 p-2 last:mb-0"
        >
          <div className="font-mono text-[11px] font-semibold">{name}</div>
          <div className="mt-0.5 space-y-0.5">
            <KV k="task" v={e.task} />
            <KV k="schedule" v={e.schedule} />
            {e.options && Object.keys(e.options).length > 0 && (
              <KV k="options" v={JSON.stringify(e.options)} />
            )}
            {e.kwargs && Object.keys(e.kwargs).length > 0 && (
              <KV k="kwargs" v={JSON.stringify(e.kwargs)} />
            )}
          </div>
        </div>
      ))}
    </Card>
  )
}

/**
 * Celery's ``stats().total`` is a dict of ``{task_name: count}``, not
 * an integer (worker-lifetime totals per task name). Older code
 * ``String(...)`` rendered ``[object Object]``. Render the sum so
 * operators see a single "how many tasks has this worker handled
 * total" number, plus the top 3 tasks in a title tooltip.
 */
function formatTotalTasks(total: unknown): string {
  if (total == null) return "—"
  if (typeof total === "number") return String(total)
  if (typeof total === "object" && total !== null) {
    const entries = Object.entries(total as Record<string, unknown>)
      .filter(([, v]) => typeof v === "number")
      .map(([k, v]) => [k, v as number] as const)
    if (entries.length === 0) return "0"
    const sum = entries.reduce((acc, [, v]) => acc + v, 0)
    // Top 3 by count for the hover, so operators can spot which
    // task dominates the worker's lifetime without opening raw JSON.
    const top = entries
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([name, count]) => `${name}: ${count}`)
      .join(" · ")
    return top ? `${sum}  (${top})` : String(sum)
  }
  return String(total)
}

/**
 * Seconds → "Nh Mm" / "Nm Ss" / "Ns" for worker uptime. 942s is
 * ``15m 42s`` instead of a raw number — more scannable at a glance.
 */
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  const mm = m % 60
  return `${h}h ${mm}m`
}

function RedisAndStaleCard({ data }: { data: RuntimeConfigResponse }) {
  const r = data.redis_queues
  const s = data.stale_import_sessions
  return (
    <Card
      icon={<Database className="h-4 w-4" />}
      title="Redis + sessões v2 travadas"
      hint="Profundidade de fila + importações v2 além do hard limit."
    >
      <div className="text-[11px] font-semibold text-muted-foreground">queue depth (LLEN)</div>
      {Object.entries(r.depths || {}).map(([q, d]) => (
        <KV key={q} k={q} v={d == null ? "—" : String(d)} />
      ))}
      {Object.keys(r.depths || {}).length === 0 && (
        <div className="text-muted-foreground">— sem dados</div>
      )}
      {r.error && (
        <div className="mt-1 text-[11px] text-amber-600">! {r.error}</div>
      )}

      <div className="pt-2 text-[11px] font-semibold text-muted-foreground">
        stale v2 import sessions
      </div>
      {s.count != null ? (
        <>
          <KV k="count" v={String(s.count)} />
          {s.oldest_pks?.length > 0 && (
            <KV k="oldest_pks" v={s.oldest_pks.join(", ")} />
          )}
          {s.hard_limit_seconds != null && (
            <KV k="hard_limit_s" v={String(s.hard_limit_seconds)} />
          )}
          {s.count > 0 && (
            <div className="mt-1 rounded-md bg-amber-500/10 p-2 text-[11px] text-amber-700">
              Reaper do Beat deve zerar isso a cada 5 min. Se persistir,
              o serviço <code className="rounded bg-amber-500/20 px-1">beat</code> pode não estar rodando.
            </div>
          )}
        </>
      ) : (
        <div className="text-muted-foreground">— indisponível</div>
      )}
      {s.error && (
        <div className="mt-1 text-[11px] text-destructive">! {s.error}</div>
      )}
    </Card>
  )
}
