import { useMemo, useState } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Link2, Link2Off, Search } from "lucide-react"
import { Link } from "react-router-dom"
import { useJournalEntriesDrill } from "@/features/reconciliation"
import { cn, formatCurrency } from "@/lib/utils"

/**
 * Inline JE drill for a single chart-of-accounts account scoped to the
 * report's active period. Used by the Demonstrativos page when an
 * operator expands a leaf account row to audit which journal entries
 * make up that account's contribution.
 *
 * Why a panel and not a drawer:
 *   * Lets operators read the JE list in context next to the totals
 *     without losing their place in the statement.
 *   * Multiple panels can be open at once for cross-checking sibling
 *     accounts (e.g. Receita Bruta vs Vendas Canceladas).
 *
 * Server-side filters used:
 *   ``account``, ``transaction_date_after``, ``transaction_date_before``,
 *   ``entity`` (all declared on ``JournalEntryFilter``). Date filter
 *   uses ``transaction.date`` to mirror the report's date scope.
 */

const PAGE_STEP = 100
const MAX_LIMIT = 500

type SortKey = "date" | "effective" | "description" | "debit" | "credit" | "net"
type SortDir = "asc" | "desc"

export function JournalEntriesPanel({
  accountId,
  date_from,
  date_to,
  entity,
  currency,
  basis = "accrual",
}: {
  accountId: number
  date_from?: string
  date_to?: string
  entity?: number
  currency: string
  /** Report basis. When ``cash``, the panel surfaces the
   *  ``effective_cash_date`` column which explains *why* the JE landed
   *  on this date (linked bank-tx date for reconciled JEs vs. the JE
   *  date itself when unreconciled). */
  basis?: "accrual" | "cash"
}) {
  const [limit, setLimit] = useState(PAGE_STEP)
  const [filter, setFilter] = useState("")
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "date", dir: "desc" })

  const { data: rows = [], isLoading, isError } = useJournalEntriesDrill({
    account: accountId,
    transaction_date_after: date_from,
    transaction_date_before: date_to,
    entity,
    limit,
  })

  const items = useMemo(() => {
    return (rows ?? []).map((r) => {
      const debit = Number(r.debit_amount ?? 0) || 0
      const credit = Number(r.credit_amount ?? 0) || 0
      return {
        id: r.id,
        transaction_id: r.transaction_id,
        date: r.date || "",
        description: r.description?.trim() || "(sem descrição)",
        debit,
        credit,
        net: debit - credit,
        state: r.state,
        is_reconciled: !!r.is_reconciled,
        is_cash: !!r.is_cash,
        je_date: r.je_date ?? r.date ?? null,
        linked_bank_tx_date: r.linked_bank_tx_date ?? null,
        effective_cash_date: r.effective_cash_date ?? r.date ?? null,
      }
    })
  }, [rows])

  // Client-side filter on description -- the drill response is already
  // capped at ``limit`` rows so a server round-trip per keystroke
  // would just re-fetch the same set in a different order.
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return items
    return items.filter((r) => r.description.toLowerCase().includes(q))
  }, [items, filter])

  const sorted = useMemo(() => {
    const dir = sort.dir === "desc" ? -1 : 1
    const copy = [...filtered]
    copy.sort((a, b) => {
      let av: number = 0, bv: number = 0
      if (sort.key === "description") {
        return a.description.localeCompare(b.description) * dir
      }
      if (sort.key === "date") {
        av = a.date ? new Date(a.date).getTime() : 0
        bv = b.date ? new Date(b.date).getTime() : 0
      } else if (sort.key === "effective") {
        av = a.effective_cash_date ? new Date(a.effective_cash_date).getTime() : 0
        bv = b.effective_cash_date ? new Date(b.effective_cash_date).getTime() : 0
      } else if (sort.key === "debit") {
        av = a.debit; bv = b.debit
      } else if (sort.key === "credit") {
        av = a.credit; bv = b.credit
      } else if (sort.key === "net") {
        av = a.net; bv = b.net
      }
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
    return copy
  }, [filtered, sort.key, sort.dir])

  const totals = useMemo(() => {
    let d = 0, c = 0
    for (const r of sorted) { d += r.debit; c += r.credit }
    return { debit: d, credit: c, net: d - c }
  }, [sorted])

  const onSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key !== key) {
        const numericOrDate = key !== "description"
        return { key, dir: numericOrDate ? "desc" : "asc" }
      }
      return { key, dir: prev.dir === "asc" ? "desc" : "asc" }
    })
  }

  const showCash = basis === "cash"

  if (isLoading) {
    return (
      <div className="space-y-1 p-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-5 animate-pulse rounded bg-muted/40" />
        ))}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="px-3 py-2 text-[11px] text-destructive">
        Falha ao carregar lançamentos.
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div className="px-3 py-2 text-[11px] text-muted-foreground">
        Sem lançamentos no período selecionado.
      </div>
    )
  }

  // Column template -- two extra columns when on cash basis: an
  // effective-date column and a reconciliation indicator.
  const cols = showCash
    ? "70px_70px_28px_1fr_80px_80px_80px_24px"
    : "80px_1fr_90px_90px_90px_24px"

  return (
    <div className="text-[11px]">
      {/* Filter / pagination header */}
      <div className="flex items-center gap-2 border-b border-border/40 bg-surface-3/40 px-2 py-1.5">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrar por descrição"
            className="h-6 w-full rounded-sm border border-border bg-background pl-6 pr-2 text-[11px] outline-none focus:border-ring"
          />
        </div>
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
          {filter ? `${sorted.length} / ${items.length}` : `${items.length}${rows.length === limit ? "+" : ""} lançamentos`}
        </span>
      </div>

      <div
        className="grid items-center gap-2 border-b border-border/40 bg-surface-3/60 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
        style={{ gridTemplateColumns: cols }}
      >
        <SortableLabel label="Data" k="date" sort={sort} onSort={onSort} />
        {showCash && <SortableLabel label="Efetiva" k="effective" sort={sort} onSort={onSort} title="Data efetiva usada na base caixa: data do banco quando conciliada, data do lançamento quando não." />}
        {showCash && <span title="Conciliação" className="text-center">Conc.</span>}
        <SortableLabel label="Descrição" k="description" sort={sort} onSort={onSort} />
        <SortableLabel label="Débito" k="debit" sort={sort} onSort={onSort} align="right" />
        <SortableLabel label="Crédito" k="credit" sort={sort} onSort={onSort} align="right" />
        <SortableLabel label="Líquido" k="net" sort={sort} onSort={onSort} align="right" />
        <span />
      </div>
      <div className="max-h-72 overflow-y-auto">
        {sorted.length === 0 ? (
          <div className="px-3 py-2 text-[11px] text-muted-foreground">
            Nenhum lançamento corresponde ao filtro.
          </div>
        ) : (
          sorted.map((r) => {
            const usingBankDate = !!(r.is_reconciled && r.linked_bank_tx_date)
            return (
              <div
                key={r.id}
                className="grid items-center gap-2 border-b border-border/30 px-2 py-1 hover:bg-accent/20"
                style={{ gridTemplateColumns: cols }}
              >
                <div className="tabular-nums text-muted-foreground">
                  {r.date ? r.date.slice(0, 10) : "—"}
                </div>
                {showCash && (
                  <div
                    className={cn(
                      "tabular-nums",
                      usingBankDate ? "text-foreground" : "text-muted-foreground/80",
                    )}
                    title={
                      usingBankDate
                        ? `Usando data do banco (${r.linked_bank_tx_date}). Data do lançamento: ${r.je_date ?? "—"}.`
                        : "Usando data do lançamento (não conciliado)."
                    }
                  >
                    {r.effective_cash_date ? r.effective_cash_date.slice(0, 10) : "—"}
                  </div>
                )}
                {showCash && (
                  <div className="grid place-items-center" title={r.is_reconciled ? "Conciliado" : "Não conciliado"}>
                    {r.is_reconciled ? (
                      <Link2 className="h-3 w-3 text-success" />
                    ) : (
                      <Link2Off className="h-3 w-3 text-muted-foreground/50" />
                    )}
                  </div>
                )}
                <div className="truncate" title={r.description}>
                  {r.description}
                </div>
                <div className={cn("tabular-nums text-right", r.debit > 0 ? "text-foreground" : "text-muted-foreground/60")}>
                  {r.debit > 0 ? formatCurrency(r.debit, currency) : "—"}
                </div>
                <div className={cn("tabular-nums text-right", r.credit > 0 ? "text-foreground" : "text-muted-foreground/60")}>
                  {r.credit > 0 ? formatCurrency(r.credit, currency) : "—"}
                </div>
                <div className={cn("tabular-nums text-right", r.net < 0 && "text-destructive")}>
                  {formatCurrency(r.net, currency)}
                </div>
                <Link
                  to={`/recon/transactions?id=${r.transaction_id}`}
                  className="grid place-items-center text-muted-foreground hover:text-primary"
                  title="Abrir transação no Bancada"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </div>
            )
          })
        )}
      </div>
      <div
        className="grid items-center gap-2 border-t-2 border-foreground/40 bg-surface-3/60 px-2 py-1 text-[10px] font-semibold"
        style={{ gridTemplateColumns: cols }}
      >
        {showCash ? (
          <>
            <div />
            <div />
            <div />
          </>
        ) : (
          <div />
        )}
        <div className="text-right text-muted-foreground">
          {rows.length === limit
            ? `Primeiros ${limit}${limit < MAX_LIMIT ? " (limitado)" : " (máximo)"}`
            : `${sorted.length} ${sorted.length === 1 ? "lançamento" : "lançamentos"}`}
        </div>
        <div className="tabular-nums text-right">{formatCurrency(totals.debit, currency)}</div>
        <div className="tabular-nums text-right">{formatCurrency(totals.credit, currency)}</div>
        <div className={cn("tabular-nums text-right", totals.net < 0 && "text-destructive")}>
          {formatCurrency(totals.net, currency)}
        </div>
        <div />
      </div>
      {/* Load-more button -- the drill caps at ``MAX_LIMIT`` server-side
          so we step in chunks of ``PAGE_STEP`` until we hit the cap.
          When more rows than the cap exist the operator should narrow
          the date / entity scope instead. */}
      {rows.length === limit && limit < MAX_LIMIT && (
        <div className="flex items-center justify-center border-t border-border/40 bg-surface-3/40 py-1.5">
          <button
            type="button"
            onClick={() => setLimit((l) => Math.min(MAX_LIMIT, l + PAGE_STEP))}
            className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent"
          >
            Carregar mais {Math.min(PAGE_STEP, MAX_LIMIT - limit)}
          </button>
        </div>
      )}
    </div>
  )
}

function SortableLabel({
  label,
  k,
  sort,
  onSort,
  align = "left",
  title,
}: {
  label: string
  k: SortKey
  sort: { key: SortKey; dir: SortDir }
  onSort: (k: SortKey) => void
  align?: "left" | "right"
  title?: string
}) {
  const active = sort.key === k
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      onClick={() => onSort(k)}
      title={title}
      className={cn(
        "inline-flex items-center gap-1 text-inherit hover:text-foreground",
        align === "right" && "justify-end",
      )}
    >
      <span>{label}</span>
      <Icon className={cn("h-2.5 w-2.5 shrink-0", active ? "text-foreground" : "text-muted-foreground/50")} />
    </button>
  )
}
