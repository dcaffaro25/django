import { Drawer } from "vaul"
import { History, Loader2, X } from "lucide-react"
import { useBankTxReconciliationHistory } from "@/features/reconciliation"
import type {
  BankTransaction,
  BankTxReconciliationHistoryEntry,
} from "@/features/reconciliation/types"
import { StatusBadge } from "@/components/ui/status-badge"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/**
 * Read-only audit drawer: every Reconciliation group a bank tx has
 * ever been part of, ordered most-recent first.
 *
 * Opens from the Workbench bank pane's per-row "history" icon. Helps
 * operators answer questions like "wait, didn't we already match this
 * one?" or "why is this bank tx showing as open — what's it linked
 * to?". Soft-deleted recs are visible (with an explicit badge) so
 * the operator sees that a previous match was undone.
 *
 * Data comes from
 * GET /api/bank_transactions/<id>/reconciliation-history/ — a single
 * fetch returns every column the table needs.
 */
export function BankTxReconciliationHistoryDrawer({
  open,
  onClose,
  source,
}: {
  open: boolean
  onClose: () => void
  /** The bank tx the operator clicked on. ``null`` = closed. */
  source: BankTransaction | null
}) {
  const bankTxId = source?.id ?? null
  const { data, isLoading, isError, error } = useBankTxReconciliationHistory(bankTxId)
  const entries = data ?? []

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[760px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <History className="h-3.5 w-3.5 text-muted-foreground" />
              Histórico de conciliações
              {bankTxId != null && <span className="text-muted-foreground">· #{bankTxId}</span>}
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Bank-tx header summary so the operator has the context
              of WHICH bank tx the history is for, without needing to
              cross-reference back to the workbench pane. */}
          {source && (
            <div className="hairline px-4 py-3 text-[12px]">
              <div className="text-muted-foreground">{formatDate(source.date)}</div>
              <div className="font-medium">{source.description}</div>
              <div className="mt-1 flex items-center gap-3">
                <span
                  className={cn(
                    "tabular-nums font-semibold",
                    Number(source.amount) < 0 ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {formatCurrency(Number(source.amount))}
                </span>
                <StatusBadge status={source.reconciliation_status} className="h-4" />
                {source.match_progress_pct !== undefined &&
                  source.match_progress_pct > 0 &&
                  source.match_progress_pct < 100 && (
                    <span className="text-[11px] font-medium text-amber-600">
                      {source.match_progress_pct}% · {formatCurrency(source.amount_remaining ?? "0")} restante
                    </span>
                  )}
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-3 text-[12px]">
            {isLoading && (
              <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Carregando…
              </div>
            )}
            {isError && (
              <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive">
                {error instanceof Error ? error.message : "Falha ao carregar histórico."}
              </div>
            )}
            {!isLoading && !isError && entries.length === 0 && (
              <div className="rounded-md border border-border bg-muted/20 p-4 text-center text-muted-foreground">
                Esta transação ainda não foi conciliada nenhuma vez.
              </div>
            )}
            {entries.length > 0 && <HistoryTable entries={entries} />}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function HistoryTable({ entries }: { entries: BankTxReconciliationHistoryEntry[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/40 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Data</th>
            <th className="h-7 px-2">Status</th>
            <th className="h-7 px-2 text-right">Bank</th>
            <th className="h-7 px-2 text-right">Livro</th>
            <th className="h-7 px-2 text-right">Δ</th>
            <th className="h-7 px-2 text-right">Itens</th>
            <th className="h-7 px-2">Referência / notas</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => {
            const dDelta = Number(e.discrepancy)
            const isBalanced = Math.abs(dDelta) < 0.005
            return (
              <tr
                key={e.id}
                className={cn(
                  "border-t border-border/60",
                  e.is_deleted && "opacity-60 line-through decoration-muted-foreground/40",
                )}
              >
                <td className="px-2 py-1.5 align-top text-muted-foreground tabular-nums">
                  {formatDate(e.created_at)}
                </td>
                <td className="px-2 py-1.5 align-top">
                  <StatusBadge status={e.status} className="h-4" />
                  {e.is_deleted && (
                    <span className="ml-1 text-[10px] text-muted-foreground">(removida)</span>
                  )}
                </td>
                <td className="px-2 py-1.5 align-top text-right tabular-nums">
                  {formatCurrency(e.total_bank_amount)}
                </td>
                <td className="px-2 py-1.5 align-top text-right tabular-nums">
                  {formatCurrency(e.total_journal_amount)}
                </td>
                <td
                  className={cn(
                    "px-2 py-1.5 align-top text-right tabular-nums font-medium",
                    isBalanced ? "text-emerald-600" : "text-amber-600",
                  )}
                >
                  {formatCurrency(e.discrepancy)}
                </td>
                <td className="px-2 py-1.5 align-top text-right text-muted-foreground tabular-nums">
                  {e.bank_transaction_count}b · {e.journal_entry_count}j
                </td>
                <td className="px-2 py-1.5 align-top text-muted-foreground">
                  {e.reference && (
                    <div className="font-mono text-[10px]">{e.reference}</div>
                  )}
                  {e.notes && (
                    <div className="line-clamp-2 break-words text-[11px]">{e.notes}</div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
