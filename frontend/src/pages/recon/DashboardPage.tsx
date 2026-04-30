import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import {
  AreaChart, Area, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, Legend,
} from "recharts"
import {
  AlertTriangle, Banknote, AlarmClock, Sparkles, Play, Upload, ArrowRight, Activity, ListChecks, BookOpen,
} from "lucide-react"
import { KpiCard } from "@/components/ui/kpi-card"
import { SectionHeader } from "@/components/ui/section-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { useActiveTasks, useBankAccountsDashboardKpis, useBankAccountsList, useDailyBalances, useReconKPIs, useReconTasks } from "@/features/reconciliation"
import { useUserRole } from "@/features/auth/useUserRole"
import type { BankAccountRowKpis, BookCurrencyMismatch, BookDailyWarning } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDateTime, formatDuration, formatNumber } from "@/lib/utils"

type TxMode = "both" | "balanced" | "unbalanced"

const PERIOD_OPTIONS = [7, 14, 30, 90] as const
type PeriodDays = (typeof PERIOD_OPTIONS)[number]

function isoDaysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

export function DashboardPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const navigate = useNavigate()
  // Quick-action buttons (Iniciar conciliação / Revisar sugestões /
  // Importar OFX) are write surfaces -- hide from viewers (and from
  // operators in view-as-viewer preview).
  const { canWrite } = useUserRole()

  const [period, setPeriod] = useState<PeriodDays>(30)
  // ``include_pending_book`` widens the book daily-balance series to
  // include un-posted ("pending") JEs. Off by default because the chart
  // is most often used to reason about settled cash, but exposed as a
  // toggle so operators can also see the projected book balance after
  // pending invoices clear.
  const [includePendingBook, setIncludePendingBook] = useState(false)

  const dateFrom = useMemo(() => isoDaysAgo(period), [period])
  const dateTo = useMemo(() => isoDaysAgo(0), [])

  const { data: kpis, isLoading: kpisLoading } = useReconKPIs({
    lookback_days: period,
    trend_days: period,
  })
  const { data: balances, isLoading: balancesLoading } = useDailyBalances({
    date_from: dateFrom,
    date_to: dateTo,
    include_pending_book: includePendingBook,
  })
  const { data: tasks } = useReconTasks({ pollMs: 5000 })
  const { data: active } = useActiveTasks(3000)

  // Pick the first currency bucket for display (merge bank/book/diff lines by date)
  const chartData = useMemo(() => {
    const byCur = balances?.aggregate?.by_currency
    if (!byCur) return []
    const currencies = Object.keys(byCur)
    if (!currencies.length) return []
    const c = byCur[currencies[0]!]
    if (!c) return []
    const bankByDate = new Map<string, number>((c.bank?.line ?? []).map((p) => [p.date, Number(p.balance)]))
    const bookByDate = new Map<string, number>((c.book?.line ?? []).map((p) => [p.date, Number(p.balance)]))
    const diffByDate = new Map<string, number>((c.difference?.line ?? []).map((p) => [p.date, Number(p.bank_minus_book)]))
    const dates = Array.from(new Set<string>([...bankByDate.keys(), ...bookByDate.keys(), ...diffByDate.keys()])).sort()
    return dates.map((date) => ({
      date,
      bank: bankByDate.get(date) ?? 0,
      book: bookByDate.get(date) ?? 0,
      diff: diffByDate.get(date) ?? 0,
    }))
  }, [balances])

  // Surface the service-level warnings the backend attaches to each currency
  // bucket. `no_leaf_gl_linked_to_bank_account` is the main reason the book
  // line appears flat: the daily-balances service returns a zero-opening,
  // zero-movement series for any bank account without a leaf GL link.
  const { linkWarnings, currencyMismatches } = useMemo(() => {
    const warns: BookDailyWarning[] = []
    const mismatches: BookCurrencyMismatch[] = []
    const byCur = balances?.aggregate?.by_currency
    if (byCur) {
      for (const c of Object.values(byCur)) {
        for (const w of c.book?.warnings ?? []) warns.push(w)
        for (const m of c.book?.currency_mismatches ?? []) mismatches.push(m)
      }
    }
    return { linkWarnings: warns, currencyMismatches: mismatches }
  }, [balances])

  const recentTasks = (tasks ?? []).slice(0, 6)
  const activeTasks = active ?? []

  // Transaction trend — derived from the KPI trend_14d series so it follows
  // the same reconciled-count truth as the KPI cards.
  //   balanced    = reconciled
  //   unbalanced  = new_bank_tx - reconciled (clamped ≥ 0)
  const [txMode, setTxMode] = useState<TxMode>("both")
  const txTrendData = useMemo(() => {
    const trend = kpis?.trend_14d ?? []
    return trend.map((row) => {
      const balanced = Math.max(0, Number(row.reconciled ?? 0))
      const total = Math.max(0, Number(row.new_bank_tx ?? 0))
      return {
        date: row.date,
        balanceadas: balanced,
        nao_balanceadas: Math.max(0, total - balanced),
      }
    })
  }, [kpis])
  const txTrendTotals = useMemo(() => {
    return txTrendData.reduce(
      (acc, r) => {
        acc.balanced += r.balanceadas
        acc.unbalanced += r.nao_balanceadas
        return acc
      },
      { balanced: 0, unbalanced: 0 },
    )
  }, [txTrendData])
  const txTrendHasData =
    txTrendData.length > 0 &&
    (txTrendTotals.balanced > 0 || txTrendTotals.unbalanced > 0)

  // Bank side -- legacy ``unreconciled.count`` / ``amount_abs`` still
  // reflect this side, but read the ``bank`` block too so the hook
  // continues to work if the legacy keys ever go away.
  const unreconciledCount = kpis?.unreconciled.bank?.count ?? kpis?.unreconciled.count ?? 0
  const unreconciledAmount = kpis
    ? Number(kpis.unreconciled.bank?.amount_abs ?? kpis.unreconciled.amount_abs)
    : 0
  const oldestAge = kpis?.unreconciled.bank?.oldest_age_days ?? kpis?.unreconciled.oldest_age_days ?? null
  // Book side -- introduced in the dashboard refresh so "Valores em
  // aberto" stops being bank-only. Falls back to zero when the
  // backend hasn't been redeployed yet (older payloads lack the
  // ``book`` block).
  const unreconciledBookCount = kpis?.unreconciled.book?.count ?? 0
  const unreconciledBookAmount = kpis ? Number(kpis.unreconciled.book?.amount_abs ?? 0) : 0
  const autoRate = kpis?.tasks_30d.automatch_rate != null ? kpis.tasks_30d.automatch_rate * 100 : null
  const completedTasks = kpis?.tasks_30d.completed ?? 0

  return (
    <div className="space-y-6">
      <SectionHeader
        title={t("dashboard.title")}
        subtitle={t("dashboard.subtitle") ?? ""}
        actions={
          canWrite ? (
            <>
              <button
                onClick={() => navigate("/recon/tasks?new=1")}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Play className="h-3.5 w-3.5" /> {t("dashboard.quick_start")}
              </button>
              <button
                onClick={() => navigate("/recon/tasks")}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
              >
                <Sparkles className="h-3.5 w-3.5" /> {t("dashboard.quick_review_suggestions")}
              </button>
              <button
                onClick={() => navigate("/accounting/bank-transactions?action=import")}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
              >
                <Upload className="h-3.5 w-3.5" /> {t("dashboard.quick_import_ofx")}
              </button>
            </>
          ) : null
        }
      />

      {/* KPIs — clickable for drill-down. ``Valores em aberto`` was
          previously a single card showing only the bank side; the
          dashboard now splits it into Banco / Livro so operators see
          both halves of the picture (a tenant can have substantial
          unreconciled JEs even with a clean bank ledger). */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <button onClick={() => navigate("/recon/workbench")} className="text-left transition-transform hover:scale-[1.01]">
          <KpiCard
            label={t("dashboard.kpi_open_bank", { defaultValue: "Banco em aberto" })}
            value={kpisLoading ? "—" : formatCurrency(unreconciledAmount)}
            icon={<Banknote className="h-4 w-4" />}
            tone="default"
            hint={
              <span className="text-muted-foreground/70">
                {t("dashboard.kpi_open_bank_hint", {
                  count: unreconciledCount,
                  defaultValue: "{{count}} transações →",
                })}
              </span>
            }
          />
        </button>
        <button onClick={() => navigate("/recon/workbench")} className="text-left transition-transform hover:scale-[1.01]">
          <KpiCard
            label={t("dashboard.kpi_open_book", { defaultValue: "Livro em aberto" })}
            value={kpisLoading ? "—" : formatCurrency(unreconciledBookAmount)}
            icon={<BookOpen className="h-4 w-4" />}
            tone="default"
            hint={
              <span className="text-muted-foreground/70">
                {t("dashboard.kpi_open_book_hint", {
                  count: unreconciledBookCount,
                  defaultValue: "{{count}} lançamentos →",
                })}
              </span>
            }
          />
        </button>
        <button onClick={() => navigate("/recon/tasks")} className="text-left transition-transform hover:scale-[1.01]">
          <KpiCard
            label={t("dashboard.kpi_automatch_rate")}
            value={autoRate == null ? "—" : `${autoRate.toFixed(1)}%`}
            icon={<Activity className="h-4 w-4" />}
            tone="default"
            hint={
              <span className="text-muted-foreground/70">
                {t("dashboard.period_executions_in_n_days", { count: completedTasks, n: period })} →
              </span>
            }
          />
        </button>
        <button onClick={() => navigate("/recon/workbench")} className="text-left transition-transform hover:scale-[1.01]">
          <KpiCard
            label={t("dashboard.kpi_oldest_age")}
            value={
              oldestAge == null ? (
                "—"
              ) : (
                <span>
                  {oldestAge}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">{t("dashboard.days_short")}</span>
                </span>
              )
            }
            icon={<AlarmClock className="h-4 w-4" />}
            tone="default"
            hint={kpis?.unreconciled.oldest_date ? <span>desde {kpis.unreconciled.oldest_date}</span> : undefined}
          />
        </button>
      </div>

      {/* Per-account KPI snapshot — same data block the
          ``/accounting/bank-accounts`` table uses. Operators get a
          quick read on which accounts are healthy vs need attention
          without leaving the recon dashboard. */}
      <PerAccountKpiTable />

      {/* Data-quality warnings — surface service-side flags that make the
          book series look flat or break per-currency aggregation. */}
      {(linkWarnings.length > 0 || currencyMismatches.length > 0) && (
        <div className="space-y-2">
          {linkWarnings.length > 0 && (
            <BookFlatWarning warnings={linkWarnings} onOpen={() => navigate("/accounting/bank-accounts")} />
          )}
          {currencyMismatches.length > 0 && (
            <CurrencyMismatchWarning mismatches={currencyMismatches} />
          )}
        </div>
      )}

      {/* Chart + Active tasks */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="card-elevated col-span-1 p-4 lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-[13px] font-semibold">{t("dashboard.chart_bank_vs_book")}</h3>
              <p className="text-[11px] text-muted-foreground">
                {t("dashboard.period_last_n_days", { n: period })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <PeriodSwitch value={period} onChange={setPeriod} />
              <TxModeSwitch value={txMode} onChange={setTxMode} />
              {/* Pending-book toggle: lets operators ask the chart to
                  include un-posted JEs in the book series. Off by
                  default since most operators want settled cash, but
                  exposed here so a "where will my book balance land
                  once invoices clear?" view is one click away. */}
              <label
                className="inline-flex h-8 select-none items-center gap-1.5 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-foreground hover:bg-accent"
                title="Incluir lançamentos pendentes (não-postados) na série do livro"
              >
                <input
                  type="checkbox"
                  className="h-3 w-3 accent-primary"
                  checked={includePendingBook}
                  onChange={(e) => setIncludePendingBook(e.target.checked)}
                />
                Pendentes (livro)
              </label>
            </div>
          </div>
          <div className="h-[240px] w-full">
            {balancesLoading ? (
              <div className="h-full w-full animate-pulse rounded-md surface-3" />
            ) : chartData.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="bank" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="book" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--info))" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="hsl(var(--info))" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--surface-3))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" name="Banco" dataKey="bank" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#bank)" />
                  <Area type="monotone" name="Livro" dataKey="book" stroke="hsl(var(--info))" strokeWidth={2} fill="url(#book)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          {/* Transaction volume — balanced vs unbalanced per day. Toggled
              via the TxModeSwitch above; defaults to stacked 'both'. */}
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-medium text-muted-foreground">
                {t("dashboard.chart_tx_section")}
              </span>
              <span className="text-[10px] text-muted-foreground/70">
                {txTrendHasData
                  ? `${txTrendTotals.balanced + txTrendTotals.unbalanced} em ${txTrendData.length}d`
                  : kpisLoading
                    ? "…"
                    : t("dashboard.period_no_movement_n_days", { n: period })}
              </span>
            </div>
            <div className="h-24 w-full">
              {txTrendHasData ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={txTrendData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      width={60}
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--surface-3))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    {txMode !== "unbalanced" && (
                      <Bar
                        dataKey="balanceadas"
                        name={t("dashboard.chart_tx_balanced") ?? "Balanceadas"}
                        stackId="tx"
                        fill="hsl(var(--success))"
                        radius={txMode === "both" ? [0, 0, 0, 0] : [2, 2, 0, 0]}
                      />
                    )}
                    {txMode !== "balanced" && (
                      <Bar
                        dataKey="nao_balanceadas"
                        name={t("dashboard.chart_tx_unbalanced") ?? "Não balanceadas"}
                        stackId="tx"
                        fill="hsl(var(--danger))"
                        radius={[2, 2, 0, 0]}
                      />
                    )}
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border text-[11px] text-muted-foreground">
                  {kpisLoading
                    ? "Carregando…"
                    : t("dashboard.period_no_movement_n_days", { n: period })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Active tasks strip */}
        <div className="card-elevated p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-[13px] font-semibold">{t("dashboard.active_tasks")}</h3>
            <button
              onClick={() => navigate("/recon/tasks")}
              className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              {t("actions.view_all", { ns: "common" })} <ArrowRight className="h-3 w-3" />
            </button>
          </div>
          {activeTasks.length === 0 ? (
            <div className="flex h-[200px] flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border text-[12px] text-muted-foreground">
              <ListChecks className="h-5 w-5" />
              {t("dashboard.no_active_tasks")}
            </div>
          ) : (
            <ul className="space-y-2">
              {activeTasks.slice(0, 6).map((task) => (
                <li key={task.id} className="rounded-md border border-border p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] text-muted-foreground">#{task.id}</span>
                    <StatusBadge status={task.status} />
                  </div>
                  <div className="mt-1 truncate text-[13px] font-medium">
                    {task.config_name ?? task.pipeline_name ?? "—"}
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>Bancárias: <span className="tabular-nums text-foreground">{task.bank_candidates ?? 0}</span></span>
                    <span>Sug.: <span className="tabular-nums text-foreground">{task.suggestion_count ?? 0}</span></span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Recent tasks */}
      <div className="card-elevated p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[13px] font-semibold">{t("dashboard.recent_tasks")}</h3>
          <button
            onClick={() => navigate("/recon/tasks")}
            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            {t("actions.view_all", { ns: "common" })} <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-[12px]">
            <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-8 px-3">ID</th>
                <th className="h-8 px-3">Status</th>
                <th className="h-8 px-3">Configuração</th>
                <th className="h-8 px-3 text-right">Bancárias</th>
                <th className="h-8 px-3 text-right">Contábeis</th>
                <th className="h-8 px-3 text-right">Sugestões</th>
                <th className="h-8 px-3 text-right">Auto</th>
                <th className="h-8 px-3 text-right">Duração</th>
                <th className="h-8 px-3">Iniciado</th>
              </tr>
            </thead>
            <tbody>
              {recentTasks.length === 0 ? (
                <tr>
                  <td className="h-16 px-3 text-center text-muted-foreground" colSpan={9}>
                    {t("tasks.empty")}
                  </td>
                </tr>
              ) : recentTasks.map((task) => {
                // All executions land on /recon/tasks?id= — the merged page
                // shows the suggestions panel for past runs and the live
                // status drawer for in-flight ones.
                const past = task.status === "completed" || task.status === "failed" || task.status === "cancelled"
                const href = `/recon/tasks?id=${task.id}${past ? "" : "&live=1"}`
                return (
                <tr
                  key={task.id}
                  onClick={() => navigate(href)}
                  className="cursor-pointer border-t border-border hover:bg-accent/50"
                >
                  <td className="h-9 px-3 font-mono text-muted-foreground">#{task.id}</td>
                  <td className="h-9 px-3"><StatusBadge status={task.status} /></td>
                  <td className="h-9 px-3 font-medium">{task.config_name ?? task.pipeline_name ?? "—"}</td>
                  <td className="h-9 px-3 text-right tabular-nums">{task.bank_candidates ?? "—"}</td>
                  <td className="h-9 px-3 text-right tabular-nums">{task.journal_candidates ?? "—"}</td>
                  <td className="h-9 px-3 text-right tabular-nums">{task.suggestion_count ?? "—"}</td>
                  <td className="h-9 px-3 text-right tabular-nums">{task.auto_match_applied ?? "—"}</td>
                  <td className="h-9 px-3 text-right tabular-nums text-muted-foreground">{formatDuration(task.duration_seconds ?? null)}</td>
                  <td className="h-9 px-3 text-muted-foreground">{task.created_at ? formatDateTime(task.created_at) : "—"}</td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/**
 * Compact per-account KPI snapshot for the recon dashboard. Pulls
 * the per-account block already attached to ``GET /api/bank_accounts/dashboard-kpis/``
 * (no extra request thanks to React Query dedup with the contas-bancárias
 * page). Sorted by largest "amount remaining" so accounts with the
 * most unreconciled work bubble to the top — that's the natural
 * triage order on this dashboard.
 */
function PerAccountKpiTable() {
  const { t } = useTranslation(["reconciliation", "common"])
  const navigate = useNavigate()
  const { data: kpis, isLoading } = useBankAccountsDashboardKpis()
  const rows = useMemo(() => {
    const accs = kpis?.accounts
    if (!accs || typeof accs !== "object") return []
    const list: Array<{ id: number } & BankAccountRowKpis> = []
    for (const [id, row] of Object.entries(accs)) {
      const idNum = Number(id)
      if (!Number.isFinite(idNum) || !row) continue
      list.push({ id: idNum, ...(row as BankAccountRowKpis) })
    }
    list.sort((a, b) => Number(b.amount_remaining) - Number(a.amount_remaining))
    return list
  }, [kpis])

  if (isLoading) {
    return (
      <div className="card-elevated p-3 text-[12px] text-muted-foreground">
        Carregando contas…
      </div>
    )
  }
  if (rows.length === 0) return null

  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-[13px] font-semibold">{t("dashboard.kpi_per_account_title", "Conciliação por conta")}</h3>
          <p className="text-[11px] text-muted-foreground">
            {t("dashboard.kpi_per_account_subtitle", "Ordenado pelo maior valor pendente")}
          </p>
        </div>
        <button
          onClick={() => navigate("/accounting/bank-accounts")}
          className="text-[11px] text-primary hover:underline"
        >
          ver todas →
        </button>
      </div>
      <table className="w-full text-[12px]">
        <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-8 px-3">Conta</th>
            <th className="h-8 px-3 text-right">Saldo</th>
            <th className="h-8 px-3 text-right">Restante a conciliar</th>
            <th className="h-8 px-3 text-right">% conc. (total)</th>
            <th className="h-8 px-3 text-right">% conc. (30d)</th>
            <th className="h-8 px-3 text-right">Net 30d</th>
            <th className="h-8 px-3 text-right">Burn 3m/mês</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cur = r.currency_code ?? "BRL"
            return (
              <tr
                key={r.id}
                onClick={() => navigate(`/accounting/bank-accounts/${r.id}`)}
                className="cursor-pointer border-t border-border hover:bg-accent/50"
              >
                <td className="h-9 px-3 font-medium">{r.name ?? `Conta #${r.id}`}</td>
                <td className="h-9 px-3 text-right tabular-nums">
                  {formatCurrency(Number(r.current_balance ?? 0), cur)}
                </td>
                <td className="h-9 px-3 text-right tabular-nums">
                  {Number(r.amount_remaining) > 0 ? (
                    <span className="font-medium text-amber-600">
                      {formatCurrency(Number(r.amount_remaining), cur)}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">{formatCurrency(0, cur)}</span>
                  )}
                </td>
                <td className="h-9 px-3 text-right tabular-nums">
                  <ReconRatePill pct={r.reconciliation_rate_pct_lifetime} />
                </td>
                <td className="h-9 px-3 text-right tabular-nums">
                  <ReconRatePill pct={r.reconciliation_rate_pct_window} />
                </td>
                <td className="h-9 px-3 text-right tabular-nums">
                  <SignedNum amount={r.net_window} cur={cur} />
                </td>
                <td className="h-9 px-3 text-right tabular-nums">
                  <BurnNum amount={r.burn_avg_monthly} cur={cur} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ReconRatePill({ pct }: { pct: number }) {
  if (pct == null || pct < 0) return <span className="text-muted-foreground">—</span>
  const color =
    pct >= 90 ? "text-emerald-600" : pct >= 50 ? "text-amber-600" : "text-destructive"
  return <span className={cn("font-medium", color)}>{pct}%</span>
}

function SignedNum({ amount, cur }: { amount: string; cur: string }) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return <span className="text-muted-foreground">—</span>
  if (n === 0) return <span className="text-muted-foreground">{formatCurrency(0, cur)}</span>
  return (
    <span className={n > 0 ? "text-emerald-600" : "text-destructive"}>
      {formatCurrency(n, cur)}
    </span>
  )
}

function BurnNum({ amount, cur }: { amount: string; cur: string }) {
  const n = Number(amount)
  if (!Number.isFinite(n) || n === 0) return <span className="text-muted-foreground">—</span>
  return (
    <span className={n > 0 ? "text-destructive" : "text-emerald-600"}>
      {formatCurrency(Math.abs(n), cur)}
    </span>
  )
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border text-[12px] text-muted-foreground">
      Sem dados de saldos para o período selecionado.
    </div>
  )
}

/**
 * Banner shown when one or more bank accounts in the dashboard window have
 * no leaf GL account linked (`Account.bank_account=ba`). In that state the
 * book daily-balances service returns zero-opening + zero-movement arrays
 * for the affected accounts, which averages down to a ~flat aggregate book
 * line on the chart. The CTA jumps to the bank-accounts list so the user
 * can fix the link in Accounting.
 */
function BookFlatWarning({
  warnings,
  onOpen,
}: {
  warnings: BookDailyWarning[]
  onOpen: () => void
}) {
  const { t } = useTranslation("reconciliation")
  // Resolve bank-account names from the cached list. Falls back to
  // the bare id if the list hasn't loaded yet (no flicker either way
  // because both renders pick up React Query's cached snapshot).
  const { data: accounts = [] } = useBankAccountsList()
  const accountById = new Map(accounts.map((a) => [a.id, a]))
  const labels = warnings.map((w) => {
    const a = accountById.get(w.bank_account_id)
    return a ? a.name : `id ${w.bank_account_id}`
  })
  const preview = labels.slice(0, 6).join(", ") + (labels.length > 6 ? ` (+${labels.length - 6})` : "")
  return (
    <div className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-[12px]">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="font-semibold text-foreground">
          {t("dashboard.book_flat_warning_title")}
        </div>
        <div className="text-muted-foreground">
          {t("dashboard.book_flat_warning_desc", { count: warnings.length })}
        </div>
        <div className="text-[11px] text-muted-foreground/80">
          {preview}
        </div>
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent"
      >
        {t("dashboard.book_flat_warning_cta")} <ArrowRight className="h-3 w-3" />
      </button>
    </div>
  )
}

/**
 * Complementary warning for bank accounts whose linked leaf GL sits in a
 * different currency from the bank account itself. The per-currency
 * aggregation can't reconcile those cleanly — callers should know the book
 * total for that currency may not match reality.
 */
function CurrencyMismatchWarning({
  mismatches,
}: {
  mismatches: BookCurrencyMismatch[]
}) {
  const { t } = useTranslation("reconciliation")
  const ids = mismatches.map((m) => m.bank_account_id)
  const preview = ids.slice(0, 8).join(", ") + (ids.length > 8 ? ` (+${ids.length - 8})` : "")
  return (
    <div className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-[12px]">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="font-semibold text-foreground">
          {t("dashboard.book_currency_mismatch_title")}
        </div>
        <div className="text-muted-foreground">
          {t("dashboard.book_currency_mismatch_desc", { count: mismatches.length })}
        </div>
        <div className="font-mono text-[11px] text-muted-foreground/80">
          {t("dashboard.book_flat_warning_ids", { ids: preview })}
        </div>
      </div>
    </div>
  )
}

/**
 * Page-level period selector. Controls the lookback window for the
 * bank/book balance chart, the transaction-volume chart, and the
 * "X execuções em Nd" KPI hint. Offers 7/14/30/90 days.
 */
function PeriodSwitch({
  value,
  onChange,
}: {
  value: PeriodDays
  onChange: (v: PeriodDays) => void
}) {
  const { t } = useTranslation("reconciliation")
  return (
    <div
      role="tablist"
      aria-label={t("dashboard.period_label")}
      className="inline-flex h-8 shrink-0 items-center rounded-md border border-border bg-background p-0.5 text-[11px]"
    >
      {PERIOD_OPTIONS.map((opt) => {
        const active = opt === value
        return (
          <button
            key={opt}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt)}
            className={cn(
              "inline-flex h-7 min-w-[2.25rem] items-center justify-center rounded px-2 font-medium tabular-nums transition-colors",
              active
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t(`dashboard.period_${opt}d` as const)}
          </button>
        )
      })}
    </div>
  )
}

/**
 * Segmented control to filter the transaction-volume bar chart by
 * reconciliation status. `both` stacks balanced + unbalanced; the other
 * two render only the matching series.
 */
function TxModeSwitch({
  value,
  onChange,
}: {
  value: TxMode
  onChange: (v: TxMode) => void
}) {
  const { t } = useTranslation("reconciliation")
  const options: Array<{ id: TxMode; label: string; dot?: string }> = [
    { id: "both", label: t("dashboard.chart_tx_all") },
    {
      id: "balanced",
      label: t("dashboard.chart_tx_balanced"),
      dot: "hsl(var(--success))",
    },
    {
      id: "unbalanced",
      label: t("dashboard.chart_tx_unbalanced"),
      dot: "hsl(var(--danger))",
    },
  ]
  return (
    <div
      role="tablist"
      aria-label="Filtrar transações"
      className="inline-flex h-7 shrink-0 items-center rounded-md border border-border bg-background p-0.5 text-[11px]"
    >
      {options.map((opt) => {
        const active = opt.id === value
        return (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.id)}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded px-2 font-medium transition-colors",
              active
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {opt.dot && (
              <span
                aria-hidden
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: opt.dot }}
              />
            )}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
