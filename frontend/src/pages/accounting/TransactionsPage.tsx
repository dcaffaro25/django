import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  Plus, Trash2, Save, X, Receipt, Copy, Search, Filter, RotateCcw,
  CheckCircle2, PlayCircle, XCircle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { StatusBadge } from "@/components/ui/status-badge"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useCurrencies, useDeleteTransaction, useEntities, useSaveTransaction,
  useTransactionAction, useTransactions,
} from "@/features/reconciliation"
import type { Transaction, TransactionWrite } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

function isoDaysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const STATE_FILTERS = ["all", "pending", "posted", "canceled"] as const

export function TransactionsPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const [editing, setEditing] = useState<Transaction | "new" | null>(null)
  const [stateFilter, setStateFilter] = useState<(typeof STATE_FILTERS)[number]>("all")
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(60))
  const [dateTo, setDateTo] = useState(isoDaysAgo(0))
  const [entityFilter, setEntityFilter] = useState<number | "">("")
  const [search, setSearch] = useState("")

  const { data: entities = [] } = useEntities()
  const { data: txs = [], isLoading } = useTransactions({
    state: stateFilter === "all" ? undefined : stateFilter,
    date_after: dateFrom || undefined,
    date_before: dateTo || undefined,
    entity: entityFilter || undefined,
    ordering: "-date",
    page_size: 1000,
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return txs
    return txs.filter((t) => (t.description ?? "").toLowerCase().includes(q))
  }, [txs, search])

  const { sort, sorted, toggle: toggleSort } = useSortable(filtered, {
    initialKey: "date",
    initialDirection: "desc",
    accessors: {
      id: (r) => r.id,
      date: (r) => r.date,
      entity: (r) => r.entity_name ?? "",
      description: (r) => r.description,
      amount: (r) => Number(r.amount),
      state: (r) => r.state,
    },
  })

  const columns: ColumnDef[] = useMemo(() => [
    { key: "id", label: "ID", alwaysVisible: true },
    { key: "date", label: "Data" },
    { key: "entity", label: "Entidade" },
    { key: "description", label: "Descrição", alwaysVisible: true },
    { key: "amount", label: "Valor" },
    { key: "state", label: "Status" },
    { key: "flags", label: "Flags", defaultVisible: false },
  ], [])
  const col = useColumnVisibility("accounting.transactions", columns)

  const del = useDeleteTransaction()
  const action = useTransactionAction()

  const onDelete = (tx: Transaction, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir transação #${tx.id}?`)) return
    del.mutate(tx.id, {
      onSuccess: () => toast.success("Transação excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (tx: Transaction, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...tx, id: undefined as unknown as number, description: `${tx.description} (cópia)`, state: "pending" })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} transaç${ids.length > 1 ? "ões" : "ão"}?`)) return
    const res = await Promise.allSettled(ids.map((id) => del.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídas · ${failed} falharam`)
    else toast.success(`${ids.length} transações excluídas`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Transações"
        subtitle="Lançamentos contábeis agrupados"
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
              onClick={() => setEditing("new")}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> Nova transação
            </button>
          </>
        }
      />

      {/* KPI strip — quick quality signals on the current filtered set.
          Deeper JE drill-down + due-date respect stats are planned as a
          follow-up (requires per-transaction JE fetch or a new aggregate
          endpoint on the backend). */}
      <TransactionStats transactions={filtered} />

      {/* Filters */}
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
        <Field label="Entidade">
          <select value={entityFilter} onChange={(e) => setEntityFilter(e.target.value ? Number(e.target.value) : "")}
            className="h-8 w-[180px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring">
            <option value="">Todas</option>
            {entities.map((en) => <option key={en.id} value={en.id}>{en.path ?? en.name}</option>)}
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
          onClick={() => { setStateFilter("all"); setDateFrom(isoDaysAgo(60)); setDateTo(isoDaysAgo(0)); setEntityFilter(""); setSearch("") }}
          className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" /> Limpar
        </button>
      </div>

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1 text-[12px]">
        {STATE_FILTERS.map((s) => (
          <button key={s} onClick={() => setStateFilter(s)}
            className={cn("h-6 rounded-sm px-2.5 font-medium capitalize transition-colors",
              stateFilter === s ? "bg-background text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground")}>
            {s === "all" ? "Todas" : t(`status.${s}`, { ns: "common", defaultValue: s })}
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
              {col.isVisible("date") && <th className="h-9 px-3"><SortableHeader columnKey="date" label="Data" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("entity") && <th className="h-9 px-3"><SortableHeader columnKey="entity" label="Entidade" sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 px-3"><SortableHeader columnKey="description" label="Descrição" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("amount") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="amount" align="right" label="Valor" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("state") && <th className="h-9 px-3"><SortableHeader columnKey="state" label="Status" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("flags") && <th className="h-9 px-3">Flags</th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={9} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={9} className="h-24 px-3 text-center text-muted-foreground">Nenhuma transação no filtro atual</td>
              </tr>
            ) : (
              sorted.map((tx) => (
                <tr key={tx.id} onClick={() => setEditing(tx)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(tx.id) && "bg-primary/5",
                  )}>
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(tx.id)} onToggle={() => selection.toggle(tx.id)} />
                  </td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">#{tx.id}</td>
                  {col.isVisible("date") && <td className="h-10 px-3 text-muted-foreground">{formatDate(tx.date)}</td>}
                  {col.isVisible("entity") && <td className="h-10 px-3 text-muted-foreground">{tx.entity_name ?? `#${tx.entity}`}</td>}
                  <td className="h-10 px-3 font-medium">
                    <span className="truncate">{tx.description}</span>
                  </td>
                  {col.isVisible("amount") && (
                    <td className="h-10 px-3 text-right tabular-nums">{formatCurrency(Number(tx.amount), tx.currency_code ?? "BRL")}</td>
                  )}
                  {col.isVisible("state") && <td className="h-10 px-3"><StatusBadge status={tx.state} /></td>}
                  {col.isVisible("flags") && (
                    <td className="h-10 px-3 text-[10px] text-muted-foreground">
                      {tx.is_balanced ? "✓B " : "—B "}
                      {tx.is_reconciled ? "✓R " : "—R "}
                      {tx.is_posted ? "✓P" : "—P"}
                    </td>
                  )}
                  <RowActionsCell>
                    {tx.state !== "posted" && (
                      <RowAction
                        icon={<PlayCircle className="h-3.5 w-3.5" />}
                        label="Postar"
                        onClick={(e) => {
                          e.stopPropagation()
                          action.mutate({ id: tx.id, action: "post" }, {
                            onSuccess: () => toast.success(`Transação #${tx.id} postada`),
                            onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
                          })
                        }}
                      />
                    )}
                    <RowAction icon={<Copy className="h-3.5 w-3.5" />} label="Duplicar" onClick={(e) => onDuplicate(tx, e)} />
                    <RowAction icon={<Trash2 className="h-3.5 w-3.5" />} label="Excluir" variant="danger" onClick={(e) => onDelete(tx, e)} />
                  </RowActionsCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <TransactionEditor
        open={editing !== null}
        transaction={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

/**
 * KPI strip for the Transactions page. Computes lightweight aggregates
 * across the currently filtered result set (no extra API calls). Stats
 * that need per-JE data (due-date respect, reconciled coverage per line)
 * can be added here once a dedicated endpoint exists.
 */
function TransactionStats({ transactions }: { transactions: Transaction[] }) {
  const total = transactions.length
  if (total === 0) return null
  const balanced = transactions.filter((t) => t.is_balanced).length
  const reconciled = transactions.filter((t) => t.is_reconciled).length
  const posted = transactions.filter((t) => t.is_posted).length
  const pct = (n: number) => (total === 0 ? 0 : Math.round((n / total) * 100))
  const sumAbs = transactions.reduce((s, t) => s + Math.abs(Number(t.amount) || 0), 0)

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <StatCard label="Transações" value={String(total)} hint={`∑ |valor| = ${sumAbs.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
      <StatCard label="Balanceadas" value={`${pct(balanced)}%`} hint={`${balanced}/${total}`} tone={pct(balanced) === 100 ? "ok" : pct(balanced) >= 90 ? "warn" : "bad"} />
      <StatCard label="Postadas" value={`${pct(posted)}%`} hint={`${posted}/${total}`} tone={pct(posted) >= 90 ? "ok" : pct(posted) >= 50 ? "warn" : "bad"} />
      <StatCard label="Conciliadas" value={`${pct(reconciled)}%`} hint={`${reconciled}/${total}`} tone={pct(reconciled) >= 80 ? "ok" : pct(reconciled) >= 40 ? "warn" : "bad"} />
      <StatCard label="Abertas" value={String(total - posted)} hint="pendentes ou canceladas" />
    </div>
  )
}

function StatCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: "ok" | "warn" | "bad"
}) {
  return (
    <div className="card-elevated p-3">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 text-[18px] font-semibold tabular-nums",
          tone === "ok" && "text-emerald-500",
          tone === "warn" && "text-amber-500",
          tone === "bad" && "text-destructive",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[10px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

function TransactionEditor({
  open, transaction, onClose,
}: {
  open: boolean
  transaction: Transaction | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveTransaction()
  const action = useTransactionAction()
  const { data: entities = [] } = useEntities()
  const { data: currencies = [] } = useCurrencies()
  const [form, setForm] = useState<TransactionWrite>({
    date: new Date().toISOString().slice(0, 10),
    entity: 0,
    description: "",
    amount: "0.00",
    currency: 0,
    state: "pending",
  })

  useEffect(() => {
    if (transaction) {
      setForm({
        id: transaction.id,
        date: transaction.date,
        entity: transaction.entity,
        description: transaction.description,
        amount: transaction.amount,
        currency: transaction.currency,
        state: transaction.state,
      })
    } else {
      setForm({
        date: new Date().toISOString().slice(0, 10),
        entity: 0,
        description: "",
        amount: "0.00",
        currency: 0,
        state: "pending",
      })
    }
  }, [transaction, open])

  const set = <K extends keyof TransactionWrite>(key: K, value: TransactionWrite[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.description || !form.entity || !form.currency) {
      toast.error("Preencha descrição, entidade e moeda")
      return
    }
    save.mutate(
      { id: transaction?.id, body: form },
      {
        onSuccess: () => { toast.success("Transação salva"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  const onAction = (kind: "post" | "unpost" | "cancel") => {
    if (!transaction) return
    action.mutate({ id: transaction.id, action: kind }, {
      onSuccess: () => { toast.success(`Transação ${kind === "post" ? "postada" : kind === "unpost" ? "despostada" : "cancelada"}`); onClose() },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Receipt className="h-3.5 w-3.5 text-muted-foreground" />
              {transaction ? `Transação #${transaction.id}` : "Nova transação"}
              {transaction && <StatusBadge status={transaction.state} />}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <div className="grid grid-cols-[140px_1fr] gap-3">
              <Field label="Data">
                <input type="date" value={form.date} onChange={(e) => set("date", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
              </Field>
              <Field label="Entidade">
                <select value={form.entity} onChange={(e) => set("entity", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {entities.map((en) => <option key={en.id} value={en.id}>{en.path ?? en.name}</option>)}
                </select>
              </Field>
            </div>

            <Field label="Descrição">
              <input value={form.description} onChange={(e) => set("description", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Valor">
                <input type="number" step="0.01" value={form.amount} onChange={(e) => set("amount", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Moeda">
                <select value={form.currency} onChange={(e) => set("currency", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {currencies.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
                </select>
              </Field>
            </div>

            {transaction && (
              <div className="rounded-md border border-border bg-surface-3 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Ações</div>
                <div className="flex flex-wrap gap-2">
                  {transaction.state !== "posted" && (
                    <button onClick={() => onAction("post")} disabled={action.isPending}
                      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2.5 text-[11px] font-medium text-primary hover:bg-primary/15">
                      <PlayCircle className="h-3 w-3" /> Postar
                    </button>
                  )}
                  {transaction.state === "posted" && (
                    <button onClick={() => onAction("unpost")} disabled={action.isPending}
                      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent">
                      <CheckCircle2 className="h-3 w-3" /> Despostar
                    </button>
                  )}
                  <button onClick={() => onAction("cancel")} disabled={action.isPending}
                    className="inline-flex h-7 items-center gap-1.5 rounded-md border border-danger/30 bg-danger/10 px-2.5 text-[11px] font-medium text-danger hover:bg-danger/15">
                    <XCircle className="h-3 w-3" /> Cancelar
                  </button>
                </div>
              </div>
            )}
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
