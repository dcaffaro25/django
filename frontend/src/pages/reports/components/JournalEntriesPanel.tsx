import { useMemo } from "react"
import { ExternalLink } from "lucide-react"
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
export function JournalEntriesPanel({
  accountId,
  date_from,
  date_to,
  entity,
  currency,
  limit = 100,
}: {
  accountId: number
  date_from?: string
  date_to?: string
  entity?: number
  currency: string
  limit?: number
}) {
  const { data: rows = [], isLoading, isError } = useJournalEntriesDrill({
    account: accountId,
    transaction_date_after: date_from,
    transaction_date_before: date_to,
    entity,
    limit,
  })

  // Pre-format the slim drill payload. The endpoint returns decimals
  // as strings; coerce defensively. Truncation is reported in the
  // footer when the response hit ``limit`` (a request for >limit rows
  // is silently capped server-side).
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
      }
    })
  }, [rows])

  const totals = useMemo(() => {
    let d = 0, c = 0
    for (const r of items) { d += r.debit; c += r.credit }
    return { debit: d, credit: c, net: d - c }
  }, [items])

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

  return (
    <div className="text-[11px]">
      <div className="grid grid-cols-[80px_1fr_90px_90px_90px_24px] items-center gap-2 border-b border-border/40 bg-surface-3/60 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div>Data</div>
        <div>Descrição</div>
        <div className="text-right">Débito</div>
        <div className="text-right">Crédito</div>
        <div className="text-right">Líquido</div>
        <div />
      </div>
      <div className="max-h-72 overflow-y-auto">
        {items.map((r) => (
          <div
            key={r.id}
            className="grid grid-cols-[80px_1fr_90px_90px_90px_24px] items-center gap-2 border-b border-border/30 px-2 py-1 hover:bg-accent/20"
          >
            <div className="tabular-nums text-muted-foreground">
              {r.date ? r.date.slice(0, 10) : "—"}
            </div>
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
        ))}
      </div>
      <div className="grid grid-cols-[80px_1fr_90px_90px_90px_24px] items-center gap-2 border-t-2 border-foreground/40 bg-surface-3/60 px-2 py-1 text-[10px] font-semibold">
        <div />
        <div className="text-right text-muted-foreground">
          {items.length === limit ? `Primeiros ${limit} (limitado)` : `${items.length} ${items.length === 1 ? "lançamento" : "lançamentos"}`}
        </div>
        <div className="tabular-nums text-right">{formatCurrency(totals.debit, currency)}</div>
        <div className="tabular-nums text-right">{formatCurrency(totals.credit, currency)}</div>
        <div className={cn("tabular-nums text-right", totals.net < 0 && "text-destructive")}>
          {formatCurrency(totals.net, currency)}
        </div>
        <div />
      </div>
    </div>
  )
}
