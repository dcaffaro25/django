import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  Brain, Activity, Play, RefreshCw, CheckCircle2, AlertCircle, Loader2,
  BookOpen, Wallet, FileCog,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { KpiCard } from "@/components/ui/kpi-card"
import { StatusBadge } from "@/components/ui/status-badge"
import {
  useEmbeddingsHealth,
  useEmbeddingsJobs,
  useEmbeddingsMissingCounts,
  useEmbeddingsTask,
  useStartEmbeddingsBackfill,
} from "@/features/reconciliation"
import type {
  EmbeddingCategoryProgress,
  EmbeddingHealth,
  EmbeddingJob,
  EmbeddingTaskState,
} from "@/features/reconciliation/types"
import { cn, formatDateTime, formatNumber } from "@/lib/utils"

const TERMINAL_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"])

/**
 * Reconciliation → Embeddings.
 *
 * Operator-facing control panel for the vector-embedding backfill. The
 * semantic-match / fuzzy pipelines depend on every `Transaction`,
 * `BankTransaction`, and `Account` having a `description_embedding`
 * (pgvector, 768-d). Records without an embedding silently short-circuit
 * those similarity components, so we surface:
 *
 *   - **Health** of the embedding provider (latency + model),
 *   - How many rows are still missing embeddings (split by model),
 *   - A one-click backfill trigger with a per-model cap,
 *   - Live progress of the Celery task kicked off by that trigger,
 *   - A history table of recent backfill jobs.
 *
 * Heavy lifting lives in `useEmbeddings*` hooks (hooks.ts); this page is
 * mostly wiring + layout.
 */
export function EmbeddingsPage() {
  const { t } = useTranslation(["reconciliation", "common"])

  const {
    data: health,
    isLoading: healthLoading,
    isFetching: healthFetching,
    refetch: refetchHealth,
  } = useEmbeddingsHealth()

  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const {
    data: activeTask,
    isFetching: activeFetching,
  } = useEmbeddingsTask(activeTaskId)

  const taskState = (activeTask?.state ?? "").toUpperCase()
  const taskRunning = !!activeTaskId && !TERMINAL_STATES.has(taskState)

  // While a task is running, tighten the missing-count poll interval so
  // the KPIs tick down in near-real-time. Falls back to a lazy 30s when
  // idle.
  const {
    data: missing,
    isLoading: missingLoading,
    refetch: refetchMissing,
  } = useEmbeddingsMissingCounts(taskRunning ? 3_000 : 30_000)

  const {
    data: jobs,
    isFetching: jobsFetching,
    refetch: refetchJobs,
  } = useEmbeddingsJobs(undefined, taskRunning ? 3_000 : undefined)

  const backfill = useStartEmbeddingsBackfill()
  const [perModelLimit, setPerModelLimit] = useState<string>("")

  // When a task reaches a terminal state, surface a toast, drop it from
  // local state (so the progress panel collapses back to its idle hint),
  // and trigger a final refresh of the counts + jobs list.
  useEffect(() => {
    if (!activeTaskId || !taskState || !TERMINAL_STATES.has(taskState)) return
    if (taskState === "SUCCESS") {
      toast.success(t("embeddings.toasts.completed") ?? "Embeddings gerados")
    } else if (taskState === "FAILURE") {
      toast.error(activeTask?.error || (t("embeddings.toasts.failed") ?? "Falha na geração"))
    } else {
      toast.info(t("embeddings.toasts.cancelled") ?? "Tarefa cancelada")
    }
    refetchMissing()
    refetchJobs()
    // Keep the task id around one tick so the progress panel shows the
    // terminal breakdown; user can dismiss via "Nova execução".
  }, [taskState, activeTaskId, activeTask?.error, refetchMissing, refetchJobs, t])

  const onStart = () => {
    const parsed = Number(perModelLimit)
    const payload = {
      per_model_limit: perModelLimit.trim() === "" ? undefined : (Number.isFinite(parsed) && parsed > 0 ? parsed : undefined),
    }
    backfill.mutate(payload, {
      onSuccess: (res) => {
        setActiveTaskId(res.task_id)
        toast.success(t("embeddings.toasts.started") ?? "Geração iniciada")
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  // Latest job in the list can be promoted to "active" on page load if
  // nothing is being polled — lets the operator resume watching a job
  // they kicked off from another tab.
  useEffect(() => {
    if (activeTaskId || !jobs?.length) return
    const latest = jobs[0]
    if (latest && !TERMINAL_STATES.has((latest.status ?? "").toUpperCase())) {
      setActiveTaskId(latest.task_id)
    }
  }, [jobs, activeTaskId])

  const totalMissing = missing?.total_missing ?? 0
  const canStart = !backfill.isPending && !taskRunning

  return (
    <div className="space-y-6">
      <SectionHeader
        title={t("embeddings.title")}
        subtitle={t("embeddings.subtitle") ?? ""}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                refetchHealth()
                refetchMissing()
                refetchJobs()
              }}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
              title={t("actions.refresh", { ns: "common" }) ?? "Atualizar"}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", (healthFetching || jobsFetching) && "animate-spin")} />
              {t("actions.refresh", { ns: "common" })}
            </button>
          </div>
        }
      />

      {/* Health + trigger row */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <HealthCard
          health={health}
          loading={healthLoading}
        />
        <div className="card-elevated col-span-1 p-4 lg:col-span-2">
          <div className="mb-3 flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            <h3 className="text-[13px] font-semibold">{t("embeddings.backfill_title")}</h3>
          </div>
          <p className="mb-3 text-[12px] text-muted-foreground">
            {t("embeddings.backfill_hint")}
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              {t("embeddings.per_model_limit")}
              <input
                type="number"
                min={1}
                step={100}
                value={perModelLimit}
                onChange={(e) => setPerModelLimit(e.target.value)}
                placeholder={t("embeddings.per_model_limit_placeholder") ?? "Sem limite"}
                className="h-8 w-40 rounded-md border border-border bg-background px-2 text-[12px] tabular-nums outline-none focus:border-ring"
              />
            </label>
            <button
              onClick={onStart}
              disabled={!canStart || totalMissing === 0}
              title={totalMissing === 0 ? t("embeddings.nothing_to_do") ?? "" : undefined}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {backfill.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {t("embeddings.start")}
            </button>
            {taskRunning && (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Activity className="h-3 w-3 animate-pulse text-primary" />
                {t("embeddings.running_hint")}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Missing counts */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label={t("embeddings.missing_transactions")}
          value={missingLoading ? "—" : formatNumber(missing?.transactions_missing ?? 0)}
          icon={<BookOpen className="h-4 w-4" />}
          tone="default"
        />
        <KpiCard
          label={t("embeddings.missing_bank_transactions")}
          value={missingLoading ? "—" : formatNumber(missing?.bank_transactions_missing ?? 0)}
          icon={<Wallet className="h-4 w-4" />}
          tone="default"
        />
        <KpiCard
          label={t("embeddings.missing_accounts")}
          value={missingLoading ? "—" : formatNumber(missing?.accounts_missing ?? 0)}
          icon={<FileCog className="h-4 w-4" />}
          tone="default"
        />
        <KpiCard
          label={t("embeddings.missing_total")}
          value={missingLoading ? "—" : formatNumber(totalMissing)}
          icon={<Brain className="h-4 w-4" />}
          tone={totalMissing > 0 ? "warning" : "default"}
        />
      </div>

      {/* Live task progress */}
      {activeTaskId && activeTask && (
        <div className="card-elevated p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-[13px] font-semibold">{t("embeddings.progress_title")}</h3>
              <StatusBadge status={mapTaskState(taskState)} />
              {activeFetching && <Loader2 className="h-3 w-3 animate-spin text-primary/80" />}
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] text-muted-foreground">{activeTask.task_id}</span>
              {!taskRunning && (
                <button
                  onClick={() => setActiveTaskId(null)}
                  className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
                >
                  {t("actions.close", { ns: "common" })}
                </button>
              )}
            </div>
          </div>
          <ProgressBreakdown progress={activeTask.progress} />
          {activeTask.error && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 p-2 text-[12px] text-danger">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px]">
                {activeTask.error}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Recent jobs */}
      <div className="card-elevated p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[13px] font-semibold">{t("embeddings.recent_jobs")}</h3>
          <span className="text-[11px] text-muted-foreground">
            {(jobs ?? []).length} {(jobs ?? []).length === 1 ? "job" : "jobs"}
          </span>
        </div>
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-[12px]">
            <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-8 px-3">Task</th>
                <th className="h-8 px-3">Status</th>
                <th className="h-8 px-3">Kind</th>
                <th className="h-8 px-3 text-right">Progresso</th>
                <th className="h-8 px-3">Iniciado</th>
                <th className="h-8 px-3">Atualizado</th>
              </tr>
            </thead>
            <tbody>
              {(!jobs || jobs.length === 0) ? (
                <tr>
                  <td colSpan={6} className="h-16 px-3 text-center text-muted-foreground">
                    {t("embeddings.no_jobs")}
                  </td>
                </tr>
              ) : jobs.map((job) => (
                <JobRow
                  key={job.task_id}
                  job={job}
                  isActive={job.task_id === activeTaskId}
                  onResume={() => setActiveTaskId(job.task_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/* ---------------- Subcomponents ---------------- */

/**
 * Map the Celery state string the backend returns to one of the ui's
 * StatusBadge tones so the visual vocabulary matches the tasks page.
 */
function mapTaskState(state: string): string {
  const s = state.toUpperCase()
  if (s === "SUCCESS") return "completed"
  if (s === "FAILURE") return "failed"
  if (s === "REVOKED") return "cancelled"
  if (s === "PENDING") return "queued"
  if (s === "STARTED" || s === "RUNNING" || s === "RETRY" || s === "PROGRESS") return "running"
  return s.toLowerCase() || "queued"
}

function HealthCard({
  health,
  loading,
}: {
  health?: EmbeddingHealth
  loading: boolean
}) {
  const { t } = useTranslation("reconciliation")
  const ok = !!health?.ok
  return (
    <div className="card-elevated p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <h3 className="text-[13px] font-semibold">{t("embeddings.health_title")}</h3>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
            loading
              ? "border-border bg-muted/30 text-muted-foreground"
              : ok
                ? "border-success/30 bg-success/10 text-success"
                : "border-danger/30 bg-danger/10 text-danger",
          )}
        >
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : ok ? (
            <CheckCircle2 className="h-3 w-3" />
          ) : (
            <AlertCircle className="h-3 w-3" />
          )}
          {loading ? "…" : ok ? t("embeddings.health_ok") : t("embeddings.health_down")}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
        <dt className="text-muted-foreground">{t("embeddings.health_model")}</dt>
        <dd className="truncate font-mono">{health?.model ?? "—"}</dd>
        <dt className="text-muted-foreground">{t("embeddings.health_dim")}</dt>
        <dd className="tabular-nums">{health?.dim ?? "—"}</dd>
        <dt className="text-muted-foreground">{t("embeddings.health_latency")}</dt>
        <dd className="tabular-nums">{health?.latency_ms != null ? `${health.latency_ms} ms` : "—"}</dd>
        <dt className="text-muted-foreground">{t("embeddings.health_endpoint")}</dt>
        <dd className="truncate font-mono">{health?.endpoint ?? "—"}</dd>
      </dl>
      {health?.error && (
        <div className="mt-2 rounded-md border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">
          {health.error}
        </div>
      )}
    </div>
  )
}

function ProgressBreakdown({
  progress,
}: {
  progress?: EmbeddingTaskState["progress"]
}) {
  const entries = useMemo(() => {
    if (!progress) return []
    return Object.entries(progress)
      .filter(([, v]) => !!v)
      .map(([key, v]) => [key, v as EmbeddingCategoryProgress] as const)
  }, [progress])
  if (entries.length === 0) {
    return (
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Aguardando primeiros dados do worker…
      </div>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {entries.map(([key, p]) => {
        const pct = p.total > 0 ? Math.min(100, (p.done / p.total) * 100) : 0
        const done = p.total > 0 && p.done >= p.total
        return (
          <div key={key} className="rounded-md border border-border bg-surface-3 p-2.5">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-medium capitalize">{categoryLabel(key)}</span>
              <span className="tabular-nums text-[11px] text-muted-foreground">
                {p.done.toLocaleString("pt-BR")} / {p.total.toLocaleString("pt-BR")}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted/40">
              <div
                className={cn("h-full transition-[width]", done ? "bg-success" : "bg-primary")}
                style={{ width: `${pct.toFixed(1)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function categoryLabel(key: string): string {
  switch (key) {
    case "transactions": return "Lançamentos"
    case "bank_transactions": return "Extratos"
    case "accounts": return "Plano de contas"
    default: return key.replace(/_/g, " ")
  }
}

function JobRow({
  job,
  isActive,
  onResume,
}: {
  job: EmbeddingJob
  isActive: boolean
  onResume: () => void
}) {
  const progressSummary = useMemo(() => {
    const p = job.progress
    if (!p) return "—"
    const parts: string[] = []
    for (const [k, v] of Object.entries(p)) {
      if (!v) continue
      parts.push(`${categoryLabel(k)}: ${v.done}/${v.total}`)
    }
    return parts.length > 0 ? parts.join(" · ") : "—"
  }, [job.progress])
  const terminal = TERMINAL_STATES.has((job.status ?? "").toUpperCase())
  return (
    <tr
      onClick={terminal ? undefined : onResume}
      className={cn(
        "border-t border-border",
        !terminal && "cursor-pointer hover:bg-accent/50",
        isActive && "bg-primary/5",
      )}
    >
      <td className="h-9 px-3 font-mono text-[11px] text-muted-foreground">{job.task_id}</td>
      <td className="h-9 px-3"><StatusBadge status={mapTaskState(job.status ?? "")} /></td>
      <td className="h-9 px-3">{job.kind ?? "embeddings"}</td>
      <td className="h-9 px-3 text-right tabular-nums text-[11px] text-muted-foreground">{progressSummary}</td>
      <td className="h-9 px-3 text-muted-foreground">{job.created_at ? formatDateTime(job.created_at) : "—"}</td>
      <td className="h-9 px-3 text-muted-foreground">{job.updated_at ? formatDateTime(job.updated_at) : "—"}</td>
    </tr>
  )
}
