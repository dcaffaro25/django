import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Plus, Trash2, Save, X, BookOpen, Copy, Search, Filter, RotateCcw, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { SearchableAccountSelect } from "@/components/reconciliation/SearchableAccountSelect"
import { ColumnMenu } from "@/components/ui/column-menu"
import { DownloadXlsxButton } from "@/components/ui/download-xlsx-button"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { StatusBadge } from "@/components/ui/status-badge"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useAccounts, useBankAccountsList, useDeleteJournalEntry, useJournalEntries, useSaveJournalEntry,
} from "@/features/reconciliation"
import { useUserRole } from "@/features/auth/useUserRole"
import type { JournalEntry } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

function isoDaysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const STATUS_FILTERS = ["all", "pending", "matched", "approved", "unmatched"] as const

export function JournalEntriesPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const [editing, setEditing] = useState<JournalEntry | "new" | null>(null)
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all")
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(60))
  const [dateTo, setDateTo] = useState(isoDaysAgo(0))
  const [bankAccountFilter, setBankAccountFilter] = useState<number | "">("")
  const [search, setSearch] = useState("")

  const { canWrite } = useUserRole()
  const { data: bankAccounts = [] } = useBankAccountsList()
  const { data: entries = [], isLoading, isFetching, refetch } = useJournalEntries({
    reconciliation_status: statusFilter === "all" ? undefined : statusFilter,
    transaction_date_after: dateFrom || undefined,
    transaction_date_before: dateTo || undefined,
    bank_account: bankAccountFilter || undefined,
    ordering: "-transaction_date",
    limit: 1000,
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return entries
    return entries.filter((e) => (e.description ?? "").toLowerCase().includes(q))
  }, [entries, search])

  const { sort, sorted, toggle: toggleSort } = useSortable(filtered, {
    initialKey: "transaction_date",
    initialDirection: "desc",
    accessors: {
      id: (r) => r.id,
      transaction_date: (r) => r.transaction_date,
      description: (r) => r.description,
      value: (r) => Number(r.transaction_value),
      status: (r) => r.reconciliation_status,
      bank_account: (r) => r.bank_account?.name ?? "",
    },
  })

  const columns: ColumnDef[] = useMemo(() => [
    { key: "id", label: "ID", alwaysVisible: true },
    { key: "transaction_date", label: "Data" },
    { key: "description", label: "Descrição", alwaysVisible: true },
    { key: "bank_account", label: "Conta bancária" },
    { key: "value", label: "Valor" },
    { key: "status", label: "Status" },
  ], [])
  const col = useColumnVisibility("accounting.journal_entries", columns)

  const del = useDeleteJournalEntry()
  const onDelete = (je: JournalEntry, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir lançamento #${je.id}?`)) return
    del.mutate(je.id, {
      onSuccess: () => toast.success("Lançamento excluído"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (je: JournalEntry, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...je, id: undefined as unknown as number, description: `${je.description} (cópia)` })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} lançamento${ids.length > 1 ? "s" : ""}?`)) return
    const res = await Promise.allSettled(ids.map((id) => del.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídos · ${failed} falharam`)
    else toast.success(`${ids.length} lançamentos excluídos`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Lançamentos contábeis"
        subtitle="Débitos e créditos individuais"
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
            <DownloadXlsxButton
              path="/api/journal_entries/export_xlsx/"
              params={{
                reconciliation_status: statusFilter === "all" ? undefined : statusFilter,
                transaction_date_after: dateFrom || undefined,
                transaction_date_before: dateTo || undefined,
                bank_account: bankAccountFilter || undefined,
                ordering: "-transaction_date",
              }}
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
                <Plus className="h-3.5 w-3.5" /> Novo lançamento
              </button>
            )}
          </>
        }
      />

      <div className="card-elevated flex flex-wrap items-end gap-3 p-3">
        <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <Filter className="h-3.5 w-3.5" /> Filtros
        </div>
        <Field label="Período">
          <div className="flex items-center gap-1">
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring" />
            <span className="text-muted-foreground">→</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring" />
          </div>
        </Field>
        <Field label="Conta bancária">
          <select value={bankAccountFilter} onChange={(e) => setBankAccountFilter(e.target.value ? Number(e.target.value) : "")}
            className="h-8 w-[180px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring">
            <option value="">Todas</option>
            {bankAccounts.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </Field>
        <Field label="Buscar">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Descrição..."
              className="h-8 w-[220px] rounded-md border border-border bg-background pl-7 pr-2 text-[12px] outline-none focus:border-ring" />
          </div>
        </Field>
        <button
          onClick={() => { setStatusFilter("all"); setDateFrom(isoDaysAgo(60)); setDateTo(isoDaysAgo(0)); setBankAccountFilter(""); setSearch("") }}
          className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" /> Limpar
        </button>
      </div>

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[12px]">
        {STATUS_FILTERS.map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={cn("h-6 rounded-sm px-2.5 font-medium capitalize transition-colors",
              statusFilter === s ? "bg-background text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground")}>
            {s === "all" ? "Todos" : t(`status.${s}`, { ns: "common", defaultValue: s })}
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
              <th className="h-9 px-3"><SortableHeader columnKey="id" label="ID" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("transaction_date") && <th className="h-9 px-3"><SortableHeader columnKey="transaction_date" label="Data" sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 px-3"><SortableHeader columnKey="description" label="Descrição" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("bank_account") && <th className="h-9 px-3"><SortableHeader columnKey="bank_account" label="Conta bancária" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("value") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="value" align="right" label="Valor" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("status") && <th className="h-9 px-3"><SortableHeader columnKey="status" label="Status" sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={8} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={8} className="h-24 px-3 text-center text-muted-foreground">Nenhum lançamento no filtro atual</td>
              </tr>
            ) : (
              sorted.map((je) => (
                <tr key={je.id} onClick={() => setEditing(je)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(je.id) && "bg-primary/5",
                  )}>
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(je.id)} onToggle={() => selection.toggle(je.id)} />
                  </td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">#{je.id}</td>
                  {col.isVisible("transaction_date") && <td className="h-10 px-3 text-muted-foreground">{formatDate(je.transaction_date)}</td>}
                  <td className="h-10 px-3 font-medium"><span className="truncate">{je.description}</span></td>
                  {col.isVisible("bank_account") && <td className="h-10 px-3 text-muted-foreground">{je.bank_account?.name ?? "—"}</td>}
                  {col.isVisible("value") && (
                    <td className="h-10 px-3 text-right tabular-nums">{formatCurrency(Number(je.transaction_value))}</td>
                  )}
                  {col.isVisible("status") && <td className="h-10 px-3"><StatusBadge status={je.reconciliation_status} /></td>}
                  <RowActionsCell>
                    <RowAction icon={<Copy className="h-3.5 w-3.5" />} label="Duplicar" onClick={(e) => onDuplicate(je, e)} />
                    <RowAction icon={<Trash2 className="h-3.5 w-3.5" />} label="Excluir" variant="danger" onClick={(e) => onDelete(je, e)} />
                  </RowActionsCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <JournalEntryEditor
        open={editing !== null}
        entry={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

function JournalEntryEditor({
  open, entry, onClose,
}: {
  open: boolean
  entry: JournalEntry | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveJournalEntry()
  const { data: accounts = [] } = useAccounts()
  // Mirror the underlying JournalEntry type's nullability for ``account``
  // (the type was widened to ``number | null`` when it became part of the
  // list payload for the report drill-down). Without ``null`` here, the
  // ``setForm({ ...entry })`` reset path fails strict typing.
  const [form, setForm] = useState<Partial<JournalEntry> & { account?: number | null; debit_amount?: string | null; credit_amount?: string | null }>({
    description: "",
    transaction_date: new Date().toISOString().slice(0, 10),
  })

  useEffect(() => {
    if (entry) setForm({ ...entry })
    else setForm({ description: "", transaction_date: new Date().toISOString().slice(0, 10) })
  }, [entry, open])

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.description) { toast.error("Descrição obrigatória"); return }
    save.mutate(
      { id: entry?.id, body: form as Partial<JournalEntry> },
      {
        onSuccess: () => { toast.success("Lançamento salvo"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
              {entry ? `Lançamento #${entry.id}` : "Novo lançamento"}
              {entry && <StatusBadge status={entry.reconciliation_status} />}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <Field label="Data da transação">
              <input type="date" value={form.transaction_date ?? ""} onChange={(e) => set("transaction_date", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <Field label="Descrição">
              <input value={form.description ?? ""} onChange={(e) => set("description", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <Field label="Conta">
              {/* SearchableAccountSelect instead of a native <select>:
                  journal-entry accounts can be deep (``Ativo >
                  Circulante > Bancos > BB > CC 12345``) and Chromium's
                  native dropdown renders options at the button's width,
                  truncating paths to ~30 chars. The shared component
                  gets a 720px popover and a two-line row so the full
                  path is always visible. Search makes picking from
                  large charts bearable too. */}
              <SearchableAccountSelect
                accounts={accounts}
                value={typeof form.account === "number" ? form.account : null}
                onChange={(id) => set("account", id ?? undefined)}
                placeholder="—"
                compact
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Débito">
                <input type="number" step="0.01" value={form.debit_amount ?? ""} onChange={(e) => set("debit_amount", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Crédito">
                <input type="number" step="0.01" value={form.credit_amount ?? ""} onChange={(e) => set("credit_amount", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
            </div>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
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
