import { useMemo, useEffect, useRef, useState } from "react"
import { Link, Outlet, useSearchParams } from "react-router-dom"
import { FileBarChart, Sparkles, Wallet, Receipt, ListChecks, ChevronLeft, ChevronRight, ChevronDown, Pencil, FileDown } from "lucide-react"
import { toast } from "sonner"
import { DownloadXlsxButton } from "@/components/ui/download-xlsx-button"
import { TabbedShell } from "@/components/layout/TabbedShell"
import {
  useAccount,
  useEntities,
  useFinancialStatements,
} from "@/features/reconciliation"
import {
  CASHFLOW_CATEGORY_LABELS,
  CASHFLOW_SECTION_LABELS,
  CASHFLOW_SECTION_ORDER,
  CASHFLOW_SECTION_SHORT,
} from "@/features/reconciliation/taxonomy_labels"
import { cn, formatCurrency } from "@/lib/utils"
import type {
  FinancialStatementsCategory,
  FinancialStatementsPayload,
} from "@/features/reconciliation/types"
import { useUserRole } from "@/features/auth/useUserRole"
import { DrillableLine } from "./components/DrillableLine"
import { AccountWiringModal } from "./components/AccountWiringModal"
import { JournalEntriesPanel } from "./components/JournalEntriesPanel"

/** Read every shared filter (``include_pending``, ``date_from``,
 *  ``date_to``, ``entity``, ``basis``) from the URL so every tab
 *  consumes the same scope without prop-drilling. ``basis`` only
 *  affects the DRE tab today (Balanço is always anchor + flows; DFC
 *  is intrinsically cash-basis), but it's a global URL param so the
 *  toggle is shareable / bookmarkable. */
function useReportFilters() {
  const [params] = useSearchParams()
  const v = (params.get("include_pending") ?? "").toLowerCase()
  const includePending = v === "1" || v === "true" || v === "yes"
  const date_from = params.get("date_from") || undefined
  const date_to = params.get("date_to") || undefined
  const entityRaw = params.get("entity")
  const entity = entityRaw ? Number(entityRaw) || undefined : undefined
  const basisRaw = (params.get("basis") || "").toLowerCase()
  const basis: "accrual" | "cash" = basisRaw === "cash" ? "cash" : "accrual"
  return { includePending, date_from, date_to, entity, basis }
}

/**
 * The Demonstrativos hub: tabbed shell with the four standard
 * Brazilian financial statements (DRE, Balanço Patrimonial, DFC) plus
 * a "Personalizados" tab that surfaces user-built templates from the
 * existing /reports/build flow.
 *
 * Each standard tab is a pure-frontend computation over the chart of
 * accounts -- it groups leaves by ``effective_category`` and rolls
 * subtree balances. No AI calls, no extra backend endpoints, sub-second
 * once the accounts list is in cache.
 */
export function StandardReportsPage() {
  const [params, setParams] = useSearchParams()
  const { includePending, date_from, date_to, entity, basis } = useReportFilters()
  const { data: entities = [] } = useEntities()

  // Single-place mutator: copy the current params, set/delete one
  // key, replace. ``replace: true`` keeps the back button useful
  // (filter tweaks don't pollute history).
  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const togglePending = () =>
    setFilter("include_pending", includePending ? null : "1")

  // Apply both date_from and date_to atomically (one history entry,
  // one re-render). ``null/null`` clears the range entirely.
  const setDateRange = (from: string | null, to: string | null) => {
    const next = new URLSearchParams(params)
    if (from) next.set("date_from", from); else next.delete("date_from")
    if (to) next.set("date_to", to); else next.delete("date_to")
    setParams(next, { replace: true })
  }

  // Year is inferred from the currently-selected ``date_to`` (or
  // today) so the stepper / quarter chips / month menu all operate
  // on the same year context. Switching year preserves the period
  // type (year → year, quarter → same quarter previous/next year,
  // month → same month previous/next year).
  const yearAnchor = (() => {
    const ref = date_to || date_from
    if (ref) {
      const y = Number(ref.slice(0, 4))
      if (Number.isFinite(y)) return y
    }
    return new Date().getFullYear()
  })()
  const iso = (y: number, m: number, d: number) =>
    `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`
  const monthEnd = (y: number, m: number) => new Date(y, m, 0).getDate()
  const MONTH_ABBR = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

  // Detect what kind of period the active range represents. Drives
  // the active-state highlight on each control AND makes the year
  // arrows preserve period type ("Q1 2026 → ◀ → Q1 2025") instead
  // of always collapsing to "full year".
  const period: "year" | "quarter" | "month" | "custom" | null = (() => {
    if (!date_from || !date_to) return null
    const [fy, fm, fd] = date_from.split("-").map(Number)
    const [ty, tm, td] = date_to.split("-").map(Number)
    if (fy !== ty) return "custom"
    if (fm === 1 && fd === 1 && tm === 12 && td === 31) return "year"
    for (let q = 1; q <= 4; q++) {
      const sm = (q - 1) * 3 + 1
      const em = sm + 2
      if (fm === sm && fd === 1 && tm === em && td === monthEnd(fy, em)) return "quarter"
    }
    if (fm === tm && fd === 1 && td === monthEnd(fy, fm)) return "month"
    return "custom"
  })()
  const activeQuarter =
    period === "quarter" && date_from
      ? Math.floor((Number(date_from.slice(5, 7)) - 1) / 3) + 1
      : null
  const activeMonth =
    period === "month" && date_from ? Number(date_from.slice(5, 7)) : null

  const setYearRange = (y: number) =>
    setDateRange(iso(y, 1, 1), iso(y, 12, 31))
  const setQuarterRange = (y: number, q: number) => {
    const sm = (q - 1) * 3 + 1
    const em = sm + 2
    setDateRange(iso(y, sm, 1), iso(y, em, monthEnd(y, em)))
  }
  const setMonthRange = (y: number, m: number) =>
    setDateRange(iso(y, m, 1), iso(y, m, monthEnd(y, m)))

  const shiftYear = (delta: number) => {
    const ny = yearAnchor + delta
    if (period === "quarter" && activeQuarter) setQuarterRange(ny, activeQuarter)
    else if (period === "month" && activeMonth) setMonthRange(ny, activeMonth)
    else setYearRange(ny)
  }

  // Month menu — controlled popover. Clicking outside or pressing
  // Escape closes it; selecting a month closes it as a side effect.
  const [monthMenuOpen, setMonthMenuOpen] = useState(false)
  const monthMenuRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!monthMenuOpen) return
    const onDoc = (e: MouseEvent) => {
      if (!monthMenuRef.current?.contains(e.target as Node)) setMonthMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMonthMenuOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDoc)
      document.removeEventListener("keydown", onKey)
    }
  }, [monthMenuOpen])

  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Demonstrativos"
        subtitle="DRE · Balanço · DFC · Modelos personalizados"
        actions={
          <div className="flex flex-col items-end gap-1.5">
            <div className="flex flex-wrap items-center gap-1">
              {/* Year stepper: ◀ 2026 ▶. Arrows shift the year while
                  preserving period type — Q1 2026 → ◀ → Q1 2025.
                  Clicking the year text itself selects the full year. */}
              <div className="flex h-6 items-stretch overflow-hidden rounded-md border border-border bg-surface-2 text-[10px]">
                <button
                  type="button"
                  onClick={() => shiftYear(-1)}
                  className="grid w-6 place-items-center text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                  title={`Ano anterior (${yearAnchor - 1})`}
                  aria-label="Ano anterior"
                >
                  <ChevronLeft className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => setYearRange(yearAnchor)}
                  className={cn(
                    "border-x border-border px-2 font-semibold tabular-nums transition-colors",
                    period === "year"
                      ? "bg-primary/10 text-primary"
                      : "text-foreground hover:bg-accent/40",
                  )}
                  title={`Ano todo de ${yearAnchor}`}
                >
                  {yearAnchor}
                </button>
                <button
                  type="button"
                  onClick={() => shiftYear(1)}
                  className="grid w-6 place-items-center text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                  title={`Próximo ano (${yearAnchor + 1})`}
                  aria-label="Próximo ano"
                >
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>

              {/* Quarter chips — operate on the anchor year. */}
              {[1, 2, 3, 4].map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuarterRange(yearAnchor, q)}
                  className={cn(
                    "h-6 rounded-md border px-2 text-[10px] font-medium transition-colors",
                    activeQuarter === q
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                  title={`T${q} de ${yearAnchor}`}
                >
                  T{q}
                </button>
              ))}

              {/* Month dropdown — 12 buttons in a 3×4 grid in the popover. */}
              <div ref={monthMenuRef} className="relative">
                <button
                  type="button"
                  onClick={() => setMonthMenuOpen((v) => !v)}
                  className={cn(
                    "inline-flex h-6 items-center gap-1 rounded-md border px-2 text-[10px] font-medium transition-colors",
                    activeMonth
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                  aria-expanded={monthMenuOpen}
                  aria-haspopup="menu"
                  title="Selecionar mês"
                >
                  {activeMonth ? `${MONTH_ABBR[activeMonth - 1]}/${String(yearAnchor).slice(2)}` : "Mês"}
                  <ChevronDown className="h-3 w-3" />
                </button>
                {monthMenuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 z-20 mt-1 grid w-44 grid-cols-3 gap-1 rounded-md border border-border bg-surface-2 p-1.5 shadow-lg"
                  >
                    {MONTH_ABBR.map((label, i) => {
                      const m = i + 1
                      const active = activeMonth === m
                      return (
                        <button
                          key={label}
                          type="button"
                          onClick={() => {
                            setMonthRange(yearAnchor, m)
                            setMonthMenuOpen(false)
                          }}
                          className={cn(
                            "h-6 rounded-md border text-[10px] font-medium transition-colors",
                            active
                              ? "border-primary/40 bg-primary/10 text-primary"
                              : "border-transparent text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                          )}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              {(date_from || date_to) && (
                <button
                  type="button"
                  onClick={() => setDateRange(null, null)}
                  className="h-6 rounded-md border border-border bg-surface-2 px-2 text-[10px] font-medium text-muted-foreground hover:text-destructive"
                  title="Limpar filtro de data"
                >
                  Limpar
                </button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px]">
                <span className="text-muted-foreground">De</span>
                <input
                  type="date"
                  value={date_from ?? ""}
                  onChange={(e) => setFilter("date_from", e.target.value || null)}
                  className="bg-transparent text-[11px] outline-none [color-scheme:dark]"
                  aria-label="Data inicial"
                />
                <span className="text-muted-foreground">até</span>
                <input
                  type="date"
                  value={date_to ?? ""}
                  onChange={(e) => setFilter("date_to", e.target.value || null)}
                  className="bg-transparent text-[11px] outline-none [color-scheme:dark]"
                  aria-label="Data final"
                />
              </div>
              <select
                value={entity ? String(entity) : ""}
                onChange={(e) => setFilter("entity", e.target.value || null)}
                className="h-7 rounded-md border border-border bg-surface-2 px-2 text-[11px] outline-none"
                aria-label="Entidade"
                title="Filtra os lançamentos pela entidade da transação. Quando selecionado, os saldos âncora (balance) são zerados pois o âncora é por tenant, não por entidade."
              >
                <option value="">Todas as entidades</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
              <label
                className={cn(
                  "inline-flex cursor-pointer select-none items-center gap-2 rounded-md border border-border px-2.5 py-1 text-[11px] transition-colors",
                  includePending
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "bg-surface-2 text-muted-foreground hover:text-foreground",
                )}
                title="Inclui lançamentos em estado 'pending' no saldo de cada conta. Útil para tenants cujos JEs ainda não foram contabilizados (posted)."
              >
                <input
                  type="checkbox"
                  className="h-3 w-3 cursor-pointer accent-primary"
                  checked={includePending}
                  onChange={togglePending}
                />
                Incluir pendentes
              </label>
              {/* Accrual / cash basis toggle. Affects the DRE and the
                  per-account flow shown in the chart of accounts;
                  Balanço is anchor + flows regardless, and DFC is
                  cash by definition. Disabled when no date range is
                  selected because the backend silently falls back to
                  accrual without both bounds. */}
              <div
                role="group"
                aria-label="Regime de competência"
                className={cn(
                  "inline-flex h-6 items-stretch overflow-hidden rounded-md border border-border bg-surface-2 text-[10px]",
                  !(date_from && date_to) && "opacity-50",
                )}
                title={
                  date_from && date_to
                    ? "Competência: data do lançamento. Caixa: data em que o caixa entrou/saiu (perna bancária da transação)."
                    : "Selecione um período para alternar entre regime de competência e caixa"
                }
              >
                <button
                  type="button"
                  onClick={() => setFilter("basis", null)}
                  className={cn(
                    "px-2 font-medium transition-colors",
                    basis === "accrual"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
                  )}
                  disabled={!(date_from && date_to)}
                >
                  Competência
                </button>
                <button
                  type="button"
                  onClick={() => setFilter("basis", "cash")}
                  className={cn(
                    "border-l border-border px-2 font-medium transition-colors",
                    basis === "cash"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
                  )}
                  disabled={!(date_from && date_to)}
                >
                  Caixa
                </button>
              </div>
              <ReportExportButtons
                params={{
                  date_from,
                  date_to,
                  entity,
                  include_pending: includePending ? "1" : undefined,
                  basis,
                }}
              />
            </div>
          </div>
        }
        tabs={[
          { to: "/reports", end: true, label: "DRE", icon: FileBarChart },
          { to: "/reports/balanco", label: "Balanço Patrimonial", icon: Wallet },
          { to: "/reports/dfc", label: "Fluxo de Caixa", icon: Receipt },
          { to: "/reports/custom", label: "Personalizados", icon: Sparkles },
          { to: "/reports/history", label: "Histórico", icon: ListChecks },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}

// ---------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------

// ``summariseByCategory`` was the client-side aggregation that ran
// over the full accounts list to compute the 14 DRE/Balanço buckets.
// Removed in favor of ``useFinancialStatements``, which gets the same
// data already aggregated server-side for ~30KB on the wire instead
// of ~3MB. The same FLOW_CATEGORIES rule (no anchor on income-
// statement categories) lives in
// ``accounting/services/financial_statements.py:FLOW_CATEGORIES``.

function StatementLine({
  label, value, currency, bold, indent, negative,
}: {
  label: string
  value?: number | null
  currency: string
  bold?: boolean
  indent?: number
  negative?: boolean
}) {
  const display = value == null ? "—" : formatCurrency(value, currency)
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-border/40 px-3 py-1.5 text-[12px]",
        bold && "border-b-foreground/30 bg-surface-3 font-semibold",
      )}
      style={{ paddingLeft: 12 + (indent ?? 0) * 16 }}
    >
      <div className="truncate">{label}</div>
      <div
        className={cn(
          "tabular-nums",
          negative && value != null && value !== 0 && "text-destructive",
        )}
      >
        {display}
      </div>
    </div>
  )
}

/** PDF + Excel export buttons. Both consume the URL filters so the
 *  exported file matches what the operator sees on screen.
 *
 *  PDF: client-side via html2pdf, captures the active tab's main
 *  card (each tab marks its container with ``data-statement-card``).
 *  Excel: server-side via ``DownloadXlsxButton`` hitting
 *  ``/api/accounts/financial-statements/?format=xlsx&...``. Backend
 *  ships a 4-sheet workbook (DRE / Balanço / DFC / Memória de
 *  cálculo) with formula-driven subtotals. */
function ReportExportButtons({
  params,
}: {
  params: Record<string, string | number | boolean | undefined | null>
}) {
  const [pdfBusy, setPdfBusy] = useState(false)

  const onPdf = async () => {
    const target = document.querySelector<HTMLElement>("[data-statement-card]")
    if (!target) {
      toast.error("Nada para exportar — abra um demonstrativo primeiro")
      return
    }
    setPdfBusy(true)
    try {
      // Lazy-load html2pdf so it's only fetched when the user actually
      // clicks export. The legacy ReportBuilder page already does
      // this; we keep the same dynamic-import shape so the chunk is
      // shared.
      const mod = await import("html2pdf.js")
      const html2pdf = mod.default
      const tabName = (() => {
        const path = window.location.pathname
        if (path.endsWith("/balanco")) return "balanco"
        if (path.endsWith("/dfc")) return "dfc"
        return "dre"
      })()
      const df = (params.date_from as string) || "inicio"
      const dt = (params.date_to as string) || "fim"
      const filename = `demonstrativo-${tabName}-${df}-${dt}.pdf`
      await html2pdf()
        .from(target)
        .set({
          margin: [10, 10, 10, 10],
          filename,
          image: { type: "jpeg", quality: 0.95 },
          html2canvas: { scale: 2, backgroundColor: "#ffffff" },
          jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
        })
        .save()
    } catch (e) {
      toast.error(
        e instanceof Error ? `Falha ao gerar PDF: ${e.message}` : "Falha ao gerar PDF",
      )
    } finally {
      setPdfBusy(false)
    }
  }

  return (
    <div className="ml-auto flex items-center gap-1">
      <button
        type="button"
        onClick={onPdf}
        disabled={pdfBusy}
        title="Baixar como PDF"
        className={cn(
          "inline-flex h-6 items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground",
          pdfBusy && "opacity-60",
        )}
      >
        <FileDown className="h-3 w-3" />
        {pdfBusy ? "Gerando..." : "PDF"}
      </button>
      <DownloadXlsxButton
        path="/api/accounts/financial-statements/"
        params={{ ...params, format: "xlsx" }}
        label="Excel"
        title="Baixar como Excel (DRE + Balanço + DFC + memória de cálculo)"
        className="h-6 px-2 text-[10px]"
      />
    </div>
  )
}

function StatementSkeleton() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-7 animate-pulse rounded bg-muted/40" />
      ))}
    </div>
  )
}

function NotEnoughDataNotice() {
  return (
    <div className="card-elevated p-4 text-[12px] text-muted-foreground">
      <p className="mb-1 font-medium text-foreground">Sem dados suficientes</p>
      <p>
        As contas ainda não foram categorizadas. Vá ao{" "}
        <Link to="/accounting/accounts" className="text-primary hover:underline">
          Plano de contas
        </Link>{" "}
        para definir <code>report_category</code> nos nós principais (Ativo
        Circulante, Despesas Operacionais, etc.). Os descendentes herdam a
        categoria automaticamente.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: DRE
// ---------------------------------------------------------------------

export function DreTab() {
  const { includePending, date_from, date_to, entity, basis } = useReportFilters()
  const { data, isLoading } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
  })
  const wiring = useAccountWiring()
  const { canWrite } = useUserRole()
  // Gate the "edit account categorization" pencil so the wiring
  // modal entry only appears for operators who can actually save
  // changes. Hides automatically in view-as-viewer preview because
  // ``canWrite`` follows the role overlay.
  const onEditAccount = canWrite ? wiring.open : undefined

  if (isLoading) return <StatementSkeleton />
  if (!data || data.categories.length === 0) return <NotEnoughDataNotice />

  const currency = data.currency
  const byKey = indexCategories(data.categories)

  // Pull the DRE-relevant categories. Server-side sign convention
  // ("positive = balance increased") means credit-natural categories
  // (deducao_receita, receita_financeira) arrive negative when they
  // accumulate debits, and debit-natural categories (custo, despesa_*,
  // imposto) arrive positive when they accumulate debits. The DRE math
  // therefore SUMS credit-natural categories and SUBTRACTS debit-natural
  // ones from the running total. Keep this alignment in sync with
  // ``REPORT_CATEGORY_META[*].sign_hint`` — if a category's sign_hint
  // changes, the corresponding line below changes from + to - or back.
  const get = (k: string) => byKey.get(k)?.amount ?? 0
  const accs = (k: string) => byKey.get(k)?.accounts ?? []
  const receitaBruta = get("receita_bruta")            // credit_natural → +
  const deducoes = get("deducao_receita")              // credit_natural → +
  const receitaLiquida = receitaBruta + deducoes
  const custos = get("custo")                          // debit_natural  → -
  const lucroBruto = receitaLiquida - custos
  const despesasOp = get("despesa_operacional")        // debit_natural  → -
  const ebit = lucroBruto - despesasOp
  const receitaFin = get("receita_financeira")         // credit_natural → +
  const despesaFin = get("despesa_financeira")         // debit_natural  → -
  const outras = get("outras_receitas")                // any → + (Outras
  // Receitas/Despesas is a CPC 26 line in its own right and per Brazilian
  // practice sits inside the Resultado Financeiro grouping; rolling it
  // into resultadoFin keeps the displayed subtotal consistent with what
  // the operator sees nested beneath it).
  const resultadoFin = receitaFin - despesaFin + outras
  const lair = ebit + resultadoFin
  const impostoLucro = get("imposto_sobre_lucro")      // debit_natural  → -
  const lucroLiq = lair - impostoLucro

  const drill = { date_from, date_to, entity, onEditAccount }

  // DRE is single-column; on wide screens it stretches and the labels
  // float far from the values. Cap at ~960px and centre so the line
  // items stay readable while the rest of the page (header strip,
  // tabs) keeps using the full width.
  //
  // ``data-statement-card`` marks this wrapper as the PDF-export
  // target. ``ReportExportButtons`` does ``document.querySelector(
  // "[data-statement-card]")`` — keep at most one of these per tab so
  // the PDF capture is unambiguous.
  return (
    <div data-statement-card className="mx-auto w-full max-w-3xl space-y-2">
      {basis === "cash" && (
        <div className="card-elevated rounded-md border-l-2 border-l-primary/60 px-3 py-2 text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">Regime de caixa.</span>{" "}
          Cada lançamento entra no período conforme a data em que o caixa
          bateu na conta (perna bancária da transação). Transações com pernas
          bancárias em múltiplos períodos são alocadas proporcionalmente ao
          montante que liquidou no intervalo selecionado.
        </div>
      )}
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="flex items-center justify-between border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <div>Linha</div>
          <div className="tabular-nums">{currency}</div>
        </div>
        <DrillableLine label="Receita Bruta" value={receitaBruta} currency={currency} bold accounts={accs("receita_bruta")} {...drill} />
        <DrillableLine label="(-) Deduções da Receita" value={deducoes} currency={currency} indent={1} negative accounts={accs("deducao_receita")} {...drill} />
        <StatementLine label="Receita Líquida" value={receitaLiquida} currency={currency} bold />
        <DrillableLine label="(-) Custos" value={custos} currency={currency} indent={1} negative accounts={accs("custo")} {...drill} />
        <StatementLine label="Lucro Bruto" value={lucroBruto} currency={currency} bold />
        <DrillableLine label="(-) Despesas Operacionais" value={despesasOp} currency={currency} indent={1} negative accounts={accs("despesa_operacional")} {...drill} />
        <StatementLine label="EBIT (Lucro Operacional)" value={ebit} currency={currency} bold />
        <DrillableLine label="(+) Receitas Financeiras" value={receitaFin} currency={currency} indent={1} accounts={accs("receita_financeira")} {...drill} />
        <DrillableLine label="(-) Despesas Financeiras" value={despesaFin} currency={currency} indent={1} negative accounts={accs("despesa_financeira")} {...drill} />
        <DrillableLine label="(+/-) Outras Receitas/Despesas" value={outras} currency={currency} indent={1} accounts={accs("outras_receitas")} {...drill} />
        <StatementLine label="Resultado Financeiro" value={resultadoFin} currency={currency} indent={1} />
        <StatementLine label="LAIR (Lucro antes IR)" value={lair} currency={currency} bold />
        <DrillableLine label="(-) IRPJ + CSLL" value={impostoLucro} currency={currency} indent={1} negative accounts={accs("imposto_sobre_lucro")} {...drill} />
        <StatementLine label="Lucro Líquido do Exercício" value={lucroLiq} currency={currency} bold />
      </div>
      <WiringModalController wiring={wiring} />
    </div>
  )
}

/** Pre-index the category array by key for O(1) lookup. Each entry
 *  carries the parsed amount + the AccountContribution-shaped accounts
 *  list (DrillableLine consumes ``amount`` per row, so we map the
 *  Decimal-string ``amount`` into a number once here). */
function indexCategories(
  categories: FinancialStatementsCategory[],
): Map<string, { amount: number; accounts: Array<{ id: number; name: string; amount: number }> }> {
  const m = new Map<string, { amount: number; accounts: Array<{ id: number; name: string; amount: number }> }>()
  for (const c of categories) {
    m.set(c.key, {
      amount: Number(c.amount) || 0,
      accounts: c.accounts.map((a) => ({
        id: a.id,
        name: a.name,
        amount: Number(a.amount) || 0,
      })),
    })
  }
  return m
}

/** Wiring-modal state owned by each report tab. The modal target is
 *  loaded lazily via ``useAccount(id)`` so the report tab doesn't
 *  have to fetch the full 356-row chart just to support inline edits.
 *  Returns ``isOpen``, ``account`` (null while loading or no target),
 *  ``open(id)`` and ``close()``. */
function useAccountWiring() {
  const [editingId, setEditingId] = useState<number | null>(null)
  return {
    editingId,
    isOpen: editingId != null,
    open: (id: number) => setEditingId(id),
    close: () => setEditingId(null),
  }
}

/** Renders the wiring modal with a lazy single-account fetch. We keep
 *  the modal mounted only when there's a target so the fetch doesn't
 *  fire on every page load. */
function WiringModalController({
  wiring,
}: {
  wiring: ReturnType<typeof useAccountWiring>
}) {
  const { data: account } = useAccount(wiring.editingId)
  return (
    <AccountWiringModal
      account={account ?? null}
      open={wiring.isOpen}
      onClose={wiring.close}
    />
  )
}

// ---------------------------------------------------------------------
// Tab: Balanço Patrimonial
// ---------------------------------------------------------------------

export function BalancoTab() {
  const { includePending, date_from, date_to, entity, basis } = useReportFilters()
  const { data, isLoading } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
  })
  const wiring = useAccountWiring()
  const { canWrite } = useUserRole()
  const onEditAccount = canWrite ? wiring.open : undefined
  if (isLoading) return <StatementSkeleton />
  if (!data || data.categories.length === 0) return <NotEnoughDataNotice />

  const currency = data.currency
  const byKey = indexCategories(data.categories)
  const get = (k: string) => byKey.get(k)?.amount ?? 0
  const accs = (k: string) => byKey.get(k)?.accounts ?? []
  const ativoCirc = get("ativo_circulante")
  const ativoNc = get("ativo_nao_circulante")
  const totalAtivo = ativoCirc + ativoNc
  const passCirc = get("passivo_circulante")
  const passNc = get("passivo_nao_circulante")
  const pl = get("patrimonio_liquido")
  const totalPassivoPl = passCirc + passNc + pl
  const balanced = Math.abs(totalAtivo - totalPassivoPl) < 0.01

  const drill = { date_from, date_to, entity, onEditAccount }

  // ``data-statement-card`` marks the whole grid (Ativo + Passivo + reconciliation
  // banner) as the PDF export target — see ``ReportExportButtons``.
  return (
    <div data-statement-card className="grid gap-4 md:grid-cols-2">
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Ativo
        </div>
        <DrillableLine label="Ativo Circulante" value={ativoCirc} currency={currency} indent={0} accounts={accs("ativo_circulante")} {...drill} />
        <DrillableLine label="Ativo Não Circulante" value={ativoNc} currency={currency} indent={0} accounts={accs("ativo_nao_circulante")} {...drill} />
        <StatementLine label="Total do Ativo" value={totalAtivo} currency={currency} bold />
      </div>
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Passivo + Patrimônio Líquido
        </div>
        <DrillableLine label="Passivo Circulante" value={passCirc} currency={currency} indent={0} accounts={accs("passivo_circulante")} {...drill} />
        <DrillableLine label="Passivo Não Circulante" value={passNc} currency={currency} indent={0} accounts={accs("passivo_nao_circulante")} {...drill} />
        <DrillableLine label="Patrimônio Líquido" value={pl} currency={currency} indent={0} accounts={accs("patrimonio_liquido")} {...drill} />
        <StatementLine label="Total Passivo + PL" value={totalPassivoPl} currency={currency} bold />
      </div>
      <div className={cn(
        "md:col-span-2 rounded-md border p-3 text-[12px]",
        balanced
          ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/5 text-destructive",
      )}>
        {balanced ? (
          <>✓ Balanço fecha: Total Ativo = Total Passivo + PL</>
        ) : (
          <>
            ⚠ Diferença: {formatCurrency(totalAtivo - totalPassivoPl, currency)}.
            Verifique se as contas estão classificadas corretamente.
          </>
        )}
      </div>
      <WiringModalController wiring={wiring} />
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: DFC (Fluxo de Caixa direto)
// ---------------------------------------------------------------------

/** Direct-method DFC tab. Pulls the pre-aggregated payload from the
 *  backend (``GET /api/accounts/financial-statements/``) and renders
 *  FCO / FCI / FCF sections, each broken down by
 *  ``effective_cashflow_category``.
 *
 *  Math is server-side (per-transaction proportional weighting +
 *  taxonomy resolution + sign correction). The frontend just sorts,
 *  groups, formats, and lets the operator drill into the per-account
 *  rows that drove each category. */
export function DfcTab() {
  const { includePending, date_from, date_to, entity, basis } = useReportFilters()
  const { data, isLoading, isError } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
  })
  const wiring = useAccountWiring()
  const { canWrite } = useUserRole()
  const onEditAccount = canWrite ? wiring.open : undefined

  if (!date_from || !date_to) {
    return (
      <div className="card-elevated p-4 text-[12px] text-muted-foreground">
        <p className="mb-1 font-medium text-foreground">Selecione um período</p>
        <p>
          A DFC direta agrega os impactos de caixa por categoria contábil
          dentro de um intervalo. Use os botões de ano / trimestre / mês no
          topo da página para escolher o intervalo desejado.
        </p>
      </div>
    )
  }

  if (isLoading) return <StatementSkeleton />
  if (isError || !data || !data.cashflow) {
    return (
      <div className="card-elevated p-4 text-[12px] text-destructive">
        Falha ao carregar a DFC. Verifique sua conexão e tente novamente.
      </div>
    )
  }

  const currency = data.currency
  const cashTotal = Number(data.cash_total) || 0

  // ``data-statement-card`` marks the whole DFC wrapper (KPI strip +
  // categorised statement) as the PDF export target.
  return (
    <div data-statement-card className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        <KpiCard
          label="Saldo de Caixa (atual)"
          value={cashTotal}
          currency={currency}
          hint="Soma das contas com tag cash / bank_account"
        />
        <KpiCard
          label="Variação líquida no período"
          value={Number(data.cashflow.by_section.net_change_in_cash) || 0}
          currency={currency}
          hint="FCO + FCI + FCF para o intervalo selecionado"
          accent
        />
        <KpiCard
          label="Categorias movidas"
          value={data.cashflow.by_category.length}
          format="int"
          hint="Linhas com fluxo no período"
        />
      </div>

      <CashflowDirectStatement
        payload={data}
        currency={currency}
        date_from={date_from}
        date_to={date_to}
        entity={entity}
        onEditAccount={onEditAccount}
      />
      <WiringModalController wiring={wiring} />
    </div>
  )
}

function KpiCard({
  label,
  value,
  currency,
  hint,
  accent,
  format = "currency",
}: {
  label: string
  value: number
  /** Required when ``format="currency"`` (the default); ignored for
   *  ``format="int"``. We keep it optional so the int-mode card sites
   *  (e.g. "Categorias movidas") don't have to thread a meaningless
   *  currency code just to satisfy the type. */
  currency?: string
  hint?: string
  accent?: boolean
  format?: "currency" | "int"
}) {
  return (
    <div
      className={cn(
        "card-elevated rounded-md p-3",
        accent && "border-l-2 border-l-primary/60",
      )}
    >
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-[20px] font-semibold tabular-nums">
        {format === "currency"
          ? formatCurrency(value, currency ?? "BRL")
          : value.toLocaleString("pt-BR")}
      </div>
      {hint && (
        <div className="mt-1 text-[10px] text-muted-foreground">{hint}</div>
      )}
    </div>
  )
}

/** Render the FCO / FCI / FCF / Não classificadas blocks. Each block
 *  expands to show its constituent categories + per-account rows so
 *  operators can audit which transactions/accounts moved the period
 *  totals. */
function CashflowDirectStatement({
  payload,
  currency,
  date_from,
  date_to,
  entity,
  onEditAccount,
}: {
  payload: FinancialStatementsPayload
  currency: string
  date_from?: string
  date_to?: string
  entity?: number
  onEditAccount?: (id: number) => void
}) {
  const cashflow = payload.cashflow
  if (!cashflow) return null

  // Bucket categories by section, preserving backend order (already
  // sorted: section then absolute amount). Accounts per category come
  // pre-attached by the backend, so no second pass needed.
  const bySection = useMemo(() => {
    const m = new Map<
      string,
      Array<{
        category: string
        amount: number
        account_count: number
        accounts: Array<{ id: number; name: string; amount: number }>
      }>
    >()
    for (const r of cashflow.by_category) {
      const arr = m.get(r.section) ?? []
      arr.push({
        category: r.key,
        amount: Number(r.amount) || 0,
        account_count: r.account_count,
        accounts: r.accounts.map((a) => ({
          id: a.id,
          name: a.name,
          amount: Number(a.amount) || 0,
        })),
      })
      m.set(r.section, arr)
    }
    return m
  }, [cashflow])

  return (
    <div className="card-elevated overflow-hidden text-[12px]">
      <div className="flex items-center justify-between border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div>Atividade</div>
        <div className="tabular-nums">{currency}</div>
      </div>
      {CASHFLOW_SECTION_ORDER.map((section) => {
        const rows = bySection.get(section) ?? []
        if (!rows.length) return null
        const sectionTotal = Number(cashflow.by_section[section]) || 0
        return (
          <CashflowSectionBlock
            key={section}
            sectionCode={section}
            label={CASHFLOW_SECTION_LABELS[section] ?? section}
            short={CASHFLOW_SECTION_SHORT[section] ?? "—"}
            total={sectionTotal}
            currency={currency}
            categories={rows}
            date_from={date_from}
            date_to={date_to}
            entity={entity}
            onEditAccount={onEditAccount}
          />
        )
      })}
      <div className="flex items-center justify-between border-b-2 border-foreground/40 bg-surface-3 px-3 py-2 text-[12px] font-semibold">
        <div>Variação Líquida do Caixa</div>
        <div className="tabular-nums">
          {formatCurrency(Number(cashflow.by_section.net_change_in_cash) || 0, currency)}
        </div>
      </div>
    </div>
  )
}

function CashflowSectionBlock({
  sectionCode,
  label,
  short,
  total,
  currency,
  categories,
  date_from,
  date_to,
  entity,
  onEditAccount,
}: {
  sectionCode: string
  label: string
  short: string
  total: number
  currency: string
  categories: Array<{
    category: string
    amount: number
    account_count: number
    accounts: Array<{ id: number; name: string; amount: number }>
  }>
  date_from?: string
  date_to?: string
  entity?: number
  onEditAccount?: (id: number) => void
}) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())
  const [collapsed, setCollapsed] = useState(false)

  const toggleCat = (cat: string) =>
    setExpandedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })

  return (
    <>
      <div
        className={cn(
          "flex cursor-pointer items-center justify-between border-b border-border bg-surface-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider transition-colors hover:bg-surface-3",
          sectionCode === "no_section"
            ? "text-amber-700 dark:text-amber-400"
            : "text-foreground",
        )}
        onClick={() => setCollapsed((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ChevronDown
            className={cn(
              "h-3 w-3 transition-transform",
              collapsed && "-rotate-90",
            )}
          />
          <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-bold tracking-tighter">
            {short}
          </span>
          <span>{label}</span>
        </div>
        <div className="tabular-nums">{formatCurrency(total, currency)}</div>
      </div>
      {!collapsed &&
        categories.map((c) => {
          const expanded = expandedCats.has(c.category)
          const accounts = c.accounts
          return (
            <div key={c.category}>
              <div
                className={cn(
                  "flex cursor-pointer items-center justify-between border-b border-border/40 px-3 py-1.5 transition-colors hover:bg-accent/30",
                  expanded && "bg-accent/20",
                )}
                style={{ paddingLeft: 28 }}
                onClick={() => toggleCat(c.category)}
              >
                <div className="flex items-center gap-2 truncate">
                  <ChevronDown
                    className={cn(
                      "h-3 w-3 transition-transform text-muted-foreground",
                      !expanded && "-rotate-90",
                    )}
                  />
                  <span className="truncate">
                    {CASHFLOW_CATEGORY_LABELS[c.category]
                      ?? (c.category === "<no_cashflow_category>"
                          ? "Sem categoria DFC"
                          : c.category)}
                  </span>
                  <span className="ml-1 text-[10px] text-muted-foreground">
                    ({c.account_count} {c.account_count === 1 ? "conta" : "contas"})
                  </span>
                </div>
                <div
                  className={cn(
                    "tabular-nums",
                    c.amount < 0 && "text-destructive",
                  )}
                >
                  {formatCurrency(c.amount, currency)}
                </div>
              </div>
              {expanded &&
                accounts.map((a) => (
                  <CashflowAccountRow
                    key={a.id}
                    account={a}
                    currency={currency}
                    date_from={date_from}
                    date_to={date_to}
                    entity={entity}
                    onEdit={onEditAccount}
                  />
                ))}
            </div>
          )
        })}
    </>
  )
}

/** Per-account row inside a DFC category. Identical look to the rest
 *  of the DFC, plus: clicking expands the inline JE drill, hovering
 *  reveals a pencil that opens ``AccountWiringModal``. The DFC's
 *  account-level numbers come pre-aggregated from the backend so the
 *  JE list here is a *secondary* projection: it shows every JE that
 *  hit the account in the period (accrual view), even ones that
 *  didn't touch cash. That's intentional — operators auditing the
 *  DFC almost always also want to see the upstream accrual leg. */
function CashflowAccountRow({
  account,
  currency,
  date_from,
  date_to,
  entity,
  onEdit,
}: {
  account: { id: number; name: string; amount: number }
  currency: string
  date_from?: string
  date_to?: string
  entity?: number
  onEdit?: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <div
        className="group flex cursor-pointer items-center justify-between border-b border-border/30 bg-surface-2/40 px-3 py-1 text-[11px] transition-colors hover:bg-accent/30"
        style={{ paddingLeft: 56 }}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <ChevronDown
            className={cn(
              "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
              !open && "-rotate-90",
            )}
          />
          <span className="truncate text-muted-foreground">{account.name}</span>
          {onEdit && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onEdit(account.id) }}
              className="ml-1 grid h-5 w-5 place-items-center rounded-sm text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100"
              title="Editar categorização"
              aria-label="Editar categorização"
            >
              <Pencil className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className={cn("tabular-nums", account.amount < 0 && "text-destructive")}>
          {formatCurrency(account.amount, currency)}
        </div>
      </div>
      {open && (
        <div className="border-b border-border/30 bg-background/40" style={{ paddingLeft: 72 }}>
          <JournalEntriesPanel
            accountId={account.id}
            date_from={date_from}
            date_to={date_to}
            entity={entity}
            currency={currency}
          />
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------
// Tab: Custom (links to existing builder + history)
// ---------------------------------------------------------------------

export function CustomReportsTab() {
  return (
    <div className="space-y-3">
      <div className="card-elevated p-4 text-[12px]">
        <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
          <Sparkles className="h-4 w-4 text-amber-500" />
          Modelos personalizados
        </div>
        <p className="mb-3 text-muted-foreground">
          Construa um demonstrativo customizado com IA ou manualmente. O
          construtor aceita seletores por <code>report_category</code>,
          <code> tags</code> ou <code>account_ids</code>, e tem suporte para
          fórmulas, subtotais, comparativos por período e exportação.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/reports/build"
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Sparkles className="h-3.5 w-3.5" /> Abrir construtor
          </Link>
          <Link
            to="/reports/history"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            <ListChecks className="h-3.5 w-3.5" /> Histórico
          </Link>
        </div>
      </div>
    </div>
  )
}
