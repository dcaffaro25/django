import { Drawer } from "vaul"
import { FileText, Loader2, X } from "lucide-react"
import { useTransactionJournalEntries } from "@/features/reconciliation"
import type { JournalEntry, TransactionJournalEntry } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/**
 * Read-only inspector for the Transaction behind a book row.
 *
 * Opens from the Bancada book pane's per-row "Ver transação" button and
 * shows every JE attached to the same Transaction as the clicked row —
 * so operators can see the full double-entry picture (cash leg + contra
 * legs) before deciding whether to adjust, reconcile, or skip.
 *
 * The clicked row is highlighted in the list so it's obvious which entry
 * was the entry point. Data comes straight from
 * GET /api/transactions/{id}/journal_entries/ (no aggregation, just the
 * serializer output) — editing is out of scope for this drawer.
 */
export function TransactionDetailsDrawer({
  open,
  onClose,
  source,
}: {
  open: boolean
  onClose: () => void
  /** The book-pane row that opened the drawer. null = closed. */
  source: JournalEntry | null
}) {
  const txId = source?.transaction_id ?? null
  const { data: entries, isLoading, isError, error } = useTransactionJournalEntries(txId)

  const totals = (entries ?? []).reduce(
    (acc, je) => {
      const d = Number(je.debit_amount) || 0
      const c = Number(je.credit_amount) || 0
      acc.debit += d
      acc.credit += c
      return acc
    },
    { debit: 0, credit: 0 },
  )
  const balanced = Math.abs(totals.debit - totals.credit) < 0.005

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[720px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              Detalhes da transação{txId != null && ` #${txId}`}
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            {source && (
              <div className="rounded-md border border-border bg-surface-3 p-2.5 text-[11px]">
                <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">
                  Lançamento de origem
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">#{source.id}</span>
                  <span className="truncate">{source.description}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
                  {source.transaction_date && <span>{formatDate(source.transaction_date)}</span>}
                  {source.bank_account?.name && <span>· {source.bank_account.name}</span>}
                  <span className="tabular-nums">· Valor {formatCurrency(Number(source.transaction_value))}</span>
                </div>
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Carregando lançamentos…
              </div>
            ) : isError ? (
              <div className="rounded-md border border-danger/40 bg-danger/5 p-2.5 text-[11px] text-danger">
                {error instanceof Error ? error.message : "Erro ao carregar a transação."}
              </div>
            ) : (
              <>
                <div className="rounded-md border border-border">
                  <div className="grid grid-cols-[auto_1fr_120px_120px] gap-2 border-b border-border bg-muted/30 px-2 py-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    <span className="w-12">JE</span>
                    <span>Conta · descrição</span>
                    <span className="text-right">Débito</span>
                    <span className="text-right">Crédito</span>
                  </div>
                  {(entries ?? []).length === 0 ? (
                    <div className="px-2 py-3 text-center text-muted-foreground">
                      Nenhum lançamento vinculado.
                    </div>
                  ) : (
                    (entries ?? []).map((je) => {
                      const isSource = je.id === source?.id
                      return (
                        <JournalEntryRow key={je.id} je={je} isSource={isSource} />
                      )
                    })
                  )}
                  <div className="grid grid-cols-[auto_1fr_120px_120px] gap-2 border-t border-border bg-muted/30 px-2 py-1.5 text-[11px] font-semibold">
                    <span className="w-12 text-muted-foreground">Σ</span>
                    <span className="text-muted-foreground">Totais</span>
                    <span className="text-right tabular-nums">{formatCurrency(totals.debit)}</span>
                    <span className="text-right tabular-nums">{formatCurrency(totals.credit)}</span>
                  </div>
                </div>

                <div
                  className={cn(
                    "flex items-center justify-between rounded-md border px-2.5 py-1.5 text-[11px]",
                    balanced
                      ? "border-success/30 bg-success/5 text-success"
                      : "border-warning/30 bg-warning/5 text-warning",
                  )}
                >
                  <span>{balanced ? "Transação balanceada (Σd = Σc)" : "Transação desbalanceada"}</span>
                  <span className="tabular-nums">
                    Δ {formatCurrency(totals.debit - totals.credit)}
                  </span>
                </div>
              </>
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Fechar
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function JournalEntryRow({ je, isSource }: { je: TransactionJournalEntry; isSource: boolean }) {
  // Account may arrive as a nested object or as a PK — mirror the loose
  // shape the type declaration spells out, and render whichever we have.
  const acct = typeof je.account === "object" && je.account != null ? je.account : null
  const acctLabel = acct
    ? `${acct.account_code ? `${acct.account_code} · ` : ""}${acct.name}`
    : typeof je.account === "number"
    ? `Conta #${je.account}`
    : "—"
  const debit = Number(je.debit_amount) || 0
  const credit = Number(je.credit_amount) || 0

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_1fr_120px_120px] items-start gap-2 border-b border-border/60 px-2 py-1.5 last:border-b-0",
        isSource && "bg-primary/10",
      )}
    >
      <span className="w-12 font-mono text-[10px] text-muted-foreground">#{je.id}</span>
      <div className="min-w-0">
        <div className="truncate font-medium">{acctLabel}</div>
        {je.description && (
          <div className="truncate text-[10px] text-muted-foreground">{je.description}</div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
          {je.date && <span>{formatDate(je.date)}</span>}
          {je.state && <span>· {je.state}</span>}
          {je.has_designated_bank && <span>· caixa</span>}
        </div>
      </div>
      <span className="text-right tabular-nums">
        {debit > 0 ? formatCurrency(debit) : <span className="text-muted-foreground">—</span>}
      </span>
      <span className="text-right tabular-nums">
        {credit > 0 ? formatCurrency(credit) : <span className="text-muted-foreground">—</span>}
      </span>
    </div>
  )
}
