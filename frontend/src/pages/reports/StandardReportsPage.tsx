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
  FinancialStatementsBalanceDiagnostics,
  FinancialStatementsCategory,
  FinancialStatementsPayload,
} from "@/features/reconciliation/types"
import { useUserRole } from "@/features/auth/useUserRole"
import { DrillableLine } from "./components/DrillableLine"
import { AccountWiringModal } from "./components/AccountWiringModal"
import { JournalEntriesPanel } from "./components/JournalEntriesPanel"

type Granularity = "month" | "quarter" | "semester" | "year"
type Compare = "previous_period" | "previous_year"

/** Read every shared filter (``include_pending``, ``date_from``,
 *  ``date_to``, ``entity``, ``basis``, ``granularity``, ``compare``)
 *  from the URL so every tab consumes the same scope without
 *  prop-drilling. ``basis`` only affects the DRE tab today (Balanço
 *  is always anchor + flows; DFC is intrinsically cash-basis), but
 *  it's a global URL param so the toggle is shareable / bookmarkable.
 *
 *  ``granularity`` triggers the per-period column expansion
 *  (server-side ``series=...``); ``compare`` adds a delta column
 *  against ``previous_period`` or ``previous_year``. Both default to
 *  off and degrade silently when the value isn't recognised. */
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
  const granRaw = (params.get("granularity") || "").toLowerCase()
  const granularity: Granularity | undefined =
    granRaw === "month" || granRaw === "quarter" ||
    granRaw === "semester" || granRaw === "year"
      ? granRaw
      : undefined
  const cmpRaw = (params.get("compare") || "").toLowerCase()
  const compare: Compare | undefined =
    cmpRaw === "previous_period" || cmpRaw === "previous_year"
      ? cmpRaw
      : undefined
  return { includePending, date_from, date_to, entity, basis, granularity, compare }
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
  const { includePending, date_from, date_to, entity, basis, granularity, compare } =
    useReportFilters()
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
              {/* Granularity — splits the period into sub-period
                  columns (Mês / Trim. / Sem. / Ano). Disabled without
                  a date range because the backend ignores series in
                  that case. */}
              <select
                value={granularity ?? ""}
                onChange={(e) => setFilter("granularity", e.target.value || null)}
                disabled={!(date_from && date_to)}
                className={cn(
                  "h-7 rounded-md border border-border bg-surface-2 px-2 text-[11px] outline-none disabled:opacity-50",
                  granularity && "border-primary/40 bg-primary/10 text-primary",
                )}
                aria-label="Granularidade"
                title="Quebra o período em sub-períodos (uma coluna por sub-período)."
              >
                <option value="">Total</option>
                <option value="month">Mensal</option>
                <option value="quarter">Trimestral</option>
                <option value="semester">Semestral</option>
                <option value="year">Anual</option>
              </select>
              {/* Comparison — adds a second-window column with Δ% and
                  Δ-abs against the main period. Same disabled-without-
                  range guard as granularity. */}
              <select
                value={compare ?? ""}
                onChange={(e) => setFilter("compare", e.target.value || null)}
                disabled={!(date_from && date_to)}
                className={cn(
                  "h-7 rounded-md border border-border bg-surface-2 px-2 text-[11px] outline-none disabled:opacity-50",
                  compare && "border-primary/40 bg-primary/10 text-primary",
                )}
                aria-label="Comparação"
                title="Compara contra o período anterior (mesma duração) ou contra o mesmo período do ano anterior."
              >
                <option value="">Sem comparação</option>
                <option value="previous_period">vs. Período anterior</option>
                <option value="previous_year">vs. Mesmo período ano anterior</option>
              </select>
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
// DRE / Balanço derived-line helpers (shared by single + multi-column)
// ---------------------------------------------------------------------

/** Per-row spec rendered by both the single-column and multi-column
 *  statements. ``key`` is either a category code (looked up via the
 *  amount getter) or a ``"derived:..."`` synthetic key whose value is
 *  computed from earlier rows. Drill-down is enabled by setting
 *  ``categoryKey`` to a real category code; synthetic rows omit it. */
type RowSpec = {
  label: string
  /** Display flags: bold = subtotal, indent = nesting depth,
   *  negative = render in destructive color when non-zero. */
  bold?: boolean
  indent?: number
  negative?: boolean
  /** Direct lookup against ``getAmount(categoryKey)``. Mutually
   *  exclusive with ``derive``. */
  categoryKey?: string
  /** Synthetic subtotal: receives the running totals so far and
   *  returns this row's amount. Lets the multi-column path stay a
   *  pure function of ``getAmount`` without re-implementing DRE math
   *  per column. */
  derive?: (rows: Record<string, number>) => number
  /** Stable id used to feed ``derive`` for downstream rows. Falls
   *  back to ``categoryKey`` when omitted. */
  id?: string
}

const DRE_ROWS: RowSpec[] = [
  { id: "receita_bruta", label: "Receita Bruta", categoryKey: "receita_bruta", bold: true },
  { id: "deducao_receita", label: "(-) Deduções da Receita", categoryKey: "deducao_receita", indent: 1, negative: true },
  { id: "receita_liquida", label: "Receita Líquida", bold: true,
    derive: (r) => (r.receita_bruta ?? 0) + (r.deducao_receita ?? 0) },
  { id: "custo", label: "(-) Custos", categoryKey: "custo", indent: 1, negative: true },
  { id: "lucro_bruto", label: "Lucro Bruto", bold: true,
    derive: (r) => (r.receita_liquida ?? 0) - (r.custo ?? 0) },
  { id: "despesa_operacional", label: "(-) Despesas Operacionais", categoryKey: "despesa_operacional", indent: 1, negative: true },
  { id: "ebit", label: "EBIT (Lucro Operacional)", bold: true,
    derive: (r) => (r.lucro_bruto ?? 0) - (r.despesa_operacional ?? 0) },
  { id: "receita_financeira", label: "(+) Receitas Financeiras", categoryKey: "receita_financeira", indent: 1 },
  { id: "despesa_financeira", label: "(-) Despesas Financeiras", categoryKey: "despesa_financeira", indent: 1, negative: true },
  { id: "outras_receitas", label: "(+/-) Outras Receitas/Despesas", categoryKey: "outras_receitas", indent: 1 },
  { id: "resultado_financeiro", label: "Resultado Financeiro", indent: 1,
    derive: (r) => (r.receita_financeira ?? 0) - (r.despesa_financeira ?? 0) + (r.outras_receitas ?? 0) },
  { id: "lair", label: "LAIR (Lucro antes IR)", bold: true,
    derive: (r) => (r.ebit ?? 0) + (r.resultado_financeiro ?? 0) },
  { id: "imposto_sobre_lucro", label: "(-) IRPJ + CSLL", categoryKey: "imposto_sobre_lucro", indent: 1, negative: true },
  { id: "lucro_liquido", label: "Lucro Líquido do Exercício", bold: true,
    derive: (r) => (r.lair ?? 0) - (r.imposto_sobre_lucro ?? 0) },
]

const BALANCO_ATIVO_ROWS: RowSpec[] = [
  { id: "ativo_circulante", label: "Ativo Circulante", categoryKey: "ativo_circulante" },
  { id: "ativo_nao_circulante", label: "Ativo Não Circulante", categoryKey: "ativo_nao_circulante" },
  { id: "total_ativo", label: "Total do Ativo", bold: true,
    derive: (r) => (r.ativo_circulante ?? 0) + (r.ativo_nao_circulante ?? 0) },
]

const BALANCO_PASSIVO_ROWS: RowSpec[] = [
  { id: "passivo_circulante", label: "Passivo Circulante", categoryKey: "passivo_circulante" },
  { id: "passivo_nao_circulante", label: "Passivo Não Circulante", categoryKey: "passivo_nao_circulante" },
  { id: "patrimonio_liquido", label: "Patrimônio Líquido", categoryKey: "patrimonio_liquido" },
  { id: "total_passivo_pl", label: "Total Passivo + PL", bold: true,
    derive: (r) => (r.passivo_circulante ?? 0) + (r.passivo_nao_circulante ?? 0) + (r.patrimonio_liquido ?? 0) },
]

/** Walk a list of ``RowSpec``s with a value getter, returning
 *  ``{rowId: amount}``. Synthetic ``derive`` rows feed off earlier
 *  resolved values. */
function resolveRows(
  rows: RowSpec[],
  getAmount: (categoryKey: string) => number,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const row of rows) {
    const id = row.id || row.categoryKey || row.label
    if (row.derive) out[id] = row.derive(out)
    else if (row.categoryKey) out[id] = getAmount(row.categoryKey)
    else out[id] = 0
  }
  return out
}

/** Build a value getter from a totals map (``{cat_key: number}``). */
function makeGetter(totals: Record<string, number>): (k: string) => number {
  return (k) => totals[k] ?? 0
}

/** Convert the main payload's ``categories`` array into a
 *  ``{cat_key: amount}`` totals map so the rest of the pipeline can
 *  treat it the same as a series-period or comparison ``totals``. */
function categoriesToTotals(
  cats: FinancialStatementsCategory[],
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const c of cats) out[c.key] = Number(c.amount) || 0
  return out
}

/** Convert a series/comparison ``totals`` (Decimal-as-string) into a
 *  number map. */
function stringTotalsToNumbers(
  totals: Record<string, string>,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(totals)) out[k] = Number(v) || 0
  return out
}

// ---------------------------------------------------------------------
// Multi-column statement (used by DRE and Balanço when ``series`` or
// ``compare`` is set).
// ---------------------------------------------------------------------

/** One column shown to the right of the row label. */
type StatementColumn = {
  /** Header text (Total, Jan/25, vs. 2024, Δ%). */
  header: string
  /** Resolves the row's value for this column from the row id map.
   *  Returning ``null`` renders an em-dash (used for percentage rows
   *  where the comparison can't be computed). */
  getValue: (resolved: Record<string, number>, rowId: string) => number | null
  /** When set, the cell is rendered as a percentage string; otherwise
   *  as a currency value. */
  asPercent?: boolean
  /** Slimmer column for percentage / delta cells. */
  narrow?: boolean
}

/** Renders a ``RowSpec[]`` with one or more numeric columns. Used when
 *  granularity or comparison is on; the single-column / drill-down
 *  view still owns the no-extras path so DRE row drill-downs keep
 *  working. */
function MultiColumnStatement({
  title,
  rows,
  resolvedColumns,
  currency,
  highlightId,
}: {
  title?: string
  rows: RowSpec[]
  resolvedColumns: Array<{ column: StatementColumn; resolved: Record<string, number> }>
  currency: string
  /** Row id whose row should be highlighted (e.g. ``lucro_liquido``).
   *  Optional, purely cosmetic. */
  highlightId?: string
}) {
  const columns = resolvedColumns.map((c) => c.column)
  const gridCols = `minmax(180px, 1fr) ${columns.map((c) => (c.narrow ? "80px" : "120px")).join(" ")}`
  return (
    <div className="card-elevated overflow-x-auto text-[12px]">
      {title && (
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </div>
      )}
      <div
        className="grid border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
        style={{ gridTemplateColumns: gridCols }}
      >
        <div>Linha</div>
        {columns.map((c, i) => (
          <div key={i} className="text-right tabular-nums">{c.header}</div>
        ))}
      </div>
      {rows.map((row) => {
        const id = row.id || row.categoryKey || row.label
        const isHighlight = highlightId === id
        return (
          <div
            key={id}
            className={cn(
              "grid items-center border-b border-border/40 px-3 py-1.5",
              row.bold && "border-b-foreground/30 bg-surface-3 font-semibold",
              isHighlight && "bg-primary/5",
            )}
            style={{
              gridTemplateColumns: gridCols,
              paddingLeft: 12 + (row.indent ?? 0) * 16,
            }}
          >
            <div className="truncate">{row.label}</div>
            {resolvedColumns.map((rc, i) => {
              const v = rc.column.getValue(rc.resolved, id)
              const display =
                v == null
                  ? "—"
                  : rc.column.asPercent
                  ? v === 0 ? "0,0%" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`
                  : formatCurrency(v, currency)
              return (
                <div
                  key={i}
                  className={cn(
                    "text-right tabular-nums",
                    row.negative && v != null && v !== 0 && !rc.column.asPercent && "text-destructive",
                    rc.column.asPercent && v != null && v < 0 && "text-destructive",
                    rc.column.asPercent && v != null && v > 0 && "text-emerald-600 dark:text-emerald-400",
                  )}
                >
                  {display}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

/** Build the column list for a statement. Order: per-period series
 *  columns (when ``series`` is set), then "Total", then comparison +
 *  Δ% (when ``compare`` is set). When neither is set, returns just
 *  "Total" so the multi-column shape can still be used. */
function buildColumns({
  rows,
  data,
  mainTotals,
}: {
  rows: RowSpec[]
  data: FinancialStatementsPayload
  /** Pre-resolved totals map for the main window — drives the "Total"
   *  column. */
  mainTotals: Record<string, number>
}): Array<{ column: StatementColumn; resolved: Record<string, number> }> {
  const out: Array<{ column: StatementColumn; resolved: Record<string, number> }> = []

  if (data.series) {
    for (const p of data.series.periods) {
      const totals = stringTotalsToNumbers(p.totals)
      const resolved = resolveRows(rows, makeGetter(totals))
      out.push({
        column: {
          header: p.label,
          getValue: (r, id) => r[id] ?? 0,
        },
        resolved,
      })
    }
  }

  // Always show the Total column for the requested window.
  const mainResolved = resolveRows(rows, makeGetter(mainTotals))
  out.push({
    column: {
      header: "Total",
      getValue: (r, id) => r[id] ?? 0,
    },
    resolved: mainResolved,
  })

  if (data.comparison) {
    const cmpTotals = stringTotalsToNumbers(data.comparison.totals)
    const cmpResolved = resolveRows(rows, makeGetter(cmpTotals))
    const shortLabel =
      data.comparison.type === "previous_year" ? "Ano anterior" : "Período anterior"
    out.push({
      column: {
        header: shortLabel,
        getValue: (r, id) => r[id] ?? 0,
      },
      resolved: cmpResolved,
    })
    // Δ% column shares the row spec but synthesises a percentage from
    // the main vs comparison resolved maps. Keep it ``narrow`` so the
    // grid stays compact.
    out.push({
      column: {
        header: "Δ%",
        narrow: true,
        asPercent: true,
        getValue: (_r, id) => {
          const cur = mainResolved[id] ?? 0
          const prev = cmpResolved[id] ?? 0
          if (prev === 0) return null
          return ((cur - prev) / Math.abs(prev)) * 100
        },
      },
      resolved: {},
    })
  }

  return out
}

// ---------------------------------------------------------------------
// Tab: DRE
// ---------------------------------------------------------------------

export function DreTab() {
  const { includePending, date_from, date_to, entity, basis, granularity, compare } =
    useReportFilters()
  const { data, isLoading } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
    series: granularity,
    compare,
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

  // Server-side sign convention: "positive = balance increased" means
  // credit-natural categories (deducao_receita, receita_financeira)
  // arrive negative when they accumulate debits, debit-natural ones
  // arrive positive when they accumulate debits. The DRE math therefore
  // SUMS credit-natural categories and SUBTRACTS debit-natural ones.
  // See ``DRE_ROWS`` for the full pipeline; both paths (single-column
  // drill-down and multi-column series/compare) feed off the same
  // RowSpec array so the math can't drift.
  const accs = (k: string) => byKey.get(k)?.accounts ?? []
  // ``split(k)`` exposes the optional reconciled / unreconciled
  // breakdown the backend emits when ``include_pending`` is on. When
  // the category lacks a split, ``DrillableLine`` falls back to the
  // single-amount rendering it has always done.
  const split = (k: string) => {
    const b = byKey.get(k)
    return b && b.reconciled != null
      ? { reconciled: b.reconciled, unreconciled: b.unreconciled ?? 0 }
      : undefined
  }
  // ``basis`` flows through so the per-account JE drill panel knows
  // whether to show the cash-basis effective-date column (which date
  // drove inclusion: bank tx vs JE date).
  const drill = { date_from, date_to, entity, onEditAccount, basis }
  const showMultiColumn = !!(data.series || data.comparison)

  // Multi-column path — used whenever granularity or comparison is on.
  // Drops the per-row drill-down (no per-period accounts list on the
  // wire); the operator can clear the granularity to fall back to the
  // detail view. Shows a notice strip explaining the trade-off.
  if (showMultiColumn) {
    const mainTotals = categoriesToTotals(data.categories)
    const resolvedColumns = buildColumns({
      rows: DRE_ROWS,
      data,
      mainTotals,
    })
    return (
      <div data-statement-card className="mx-auto w-full max-w-6xl space-y-2">
        {basis === "cash" && (
          <div className="card-elevated rounded-md border-l-2 border-l-primary/60 px-3 py-2 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground">Regime de caixa.</span>{" "}
            Cada lançamento entra no período conforme a data em que o caixa
            bateu na conta. Transações com pernas bancárias em múltiplos
            períodos são alocadas proporcionalmente.
          </div>
        )}
        <ComparisonHeaderStrip data={data} />
        <MultiColumnStatement
          rows={DRE_ROWS}
          resolvedColumns={resolvedColumns}
          currency={currency}
          highlightId="lucro_liquido"
        />
        {data.series?.truncated && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
            Faixa muito longa para a granularidade escolhida — exibindo apenas os primeiros
            sub-períodos. Reduza o intervalo ou aumente a granularidade.
          </div>
        )}
      </div>
    )
  }

  // Single-column path — preserves the existing detail drill-down with
  // per-row account lists, JE drill panel, etc. This is the default
  // when neither series nor comparison is requested.
  const get = (k: string) => byKey.get(k)?.amount ?? 0
  const receitaBruta = get("receita_bruta")
  const deducoes = get("deducao_receita")
  const receitaLiquida = receitaBruta + deducoes
  const custos = get("custo")
  const lucroBruto = receitaLiquida - custos
  const despesasOp = get("despesa_operacional")
  const ebit = lucroBruto - despesasOp
  const receitaFin = get("receita_financeira")
  const despesaFin = get("despesa_financeira")
  const outras = get("outras_receitas")
  const resultadoFin = receitaFin - despesaFin + outras
  const lair = ebit + resultadoFin
  const impostoLucro = get("imposto_sobre_lucro")
  const lucroLiq = lair - impostoLucro

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
        <DrillableLine label="Receita Bruta" value={receitaBruta} currency={currency} bold accounts={accs("receita_bruta")} split={split("receita_bruta")} {...drill} />
        <DrillableLine label="(-) Deduções da Receita" value={deducoes} currency={currency} indent={1} negative accounts={accs("deducao_receita")} split={split("deducao_receita")} {...drill} />
        <StatementLine label="Receita Líquida" value={receitaLiquida} currency={currency} bold />
        <DrillableLine label="(-) Custos" value={custos} currency={currency} indent={1} negative accounts={accs("custo")} split={split("custo")} {...drill} />
        <StatementLine label="Lucro Bruto" value={lucroBruto} currency={currency} bold />
        <DrillableLine label="(-) Despesas Operacionais" value={despesasOp} currency={currency} indent={1} negative accounts={accs("despesa_operacional")} split={split("despesa_operacional")} {...drill} />
        <StatementLine label="EBIT (Lucro Operacional)" value={ebit} currency={currency} bold />
        <DrillableLine label="(+) Receitas Financeiras" value={receitaFin} currency={currency} indent={1} accounts={accs("receita_financeira")} split={split("receita_financeira")} {...drill} />
        <DrillableLine label="(-) Despesas Financeiras" value={despesaFin} currency={currency} indent={1} negative accounts={accs("despesa_financeira")} split={split("despesa_financeira")} {...drill} />
        <DrillableLine label="(+/-) Outras Receitas/Despesas" value={outras} currency={currency} indent={1} accounts={accs("outras_receitas")} split={split("outras_receitas")} {...drill} />
        <StatementLine label="Resultado Financeiro" value={resultadoFin} currency={currency} indent={1} />
        <StatementLine label="LAIR (Lucro antes IR)" value={lair} currency={currency} bold />
        <DrillableLine label="(-) IRPJ + CSLL" value={impostoLucro} currency={currency} indent={1} negative accounts={accs("imposto_sobre_lucro")} split={split("imposto_sobre_lucro")} {...drill} />
        <StatementLine label="Lucro Líquido do Exercício" value={lucroLiq} currency={currency} bold />
      </div>
      <WiringModalController wiring={wiring} />
    </div>
  )
}

/** Tiny header strip that surfaces the comparison window's actual
 *  date range (so the operator knows what "vs. Período anterior"
 *  resolved to). Renders nothing when no comparison is active. */
function ComparisonHeaderStrip({ data }: { data: FinancialStatementsPayload }) {
  if (!data.comparison) return null
  return (
    <div className="card-elevated rounded-md border-l-2 border-l-primary/40 px-3 py-2 text-[11px] text-muted-foreground">
      <span className="font-medium text-foreground">Comparação:</span>{" "}
      {data.comparison.label} · {data.comparison.period.date_from} a{" "}
      {data.comparison.period.date_to}
    </div>
  )
}

/** Pre-index the category array by key for O(1) lookup. Each entry
 *  carries the parsed amount + the AccountContribution-shaped accounts
 *  list (DrillableLine consumes ``amount`` per row, so we map the
 *  Decimal-string ``amount`` into a number once here). */
function indexCategories(
  categories: FinancialStatementsCategory[],
): Map<string, { amount: number; reconciled?: number; unreconciled?: number; accounts: Array<{ id: number; name: string; amount: number; synthetic?: boolean }> }> {
  const m = new Map<string, { amount: number; reconciled?: number; unreconciled?: number; accounts: Array<{ id: number; name: string; amount: number; synthetic?: boolean }> }>()
  for (const c of categories) {
    m.set(c.key, {
      amount: Number(c.amount) || 0,
      // Reconciled split surfaces only when the backend chose to emit
      // it (today: ``include_pending=true`` + FLOW_CATEGORIES). When
      // absent, the row renders the single total as before.
      ...(c.amount_reconciled != null ? { reconciled: Number(c.amount_reconciled) || 0 } : {}),
      ...(c.amount_unreconciled != null ? { unreconciled: Number(c.amount_unreconciled) || 0 } : {}),
      // Pass the ``synthetic`` flag through unchanged. DrillableLine /
      // AccountDrillRow keys on it to suppress the chevron, hide the
      // pencil, and skip the JE drill for entries like the
      // "Resultado do Exercício (período)" line that the backend
      // injects into ``patrimonio_liquido``.
      accounts: c.accounts.map((a) => ({
        id: a.id,
        name: a.name,
        amount: Number(a.amount) || 0,
        ...(a.synthetic ? { synthetic: true } : {}),
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
// Balanço imbalance diagnostics panel
// ---------------------------------------------------------------------

/** Replaces the bare "⚠ Diferença: R$ X" banner with a guided panel
 *  that explains *why* the books don't close and offers a concrete
 *  next step for each cause. The backend computes the breakdown
 *  (anchor gap, uncategorized leaves, wrong-direction PL accounts)
 *  in ``balance_diagnostics``; we just frame the narrative.
 *
 *  ``onEditAccount`` is the same callback the rest of the Balanço
 *  uses to open ``AccountWiringModal`` — clicking an uncategorized
 *  leaf or a wrong-direction account jumps the operator straight to
 *  the fix surface. Hidden in view-as-viewer mode (``onEditAccount``
 *  comes back ``undefined`` from ``canWrite``). */
function BalanceDiagnosticsPanel({
  diagnostics,
  currency,
  onEditAccount,
}: {
  diagnostics: FinancialStatementsBalanceDiagnostics
  currency: string
  onEditAccount?: (id: number) => void
}) {
  const imbalance = Number(diagnostics.imbalance) || 0
  const anchorGap = Number(diagnostics.anchor_gap.delta) || 0
  const uncatTotal = Number(diagnostics.uncategorized_total_impact) || 0
  const synthLucro = Number(diagnostics.synthetic_lucro) || 0
  const ativoAnchor = Number(diagnostics.anchor_gap.ativo_anchor) || 0
  const pasPlAnchor = Number(diagnostics.anchor_gap.pas_pl_anchor) || 0

  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive md:col-span-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="font-semibold">⚠ Balanço não fecha</div>
        <div className="tabular-nums">
          Diferença: {formatCurrency(imbalance, currency)}
        </div>
      </div>

      <p className="mb-3 text-foreground/80">
        A diferença abaixo decompõe a causa em itens acionáveis.
        Resolver cada item aproxima o Total do Ativo do Total do Passivo + PL.
      </p>

      {/* 1) Anchor gap — informational. Operator action is bookkeeping
          (recompute opening balances), not a wiring-modal click. */}
      {Math.abs(anchorGap) >= 0.01 && (
        <DiagSection
          title="Saldos iniciais não recordados no lado do Passivo + PL"
          intent="info"
          impact={anchorGap}
          currency={currency}
        >
          <p>
            O <code>balance</code> está preenchido nas folhas do Ativo
            (Σ {formatCurrency(ativoAnchor, currency)}) mas as folhas
            do Passivo + PL somam {formatCurrency(pasPlAnchor, currency)}.
            Saldos iniciais (Capital Social, Lucros Acumulados, Empréstimos,
            etc.) precisam ser registrados no <code>Account.balance</code>{" "}
            das contas correspondentes — esse é trabalho contábil, não
            uma correção de classificação.
          </p>
          <p className="mt-1 opacity-80">
            Caminho típico: Plano de Contas → conta de PL → editar saldo
            inicial em <code>balance_date</code>.
          </p>
        </DiagSection>
      )}

      {/* 2) Uncategorized leaves — each is a one-click fix. */}
      {diagnostics.uncategorized_leaves.length > 0 && (
        <DiagSection
          title={`Contas folha sem categoria (${diagnostics.uncategorized_leaves.length})`}
          intent="action"
          impact={uncatTotal}
          currency={currency}
          subtitle="Lançamentos hit estas contas mas elas não têm report_category, então não aparecem no Balanço. Clique para definir."
        >
          <div className="overflow-hidden rounded border border-destructive/20 bg-background/60">
            {diagnostics.uncategorized_leaves.map((u) => {
              const impact = Number(u.impact) || 0
              return (
                <button
                  key={u.id}
                  type="button"
                  onClick={onEditAccount ? () => onEditAccount(u.id) : undefined}
                  disabled={!onEditAccount}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 border-b border-border/40 px-2.5 py-1.5 text-left text-[11px] transition-colors last:border-b-0",
                    onEditAccount
                      ? "cursor-pointer hover:bg-accent/30"
                      : "cursor-default opacity-80",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-foreground">{u.name}</div>
                    {u.suggested_label && (
                      <div className="text-[10px] text-muted-foreground">
                        Sugestão: <span className="font-medium">{u.suggested_label}</span>
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="tabular-nums text-foreground">
                      {formatCurrency(impact, currency)}
                    </div>
                    <div className="text-[10px] text-muted-foreground">impacto</div>
                  </div>
                </button>
              )
            })}
          </div>
        </DiagSection>
      )}

      {/* 3) Wrong-direction Passivo/PL leaves. */}
      {diagnostics.wrong_direction_accounts.length > 0 && (
        <DiagSection
          title={`Direção provavelmente invertida (${diagnostics.wrong_direction_accounts.length})`}
          intent="action"
          subtitle="Contas em Passivo / PL devem ser credit-natural (account_direction = -1). Estas estão como +1; o sinal do agregado pode estar invertido."
        >
          <div className="overflow-hidden rounded border border-destructive/20 bg-background/60">
            {diagnostics.wrong_direction_accounts.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={onEditAccount ? () => onEditAccount(w.id) : undefined}
                disabled={!onEditAccount}
                className={cn(
                  "flex w-full items-center justify-between gap-3 border-b border-border/40 px-2.5 py-1.5 text-left text-[11px] transition-colors last:border-b-0",
                  onEditAccount
                    ? "cursor-pointer hover:bg-accent/30"
                    : "cursor-default opacity-80",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-foreground">{w.name}</div>
                  <div className="text-[10px] text-muted-foreground">
                    Categoria: {w.current_category} · Direção atual: +1 · Sugerido: −1
                  </div>
                </div>
              </button>
            ))}
          </div>
        </DiagSection>
      )}

      {/* Footnote: synthetic Resultado do Exercício explanation. */}
      {Math.abs(synthLucro) >= 0.01 && (
        <p className="mt-3 text-[10px] text-muted-foreground">
          Nota: o Patrimônio Líquido inclui {formatCurrency(synthLucro, currency)} de{" "}
          <em>Resultado do Exercício (período)</em>, uma linha sintética
          que reflete o resultado da DRE no período. Sem ela, o
          desbalanço seria ainda maior antes de qualquer correção
          listada acima.
        </p>
      )}
    </div>
  )
}

/** Section block inside ``BalanceDiagnosticsPanel`` — a labeled
 *  group with optional impact value. ``intent`` shifts the badge
 *  color (info = subtle, action = stronger). */
function DiagSection({
  title,
  subtitle,
  impact,
  currency,
  intent,
  children,
}: {
  title: string
  subtitle?: string
  impact?: number
  currency?: string
  intent: "info" | "action"
  children: React.ReactNode
}) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
              intent === "info"
                ? "bg-muted text-muted-foreground"
                : "bg-destructive/20 text-destructive",
            )}
          >
            {intent === "info" ? "Contábil" : "Ação"}
          </span>
          <span className="font-semibold text-foreground">{title}</span>
        </div>
        {impact != null && currency && (
          <span className="tabular-nums text-foreground/80">
            {formatCurrency(impact, currency)}
          </span>
        )}
      </div>
      {subtitle && (
        <p className="mb-1.5 text-[11px] text-muted-foreground">{subtitle}</p>
      )}
      <div className="text-[11px]">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: Balanço Patrimonial
// ---------------------------------------------------------------------

export function BalancoTab() {
  const { includePending, date_from, date_to, entity, basis, granularity, compare } =
    useReportFilters()
  const { data, isLoading } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
    series: granularity,
    compare,
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
  // ``split(k)`` exposes the optional reconciled / unreconciled
  // breakdown the backend emits when ``include_pending`` is on. When
  // the category lacks a split, ``DrillableLine`` falls back to the
  // single-amount rendering it has always done.
  const split = (k: string) => {
    const b = byKey.get(k)
    return b && b.reconciled != null
      ? { reconciled: b.reconciled, unreconciled: b.unreconciled ?? 0 }
      : undefined
  }
  // ``basis`` flows through so the per-account JE drill panel knows
  // whether to show the cash-basis effective-date column (which date
  // drove inclusion: bank tx vs JE date).
  const drill = { date_from, date_to, entity, onEditAccount, basis }
  const showMultiColumn = !!(data.series || data.comparison)

  // Multi-column path — Ativo and Passivo+PL are rendered as two
  // separate ``MultiColumnStatement`` cards stacked, each with its
  // own per-period columns. The balance-check banner uses the main
  // column totals so it still validates the active period.
  if (showMultiColumn) {
    const mainTotals = categoriesToTotals(data.categories)
    const ativoCols = buildColumns({ rows: BALANCO_ATIVO_ROWS, data, mainTotals })
    const passivoCols = buildColumns({ rows: BALANCO_PASSIVO_ROWS, data, mainTotals })
    const totalAtivoMain = (ativoCols[ativoCols.length - (data.comparison ? 3 : 1)]
      ?.resolved.total_ativo) ?? 0
    const totalPassivoMain = (passivoCols[passivoCols.length - (data.comparison ? 3 : 1)]
      ?.resolved.total_passivo_pl) ?? 0
    const balanced = Math.abs(totalAtivoMain - totalPassivoMain) < 0.01
    return (
      <div data-statement-card className="mx-auto w-full max-w-6xl space-y-3">
        <ComparisonHeaderStrip data={data} />
        <MultiColumnStatement
          title="Ativo"
          rows={BALANCO_ATIVO_ROWS}
          resolvedColumns={ativoCols}
          currency={currency}
          highlightId="total_ativo"
        />
        <MultiColumnStatement
          title="Passivo + Patrimônio Líquido"
          rows={BALANCO_PASSIVO_ROWS}
          resolvedColumns={passivoCols}
          currency={currency}
          highlightId="total_passivo_pl"
        />
        {balanced ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-[12px] text-emerald-700 dark:text-emerald-400">
            ✓ Balanço fecha (período principal): Total Ativo = Total Passivo + PL
          </div>
        ) : data.balance_diagnostics ? (
          <BalanceDiagnosticsPanel
            diagnostics={data.balance_diagnostics}
            currency={currency}
            onEditAccount={onEditAccount}
          />
        ) : (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive">
            ⚠ Diferença no período principal:{" "}
            {formatCurrency(totalAtivoMain - totalPassivoMain, currency)}.
          </div>
        )}
        {data.series?.truncated && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
            Faixa muito longa para a granularidade escolhida — exibindo apenas os primeiros sub-períodos.
          </div>
        )}
        <WiringModalController wiring={wiring} />
      </div>
    )
  }

  // Single-column path with full drill-down (default).
  const ativoCirc = get("ativo_circulante")
  const ativoNc = get("ativo_nao_circulante")
  const totalAtivo = ativoCirc + ativoNc
  const passCirc = get("passivo_circulante")
  const passNc = get("passivo_nao_circulante")
  const pl = get("patrimonio_liquido")
  const totalPassivoPl = passCirc + passNc + pl
  const balanced = Math.abs(totalAtivo - totalPassivoPl) < 0.01

  return (
    <div data-statement-card className="grid gap-4 md:grid-cols-2">
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Ativo
        </div>
        <DrillableLine label="Ativo Circulante" value={ativoCirc} currency={currency} indent={0} accounts={accs("ativo_circulante")} split={split("ativo_circulante")} {...drill} />
        <DrillableLine label="Ativo Não Circulante" value={ativoNc} currency={currency} indent={0} accounts={accs("ativo_nao_circulante")} split={split("ativo_nao_circulante")} {...drill} />
        <StatementLine label="Total do Ativo" value={totalAtivo} currency={currency} bold />
      </div>
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Passivo + Patrimônio Líquido
        </div>
        <DrillableLine label="Passivo Circulante" value={passCirc} currency={currency} indent={0} accounts={accs("passivo_circulante")} split={split("passivo_circulante")} {...drill} />
        <DrillableLine label="Passivo Não Circulante" value={passNc} currency={currency} indent={0} accounts={accs("passivo_nao_circulante")} split={split("passivo_nao_circulante")} {...drill} />
        <DrillableLine label="Patrimônio Líquido" value={pl} currency={currency} indent={0} accounts={accs("patrimonio_liquido")} split={split("patrimonio_liquido")} {...drill} />
        <StatementLine label="Total Passivo + PL" value={totalPassivoPl} currency={currency} bold />
      </div>
      {balanced ? (
        <div className="md:col-span-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-[12px] text-emerald-700 dark:text-emerald-400">
          ✓ Balanço fecha: Total Ativo = Total Passivo + PL
        </div>
      ) : data.balance_diagnostics ? (
        <BalanceDiagnosticsPanel
          diagnostics={data.balance_diagnostics}
          currency={currency}
          onEditAccount={onEditAccount}
        />
      ) : (
        <div className="md:col-span-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive">
          ⚠ Diferença: {formatCurrency(totalAtivo - totalPassivoPl, currency)}.
          Verifique se as contas estão classificadas corretamente.
        </div>
      )}
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
  const { includePending, date_from, date_to, entity, basis, granularity, compare } =
    useReportFilters()
  const { data, isLoading, isError } = useFinancialStatements({
    include_pending: includePending,
    date_from,
    date_to,
    entity,
    basis,
    series: granularity,
    compare,
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
  const showMultiColumn = !!(data.series || data.comparison)

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

      <ComparisonHeaderStrip data={data} />

      {showMultiColumn ? (
        <CashflowSectionMatrix data={data} currency={currency} />
      ) : (
        <CashflowDirectStatement
          payload={data}
          currency={currency}
          date_from={date_from}
          date_to={date_to}
          entity={entity}
          onEditAccount={onEditAccount}
        />
      )}
      {data.series?.truncated && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
          Faixa muito longa para a granularidade escolhida — exibindo apenas os primeiros sub-períodos.
        </div>
      )}
      <WiringModalController wiring={wiring} />
    </div>
  )
}

/** DFC matrix view used when granularity or comparison is on. Rows
 *  are the four section totals (FCO / FCI / FCF / Não classificadas)
 *  plus "Variação líquida"; columns are the per-period totals plus
 *  the main-window total plus optional comparison + Δ%. Drops the
 *  per-category drill-down which the single-column view owns — the
 *  user can clear granularity to fall back to the detail layout. */
function CashflowSectionMatrix({
  data,
  currency,
}: {
  data: FinancialStatementsPayload
  currency: string
}) {
  if (!data.cashflow) return null

  const sectionRows: RowSpec[] = [
    { id: "operacional", label: CASHFLOW_SECTION_LABELS.operacional ?? "Operacional", categoryKey: "operacional" },
    { id: "investimento", label: CASHFLOW_SECTION_LABELS.investimento ?? "Investimento", categoryKey: "investimento" },
    { id: "financiamento", label: CASHFLOW_SECTION_LABELS.financiamento ?? "Financiamento", categoryKey: "financiamento" },
    { id: "no_section", label: "Não classificadas", categoryKey: "no_section" },
    { id: "net_change_in_cash", label: "Variação Líquida do Caixa", bold: true,
      derive: (r) => (r.operacional ?? 0) + (r.investimento ?? 0) + (r.financiamento ?? 0) + (r.no_section ?? 0) },
  ]

  // The DFC matrix doesn't go through ``buildColumns`` because its
  // value source is ``cashflow_totals`` (per period) and
  // ``cashflow.by_section`` (main), not ``categories`` /
  // ``totals``. So we resolve columns manually with the same
  // shape the rest of the multi-column layer expects.
  const columns: Array<{ column: StatementColumn; resolved: Record<string, number> }> = []

  if (data.series) {
    for (const p of data.series.periods) {
      const totals = stringTotalsToNumbers(p.cashflow_totals ?? {})
      const resolved = resolveRows(sectionRows, makeGetter(totals))
      columns.push({
        column: { header: p.label, getValue: (r, id) => r[id] ?? 0 },
        resolved,
      })
    }
  }

  const mainTotals = stringTotalsToNumbers(data.cashflow.by_section)
  const mainResolved = resolveRows(sectionRows, makeGetter(mainTotals))
  columns.push({
    column: { header: "Total", getValue: (r, id) => r[id] ?? 0 },
    resolved: mainResolved,
  })

  if (data.comparison) {
    const cmpTotals = stringTotalsToNumbers(data.comparison.cashflow_totals ?? {})
    const cmpResolved = resolveRows(sectionRows, makeGetter(cmpTotals))
    const shortLabel =
      data.comparison.type === "previous_year" ? "Ano anterior" : "Período anterior"
    columns.push({
      column: { header: shortLabel, getValue: (r, id) => r[id] ?? 0 },
      resolved: cmpResolved,
    })
    columns.push({
      column: {
        header: "Δ%",
        narrow: true,
        asPercent: true,
        getValue: (_r, id) => {
          const cur = mainResolved[id] ?? 0
          const prev = cmpResolved[id] ?? 0
          if (prev === 0) return null
          return ((cur - prev) / Math.abs(prev)) * 100
        },
      },
      resolved: {},
    })
  }

  return (
    <MultiColumnStatement
      title="Atividades"
      rows={sectionRows}
      resolvedColumns={columns}
      currency={currency}
      highlightId="net_change_in_cash"
    />
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
