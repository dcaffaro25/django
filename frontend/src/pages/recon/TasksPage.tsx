import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useSearchParams } from "react-router-dom"
import { Play, RefreshCw, XCircle, AlertCircle, Copy, Hash, RotateCw, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { SectionHeader } from "@/components/ui/section-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
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
import type { ReconTaskStatus } from "@/features/reconciliation/types"

const STATUS_FILTERS: (ReconTaskStatus | "all")[] = ["all", "running", "queued", "completed", "failed", "cancelled"]

/**
 * "Past" here means the task is no longer actionable (the engine has stopped
 * running). These tasks have persisted suggestions the user likely wants to
 * review on the Sugestões page. Running/queued tasks still open the live
 * detail drawer instead.
 */
const PAST_STATUSES: ReconTaskStatus[] = ["completed", "failed", "cancelled"]
function isPast(status: string | undefined): boolean {
  return !!status && (PAST_STATUSES as string[]).includes(status)
}

export function TasksPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = Number(searchParams.get("id") ?? 0) || null
  const showNew = searchParams.get("new") === "1"

  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all")
  const { data, isLoading, refetch, isFetching } = useReconTasks({
    status: statusFilter === "all" ? undefined : statusFilter,
    pollMs: 5000,
  })

  const rawRows = useMemo(() => data ?? [], [data])

  const startTask = useStartReconTask()

  const { sort, sorted: rows, toggle: toggleSort } = useSortable(rawRows, {
    initialKey: "id",
    initialDirection: "desc",
    accessors: {
      id: (r) => r.id,
      status: (r) => r.status,
      config: (r) => r.config_name ?? r.pipeline_name ?? "",
      bank_candidates: (r) => r.bank_candidates ?? 0,
      journal_candidates: (r) => r.journal_candidates ?? 0,
      suggestions: (r) => r.suggestion_count ?? 0,
      matches: (r) => r.matched_bank_transactions ?? 0,
      auto_applied: (r) => r.auto_match_applied ?? 0,
      duration: (r) => r.duration_seconds ?? 0,
      started_at: (r) => r.created_at ?? "",
    },
  })

  const onRerun = (task: typeof rows[number]) => {
    const body = task.config ? { config_id: task.config, auto_match_100: !!task.auto_match_enabled } : task.pipeline ? { pipeline_id: task.pipeline, auto_match_100: !!task.auto_match_enabled } : null
    if (!body) {
      toast.error("Execução sem config/pipeline referenciado")
      return
    }
    startTask.mutate(body, {
      onSuccess: (newTask) => toast.success(`Nova execução #${newTask.id} iniciada`),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const deleteTask = useDeleteReconTask()
  const onDelete = (task: typeof rows[number], e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir execução #${task.id}?`)) return
    deleteTask.mutate(task.id, {
      onSuccess: () => toast.success("Execução excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const selection = useRowSelection<number>()
  const sortedIds = rows.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} execuç${ids.length > 1 ? "ões" : "ão"}?`)) return
    const res = await Promise.allSettled(ids.map((id) => deleteTask.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídas · ${failed} falharam`)
    else toast.success(`${ids.length} execuções excluídas`)
    selection.clear()
  }

  const taskColumns: ColumnDef[] = useMemo(
    () => [
      { key: "id", label: t("tasks.columns.id"), alwaysVisible: true },
      { key: "status", label: t("tasks.columns.status"), alwaysVisible: true },
      { key: "config", label: `${t("tasks.columns.config")} / ${t("tasks.columns.pipeline")}` },
      { key: "bank_candidates", label: t("tasks.columns.bank_candidates") },
      { key: "journal_candidates", label: t("tasks.columns.journal_candidates") },
      { key: "suggestions", label: t("tasks.columns.suggestions") },
      { key: "matches", label: t("tasks.columns.matches") },
      { key: "auto_applied", label: t("tasks.columns.auto_applied") },
      { key: "duration", label: t("tasks.columns.duration") },
      { key: "started_at", label: t("tasks.columns.started_at") },
    ],
    [t],
  )
  const col = useColumnVisibility("recon.tasks", taskColumns)

  return (
    <div className="space-y-4">
      <SectionHeader
        title={t("tasks.title")}
        subtitle={t("tasks.subtitle") ?? ""}
        actions={
          <>
            <ColumnMenu
              columns={taskColumns}
              isVisible={col.isVisible}
              toggle={col.toggle}
              showAll={col.showAll}
              resetDefaults={col.resetDefaults}
              label={t("actions.columns", { ns: "common" })}
            />
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              {t("actions.refresh", { ns: "common" })}
            </button>
            <button
              onClick={() => setSearchParams({ new: "1" })}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Play className="h-3.5 w-3.5" /> {t("tasks.new_task")}
            </button>
          </>
        }
      />

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[12px]">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={cn(
              "h-6 rounded-sm px-2.5 font-medium capitalize transition-colors",
              statusFilter === s ? "bg-background text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "all" ? "Todas" : t(`status.${s}`, { ns: "common" })}
          </button>
        ))}
      </div>

      {/* Cap the executions table so it never pushes the rest of the page
          off-screen — instead the rows scroll inside the card with a sticky
          header. max-h tuned to fit ~14 rows of 40px plus the filter tabs
          above; adjust if the row density changes. */}
      <div className="card-elevated overflow-hidden">
        <div className="max-h-[calc(100dvh-260px)] min-h-[240px] overflow-y-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 z-10 bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground shadow-[0_1px_0_0_hsl(var(--border))]">
            <tr>
              <th className="h-9 w-10 px-3">
                <SelectAllCheckbox
                  allSelected={selection.allSelected(sortedIds)}
                  someSelected={selection.someSelected(sortedIds)}
                  onToggle={() => selection.toggleAll(sortedIds)}
                />
              </th>
              <th className="h-9 px-3"><SortableHeader columnKey="id" label={t("tasks.columns.id")} sort={sort} onToggle={toggleSort} /></th>
              <th className="h-9 px-3"><SortableHeader columnKey="status" label={t("tasks.columns.status")} sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("config") && <th className="h-9 px-3"><SortableHeader columnKey="config" label={`${t("tasks.columns.config")} / ${t("tasks.columns.pipeline")}`} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("bank_candidates") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="bank_candidates" align="right" label={t("tasks.columns.bank_candidates")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("journal_candidates") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="journal_candidates" align="right" label={t("tasks.columns.journal_candidates")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("suggestions") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="suggestions" align="right" label={t("tasks.columns.suggestions")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("matches") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="matches" align="right" label={t("tasks.columns.matches")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("auto_applied") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="auto_applied" align="right" label={t("tasks.columns.auto_applied")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("duration") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="duration" align="right" label={t("tasks.columns.duration")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("started_at") && <th className="h-9 px-3"><SortableHeader columnKey="started_at" label={t("tasks.columns.started_at")} sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-t border-border">
                  <td colSpan={12} className="h-10 px-3">
                    <div className="h-4 w-full animate-pulse rounded bg-muted/60" />
                  </td>
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="h-24 px-3 text-center text-muted-foreground">
                  {t("tasks.empty")}
                </td>
              </tr>
            ) : (
              rows.map((task) => (
                <tr
                  key={task.id}
                  onClick={() => {
                    // Past executions: go straight to the Sugestões page
                    // filtered by this task so the user can review/approve
                    // the persisted suggestions. Active tasks still open
                    // the live status drawer.
                    if (isPast(task.status)) {
                      navigate(`/recon/suggestions?task_id=${task.id}`)
                    } else {
                      setSearchParams({ id: String(task.id) })
                    }
                  }}
                  className={cn(
                    "group cursor-pointer border-t border-border transition-colors hover:bg-accent/50",
                    selectedId === task.id && "bg-primary/5",
                    selection.isSelected(task.id) && "bg-primary/5",
                  )}
                >
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(task.id)} onToggle={() => selection.toggle(task.id)} />
                  </td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">#{task.id}</td>
                  <td className="h-10 px-3"><StatusBadge status={task.status} /></td>
                  {col.isVisible("config") && <td className="h-10 px-3 font-medium">{task.config_name ?? task.pipeline_name ?? "—"}</td>}
                  {col.isVisible("bank_candidates") && <td className="h-10 px-3 text-right tabular-nums">{formatNumber(task.bank_candidates ?? 0)}</td>}
                  {col.isVisible("journal_candidates") && <td className="h-10 px-3 text-right tabular-nums">{formatNumber(task.journal_candidates ?? 0)}</td>}
                  {col.isVisible("suggestions") && <td className="h-10 px-3 text-right tabular-nums">{formatNumber(task.suggestion_count ?? 0)}</td>}
                  {col.isVisible("matches") && <td className="h-10 px-3 text-right tabular-nums">{formatNumber(task.matched_bank_transactions ?? 0)}</td>}
                  {col.isVisible("auto_applied") && <td className="h-10 px-3 text-right tabular-nums">{formatNumber(task.auto_match_applied ?? 0)}</td>}
                  {col.isVisible("duration") && (
                    <td className="h-10 px-3 text-right tabular-nums text-muted-foreground">{formatDuration(task.duration_seconds ?? null)}</td>
                  )}
                  {col.isVisible("started_at") && (
                    <td className="h-10 px-3 text-muted-foreground">{task.created_at ? formatDateTime(task.created_at) : "—"}</td>
                  )}
                  <RowActionsCell>
                    <RowAction
                      icon={<RotateCw className="h-3.5 w-3.5" />}
                      label="Executar novamente"
                      onClick={() => onRerun(task)}
                    />
                    <RowAction
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      label="Excluir"
                      variant="danger"
                      onClick={(e) => onDelete(task, e)}
                    />
                  </RowActionsCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>

      <TaskDetailDrawer
        taskId={selectedId}
        onClose={() => setSearchParams({})}
      />

      <NewTaskDrawer
        open={showNew}
        onClose={() => setSearchParams({})}
      />
    </div>
  )
}

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
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
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
                    <Copy className="h-3 w-3" /> celery
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
                  <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-danger">{task.error_message}</pre>
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
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              ×
            </button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[13px]">
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Configuração</label>
              <select
                value={configId}
                onChange={(e) => { setConfigId(e.target.value ? Number(e.target.value) : ""); setPipelineId("") }}
                className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
              >
                <option value="">—</option>
                {(configs ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.name}{c.is_default ? " (padrão)" : ""}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              OU
              <span className="h-px flex-1 bg-border" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Pipeline</label>
              <select
                value={pipelineId}
                onChange={(e) => { setPipelineId(e.target.value ? Number(e.target.value) : ""); setConfigId("") }}
                className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
              >
                <option value="">—</option>
                {(pipelines ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}{p.is_default ? " (padrão)" : ""}</option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
              <input type="checkbox" checked={autoMatch} onChange={(e) => setAutoMatch(e.target.checked)} className="accent-primary" />
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
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</div>
      {children}
    </div>
  )
}
