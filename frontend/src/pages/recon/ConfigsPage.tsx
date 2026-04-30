import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Plus, Trash2, Save, Star, X, SlidersHorizontal, Copy, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import {
  BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox,
} from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useAccounts,
  useDeleteReconConfig,
  useFilterColumns,
  usePreviewCounts,
  useReconConfigsFull,
  useSaveReconConfig,
} from "@/features/reconciliation"
import { useUserRole } from "@/features/auth/useUserRole"
import type {
  FilterColumnDef,
  FilterStack,
  ReconciliationConfig,
} from "@/features/reconciliation/types"
import { FilterStackBuilder } from "@/components/reconciliation/FilterStackBuilder"
import { cn } from "@/lib/utils"

// Scope tones: outlined pills with muted label. No saturated backgrounds.
const SCOPE_TONES: Record<string, string> = {
  global: "text-muted-foreground border-border",
  company: "text-foreground border-border",
  user: "text-muted-foreground border-border",
  company_user: "text-foreground border-border",
}

export function ConfigsPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: configs = [], isLoading, isFetching, refetch } = useReconConfigsFull()
  const [editing, setEditing] = useState<ReconciliationConfig | "new" | null>(null)
  const { canWrite } = useUserRole()

  const [scopeFilter, setScopeFilter] = useState<"all" | "global" | "company" | "user" | "company_user">("all")

  const filtered = useMemo(
    () => (scopeFilter === "all" ? configs : configs.filter((c) => c.scope === scopeFilter)),
    [configs, scopeFilter],
  )

  const { sort, sorted, toggle: toggleSort } = useSortable(filtered, {
    initialKey: "name",
    initialDirection: "asc",
    accessors: {
      name: (r) => r.name,
      scope: (r) => r.scope,
      embedding_weight: (r) => Number(r.embedding_weight),
      amount_weight: (r) => Number(r.amount_weight),
      currency_weight: (r) => Number(r.currency_weight),
      date_weight: (r) => Number(r.date_weight),
      min_confidence: (r) => Number(r.min_confidence),
      max_suggestions: (r) => r.max_suggestions,
      is_default: (r) => (r.is_default ? 1 : 0),
    },
  })

  const deleteConfig = useDeleteReconConfig()
  const onDelete = (c: (typeof sorted)[number], e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(t("configs.delete_confirm") ?? "Delete?")) return
    deleteConfig.mutate(c.id, {
      onSuccess: () => toast.success(t("configs.deleted_toast") ?? "Deleted"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((s) => s.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} configuraç${ids.length > 1 ? "ões" : "ão"}?`)) return
    const results = await Promise.allSettled(ids.map((id) => deleteConfig.mutateAsync(id)))
    const failed = results.filter((r) => r.status === "rejected").length
    if (failed > 0) toast.warning(`${ids.length - failed} excluídos · ${failed} falharam`)
    else toast.success(`${ids.length} configurações excluídas`)
    selection.clear()
  }
  const onDuplicate = (c: (typeof sorted)[number], e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...c, id: undefined as unknown as number, name: `${c.name} (cópia)`, is_default: false })
  }

  const cfgColumns: ColumnDef[] = useMemo(
    () => [
      { key: "name", label: t("configs.fields.name"), alwaysVisible: true },
      { key: "scope", label: t("configs.scope") },
      { key: "scope_preview", label: "Volume (preview)" },
      { key: "embedding_weight", label: t("configs.fields.embedding_weight") },
      { key: "amount_weight", label: t("configs.fields.amount_weight") },
      { key: "currency_weight", label: t("configs.fields.currency_weight") },
      { key: "date_weight", label: t("configs.fields.date_weight") },
      { key: "min_confidence", label: t("configs.fields.min_confidence") },
      { key: "max_suggestions", label: t("configs.fields.max_suggestions") },
      { key: "is_default", label: t("configs.fields.is_default") },
    ],
    [t],
  )
  const col = useColumnVisibility("recon.configs", cfgColumns)

  return (
    <div className="space-y-4">
      <SectionHeader
        title={t("configs.title")}
        subtitle={t("configs.subtitle") ?? ""}
        actions={
          <>
            <ColumnMenu
              columns={cfgColumns}
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
                <Plus className="h-3.5 w-3.5" /> {t("configs.new")}
              </button>
            )}
          </>
        }
      />

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[12px]">
        {(["all", "global", "company", "user", "company_user"] as const).map((s) => (
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

      {canWrite && (
        <BulkActionsBar count={selection.count} onClear={selection.clear}>
          <BulkAction
            icon={<Trash2 className="h-3 w-3" />}
            label={`Excluir ${selection.count}`}
            variant="danger"
            onClick={onBulkDelete}
          />
        </BulkActionsBar>
      )}

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
              {col.isVisible("scope_preview") && <th className="h-9 px-3 text-right text-[10px] uppercase tracking-wider text-muted-foreground">Volume</th>}
              {col.isVisible("embedding_weight") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="embedding_weight" align="right" label={t("configs.fields.embedding_weight")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("amount_weight") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="amount_weight" align="right" label={t("configs.fields.amount_weight")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("currency_weight") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="currency_weight" align="right" label={t("configs.fields.currency_weight")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("date_weight") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="date_weight" align="right" label={t("configs.fields.date_weight")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("min_confidence") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="min_confidence" align="right" label={t("configs.fields.min_confidence")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("max_suggestions") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="max_suggestions" align="right" label={t("configs.fields.max_suggestions")} sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("is_default") && <th className="h-9 px-3"><SortableHeader columnKey="is_default" label={t("configs.fields.is_default")} sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={12} className="h-10 px-3">
                    <div className="h-4 animate-pulse rounded bg-muted/60" />
                  </td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={12} className="h-24 px-3 text-center text-muted-foreground">
                  {t("configs.empty")}
                </td>
              </tr>
            ) : (
              sorted.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setEditing(c)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(c.id) && "bg-primary/5",
                  )}
                >
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(c.id)} onToggle={() => selection.toggle(c.id)} />
                  </td>
                  <td className="h-10 px-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{c.name}</span>
                      {c.description && (
                        <span className="truncate text-[11px] text-muted-foreground">{c.description}</span>
                      )}
                    </div>
                  </td>
                  {col.isVisible("scope") && (
                    <td className="h-10 px-3">
                      <span
                        className={cn(
                          "inline-flex h-5 items-center rounded-full border px-2 text-[10px] font-medium",
                          SCOPE_TONES[c.scope] ?? "",
                        )}
                      >
                        {t(`configs.scopes.${c.scope}`)}
                      </span>
                    </td>
                  )}
                  {col.isVisible("scope_preview") && (
                    <td className="h-10 px-3 text-right">
                      <ScopePreviewCell configId={c.id} />
                    </td>
                  )}
                  {col.isVisible("embedding_weight") && <td className="h-10 px-3 text-right tabular-nums">{c.embedding_weight}</td>}
                  {col.isVisible("amount_weight") && <td className="h-10 px-3 text-right tabular-nums">{c.amount_weight}</td>}
                  {col.isVisible("currency_weight") && <td className="h-10 px-3 text-right tabular-nums">{c.currency_weight}</td>}
                  {col.isVisible("date_weight") && <td className="h-10 px-3 text-right tabular-nums">{c.date_weight}</td>}
                  {col.isVisible("min_confidence") && <td className="h-10 px-3 text-right tabular-nums">{c.min_confidence}</td>}
                  {col.isVisible("max_suggestions") && <td className="h-10 px-3 text-right tabular-nums">{c.max_suggestions}</td>}
                  {col.isVisible("is_default") && (
                    <td className="h-10 px-3">{c.is_default && <Star className="h-3.5 w-3.5 fill-warning text-warning" />}</td>
                  )}
                  {canWrite ? (
                    <RowActionsCell>
                      <RowAction
                        icon={<Copy className="h-3.5 w-3.5" />}
                        label="Duplicar"
                        onClick={(e) => onDuplicate(c, e)}
                      />
                      <RowAction
                        icon={<Trash2 className="h-3.5 w-3.5" />}
                        label="Excluir"
                        variant="danger"
                        onClick={(e) => onDelete(c, e)}
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

      <ConfigEditor
        open={editing !== null}
        config={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

const BLANK: Partial<ReconciliationConfig> = {
  scope: "company",
  name: "",
  description: "",
  bank_filters: { filters: [], operator: "and" },
  book_filters: { filters: [], operator: "and" },
  embedding_weight: "0.50",
  amount_weight: "0.35",
  currency_weight: "0.10",
  date_weight: "0.05",
  amount_tolerance: "0.00",
  group_span_days: 2,
  avg_date_delta_days: 2,
  max_group_size_bank: 1,
  max_group_size_book: 1,
  allow_mixed_signs: false,
  min_confidence: "0.90",
  max_suggestions: 1000,
  max_alternatives_per_match: 2,
  duplicate_window_days: 3,
  fee_accounts: [],
  is_default: false,
  company: null,
  user: null,
}

function ConfigEditor({
  open,
  config,
  onClose,
}: {
  open: boolean
  config: ReconciliationConfig | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveReconConfig()
  const del = useDeleteReconConfig()
  const [form, setForm] = useState<Partial<ReconciliationConfig>>(BLANK)
  const { data: columnsData } = useFilterColumns()
  const { data: accounts = [] } = useAccounts()
  const preview = usePreviewCounts()
  const [previewCounts, setPreviewCounts] = useState<{ bank: number | null; book: number | null }>({ bank: null, book: null })

  const bankColumns: FilterColumnDef[] = (columnsData as { bank_transaction?: FilterColumnDef[] } | undefined)?.bank_transaction ?? []
  const bookColumns: FilterColumnDef[] = (columnsData as { journal_entry?: FilterColumnDef[] } | undefined)?.journal_entry ?? []

  useEffect(() => {
    if (config) setForm({ ...config })
    else setForm({ ...BLANK })
    setPreviewCounts({ bank: null, book: null })
  }, [config, open])

  // Debounced preview — fire when filters change.
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => {
      preview.mutate(
        {
          bank_filters: (form.bank_filters ?? null) as FilterStack | null,
          book_filters: (form.book_filters ?? null) as FilterStack | null,
        },
        {
          onSuccess: (r) => setPreviewCounts({ bank: r.bank.total, book: r.book.total }),
          onError: () => setPreviewCounts({ bank: null, book: null }),
        },
      )
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, JSON.stringify(form.bank_filters), JSON.stringify(form.book_filters)])

  const set = <K extends keyof ReconciliationConfig>(key: K, value: ReconciliationConfig[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const weights = [form.embedding_weight, form.amount_weight, form.currency_weight, form.date_weight].map((v) =>
    Number(v ?? 0),
  )
  const weightsSum = weights.reduce((s, n) => s + n, 0)
  const weightsOk = Math.abs(weightsSum - 1) < 0.0001

  const onSave = () => {
    if (!weightsOk) {
      toast.error(t("configs.weights_sum_error") ?? "Pesos inválidos")
      return
    }
    if (!form.name) {
      toast.error("Nome obrigatório")
      return
    }
    save.mutate(
      { id: config?.id, body: form },
      {
        onSuccess: () => {
          toast.success(t("configs.saved_toast") ?? "Saved")
          onClose()
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  const onDelete = () => {
    if (!config) return
    if (!window.confirm(t("configs.delete_confirm") ?? "Delete?")) return
    del.mutate(config.id, {
      onSuccess: () => {
        toast.success(t("configs.deleted_toast") ?? "Deleted")
        onClose()
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const onDuplicate = () => {
    if (!config) return
    setForm({ ...config, id: undefined, name: `${config.name} (cópia)`, is_default: false })
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[560px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
              {config ? `Editar configuração #${config.id}` : "Nova configuração"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[12px]">
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("configs.fields.name")}>
                <input
                  value={form.name ?? ""}
                  onChange={(e) => set("name", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                />
              </Field>
              <Field label={t("configs.scope")}>
                <select
                  value={form.scope}
                  onChange={(e) => set("scope", e.target.value as ReconciliationConfig["scope"])}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                >
                  <option value="global">{t("configs.scopes.global")}</option>
                  <option value="company">{t("configs.scopes.company")}</option>
                  <option value="user">{t("configs.scopes.user")}</option>
                  <option value="company_user">{t("configs.scopes.company_user")}</option>
                </select>
              </Field>
            </div>

            <Field label={t("configs.fields.description")}>
              <textarea
                value={form.description ?? ""}
                onChange={(e) => set("description", e.target.value)}
                rows={2}
                className="w-full rounded-md border border-border bg-background p-2 outline-none focus:border-ring"
              />
            </Field>

            <Section title={t("configs.weights")}>
              <div className="grid grid-cols-2 gap-3">
                <DecField label={t("configs.fields.embedding_weight")} value={form.embedding_weight} onChange={(v) => set("embedding_weight", v)} />
                <DecField label={t("configs.fields.amount_weight")} value={form.amount_weight} onChange={(v) => set("amount_weight", v)} />
                <DecField label={t("configs.fields.currency_weight")} value={form.currency_weight} onChange={(v) => set("currency_weight", v)} />
                <DecField label={t("configs.fields.date_weight")} value={form.date_weight} onChange={(v) => set("date_weight", v)} />
              </div>
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 rounded-full border border-border bg-surface-3 p-0.5">
                  <div
                    className={cn(
                      "flex h-4 items-center justify-end rounded-full px-2 text-[10px] font-medium transition-all",
                      weightsOk ? "bg-success/20 text-success" : "bg-danger/20 text-danger",
                    )}
                    style={{ width: `${Math.min(weightsSum * 100, 100)}%` }}
                  >
                    {weightsSum.toFixed(2)}
                  </div>
                </div>
                <span className={cn("text-[11px] font-medium", weightsOk ? "text-success" : "text-danger")}>
                  {t("configs.weights_sum")}: {weightsSum.toFixed(2)} / 1.00
                </span>
              </div>
              {!weightsOk && <div className="mt-1 text-[11px] text-danger">{t("configs.weights_sum_error")}</div>}
            </Section>

            <Section title={t("configs.tolerances")}>
              <div className="grid grid-cols-2 gap-3">
                <DecField label={t("configs.fields.amount_tolerance")} value={form.amount_tolerance} onChange={(v) => set("amount_tolerance", v)} />
                <NumField label={t("configs.fields.group_span_days")} value={form.group_span_days} onChange={(v) => set("group_span_days", v)} />
                <NumField label={t("configs.fields.avg_date_delta_days")} value={form.avg_date_delta_days} onChange={(v) => set("avg_date_delta_days", v)} />
                <NumField label={t("configs.fields.duplicate_window_days")} value={form.duplicate_window_days} onChange={(v) => set("duplicate_window_days", v)} />
              </div>
            </Section>

            <Section title={t("configs.groups")}>
              <div className="grid grid-cols-2 gap-3">
                <NumField label={t("configs.fields.max_group_size_bank")} value={form.max_group_size_bank} onChange={(v) => set("max_group_size_bank", v)} />
                <NumField label={t("configs.fields.max_group_size_book")} value={form.max_group_size_book} onChange={(v) => set("max_group_size_book", v)} />
              </div>
              <label className="mt-2 flex items-center gap-2 text-[12px]">
                <input type="checkbox" checked={!!form.allow_mixed_signs} onChange={(e) => set("allow_mixed_signs", e.target.checked)} className="accent-primary" />
                {t("configs.fields.allow_mixed_signs")}
              </label>
            </Section>

            <Section title={t("configs.thresholds")}>
              <div className="grid grid-cols-2 gap-3">
                <DecField label={t("configs.fields.min_confidence")} value={form.min_confidence} onChange={(v) => set("min_confidence", v)} />
                <NumField label={t("configs.fields.max_suggestions")} value={form.max_suggestions} onChange={(v) => set("max_suggestions", v)} />
                <NumField label={t("configs.fields.max_alternatives_per_match")} value={form.max_alternatives_per_match} onChange={(v) => set("max_alternatives_per_match", v)} />
              </div>
            </Section>

            <Section title="Filtros — o que esta regra considera">
              <div className="space-y-3">
                <FilterStackBuilder
                  title="Filtros de banco"
                  columns={bankColumns}
                  value={form.bank_filters ?? null}
                  onChange={(s) => set("bank_filters", s)}
                  count={previewCounts.bank}
                />
                <FilterStackBuilder
                  title="Filtros de contabilidade"
                  columns={bookColumns}
                  value={form.book_filters ?? null}
                  onChange={(s) => set("book_filters", s)}
                  count={previewCounts.book}
                />
              </div>
            </Section>

            <Section title="Comportamento avançado">
              <div className="grid grid-cols-2 gap-3">
                <NumField
                  label="Limite de tempo (s)"
                  value={form.soft_time_limit_seconds}
                  onChange={(v) => set("soft_time_limit_seconds", v)}
                />
              </div>
              <label className="mt-2 flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={!!form.require_cnpj_match}
                  onChange={(e) => set("require_cnpj_match", e.target.checked)}
                  className="accent-primary"
                />
                Exigir CNPJ igual (quando ambos presentes)
              </label>
              <div className="mt-3">
                <Field label="Similaridade textual (JSON)">
                  <textarea
                    rows={3}
                    value={form.text_similarity ? JSON.stringify(form.text_similarity, null, 2) : ""}
                    onChange={(e) => {
                      const raw = e.target.value
                      if (!raw.trim()) { set("text_similarity", {} as Record<string, unknown>); return }
                      try {
                        const parsed = JSON.parse(raw)
                        set("text_similarity", parsed)
                      } catch {
                        // swallow parse errors until valid JSON; toast on save
                      }
                    }}
                    placeholder='{"min_score": 0.85, "ngram": 3}'
                    className="w-full rounded-md border border-border bg-background p-2 font-mono text-[11px] outline-none focus:border-ring"
                  />
                </Field>
              </div>
            </Section>

            <Section title="Contas de taxas">
              <div className="max-h-40 overflow-auto rounded-md border border-border p-2">
                {accounts.length === 0 ? (
                  <div className="text-[11px] text-muted-foreground">Sem contas carregadas.</div>
                ) : (
                  <div className="grid grid-cols-2 gap-1">
                    {accounts.map((a) => {
                      const checked = (form.fee_accounts ?? []).includes(a.id)
                      return (
                        <label key={a.id} className="flex items-center gap-2 text-[11px]">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const current = form.fee_accounts ?? []
                              set(
                                "fee_accounts",
                                checked ? current.filter((id) => id !== a.id) : [...current, a.id],
                              )
                            }}
                            className="accent-primary"
                          />
                          <span className="truncate">{a.account_code ? `${a.account_code} · ` : ""}{a.name}</span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            </Section>

            <label className="flex items-center gap-2 rounded-md border border-border p-2.5 text-[12px]">
              <input type="checkbox" checked={!!form.is_default} onChange={(e) => set("is_default", e.target.checked)} className="accent-primary" />
              {t("configs.fields.is_default")}
            </label>
          </div>

          <div className="hairline flex shrink-0 items-center justify-between gap-2 border-t p-3">
            <div className="flex items-center gap-2">
              {config && (
                <>
                  <button
                    onClick={onDuplicate}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
                  >
                    <Copy className="h-3.5 w-3.5" /> Duplicar
                  </button>
                  <button
                    onClick={onDelete}
                    disabled={del.isPending}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-danger/40 bg-danger/10 px-3 text-[12px] font-medium text-danger hover:bg-danger/20 disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> {t("actions.delete", { ns: "common" })}
                  </button>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
              >
                {t("actions.cancel", { ns: "common" })}
              </button>
              <button
                onClick={onSave}
                disabled={save.isPending || !weightsOk}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                {t("actions.save", { ns: "common" })}
              </button>
            </div>
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80">{title}</div>
      <div>{children}</div>
    </div>
  )
}

function NumField({ label, value, onChange }: { label: string; value: number | undefined; onChange: (v: number) => void }) {
  return (
    <Field label={label}>
      <input
        type="number"
        value={value ?? 0}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
      />
    </Field>
  )
}

function ScopePreviewCell({ configId }: { configId: number }) {
  const [loaded, setLoaded] = useState(false)
  const [counts, setCounts] = useState<{ bank: number | null; book: number | null }>({ bank: null, book: null })
  const preview = usePreviewCounts()
  useEffect(() => {
    if (loaded) return
    let cancelled = false
    // Delay a tick to avoid firing for rows that flash by quickly.
    const h = setTimeout(() => {
      preview.mutate(
        { config_id: configId, merge_config_filters: true },
        {
          onSuccess: (r) => { if (!cancelled) { setCounts({ bank: r.bank.total, book: r.book.total }); setLoaded(true) } },
          onError: () => { if (!cancelled) setLoaded(true) },
        },
      )
    }, 250)
    return () => { cancelled = true; clearTimeout(h) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configId])

  if (!loaded) return <span className="text-[11px] text-muted-foreground">…</span>
  if (counts.bank == null) return <span className="text-[11px] text-muted-foreground">—</span>
  return (
    <span className="inline-flex items-baseline gap-1 tabular-nums text-[11px]">
      <span className="font-medium">{counts.bank.toLocaleString("pt-BR")}</span>
      <span className="text-muted-foreground">·</span>
      <span className="font-medium">{counts.book?.toLocaleString("pt-BR") ?? 0}</span>
    </span>
  )
}

function DecField({ label, value, onChange }: { label: string; value: string | undefined; onChange: (v: string) => void }) {
  return (
    <Field label={label}>
      <input
        type="number"
        step="0.01"
        value={value ?? "0"}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
      />
    </Field>
  )
}
