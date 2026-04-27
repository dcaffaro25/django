import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Copy,
  ExternalLink,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { DownloadXlsxButton } from "@/components/ui/download-xlsx-button"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useBankAccountsDashboardKpis,
  useBanks,
  useBankAccountsList,
  useCurrencies,
  useDailyBalances,
  useDeleteBankAccount,
  useEntities,
  useSaveBankAccount,
} from "@/features/reconciliation"
import type {
  BankAccountFull,
  BankAccountsDashboardKpis,
  BankAccountWrite,
} from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

export function BankAccountsPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: accounts = [], isLoading, isFetching, refetch } = useBankAccountsList()
  const [editing, setEditing] = useState<BankAccountFull | "new" | null>(null)

  const { sort, sorted, toggle: toggleSort } = useSortable(accounts, {
    initialKey: "name",
    initialDirection: "asc",
    accessors: {
      name: (r) => r.name,
      bank: (r) => r.bank?.name ?? "",
      entity: (r) => r.entity?.name ?? "",
      currency: (r) => r.currency?.code ?? "",
      account_number: (r) => r.account_number ?? "",
      current_balance: (r) => r.current_balance ?? 0,
    },
  })

  const columns: ColumnDef[] = useMemo(
    () => [
      { key: "name", label: "Nome", alwaysVisible: true },
      { key: "bank", label: "Banco" },
      { key: "entity", label: "Entidade" },
      { key: "currency", label: "Moeda" },
      { key: "account_number", label: "Conta" },
      { key: "branch_id", label: "Agência", defaultVisible: false },
      { key: "current_balance", label: "Saldo atual" },
    ],
    [],
  )
  const col = useColumnVisibility("accounting.bank_accounts", columns)

  const deleteBa = useDeleteBankAccount()
  const onDelete = (a: BankAccountFull, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir conta "${a.name}"?`)) return
    deleteBa.mutate(a.id, {
      onSuccess: () => toast.success("Conta excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (a: BankAccountFull, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...a, id: undefined as unknown as number, name: `${a.name} (cópia)` })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} conta${ids.length > 1 ? "s" : ""}?`)) return
    const res = await Promise.allSettled(ids.map((id) => deleteBa.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídas · ${failed} falharam`)
    else toast.success(`${ids.length} contas excluídas`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Contas bancárias"
        subtitle="Gerenciar contas, saldos e vínculos"
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
            <DownloadXlsxButton path="/api/bank_accounts/export_xlsx/" />
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
            <button
              onClick={() => setEditing("new")}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> Nova conta
            </button>
          </>
        }
      />

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      {/* Dashboard section -- KPI strip + currency-grouped totals +
          cross-account daily balance chart. Sits above the
          management table so the operator sees the org-wide health
          before drilling into a specific row. */}
      <BankAccountsDashboardSection />

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
              <th className="h-9 px-3"><SortableHeader columnKey="name" label="Nome" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("bank") && <th className="h-9 px-3"><SortableHeader columnKey="bank" label="Banco" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("entity") && <th className="h-9 px-3"><SortableHeader columnKey="entity" label="Entidade" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("currency") && <th className="h-9 px-3"><SortableHeader columnKey="currency" label="Moeda" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("account_number") && <th className="h-9 px-3"><SortableHeader columnKey="account_number" label="Conta" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("branch_id") && <th className="h-9 px-3">Agência</th>}
              {col.isVisible("current_balance") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="current_balance" align="right" label="Saldo atual" sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={9} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={9} className="h-24 px-3 text-center text-muted-foreground">Nenhuma conta cadastrada</td>
              </tr>
            ) : (
              sorted.map((a) => (
                <tr key={a.id} onClick={() => setEditing(a)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(a.id) && "bg-primary/5",
                  )}>
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(a.id)} onToggle={() => selection.toggle(a.id)} />
                  </td>
                  <td className="h-10 px-3 font-medium">
                    {/* The row click still opens the edit drawer
                        (preserves the existing CRUD workflow), but
                        the name itself is now a link to the per-
                        account Detail page. ``stopPropagation``
                        keeps the two paths from triggering each
                        other. */}
                    <Link
                      to={`/accounting/bank-accounts/${a.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 hover:text-primary hover:underline"
                      title="Abrir painel da conta"
                    >
                      {a.name}
                      <ExternalLink className="h-3 w-3 opacity-60" />
                    </Link>
                  </td>
                  {col.isVisible("bank") && <td className="h-10 px-3 text-muted-foreground">{a.bank?.name ?? "—"}</td>}
                  {col.isVisible("entity") && <td className="h-10 px-3 text-muted-foreground">{a.entity?.name ?? "—"}</td>}
                  {col.isVisible("currency") && <td className="h-10 px-3 text-muted-foreground">{a.currency?.code ?? "—"}</td>}
                  {col.isVisible("account_number") && <td className="h-10 px-3 font-mono text-muted-foreground">{a.account_number ?? "—"}</td>}
                  {col.isVisible("branch_id") && <td className="h-10 px-3 font-mono text-muted-foreground">{a.branch_id ?? "—"}</td>}
                  {col.isVisible("current_balance") && (
                    <td className="h-10 px-3 text-right tabular-nums">{formatCurrency(a.current_balance ?? 0, a.currency?.code ?? "BRL")}</td>
                  )}
                  <RowActionsCell>
                    <RowAction icon={<Copy className="h-3.5 w-3.5" />} label="Duplicar" onClick={(e) => onDuplicate(a, e)} />
                    <RowAction icon={<Trash2 className="h-3.5 w-3.5" />} label="Excluir" variant="danger" onClick={(e) => onDelete(a, e)} />
                  </RowActionsCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <BankAccountEditor
        open={editing !== null}
        account={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

const BLANK: BankAccountWrite = {
  name: "",
  bank: 0,
  entity: 0,
  currency: 0,
  account_number: "",
  branch_id: "",
  balance: "0.00",
  balance_date: null,
  account_type: "",
}

function BankAccountEditor({
  open, account, onClose,
}: {
  open: boolean
  account: BankAccountFull | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveBankAccount()
  const { data: banks = [] } = useBanks()
  const { data: entities = [] } = useEntities()
  const { data: currencies = [] } = useCurrencies()
  const [form, setForm] = useState<BankAccountWrite>(BLANK)

  useEffect(() => {
    if (account) {
      setForm({
        id: account.id,
        name: account.name,
        bank: account.bank?.id ?? 0,
        entity: account.entity?.id ?? 0,
        currency: account.currency?.id ?? 0,
        account_number: account.account_number ?? "",
        branch_id: account.branch_id ?? "",
        balance: account.balance ?? "0.00",
        balance_date: account.balance_date ?? null,
        account_type: account.account_type ?? "",
      })
    } else {
      setForm({ ...BLANK })
    }
  }, [account, open])

  const set = <K extends keyof BankAccountWrite>(key: K, value: BankAccountWrite[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.name || !form.bank || !form.entity || !form.currency) {
      toast.error("Preencha nome, banco, entidade e moeda")
      return
    }
    save.mutate(
      { id: account?.id, body: form },
      {
        onSuccess: () => { toast.success("Conta salva"); onClose() },
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
              <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
              {account ? `Editar conta #${account.id}` : "Nova conta bancária"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <Field label="Nome">
              <input value={form.name} onChange={(e) => set("name", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Banco">
                <select value={form.bank} onChange={(e) => set("bank", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {banks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.bank_code ? `${b.bank_code} · ` : ""}{b.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Moeda">
                <select value={form.currency} onChange={(e) => set("currency", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {currencies.map((c) => (
                    <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Entidade">
              <select value={form.entity} onChange={(e) => set("entity", Number(e.target.value))}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                <option value={0}>—</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>{e.path ?? e.name}</option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Número da conta">
                <input value={form.account_number ?? ""} onChange={(e) => set("account_number", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Agência">
                <input value={form.branch_id ?? ""} onChange={(e) => set("branch_id", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring" />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Saldo inicial">
                <input type="number" step="0.01" value={form.balance ?? "0.00"} onChange={(e) => set("balance", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Data saldo">
                <input type="date" value={form.balance_date ?? ""} onChange={(e) => set("balance_date", e.target.value || null)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
              </Field>
            </div>

            <Field label="Tipo (opcional)">
              <input value={form.account_type ?? ""} onChange={(e) => set("account_type", e.target.value)} placeholder="Corrente, Poupança..."
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>
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

// ---------------------------------------------------------------------------
// Dashboard section (Page 1 of the Bank Accounts series). Lives in the same
// file as the management table so operators get a single ``/accounting/bank-
// accounts`` URL with overview-on-top + management-below, rather than a
// separate route for each. The component lazy-fetches its own data and
// renders nothing until the org-wide KPI endpoint responds.
// ---------------------------------------------------------------------------

function BankAccountsDashboardSection() {
  const { data: kpis, isLoading } = useBankAccountsDashboardKpis()

  // Cross-account daily balance: 90-day window. Skipping the
  // ``bank_account_id`` param triggers the aggregate-by-currency
  // path of the existing endpoint. Re-uses the same hook the recon
  // DashboardPage already trusts in production.
  const today = new Date()
  const ninetyDaysAgo = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000)
  const dateRange = useMemo(
    () => ({
      date_from: ninetyDaysAgo.toISOString().slice(0, 10),
      date_to: today.toISOString().slice(0, 10),
    }),
    // Fixed at mount; if operators want fresher windows they hit
    // refresh on the page header.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )
  const { data: balanceData } = useDailyBalances({
    date_from: dateRange.date_from,
    date_to: dateRange.date_to,
    include_pending_book: true,
  })

  if (isLoading) {
    return (
      <div className="card-elevated p-3 text-[12px] text-muted-foreground">
        Carregando indicadores…
      </div>
    )
  }
  if (!kpis) return null

  return (
    <div className="space-y-3">
      <DashboardKpiStrip kpis={kpis} />
      <div className="grid gap-3 md:grid-cols-2">
        <CurrencyTotalsCard kpis={kpis} />
        <AggregateBalanceChart data={balanceData} />
      </div>
    </div>
  )
}

function DashboardKpiStrip({ kpis }: { kpis: BankAccountsDashboardKpis }) {
  const recRate = kpis.reconciliation_rate_pct ?? 0
  const recColor =
    recRate >= 90 ? "text-emerald-600" : recRate >= 50 ? "text-amber-600" : "text-destructive"
  // First currency wins for the inflow/outflow strip cards. Multi-currency
  // tenants get the per-currency breakdown in the totals card below;
  // here we keep the strip compact. Defensive on every record access
  // so a missing/non-array currency_codes doesn't blow up the strip.
  const codes = Array.isArray(kpis.currency_codes) ? kpis.currency_codes : []
  const primaryCurrency = codes[0] ?? "BRL"
  const inflowByCurr = (kpis.inflow_mtd_by_currency && typeof kpis.inflow_mtd_by_currency === "object") ? kpis.inflow_mtd_by_currency : {}
  const outflowByCurr = (kpis.outflow_mtd_by_currency && typeof kpis.outflow_mtd_by_currency === "object") ? kpis.outflow_mtd_by_currency : {}
  const inflowMtd = inflowByCurr[primaryCurrency] ?? "0"
  const outflowMtd = outflowByCurr[primaryCurrency] ?? "0"

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-5">
      <DashboardKpiCard
        icon={<Wallet className="h-3.5 w-3.5" />}
        label="Contas"
        value={kpis.account_count.toString()}
      />
      <DashboardKpiCard
        icon={<TrendingUp className="h-3.5 w-3.5" />}
        label={`% conciliado · ${kpis.recon_window_days}d`}
        value={`${recRate}%`}
        valueClassName={recColor}
      />
      <DashboardKpiCard
        icon={<AlertCircle className="h-3.5 w-3.5" />}
        label={`Pendentes > ${kpis.stale_days}d`}
        value={kpis.stale_unreconciled_count.toString()}
        valueClassName={kpis.stale_unreconciled_count > 0 ? "text-amber-600" : "text-emerald-600"}
      />
      <DashboardKpiCard
        icon={<ArrowUp className="h-3.5 w-3.5" />}
        label={`Entradas (mês) · ${primaryCurrency}`}
        value={formatCurrency(inflowMtd, primaryCurrency)}
        valueClassName="text-emerald-600"
      />
      <DashboardKpiCard
        icon={<ArrowDown className="h-3.5 w-3.5" />}
        label={`Saídas (mês) · ${primaryCurrency}`}
        value={formatCurrency(outflowMtd, primaryCurrency)}
        valueClassName="text-amber-600"
      />
    </div>
  )
}

function DashboardKpiCard({
  icon,
  label,
  value,
  valueClassName,
}: {
  icon: React.ReactNode
  label: string
  value: string
  valueClassName?: string
}) {
  return (
    <div className="card-elevated p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className={cn("mt-1 text-[15px] font-semibold tabular-nums", valueClassName)}>
        {value}
      </div>
    </div>
  )
}

function CurrencyTotalsCard({ kpis }: { kpis: BankAccountsDashboardKpis }) {
  // Defensive: backend SHOULD always return an array + dict shapes
  // here, but if any field drifts (e.g. paginated list, null,
  // single string) we don't want the whole page to crash. Each
  // dict access is guarded too.
  const rawCodes = Array.isArray(kpis.currency_codes) ? kpis.currency_codes : []
  const codes = rawCodes.length > 0 ? rawCodes : ["BRL"]
  const balanceMap = (kpis.balance_by_currency && typeof kpis.balance_by_currency === "object") ? kpis.balance_by_currency : {}
  const inflowMap = (kpis.inflow_mtd_by_currency && typeof kpis.inflow_mtd_by_currency === "object") ? kpis.inflow_mtd_by_currency : {}
  const outflowMap = (kpis.outflow_mtd_by_currency && typeof kpis.outflow_mtd_by_currency === "object") ? kpis.outflow_mtd_by_currency : {}
  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold">
        <Wallet className="h-3.5 w-3.5 text-primary" />
        Saldos por moeda
      </div>
      <table className="w-full text-[12px]">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Moeda</th>
            <th className="h-7 px-2 text-right">Saldo</th>
            <th className="h-7 px-2 text-right">Entradas (mês)</th>
            <th className="h-7 px-2 text-right">Saídas (mês)</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => {
            const balance = balanceMap[code] ?? "0"
            const inflow = inflowMap[code] ?? "0"
            const outflow = outflowMap[code] ?? "0"
            return (
              <tr key={code} className="border-t border-border/60">
                <td className="px-2 py-1.5 font-mono text-[11px]">{code}</td>
                <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
                  {formatCurrency(balance, code)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-emerald-600">
                  {formatCurrency(inflow, code)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-amber-600">
                  {formatCurrency(outflow, code)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function AggregateBalanceChart({
  data,
}: {
  data: ReturnType<typeof useDailyBalances>["data"]
}) {
  // The aggregate (no bank_account_id) branch returns per-currency
  // bank vs book daily lines under ``aggregate.by_currency[code]``.
  // For v1 we render the FIRST currency's lines as the "primary" view
  // and let the Currency Totals card above carry multi-currency
  // detail. A future commit can add a currency picker here.
  const series = useMemo(() => {
    const agg = (data as { aggregate?: { by_currency?: Record<string, { bank?: Array<{ date: string; balance: number }>; book?: Array<{ date: string; balance: number }> }> } } | undefined)?.aggregate
    const byCurr = (agg && typeof agg.by_currency === "object" && agg.by_currency) || {}
    const codes = Object.keys(byCurr)
    if (codes.length === 0) return { rows: [], code: null as string | null }
    const code = codes[0]
    // Defensive: the backend ``bank`` / ``book`` keys are arrays in
    // production, but the recon dashboard has historically seen
    // shape drift (paginated wrappers, single objects). Guard with
    // ``Array.isArray`` so this useMemo can't throw "X is not
    // iterable" and crash the whole page.
    const bankArr = Array.isArray(byCurr[code]?.bank) ? byCurr[code]!.bank! : []
    const bookArr = Array.isArray(byCurr[code]?.book) ? byCurr[code]!.book! : []
    const byDate = new Map<string, { date: string; bank: number | null; book: number | null }>()
    for (const r of bankArr) {
      if (!r || typeof r !== "object") continue
      byDate.set(r.date, { date: r.date, bank: Number(r.balance ?? 0), book: null })
    }
    for (const r of bookArr) {
      if (!r || typeof r !== "object") continue
      const prev = byDate.get(r.date) ?? { date: r.date, bank: null, book: null }
      byDate.set(r.date, { ...prev, book: Number(r.balance ?? 0) })
    }
    return {
      rows: Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date)),
      code,
    }
  }, [data])

  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <TrendingUp className="h-3.5 w-3.5 text-primary" />
          Saldo consolidado · {series.code ?? "—"} (90 dias)
        </div>
      </div>
      {series.rows.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-[12px] text-muted-foreground">
          Sem dados de saldo no período.
        </div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series.rows} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d) => d.slice(5)}
                minTickGap={20}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => formatCurrency(v, series.code ?? "BRL")}
                width={80}
              />
              <Tooltip
                formatter={(v: number) => formatCurrency(v, series.code ?? "BRL")}
                labelFormatter={(d: string) => formatDate(d)}
                contentStyle={{ fontSize: "11px" }}
              />
              <Legend wrapperStyle={{ fontSize: "11px" }} />
              <Area
                type="monotone"
                dataKey="bank"
                name="Banco"
                stroke="hsl(var(--primary))"
                fill="hsl(var(--primary) / 0.15)"
              />
              <Area
                type="monotone"
                dataKey="book"
                name="Livro"
                stroke="hsl(142 71% 45%)"
                fill="hsl(142 71% 45% / 0.15)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
