import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Plus, Trash2, Save, Star, X, Workflow, Copy, GripVertical, ChevronUp, ChevronDown, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useDeleteReconPipeline,
  useReconConfigsFull,
  useReconPipelinesFull,
  useSaveReconPipeline,
} from "@/features/reconciliation"
import { useUserRole } from "@/features/auth/useUserRole"
import type { ReconciliationPipeline, ReconciliationPipelineStage } from "@/features/reconciliation/types"
import { cn } from "@/lib/utils"

const SCOPES = ["all", "global", "company", "user", "company_user"] as const

export function PipelinesPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: pipelines = [], isLoading, isFetching, refetch } = useReconPipelinesFull()
  const [editing, setEditing] = useState<ReconciliationPipeline | "new" | null>(null)
  const [scopeFilter, setScopeFilter] = useState<(typeof SCOPES)[number]>("all")
  const { canWrite } = useUserRole()

  const filtered = useMemo(
    () => (scopeFilter === "all" ? pipelines : pipelines.filter((p) => p.scope === scopeFilter)),
    [pipelines, scopeFilter],
  )

  const { sort, sorted, toggle: toggleSort } = useSortable(filtered, {
    initialKey: "name",
    initialDirection: "asc",
    accessors: {
      name: (r) => r.name,
      scope: (r) => r.scope,
      stages: (r) => r.stages?.length ?? 0,
      auto_apply_score: (r) => Number(r.auto_apply_score),
      max_suggestions: (r) => r.max_suggestions,
      is_default: (r) => (r.is_default ? 1 : 0),
    },
  })

  const columns: ColumnDef[] = useMemo(
    () => [
      { key: "name", label: t("configs.fields.name"), alwaysVisible: true },
      { key: "scope", label: t("configs.scope") },
      { key: "stages", label: "Estágios" },
      { key: "auto_apply_score", label: "Auto-apply" },
      { key: "max_suggestions", label: t("configs.fields.max_suggestions") },
      { key: "is_default", label: t("configs.fields.is_default") },
    ],
    [t],
  )
  const col = useColumnVisibility("recon.pipelines", columns)

  const deletePipe = useDeleteReconPipeline()
  const onDelete = (p: ReconciliationPipeline, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm("Excluir este pipeline?")) return
    deletePipe.mutate(p.id, {
      onSuccess: () => toast.success("Pipeline excluído"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (p: ReconciliationPipeline, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({
      ...p,
      id: undefined as unknown as number,
      name: `${p.name} (cópia)`,
      is_default: false,
    })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} pipeline${ids.length > 1 ? "s" : ""}?`)) return
    const res = await Promise.allSettled(ids.map((id) => deletePipe.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídos · ${failed} falharam`)
    else toast.success(`${ids.length} pipelines excluídos`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Pipelines de conciliação"
        subtitle="Sequência de configurações aplicadas em estágios"
        actions={
          <>
            <ColumnMenu
              columns={columns}
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
              title={t("actions.refresh", { ns: "common" }) ?? ""}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              {t("actions.refresh", { ns: "common" })}
            </button>
            {canWrite && (
              <button
                onClick={() => setEditing("new")}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-3.5 w-3.5" /> Novo pipeline
              </button>
            )}
          </>
        }
      />

      {canWrite && (
        <BulkActionsBar count={selection.count} onClear={selection.clear}>
          <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
        </BulkActionsBar>
      )}

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[12px]">
        {SCOPES.map((s) => (
          <button
            key={s}
            onClick={() => setScopeFilter(s)}
            className={cn(
              "h-6 rounded-sm px-2.5 font-medium capitalize transition-colors",
              scopeFilter === s ? "bg-background text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "all" ? "Todos" : t(`configs.scopes.${s}`)}
          </button>
        ))}
      </div>

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-9 w-10 px-3">
                <SelectAllCheckbox
                  allSelected={selection.allSelected(sortedIds)}
                  someSelected={selection.someSelected(sortedIds)}
                  onToggle={() => selection.toggleAll(sortedIds)}
                />
              </th>
              <th className="h-9 px-3"><SortableHeader columnKey="name" label={t("configs.fields.name")} sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("scope") && <th className="h-9 px-3"><SortableHeader columnKey="scope" label={t("configs.scope")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("stages") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="stages" align="right" label="Estágios" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("auto_apply_score") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="auto_apply_score" align="right" label="Auto-apply" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("max_suggestions") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="max_suggestions" align="right" label={t("configs.fields.max_suggestions")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("is_default") && <th className="h-9 px-3"><SortableHeader columnKey="is_default" label={t("configs.fields.is_default")} sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={8} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={8} className="h-24 px-3 text-center text-muted-foreground">
                  Nenhum pipeline cadastrado
                </td>
              </tr>
            ) : (
              sorted.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => setEditing(p)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(p.id) && "bg-primary/5",
                  )}
                >
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(p.id)} onToggle={() => selection.toggle(p.id)} />
                  </td>
                  <td className="h-10 px-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{p.name}</span>
                      {p.description && <span className="truncate text-[11px] text-muted-foreground">{p.description}</span>}
                    </div>
                  </td>
                  {col.isVisible("scope") && (
                    <td className="h-10 px-3">
                      <span className="inline-flex h-5 items-center rounded-full border border-border px-2 text-[10px] font-medium text-muted-foreground">
                        {t(`configs.scopes.${p.scope}`)}
                      </span>
                    </td>
                  )}
                  {col.isVisible("stages") && <td className="h-10 px-3 text-right tabular-nums">{p.stages?.length ?? 0}</td>}
                  {col.isVisible("auto_apply_score") && <td className="h-10 px-3 text-right tabular-nums">{p.auto_apply_score}</td>}
                  {col.isVisible("max_suggestions") && <td className="h-10 px-3 text-right tabular-nums">{p.max_suggestions}</td>}
                  {col.isVisible("is_default") && (
                    <td className="h-10 px-3">{p.is_default && <Star className="h-3.5 w-3.5 fill-warning text-warning" />}</td>
                  )}
                  {canWrite ? (
                    <RowActionsCell>
                      <RowAction
                        icon={<Copy className="h-3.5 w-3.5" />}
                        label="Duplicar"
                        onClick={(e) => onDuplicate(p, e)}
                      />
                      <RowAction
                        icon={<Trash2 className="h-3.5 w-3.5" />}
                        label="Excluir"
                        variant="danger"
                        onClick={(e) => onDelete(p, e)}
                      />
                    </RowActionsCell>
                  ) : (
                    <td className="h-10 px-3" />
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <PipelineEditor
        open={editing !== null}
        pipeline={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

const BLANK: Partial<ReconciliationPipeline> = {
  scope: "company",
  name: "",
  description: "",
  auto_apply_score: "1.00",
  max_suggestions: 1000,
  soft_time_limit_seconds: null,
  is_default: false,
  company: null,
  user: null,
  stages: [],
}

function PipelineEditor({
  open, pipeline, onClose,
}: {
  open: boolean
  pipeline: ReconciliationPipeline | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveReconPipeline()
  const { data: configs = [] } = useReconConfigsFull()
  const [form, setForm] = useState<Partial<ReconciliationPipeline>>(BLANK)

  useEffect(() => {
    if (pipeline) setForm({ ...pipeline })
    else setForm({ ...BLANK })
  }, [pipeline, open])

  const set = <K extends keyof ReconciliationPipeline>(key: K, value: ReconciliationPipeline[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const stages = form.stages ?? []
  const updateStage = (i: number, patch: Partial<ReconciliationPipelineStage>) =>
    setForm((f) => ({
      ...f,
      stages: (f.stages ?? []).map((s, j) => (j === i ? { ...s, ...patch } : s)),
    }))
  const removeStage = (i: number) =>
    setForm((f) => ({ ...f, stages: (f.stages ?? []).filter((_, j) => j !== i).map((s, j) => ({ ...s, order: j + 1 })) }))
  const addStage = () =>
    setForm((f) => ({
      ...f,
      stages: [
        ...(f.stages ?? []),
        { config: configs[0]?.id ?? 0, order: (f.stages?.length ?? 0) + 1, enabled: true },
      ],
    }))
  const moveStage = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= stages.length) return
    const reordered = [...stages]
    ;[reordered[i], reordered[j]] = [reordered[j]!, reordered[i]!]
    setForm((f) => ({ ...f, stages: reordered.map((s, k) => ({ ...s, order: k + 1 })) }))
  }

  const onSave = () => {
    if (!form.name) { toast.error("Nome obrigatório"); return }
    save.mutate(
      { id: pipeline?.id, body: form },
      {
        onSuccess: () => { toast.success("Pipeline salvo"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[640px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Workflow className="h-3.5 w-3.5 text-muted-foreground" />
              {pipeline ? `Editar pipeline #${pipeline.id}` : "Novo pipeline"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[12px]">
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("configs.fields.name")}>
                <input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
              </Field>
              <Field label={t("configs.scope")}>
                <select value={form.scope} onChange={(e) => set("scope", e.target.value as ReconciliationPipeline["scope"])}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value="global">{t("configs.scopes.global")}</option>
                  <option value="company">{t("configs.scopes.company")}</option>
                  <option value="user">{t("configs.scopes.user")}</option>
                  <option value="company_user">{t("configs.scopes.company_user")}</option>
                </select>
              </Field>
            </div>
            <Field label={t("configs.fields.description")}>
              <textarea value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} rows={2}
                className="w-full rounded-md border border-border bg-background p-2 outline-none focus:border-ring" />
            </Field>

            <div className="grid grid-cols-3 gap-3">
              <Field label="Auto-apply score">
                <input type="number" step="0.01" min={0} max={1} value={form.auto_apply_score ?? "1.00"}
                  onChange={(e) => set("auto_apply_score", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label={t("configs.fields.max_suggestions")}>
                <input type="number" value={form.max_suggestions ?? 1000}
                  onChange={(e) => set("max_suggestions", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Time limit (s)">
                <input type="number" value={form.soft_time_limit_seconds ?? ""}
                  onChange={(e) => set("soft_time_limit_seconds", e.target.value ? Number(e.target.value) : null)}
                  placeholder="—" className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
            </div>

            {/* Stages */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80">Estágios</span>
                <button onClick={addStage}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md border border-dashed border-border bg-transparent px-2.5 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground">
                  <Plus className="h-3 w-3" /> Adicionar estágio
                </button>
              </div>

              {stages.length === 0 ? (
                <div className="rounded-md border border-dashed border-border p-4 text-center text-[12px] text-muted-foreground">
                  Nenhum estágio ainda.
                </div>
              ) : (
                <div className="space-y-2">
                  {stages.map((s, i) => (
                    <div key={i} className="flex items-center gap-2 rounded-md border border-border bg-surface-1 p-2">
                      <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="w-6 shrink-0 text-center font-mono text-[11px] text-muted-foreground">#{s.order}</span>
                      <select value={s.config ?? ""} onChange={(e) => updateStage(i, { config: Number(e.target.value) })}
                        className="h-8 flex-1 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring">
                        <option value="">— selecionar config —</option>
                        {configs.map((c) => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>
                      <label className="flex items-center gap-1 text-[11px]">
                        <input type="checkbox" checked={s.enabled} onChange={(e) => updateStage(i, { enabled: e.target.checked })}
                          className="accent-primary" />
                        ativo
                      </label>
                      <button onClick={() => moveStage(i, -1)} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground" title="Mover para cima">
                        <ChevronUp className="h-3 w-3" />
                      </button>
                      <button onClick={() => moveStage(i, 1)} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground" title="Mover para baixo">
                        <ChevronDown className="h-3 w-3" />
                      </button>
                      <button onClick={() => removeStage(i)} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-danger/10 hover:text-danger" title="Remover">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <label className="flex items-center gap-2 rounded-md border border-border p-2.5 text-[12px]">
              <input type="checkbox" checked={!!form.is_default} onChange={(e) => set("is_default", e.target.checked)} className="accent-primary" />
              {t("configs.fields.is_default")}
            </label>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button onClick={onSave} disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-3.5 w-3.5" />
              {t("actions.save", { ns: "common" })}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
