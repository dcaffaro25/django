import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import {
  Play,
  RefreshCw,
  XCircle,
  AlertCircle,
  Hash,
  RotateCw,
  Trash2,
  Sparkles,
  Search,
  CheckCircle2,
  Clock,
  Wand2,
  Calendar,
  Inbox,
  Zap,
} from "lucide-react"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { StatusBadge } from "@/components/ui/status-badge"
import {
  useCancelReconTask,
  useDeleteReconTask,
  useReconConfigs,
  useReconPipelines,
  useReconTask,
  useReconTasks,
  useStartReconTask,
} from "@/features/reconciliation"
import { cn, formatDateTime, formatDuration, formatNumber } from "@/lib/utils"
import type { ReconciliationTask, ReconTaskStatus } from "@/features/reconciliation/types"
import { TaskSuggestionsView } from "./SuggestionsPage"

const STATUS_FILTERS: (ReconTaskStatus | "all")[] = [
  "all",
  "running",
  "queued",
  "completed",
  "failed",
  "cancelled",
]

/**
 * "Past" here means the task is no longer actionable (the engine has stopped
 * running). These tasks have persisted suggestions the user can review on
 * the right pane. Running/queued tasks open the live detail drawer instead.
 */
const PAST_STATUSES: ReconTaskStatus[] = ["completed", "failed", "cancelled"]
function isPast(status: string | undefined): boolean {
  return !!status && (PAST_STATUSES as string[]).includes(status)
}

/** Suggestions left to triage (engine emitted - finalized). Clamped at 0
 *  because the engine count can lag behind operator activity. */
function pendingCount(t: ReconciliationTask): number {
  const total = t.suggestion_count ?? 0
  const accepted = t.matched_bank_transactions ?? 0
  return Math.max(0, total - accepted)
}

export function TasksPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = Number(searchParams.get("id") ?? 0) || null
  const showNew = searchParams.get("new") === "1"
  const liveDetail = searchParams.get("live") === "1"

  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all")
  const [search, setSearch] = useState("")
  const { data, isLoading, refetch, isFetching } = useReconTasks({
    status: statusFilter === "all" ? undefined : statusFilter,
    pollMs: 5000,
  })

  const rows = useMemo(() => {
    const all = data ?? []
    if (!search.trim()) return all
    const q = search.trim().toLowerCase()
    return all.filter((r) => {
      const haystack = [
        String(r.id),
        r.config_name,
        r.pipeline_name,
        r.status,
        r.error_message,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [data, search])

  // Default to the first past row whenever the list updates and nothing is
  // selected — gives the operator something to look at on the right pane
  // without forcing a click.
  const effectiveSelectedId = useMemo(() => {
    if (selectedId != null) return selectedId
    const firstPast = rows.find((r) => isPast(r.status))
    return firstPast?.id ?? null
  }, [selectedId, rows])

  const startTask = useStartReconTask()
  const deleteTask = useDeleteReconTask()

  const onSelect = (task: ReconciliationTask) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set("id", String(task.id))
        // Live detail drawer for in-flight runs; suggestions panel for the rest.
        if (!isPast(task.status)) next.set("live", "1")
        else next.delete("live")
        return next
      },
      { replace: true },
    )
  }

  const onClearSelection = () => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete("id")
        next.delete("live")
        return next
      },
      { replace: true },
    )
  }

  const onRerun = (task: ReconciliationTask, e: React.MouseEvent) => {
    e.stopPropagation()
    const body = task.config
      ? { config_id: task.config, auto_match_100: !!task.auto_match_enabled }
      : task.pipeline
        ? { pipeline_id: task.pipeline, auto_match_100: !!task.auto_match_enabled }
        : null
    if (!body) {
      toast.error("Execução sem config/pipeline referenciado")
      return
    }
    startTask.mutate(body, {
      onSuccess: (newTask) => toast.success(`Nova execução #${newTask.id} iniciada`),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const onDelete = (task: ReconciliationTask, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir execução #${task.id}?`)) return
    deleteTask.mutate(task.id, {
      onSuccess: () => {
        toast.success("Execução excluída")
        if (effectiveSelectedId === task.id) onClearSelection()
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  return (
    <div className="grid h-[calc(100dvh-180px)] gap-3 lg:grid-cols-[380px_minmax(0,1fr)]">
      {/* === LEFT: executions list ============================================ */}
      <div className="flex min-h-0 flex-col gap-2">
        {/* Header row — title + actions */}
        <div className="flex items-center gap-1.5">
          <div className="min-w-0">
            <h2 className="truncate text-[13px] font-semibold leading-tight">
              {t("tasks.title")}
            </h2>
            <p className="truncate text-[11px] text-muted-foreground">
              {rows.length} {rows.length === 1 ? "execução" : "execuções"}
            </p>
          </div>
          <button
            onClick={() => void refetch()}
            className={cn(
              "ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent",
              isFetching && "opacity-60",
            )}
            title={t("actions.refresh", { ns: "common" })}
          >
            <RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} />
          </button>
          <button
            onClick={() =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev)
                next.set("new", "1")
                return next
              })
            }
            className="inline-flex h-7 items-center gap-1.5 rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Play className="h-3 w-3" /> {t("tasks.new_task")}
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar #id, config…"
            className="h-7 w-full rounded-md border border-border bg-background pl-6 pr-2 text-[12px] outline-none focus:border-ring"
          />
        </div>

        {/* Status filter pills */}
        <div className="flex flex-wrap items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[11px]">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "h-5 rounded-sm px-1.5 font-medium capitalize transition-colors",
                statusFilter === s
                  ? "bg-background text-foreground shadow-soft"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s === "all" ? "Todas" : t(`status.${s}`, { ns: "common" })}
            </button>
          ))}
        </div>

        {/* Scrollable list */}
        <div className="card-elevated flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="space-y-2 p-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="h-16 animate-pulse rounded-md bg-muted/40" />
                ))}
              </div>
            ) : rows.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-1.5 p-4 text-center text-[12px] text-muted-foreground">
                <Inbox className="h-5 w-5" />
                {t("tasks.empty")}
              </div>
            ) : (
              <ul className="divide-y divide-border/60">
                {rows.map((task) => (
                  <ExecutionListItem
                    key={task.id}
                    task={task}
                    selected={effectiveSelectedId === task.id}
                    onSelect={() => onSelect(task)}
                    onRerun={(e) => onRerun(task, e)}
                    onDelete={(e) => onDelete(task, e)}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* === RIGHT: suggestions for the selected execution ==================== */}
      <div className="min-h-0 overflow-y-auto">
        {effectiveSelectedId == null ? (
          <EmptySelectionPanel />
        ) : (
          <TaskSuggestionsView
            key={effectiveSelectedId}
            taskId={effectiveSelectedId}
            embedded
            onExit={onClearSelection}
          />
        )}
      </div>

      {/* Live drawer for running/queued executions */}
      <TaskDetailDrawer
        taskId={liveDetail ? selectedId : null}
        onClose={onClearSelection}
      />

      {/* New-task drawer */}
      <NewTaskDrawer
        open={showNew}
        onClose={() =>
          setSearchParams((prev) => {
            const next = new URLSearchParams(prev)
            next.delete("new")
            return next
          })
        }
      />
    </div>
  )
}

// =============================================================================
// Execution list row (left pane)
// =============================================================================

function ExecutionListItem({
  task,
  selected,
  onSelect,
  onRerun,
  onDelete,
}: {
  task: ReconciliationTask
  selected: boolean
  onSelect: () => void
  onRerun: (e: React.MouseEvent) => void
  onDelete: (e: React.MouseEvent) => void
}) {
  const accepted = task.matched_bank_transactions ?? 0
  const total = task.suggestion_count ?? 0
  const pending = pendingCount(task)
  const auto = task.auto_match_applied ?? 0
  const banks = task.bank_candidates ?? 0
  const books = task.journal_candidates ?? 0
  const coverage = banks > 0 ? Math.min(1, accepted / banks) : 0
  const ranOn = task.created_at ? formatDateTime(task.created_at) : null
  const dur = formatDuration(task.duration_seconds ?? null)

  return (
    <li
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        "group block cursor-pointer px-2.5 py-2 text-left outline-none transition-colors hover:bg-accent/40 focus-visible:bg-accent/40",
        selected && "bg-primary/10 hover:bg-primary/15",
      )}
    >
      <div>
        {/* Row 1: status + id + name + actions */}
        <div className="flex items-center gap-1.5">
          <StatusBadge status={task.status} />
          <span className="font-mono text-[10px] text-muted-foreground">#{task.id}</span>
          <span className="ml-1 min-w-0 flex-1 truncate text-[12px] font-medium">
            {task.config_name ?? task.pipeline_name ?? "—"}
          </span>
          <span className="invisible flex shrink-0 items-center gap-0.5 group-hover:visible">
            <button
              type="button"
              onClick={onRerun}
              title="Executar novamente"
              className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-background hover:text-foreground"
            >
              <RotateCw className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              title="Excluir"
              className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-danger/10 hover:text-danger"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </span>
        </div>

        {/* Row 2: metric chips */}
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
          <span title="Candidatos banco × livro" className="inline-flex items-center gap-0.5">
            <Wand2 className="h-2.5 w-2.5" />
            {formatNumber(banks)}×{formatNumber(books)}
          </span>
          <span className="text-border">·</span>
          <span title="Sugestões geradas" className="inline-flex items-center gap-0.5">
            <Sparkles className="h-2.5 w-2.5" />
            {formatNumber(total)}
          </span>
          <span className="text-border">·</span>
          <span
            className={cn(
              "inline-flex items-center gap-0.5",
              accepted > 0 && "text-success",
            )}
            title="Bancárias conciliadas a partir desta execução"
          >
            <CheckCircle2 className="h-2.5 w-2.5" />
            {formatNumber(accepted)}
          </span>
          <span className="text-border">·</span>
          <span
            className={cn(
              "inline-flex items-center gap-0.5",
              pending > 0 && "text-foreground",
            )}
            title="Sugestões pendentes de revisão"
          >
            <Clock className="h-2.5 w-2.5" />
            {formatNumber(pending)}
          </span>
          {auto > 0 && (
            <>
              <span className="text-border">·</span>
              <span className="inline-flex items-center gap-0.5 text-info" title="Auto-aplicadas (≥ 100%)">
                <Zap className="h-2.5 w-2.5" />
                {formatNumber(auto)}
              </span>
            </>
          )}
        </div>

        {/* Row 3: progress bar of accepted / banks */}
        {banks > 0 && (
          <div className="mt-1 flex items-center gap-1.5">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-3">
              <div
                className={cn(
                  "h-full transition-[width]",
                  coverage >= 0.66
                    ? "bg-success"
                    : coverage >= 0.33
                      ? "bg-warning"
                      : "bg-primary/60",
                )}
                style={{ width: `${coverage * 100}%` }}
              />
            </div>
            <span className="w-7 text-right text-[9px] tabular-nums text-muted-foreground">
              {(coverage * 100).toFixed(0)}%
            </span>
          </div>
        )}

        {/* Row 4: when + duration + error */}
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
          {ranOn && (
            <span className="inline-flex items-center gap-0.5">
              <Calendar className="h-2.5 w-2.5" />
              {ranOn}
            </span>
          )}
          {dur && dur !== "—" && (
            <>
              <span className="text-border">·</span>
              <span className="inline-flex items-center gap-0.5">
                <Clock className="h-2.5 w-2.5" />
                {dur}
              </span>
            </>
          )}
          {task.error_message && (
            <span
              className="ml-auto inline-flex max-w-[180px] items-center gap-0.5 truncate text-danger"
              title={task.error_message}
            >
              <AlertCircle className="h-2.5 w-2.5 shrink-0" />
              {task.error_message}
            </span>
          )}
        </div>
      </div>
    </li>
  )
}

// =============================================================================
// Right-pane placeholder when no execution is selected
// =============================================================================

function EmptySelectionPanel() {
  return (
    <div className="card-elevated flex h-[60vh] flex-col items-center justify-center gap-2 px-6 text-center text-[13px] text-muted-foreground">
      <Sparkles className="h-7 w-7 text-muted-foreground/60" />
      <span className="font-medium text-foreground">Sugestões da execução</span>
      <span className="max-w-md text-[12px]">
        Selecione uma execução à esquerda para revisar as sugestões geradas. Você
        pode aceitá-las em lote, ajustar filtros por confiança, valor e data, e
        finalizar as conciliações daqui mesmo.
      </span>
    </div>
  )
}

// =============================================================================
// Live execution drawer (running/queued)
// =============================================================================

function TaskDetailDrawer({ taskId, onClose }: { taskId: number | null; onClose: () => void }) {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: task } = useReconTask(taskId)
  const cancel = useCancelReconTask()

  const onCopy = (v: string) => {
    navigator.clipboard.writeText(v)
    toast.success("Copiado")
  }

  return (
    <Drawer.Root open={!!taskId} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Hash className="h-3.5 w-3.5 text-muted-foreground" />
              Execução {task ? `#${task.id}` : ""}
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              ×
            </button>
          </div>

          {!task ? (
            <div className="p-4">
              <div className="h-4 w-32 animate-pulse rounded bg-muted/60" />
              <div className="mt-2 h-3 w-64 animate-pulse rounded bg-muted/40" />
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto p-4 text-[12px]">
              <div className="mb-4 flex items-center gap-2">
                <StatusBadge status={task.status} />
                <span className="text-muted-foreground">
                  {task.created_at ? formatDateTime(task.created_at) : "—"}
                </span>
                {task.task_id && (
                  <button
                    onClick={() => onCopy(task.task_id!)}
                    className="ml-auto inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                    title={task.task_id}
                  >
                    celery
                  </button>
                )}
              </div>

              <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="Configuração" value={task.config_name ?? "—"} />
                <Cell label="Pipeline" value={task.pipeline_name ?? "—"} />
                <Cell label="Bancárias" value={formatNumber(task.bank_candidates ?? 0)} />
                <Cell label="Contábeis" value={formatNumber(task.journal_candidates ?? 0)} />
                <Cell label="Sugestões" value={formatNumber(task.suggestion_count ?? 0)} />
                <Cell label="Matches (banco)" value={formatNumber(task.matched_bank_transactions ?? 0)} />
                <Cell label="Matches (livro)" value={formatNumber(task.matched_journal_entries ?? 0)} />
                <Cell label="Auto-aplicados" value={formatNumber(task.auto_match_applied ?? 0)} />
                <Cell label="Auto-pulados" value={formatNumber(task.auto_match_skipped ?? 0)} />
                <Cell label="Duração" value={formatDuration(task.duration_seconds ?? null)} />
              </dl>

              {task.error_message && (
                <div className="mt-4 rounded-md border border-danger/30 bg-danger/10 p-3">
                  <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-danger">
                    <AlertCircle className="h-3.5 w-3.5" />
                    {t("tasks.detail.error")}
                  </div>
                  <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-danger">
                    {task.error_message}
                  </pre>
                </div>
              )}

              <Section title={t("tasks.detail.parameters")}>
                <pre className="overflow-x-auto rounded-md border border-border bg-surface-3 p-2 font-mono text-[11px]">
                  {JSON.stringify(task.parameters ?? {}, null, 2)}
                </pre>
              </Section>

              {task.result && (
                <Section title={t("tasks.detail.results")}>
                  <pre className="max-h-[300px] overflow-auto rounded-md border border-border bg-surface-3 p-2 font-mono text-[11px]">
                    {JSON.stringify(task.result, null, 2)}
                  </pre>
                </Section>
              )}
            </div>
          )}

          {task && (task.status === "running" || task.status === "queued") && (
            <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
              <button
                disabled={cancel.isPending}
                onClick={() => cancel.mutate({ id: task.id, reason: "cancelled by user" })}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-danger/30 bg-danger/10 px-3 text-[12px] font-medium text-danger hover:bg-danger/15 disabled:opacity-50"
              >
                <XCircle className="h-3.5 w-3.5" /> {t("tasks.detail.cancel")}
              </button>
            </div>
          )}
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

// =============================================================================
// "New execution" drawer
// =============================================================================

function NewTaskDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation(["reconciliation", "common"])
  const start = useStartReconTask()
  const { data: configs } = useReconConfigs()
  const { data: pipelines } = useReconPipelines()
  const [configId, setConfigId] = useState<number | "">("")
  const [pipelineId, setPipelineId] = useState<number | "">("")
  const [autoMatch, setAutoMatch] = useState(false)

  const onSubmit = () => {
    if (!configId && !pipelineId) {
      toast.error("Selecione uma configuração ou pipeline")
      return
    }
    start.mutate(
      {
        config_id: configId || undefined,
        pipeline_id: pipelineId || undefined,
        auto_match_100: autoMatch,
      },
      {
        onSuccess: (task) => {
          toast.success(`Execução iniciada #${task.id}`)
          onClose()
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : t("errors.generic", { ns: "common" })
          toast.error(msg)
        },
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[460px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="text-[13px] font-semibold">{t("tasks.start.title")}</Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              ×
            </button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[13px]">
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Configuração
              </label>
              <select
                value={configId}
                onChange={(e) => {
                  setConfigId(e.target.value ? Number(e.target.value) : "")
                  setPipelineId("")
                }}
                className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
              >
                <option value="">—</option>
                {(configs ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.is_default ? " (padrão)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              OU
              <span className="h-px flex-1 bg-border" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Pipeline
              </label>
              <select
                value={pipelineId}
                onChange={(e) => {
                  setPipelineId(e.target.value ? Number(e.target.value) : "")
                  setConfigId("")
                }}
                className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
              >
                <option value="">—</option>
                {(pipelines ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.is_default ? " (padrão)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
              <input
                type="checkbox"
                checked={autoMatch}
                onChange={(e) => setAutoMatch(e.target.checked)}
                className="accent-primary"
              />
              <span className="text-[12px]">{t("tasks.start.auto_match_100")}</span>
            </label>
          </div>
          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button
              disabled={start.isPending}
              onClick={onSubmit}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {t("tasks.start.submit")}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Cell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  )
}
