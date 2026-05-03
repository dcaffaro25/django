import { Fragment, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  Plus, Trash2, Save, X, Receipt, Copy, Search, Filter, RotateCcw,
  CheckCircle2, PlayCircle, XCircle, ChevronRight, ChevronDown, Loader2, RefreshCw,
  CheckSquare,
} from "lucide-react"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { SectionHeader } from "@/components/ui/section-header"
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
  useBulkPostBalancedTransactions,
  useCurrencies, useDeleteTransaction, useEntities, useSaveTransaction,
  useTransactionAction, useTransactionJournalEntries, useTransactions,
} from "@/features/reconciliation"
import type {
  Transaction,
  TransactionJournalEntry,
  TransactionWrite,
} from "@/features/reconciliation/types"
import { reconApi } from "@/features/reconciliation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

function isoDaysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const STATE_FILTERS = ["all", "pending", "posted", "canceled"] as const

export function TransactionsPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { canWrite } = useUserRole()
  const [editing, setEditing] = useState<Transaction | "new" | null>(null)
  const [stateFilter, setStateFilter] = useState<(typeof STATE_FILTERS)[number]>("all")
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(60))
  const [dateTo, setDateTo] = useState(isoDaysAgo(0))
  const [entityFilter, setEntityFilter] = useState<number | "">("")
  const [search, setSearch] = useState("")

  // Bulk-post backfill modal state — same dry-run → confirm pattern as
  // the invoice-status backfill (see InvoicesPage). Operator clicks
  // "Postar balanceadas", we fire a dry-run to populate the preview,
  // then a real run on confirm. Limit lets the operator throttle the
  // first apply on large tenants (0 = unlimited).
  type BulkPostPreview = Awaited<ReturnType<typeof reconApi.bulkPostBalancedTransactions>>
  const [backfillOpen, setBackfillOpen] = useState(false)
  const [backfillPreview, setBackfillPreview] = useState<BulkPostPreview | null>(null)
  const [backfillLimit, setBackfillLimit] = useState<number>(0)
  const bulkPost = useBulkPostBalancedTransactions()

  const { data: entities = [] } = useEntities()
  const { data: txs = [], isLoading, isFetching, refetch } = useTransactions({
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
    { key: "due_date", label: "Vencimento", defaultVisible: false },
    { key: "entity", label: "Entidade" },
    { key: "description", label: "Descrição", alwaysVisible: true },
    { key: "amount", label: "Valor" },
    { key: "state", label: "Status" },
    { key: "flags", label: "Flags", defaultVisible: false },
  ], [])
  const col = useColumnVisibility("accounting.transactions", columns)

  const del = useDeleteTransaction()
  const action = useTransactionAction()

  // Row expansion for JE drill-down. Keyed by tx.id; expanded rows render
  // a nested table below the main row.
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toggleExpand = (id: number, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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

  // Auto-open the bulk-post modal when navigated with #bulk-post (the
  // CTA on the Saúde dos Dados "Transações sem posting" check links
  // here). One-shot: we strip the hash so a manual refresh doesn't
  // re-trigger.
  useEffect(() => {
    if (typeof window === "undefined") return
    if (window.location.hash !== "#bulk-post") return
    void (async () => {
      try {
        const preview = await bulkPost.mutateAsync({ dry_run: true, limit: 0 })
        setBackfillPreview(preview)
        setBackfillOpen(true)
        history.replaceState(null, "", window.location.pathname + window.location.search)
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Falha ao carregar prévia")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
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
            <DownloadXlsxButton
              path="/api/transactions/export_xlsx/"
              params={{
                state: stateFilter === "all" ? undefined : stateFilter,
                date_after: dateFrom || undefined,
                date_before: dateTo || undefined,
                entity: entityFilter || undefined,
                ordering: "-date",
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
                onClick={async () => {
                  try {
                    const preview = await bulkPost.mutateAsync({ dry_run: true, limit: 0 })
                    setBackfillPreview(preview)
                    setBackfillOpen(true)
                  } catch (err: unknown) {
                    toast.error(err instanceof Error ? err.message : "Falha ao carregar prévia")
                  }
                }}
                disabled={bulkPost.isPending}
                title="Postar transações em pending que já estão balanceadas"
                className={cn(
                  "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                  bulkPost.isPending && "opacity-60",
                )}
              >
                <CheckSquare className="h-3.5 w-3.5" /> Postar balanceadas
              </button>
            )}
            {canWrite && (
              <button
                onClick={() => setEditing("new")}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-3.5 w-3.5" /> Nova transação
              </button>
            )}
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

      {canWrite && (
        <BulkActionsBar count={selection.count} onClear={selection.clear}>
          <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
        </BulkActionsBar>
      )}

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
              <th className="h-9 w-6 px-1"></th>
              <th className="h-9 w-10 px-3">
                <SelectAllCheckbox
                  allSelected={selection.allSelected(sortedIds)}
                  someSelected={selection.someSelected(sortedIds)}
                  onToggle={() => selection.toggleAll(sortedIds)}
                />
              </th>
              <th className="h-9 px-3"><SortableHeader columnKey="id" label="ID" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("date") && <th className="h-9 px-3"><SortableHeader columnKey="date" label="Data" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("due_date") && <th className="h-9 px-3">Vencimento</th>}
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
                  <td colSpan={10} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={10} className="h-24 px-3 text-center text-muted-foreground">Nenhuma transação no filtro atual</td>
              </tr>
            ) : (
              sorted.map((tx) => {
                const isExpanded = expanded.has(tx.id)
                const dueInfo = getDueDateStatus(tx)
                return (
                  <Fragment key={tx.id}>
                    <tr onClick={() => setEditing(tx)}
                      className={cn(
                        "group cursor-pointer border-t border-border hover:bg-accent/50",
                        selection.isSelected(tx.id) && "bg-primary/5",
                        isExpanded && "bg-accent/20",
                      )}>
                      <td className="h-10 w-6 px-1">
                        <button
                          onClick={(e) => toggleExpand(tx.id, e)}
                          className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                          aria-label={isExpanded ? "Recolher" : "Expandir"}
                        >
                          {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        </button>
                      </td>
                      <td className="h-10 px-3">
                        <RowCheckbox checked={selection.isSelected(tx.id)} onToggle={() => selection.toggle(tx.id)} />
                      </td>
                      <td className="h-10 px-3 font-mono text-muted-foreground">#{tx.id}</td>
                      {col.isVisible("date") && <td className="h-10 px-3 text-muted-foreground">{formatDate(tx.date)}</td>}
                      {col.isVisible("due_date") && (
                        <td className="h-10 px-3 text-[11px]">
                          {tx.due_date ? (
                            <span className="flex items-center gap-1.5">
                              <span className="text-muted-foreground">{formatDate(tx.due_date)}</span>
                              {dueInfo.tone !== "neutral" && (
                                <span
                                  className={cn(
                                    "rounded px-1 py-0.5 text-[9px] font-semibold uppercase",
                                    dueInfo.tone === "ok" && "bg-emerald-500/15 text-emerald-500",
                                    dueInfo.tone === "late" && "bg-destructive/15 text-destructive",
                                  )}
                                >
                                  {dueInfo.label}
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      )}
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
                      {canWrite ? (
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
                      ) : (
                        <td className="h-10 px-3" />
                      )}
                    </tr>
                    {isExpanded && (
                      <tr className="border-t-0 bg-muted/10">
                        <td colSpan={10} className="px-10 py-3">
                          <JournalEntriesPanel transaction={tx} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <TransactionEditor
        open={editing !== null}
        transaction={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />

      {/* Bulk-post confirmation modal — dry-run preview, then apply.
          Mirrors the invoice-status backfill flow on InvoicesPage. */}
      <Dialog open={backfillOpen} onOpenChange={(o) => { if (!o) setBackfillOpen(false) }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Postar transações balanceadas</DialogTitle>
            <DialogDescription>
              Promove <strong>state=pending → posted</strong> em todas as
              transações que já estão balanceadas (débitos = créditos).
              Reversível por linha via "Despostar" ou no editor.
            </DialogDescription>
          </DialogHeader>

          {backfillPreview ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-md border border-border bg-muted/30 p-3">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Pré-visualização
                </div>
                <div className="mt-1 grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-[10px] text-muted-foreground">Pending balanceadas</div>
                    <div className="text-base font-medium tabular-nums">
                      {backfillPreview.scanned_pending_balanced}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-muted-foreground">A postar</div>
                    <div className="text-base font-bold tabular-nums text-success">
                      {backfillPreview.would_post}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-muted-foreground">Limite atual</div>
                    <div className="text-base font-medium tabular-nums">
                      {backfillLimit > 0 ? backfillLimit : "∞"}
                    </div>
                  </div>
                </div>
              </div>

              {backfillPreview.samples.length > 0 ? (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                    Amostra ({backfillPreview.samples.length} de {backfillPreview.would_post})
                  </div>
                  <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border/60 bg-muted/20 p-2">
                    {backfillPreview.samples.map((s) => (
                      <div key={s.id} className="flex items-center gap-2 text-[11px]">
                        <span className="font-mono text-muted-foreground">#{s.id}</span>
                        <span className="text-muted-foreground">{s.date ?? "—"}</span>
                        <span className="tabular-nums">R$ {s.amount ?? "—"}</span>
                        <span className="truncate">{s.description}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
                <span>Limitar a</span>
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={backfillLimit || ""}
                  onChange={(e) => setBackfillLimit(Number(e.target.value) || 0)}
                  placeholder="0 = sem limite"
                  className="h-7 w-[120px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                />
                <span>linhas (0 = todas)</span>
              </label>

              <div className="rounded-md border border-warning/30 bg-warning/5 p-2 text-[11px] text-muted-foreground">
                Cada Tx é postada via o serviço por-linha
                <code className="mx-1 rounded bg-muted px-1 font-mono">post_transaction</code>
                — guardas existentes (saldo, account_direction) continuam aplicando.
                Linhas que falharem ficam em pending e são listadas no resultado.
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-muted-foreground">Carregando prévia…</div>
          )}

          <DialogFooter>
            <button
              onClick={() => setBackfillOpen(false)}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              disabled={
                bulkPost.isPending ||
                !backfillPreview ||
                backfillPreview.would_post === 0
              }
              onClick={async () => {
                try {
                  const res = await bulkPost.mutateAsync({
                    dry_run: false,
                    limit: backfillLimit > 0 ? backfillLimit : undefined,
                  })
                  setBackfillOpen(false)
                  setBackfillPreview(null)
                  void refetch()
                  if (res.failed > 0) {
                    toast.warning(
                      `${res.posted} postadas · ${res.failed} falharam`,
                    )
                  } else {
                    toast.success(`${res.posted} transações postadas`)
                  }
                } catch (err: unknown) {
                  toast.error(err instanceof Error ? err.message : "Erro")
                }
              }}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90",
                (bulkPost.isPending || !backfillPreview || backfillPreview.would_post === 0) && "opacity-60",
              )}
            >
              <CheckSquare className="h-3.5 w-3.5" />
              Aplicar ({backfillPreview?.would_post ?? 0})
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/**
 * Due-date respect for a transaction. The tx.date is typically the
 * posting/settlement date; if it lands on or before due_date we consider
 * it on time. No due_date → neutral.
 */
function getDueDateStatus(tx: Transaction): { tone: "neutral" | "ok" | "late"; label: string } {
  if (!tx.due_date) return { tone: "neutral", label: "—" }
  if (!tx.is_posted) {
    const today = new Date().toISOString().slice(0, 10)
    if (today > tx.due_date) return { tone: "late", label: "atrasada" }
    return { tone: "neutral", label: "em aberto" }
  }
  if (tx.date && tx.date > tx.due_date) return { tone: "late", label: "tardia" }
  return { tone: "ok", label: "em dia" }
}

/**
 * Inline JE drill-down for one transaction. Fetches JEs via the new
 * /transactions/{id}/journal_entries/ action, lets operators edit the
 * description/debit/credit/cost_center inline, delete, or append a new
 * empty row. Edits / creates go through the existing journal_entries
 * endpoints. Keeps the parent transaction list as the primary surface.
 */
function JournalEntriesPanel({ transaction }: { transaction: Transaction }) {
  const { data: entries = [], isLoading, isError } = useTransactionJournalEntries(transaction.id)
  const qc = useQueryClient()
  const { tenant } = useTenant()

  const invalidate = () => {
    qc.invalidateQueries({
      queryKey: ["recon", tenant?.subdomain, "transaction", transaction.id, "journal_entries"],
    })
    qc.invalidateQueries({ queryKey: ["recon", tenant?.subdomain, "transactions"] })
  }

  const delJE = useMutation({
    mutationFn: (id: number) => reconApi.deleteJournalEntry(id),
    onSuccess: () => {
      toast.success("Lançamento excluído")
      invalidate()
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
  })

  const addJE = useMutation({
    mutationFn: () =>
      reconApi.createJournalEntry({
        transaction: transaction.id,
        description: transaction.description,
        debit_amount: "0.00",
        credit_amount: "0.00",
        date: transaction.date,
        bank_designation_pending: true,
      } as unknown as Partial<import("@/features/reconciliation/types").JournalEntry>),
    onSuccess: () => {
      toast.success("Lançamento adicionado")
      invalidate()
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Carregando lançamentos…
      </div>
    )
  }
  if (isError) {
    return <div className="text-[11px] text-destructive">Falha ao carregar lançamentos.</div>
  }

  const totalDebit = entries.reduce((s, e) => s + Number(e.debit_amount || 0), 0)
  const totalCredit = entries.reduce((s, e) => s + Number(e.credit_amount || 0), 0)
  const diff = totalDebit - totalCredit
  const isBalanced = Math.abs(diff) < 0.005

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Lançamentos — {entries.length}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            addJE.mutate()
          }}
          disabled={addJE.isPending}
          className="inline-flex h-6 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent disabled:opacity-50"
        >
          <Plus className="h-3 w-3" /> Adicionar
        </button>
      </div>
      {entries.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] text-muted-foreground">
          Nenhum lançamento vinculado.
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-[11px]">
            <thead className="bg-surface-3 text-left text-[9px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-7 px-2">#</th>
                <th className="h-7 px-2">Conta</th>
                <th className="h-7 px-2">Descrição</th>
                <th className="h-7 px-2 text-right">Débito</th>
                <th className="h-7 px-2 text-right">Crédito</th>
                <th className="h-7 px-2">Status</th>
                <th className="h-7 w-px px-2"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((je) => (
                <JeRow key={je.id} je={je} onDelete={() => delJE.mutate(je.id)} onSaved={invalidate} />
              ))}
              <tr className="border-t-2 border-border bg-muted/30 font-semibold">
                <td colSpan={3} className="h-7 px-2 text-right text-[10px] uppercase tracking-wider text-muted-foreground">
                  Totais
                </td>
                <td className="h-7 px-2 text-right tabular-nums">
                  {totalDebit.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </td>
                <td className="h-7 px-2 text-right tabular-nums">
                  {totalCredit.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </td>
                <td className="h-7 px-2 text-[10px]">
                  {isBalanced ? (
                    <span className="text-emerald-500">Balanceado</span>
                  ) : (
                    <span className="text-destructive">Diff {diff.toFixed(2)}</span>
                  )}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/**
 * Editable row for one journal entry. Keeps local draft state; a pencil
 * click flips to save/cancel. Fields deliberately minimal (description,
 * debit, credit) — bigger edits go through the main TransactionEditor
 * drawer. Account id changes need the account picker and are not exposed
 * here yet (would hit PATCH /journal_entries/{id}/).
 */
function JeRow({
  je,
  onDelete,
  onSaved,
}: {
  je: TransactionJournalEntry
  onDelete: () => void
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    description: je.description ?? "",
    debit_amount: String(je.debit_amount ?? "0"),
    credit_amount: String(je.credit_amount ?? "0"),
  })
  const save = useMutation({
    mutationFn: (body: Partial<import("@/features/reconciliation/types").JournalEntry>) =>
      reconApi.updateJournalEntry(je.id, body),
    onSuccess: () => {
      toast.success("Lançamento atualizado")
      setEditing(false)
      onSaved()
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
  })

  const accountLabel =
    typeof je.account === "object" && je.account !== null
      ? `${je.account.account_code ? je.account.account_code + " · " : ""}${je.account.name}`
      : typeof je.account === "number"
      ? `#${je.account}`
      : je.bank_designation_pending
      ? "pendente"
      : "—"

  return (
    <tr className="border-t border-border">
      <td className="h-7 px-2 font-mono text-muted-foreground">#{je.id}</td>
      <td className="h-7 px-2 text-muted-foreground">{accountLabel}</td>
      <td className="h-7 px-2">
        {editing ? (
          <input
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            className="h-6 w-full rounded border border-border bg-background px-1.5 text-[11px] outline-none focus:border-ring"
          />
        ) : (
          je.description ?? ""
        )}
      </td>
      <td className="h-7 px-2 text-right tabular-nums">
        {editing ? (
          <input
            type="number"
            step="0.01"
            value={draft.debit_amount}
            onChange={(e) => setDraft({ ...draft, debit_amount: e.target.value })}
            className="h-6 w-20 rounded border border-border bg-background px-1.5 text-right text-[11px] outline-none focus:border-ring"
          />
        ) : (
          Number(je.debit_amount).toLocaleString("pt-BR", { minimumFractionDigits: 2 })
        )}
      </td>
      <td className="h-7 px-2 text-right tabular-nums">
        {editing ? (
          <input
            type="number"
            step="0.01"
            value={draft.credit_amount}
            onChange={(e) => setDraft({ ...draft, credit_amount: e.target.value })}
            className="h-6 w-20 rounded border border-border bg-background px-1.5 text-right text-[11px] outline-none focus:border-ring"
          />
        ) : (
          Number(je.credit_amount).toLocaleString("pt-BR", { minimumFractionDigits: 2 })
        )}
      </td>
      <td className="h-7 px-2 text-[10px] text-muted-foreground">{je.state ?? "—"}</td>
      <td className="h-7 px-2">
        <div className="flex items-center gap-1">
          {editing ? (
            <>
              <button
                onClick={() =>
                  save.mutate({
                    description: draft.description,
                    debit_amount: draft.debit_amount,
                    credit_amount: draft.credit_amount,
                  } as unknown as Partial<import("@/features/reconciliation/types").JournalEntry>)
                }
                disabled={save.isPending}
                className="grid h-5 w-5 place-items-center rounded text-emerald-500 hover:bg-emerald-500/10 disabled:opacity-50"
                title="Salvar"
              >
                <Save className="h-3 w-3" />
              </button>
              <button
                onClick={() => {
                  setDraft({
                    description: je.description ?? "",
                    debit_amount: String(je.debit_amount ?? "0"),
                    credit_amount: String(je.credit_amount ?? "0"),
                  })
                  setEditing(false)
                }}
                className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:bg-accent"
                title="Cancelar"
              >
                <X className="h-3 w-3" />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditing(true)}
                className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                title="Editar"
              >
                <Receipt className="h-3 w-3" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (window.confirm(`Excluir lançamento #${je.id}?`)) onDelete()
                }}
                className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                title="Excluir"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
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
