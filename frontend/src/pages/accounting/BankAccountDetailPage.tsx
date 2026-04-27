import { useMemo, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  AlertCircle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Calendar,
  Clock,
  DollarSign,
  Loader2,
  RefreshCw,
  TrendingUp,
  Wallet,
} from "lucide-react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { BankTransactionDetailDrawer } from "@/components/reconciliation/BankTransactionDetailDrawer"
import {
  useBankAccount,
  useBankAccountKpis,
  useBankAccountMonthlyFlows,
  useBankTransactions,
  useDailyBalances,
} from "@/features/reconciliation"
import type { BankTransaction } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/**
 * Page 2 — Single Bank Account deep-dive.
 *
 * Mounted at ``/accounting/bank-accounts/:id``. Composition:
 *
 *  1. Header: breadcrumb back, account name + bank + entity, current balance.
 *  2. KPI strip: 6 cards (balance, recon-rate, stale count, MTD inflow,
 *     MTD outflow, last activity).
 *  3. Bank vs Book daily balance chart (recharts AreaChart) — reuses
 *     the existing ``/api/bank-book-daily-balances/`` endpoint with
 *     ``bank_account_id`` set so we get per-account lines.
 *  4. Monthly inflow/outflow bar chart (recharts BarChart) backed by
 *     the new ``/api/bank_accounts/<id>/monthly-flows/`` endpoint.
 *  5. Recent transactions table — last 50 by date desc. Click a row
 *     to open ``BankTransactionDetailDrawer`` (3-tab: details, recon
 *     history, activity placeholder). For deeper exploration the
 *     operator goes to the workbench / management page.
 */
export function BankAccountDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const accountId = id ? Number.parseInt(id, 10) : NaN
  const idValid = Number.isFinite(accountId) && accountId > 0

  const { data: account, isLoading: accountLoading, isError: accountError } =
    useBankAccount(idValid ? accountId : null)
  const { data: kpis, isLoading: kpisLoading, refetch: refetchKpis } =
    useBankAccountKpis(idValid ? accountId : null)
  const { data: flows = [] } = useBankAccountMonthlyFlows(idValid ? accountId : null, 12)

  // Daily balance window: last 90 days. Could become a date-range
  // picker later — for v1 a fixed 90-day window keeps the layout
  // honest and the load fast.
  const today = new Date()
  const ninetyDaysAgo = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000)
  const dateRange = useMemo(
    () => ({
      date_from: ninetyDaysAgo.toISOString().slice(0, 10),
      date_to: today.toISOString().slice(0, 10),
    }),
    // Dates are derived from `today` once at mount; recomputing every
    // render would re-fire the query needlessly. The 90-day window
    // only matters at first paint; operators who want fresher data
    // can hit Refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [accountId],
  )
  const { data: balanceData } = useDailyBalances({
    bank_account_id: idValid ? accountId : undefined,
    date_from: dateRange.date_from,
    date_to: dateRange.date_to,
    include_pending_book: true,
  })

  // Recent transactions — last 50, default ordering (most recent first).
  const txParams = useMemo(
    () => ({ bank_account: idValid ? accountId : undefined, page_size: 50 }),
    [accountId, idValid],
  )
  const { data: txPage, isLoading: txLoading } = useBankTransactions(txParams)
  const transactions: BankTransaction[] = useMemo(() => {
    // ``useBankTransactions`` may return an array or paginated
    // object depending on the param shape. Defensive unwrap.
    const raw = txPage as unknown
    if (Array.isArray(raw)) return raw as BankTransaction[]
    if (raw && typeof raw === "object" && "results" in raw) {
      const results = (raw as { results: unknown }).results
      return Array.isArray(results) ? (results as BankTransaction[]) : []
    }
    return []
  }, [txPage])

  const [drawerSource, setDrawerSource] = useState<BankTransaction | null>(null)

  // -------- early returns --------

  if (!idValid) {
    return (
      <div className="space-y-3">
        <SectionHeader title="Conta bancária" subtitle="ID inválido" />
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-destructive">
          O identificador da conta bancária na URL não é um número válido.
        </div>
      </div>
    )
  }

  if (accountError) {
    return (
      <div className="space-y-3">
        <SectionHeader title="Conta bancária" subtitle="Erro" />
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-destructive">
          Falha ao carregar conta bancária #{accountId}. Tente novamente ou
          volte para a lista.
        </div>
        <Button variant="outline" onClick={() => navigate("/accounting/bank-accounts")}>
          <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Voltar à lista
        </Button>
      </div>
    )
  }

  // -------- render --------

  const accountTitle = account?.name ?? "Conta bancária"
  const accountSubtitle = (() => {
    const parts: string[] = []
    if (account?.entity?.name) parts.push(account.entity.name)
    if (account?.bank?.name) parts.push(account.bank.name)
    if (account?.account_number) parts.push(`#${account.account_number}`)
    return parts.join(" · ")
  })()

  return (
    <div className="space-y-4">
      <SectionHeader
        title={accountTitle}
        subtitle={accountSubtitle || undefined}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => navigate("/accounting/bank-accounts")}
            >
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Lista
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void refetchKpis()}
              disabled={kpisLoading}
            >
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", kpisLoading && "animate-spin")} />
              Atualizar
            </Button>
          </div>
        }
      />

      {accountLoading || kpisLoading ? (
        <div className="card-elevated flex items-center justify-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando…
        </div>
      ) : (
        <KpiStrip kpis={kpis} currencyCode={kpis?.currency_code ?? null} />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <BalanceChart
          data={balanceData}
          currencyCode={kpis?.currency_code ?? account?.currency?.code ?? null}
        />
        <FlowsChart flows={flows} currencyCode={kpis?.currency_code ?? null} />
      </div>

      <RecentTransactionsTable
        transactions={transactions}
        isLoading={txLoading}
        onRowClick={(tx) => setDrawerSource(tx)}
        currencyCode={kpis?.currency_code ?? null}
      />

      <BankTransactionDetailDrawer
        open={drawerSource != null}
        onClose={() => setDrawerSource(null)}
        source={drawerSource}
      />
    </div>
  )
}

// ---- Sub-components -------------------------------------------------------

function KpiStrip({
  kpis,
  currencyCode,
}: {
  kpis: ReturnType<typeof useBankAccountKpis>["data"]
  currencyCode: string | null
}) {
  if (!kpis) return null
  const recRate = kpis.reconciliation_rate_pct
  const recColor =
    recRate >= 90 ? "text-emerald-600" : recRate >= 50 ? "text-amber-600" : "text-destructive"
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
      <KpiCard
        icon={<Wallet className="h-3.5 w-3.5" />}
        label="Saldo atual"
        value={formatCurrency(kpis.current_balance, currencyCode ?? undefined)}
      />
      <KpiCard
        icon={<TrendingUp className="h-3.5 w-3.5" />}
        label={`% conciliado · ${kpis.recon_window_days}d`}
        value={`${recRate}%`}
        valueClassName={recColor}
      />
      <KpiCard
        icon={<AlertCircle className="h-3.5 w-3.5" />}
        label={`Pendentes > ${kpis.stale_days}d`}
        value={kpis.stale_unreconciled_count.toString()}
        valueClassName={kpis.stale_unreconciled_count > 0 ? "text-amber-600" : "text-emerald-600"}
      />
      <KpiCard
        icon={<ArrowUp className="h-3.5 w-3.5" />}
        label="Entradas (mês)"
        value={formatCurrency(kpis.inflow_mtd, currencyCode ?? undefined)}
        valueClassName="text-emerald-600"
      />
      <KpiCard
        icon={<ArrowDown className="h-3.5 w-3.5" />}
        label="Saídas (mês)"
        value={formatCurrency(kpis.outflow_mtd, currencyCode ?? undefined)}
        valueClassName="text-amber-600"
      />
      <KpiCard
        icon={<Clock className="h-3.5 w-3.5" />}
        label="Última conciliação"
        value={kpis.last_reconciliation_at ? formatDate(kpis.last_reconciliation_at) : "—"}
      />
    </div>
  )
}

function KpiCard({
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

function BalanceChart({
  data,
  currencyCode,
}: {
  data: ReturnType<typeof useDailyBalances>["data"]
  currencyCode: string | null
}) {
  // The single-account branch of ``/api/bank-book-daily-balances/``
  // returns ``bank`` and ``book`` as objects of shape
  // ``{anchor_date, opening_balance, line: [{date, movement, balance}, ...]}``.
  // Merge ``line`` arrays into one chart-ready row keyed by date.
  const series = useMemo(() => {
    type Row = { date: string; balance: number }
    type Side = { line?: Row[] } | Row[] | undefined
    const pickLine = (side: Side): Row[] => {
      if (Array.isArray(side)) return side  // legacy/test shape
      if (side && Array.isArray(side.line)) return side.line
      return []
    }
    const bankArr = pickLine((data as { bank?: Side } | undefined)?.bank)
    const bookArr = pickLine((data as { book?: Side } | undefined)?.book)
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
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
  }, [data])

  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <Calendar className="h-3.5 w-3.5 text-primary" />
          Saldo: banco vs livro (90 dias)
        </div>
        <span className="text-[10px] text-muted-foreground">
          {currencyCode ?? ""}
        </span>
      </div>
      {series.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-[12px] text-muted-foreground">
          Sem dados de saldo no período.
        </div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d) => d.slice(5)}
                minTickGap={20}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => formatCurrency(v, currencyCode ?? undefined)}
                width={80}
              />
              <Tooltip
                formatter={(v: number) => formatCurrency(v, currencyCode ?? undefined)}
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
                stroke="hsl(var(--chart-2, 142 71% 45%))"
                fill="hsl(var(--chart-2, 142 71% 45%) / 0.15)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function FlowsChart({
  flows,
  currencyCode,
}: {
  flows: Array<{ month: string; inflow: string; outflow: string }>
  currencyCode: string | null
}) {
  const data = useMemo(() => {
    // Defensive: useQuery's data prop can momentarily be undefined
    // even with a `= []` destructuring default in some scenarios
    // (e.g. typed at the call site as the query's data type, which
    // is technically `T | undefined`). Guard against non-array.
    const arr = Array.isArray(flows) ? flows : []
    return arr.map((f) => ({
      month: f.month,
      Entradas: Number(f.inflow),
      // render outflow as a negative bar so the chart is signed.
      Saídas: -Number(f.outflow),
    }))
  }, [flows])
  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <DollarSign className="h-3.5 w-3.5 text-primary" />
          Entradas e saídas (12 meses)
        </div>
        <span className="text-[10px] text-muted-foreground">
          {currencyCode ?? ""}
        </span>
      </div>
      {data.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-[12px] text-muted-foreground">
          Sem dados de movimentação.
        </div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => formatCurrency(v, currencyCode ?? undefined)}
                width={80}
              />
              <Tooltip
                formatter={(v: number) => formatCurrency(Math.abs(v), currencyCode ?? undefined)}
                contentStyle={{ fontSize: "11px" }}
              />
              <Legend wrapperStyle={{ fontSize: "11px" }} />
              <Bar dataKey="Entradas" fill="hsl(142 71% 45%)" />
              <Bar dataKey="Saídas" fill="hsl(0 70% 60%)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function RecentTransactionsTable({
  transactions,
  isLoading,
  onRowClick,
  currencyCode,
}: {
  transactions: BankTransaction[]
  isLoading: boolean
  onRowClick: (tx: BankTransaction) => void
  currencyCode: string | null
}) {
  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="text-[12px] font-semibold">Transações recentes</div>
        <span className="text-[10px] text-muted-foreground">
          últimas {transactions.length}
        </span>
      </div>
      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-6 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando…
        </div>
      ) : transactions.length === 0 ? (
        <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
          Nenhuma transação encontrada para esta conta.
        </div>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="bg-muted/30 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-8 px-3">Data</th>
              <th className="h-8 px-3">Descrição</th>
              <th className="h-8 px-3">Status</th>
              <th className="h-8 px-3 text-right">Valor</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => {
              const pct = tx.match_progress_pct
              const partial = pct !== undefined && pct > 0 && pct < 100
              return (
                <tr
                  key={tx.id}
                  onClick={() => onRowClick(tx)}
                  className="cursor-pointer border-t border-border/60 hover:bg-accent/40"
                >
                  <td className="px-3 py-1.5 align-top text-muted-foreground tabular-nums">
                    {formatDate(tx.date)}
                  </td>
                  <td className="px-3 py-1.5 align-top">{tx.description}</td>
                  <td className="px-3 py-1.5 align-top">
                    <span className="text-[11px] capitalize text-muted-foreground">
                      {tx.reconciliation_status}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 align-top text-right tabular-nums">
                    <div
                      className={cn(
                        "font-semibold",
                        Number(tx.amount) < 0 ? "text-muted-foreground" : "text-foreground",
                      )}
                    >
                      {formatCurrency(Number(tx.amount), currencyCode ?? undefined)}
                    </div>
                    {partial && (
                      <div className="text-[10px] text-amber-600">
                        {pct}% · {formatCurrency(tx.amount_remaining ?? "0", currencyCode ?? undefined)} restante
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
