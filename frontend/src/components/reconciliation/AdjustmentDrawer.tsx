import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Check, Loader2, Scale, X } from "lucide-react"
import { useDeriveJournalEntries, useLeafAccounts } from "@/features/reconciliation"
import type { JournalEntry } from "@/features/reconciliation/types"
import { SearchableAccountSelect } from "@/components/reconciliation/SearchableAccountSelect"
import { logAction, logError } from "@/lib/activity-beacon"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/**
 * Creates a balanced debit/credit pair on the template JE's Transaction.
 *
 * Operators reach this from the Bancada book pane's per-row "Ajustar"
 * button. The two new entries are written via
 * ``POST /api/journal_entries/derive_from/``, which guarantees the
 * parent Transaction stays balanced (Σdebit == Σcredit) — same amount
 * on each side, one as a debit, the other as a credit.
 *
 * Intentionally simpler than the mass drawer: no list, no multi-row,
 * no M:N. One template row → one adjustment pair. Use the mass drawer
 * when the operator needs to spray the same contra across many rows.
 */
export function AdjustmentDrawer({
  open,
  onClose,
  template,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  template: JournalEntry | null
  onCreated?: () => void
}) {
  const leafAccounts = useLeafAccounts()
  const derive = useDeriveJournalEntries()

  const [debitAccountId, setDebitAccountId] = useState<number | null>(null)
  const [creditAccountId, setCreditAccountId] = useState<number | null>(null)
  const [amount, setAmount] = useState<string>("")
  const [description, setDescription] = useState<string>("")
  const [date, setDate] = useState<string>("")

  // Re-seed defaults whenever the drawer opens (or the template changes
  // between openings). We keep a focused "Ajuste:" prefix so the new
  // entries are self-documenting in downstream ledger views.
  useEffect(() => {
    if (!open || !template) return
    setDebitAccountId(null)
    setCreditAccountId(null)
    setAmount("")
    setDescription(`Ajuste: ${template.description ?? ""}`.trim())
    setDate(template.transaction_date ?? "")
    logAction("book.adjust_open", {
      meta: { template_je_id: template.id, transaction_id: template.transaction_id },
    })
  }, [open, template])

  const parsedAmount = useMemo(() => {
    const n = Number(amount)
    return Number.isFinite(n) ? n : 0
  }, [amount])

  const amountOk = parsedAmount > 0.005
  const accountsOk = debitAccountId != null && creditAccountId != null && debitAccountId !== creditAccountId
  const canSubmit = amountOk && accountsOk && !!template && !derive.isPending

  const submit = async () => {
    if (!template) return
    if (!amountOk) {
      toast.error("Informe um valor maior que zero")
      return
    }
    if (!accountsOk) {
      toast.error("Escolha contas de débito e crédito diferentes")
      return
    }
    const amt = parsedAmount.toFixed(2)
    const desc = description.trim() || (template.description ?? "")
    const dt = date || template.transaction_date || undefined

    try {
      await derive.mutateAsync({
        template_journal_entry_id: template.id,
        entries: [
          {
            account_id: debitAccountId as number,
            debit_amount: amt,
            credit_amount: null,
            description: desc,
            date: dt,
          },
          {
            account_id: creditAccountId as number,
            debit_amount: null,
            credit_amount: amt,
            description: desc,
            date: dt,
          },
        ],
      })
      logAction("book.adjust_submit", {
        meta: {
          template_je_id: template.id,
          transaction_id: template.transaction_id,
          amount: amt,
        },
      })
      toast.success("Ajuste criado (par débito/crédito)")
      onCreated?.()
      onClose()
    } catch (err) {
      logError(err, {
        meta: { action: "book.adjust_submit", template_je_id: template.id },
      })
      toast.error(err instanceof Error ? err.message : "Erro ao criar ajuste")
    }
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[720px] flex-col border-l border-border surface-2 outline-none">
          {/* Width 720px — this drawer carries TWO SearchableAccountSelect
              pickers side-by-side (débito / crédito) plus a context card
              with the origin transaction metadata. At the old 560px the
              inner 640px popover (shared component) didn't fit: it
              clipped on the right, pushing CoA codes off the visible
              area. 720 gives the popover room to open rightward from
              the left column. The popover also self-clamps + flips to
              right-anchor if the host is narrower than this (see
              SearchableAccountSelect.tsx). */}
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Scale className="h-3.5 w-3.5 text-muted-foreground" />
              Ajustar transação
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            {/* Context card — so operators see which Transaction they're
                about to extend before they confirm. */}
            {template && (
              <div className="rounded-md border border-border bg-surface-3 p-2.5 text-[11px]">
                <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">
                  Lançamento de origem
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">#{template.id}</span>
                  <span className="truncate">{template.description}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
                  <span>Transação #{template.transaction_id}</span>
                  {template.transaction_date && <span>· {formatDate(template.transaction_date)}</span>}
                  <span className="tabular-nums">
                    · Valor atual {formatCurrency(Number(template.transaction_value))}
                  </span>
                </div>
              </div>
            )}

            <p className="text-[11px] text-muted-foreground">
              Serão criados 2 lançamentos balanceados (débito + crédito) na mesma
              transação — o total de débitos e créditos continua igual.
            </p>

            {/* Amount */}
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Valor (R$)
              </span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0,00"
                className="h-9 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
              />
            </label>

            {/* Accounts — side-by-side so the debit/credit symmetry is
                obvious at a glance. Same picker used in the mass drawer. */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Conta débito
                </span>
                <SearchableAccountSelect
                  accounts={leafAccounts}
                  value={debitAccountId}
                  onChange={setDebitAccountId}
                  placeholder="Escolha a conta de débito…"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Conta crédito
                </span>
                <SearchableAccountSelect
                  accounts={leafAccounts}
                  value={creditAccountId}
                  onChange={setCreditAccountId}
                  placeholder="Escolha a conta de crédito…"
                />
              </label>
            </div>
            {debitAccountId != null && debitAccountId === creditAccountId && (
              <div className="text-[11px] text-warning">
                Débito e crédito precisam ser contas diferentes.
              </div>
            )}

            {/* Description + date */}
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Descrição
              </span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descrição dos lançamentos"
                className="h-9 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Data
              </span>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring [color-scheme:dark]"
              />
            </label>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50",
              )}
            >
              {derive.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Criar ajuste
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
