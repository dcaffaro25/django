import { useState } from "react"
import { ChevronDown, Pencil } from "lucide-react"
import { cn, formatCurrency } from "@/lib/utils"
import { JournalEntriesPanel } from "./JournalEntriesPanel"

/** A single account contribution row that can drill into its JE list.
 *
 *  ``synthetic=true`` marks rows that don't correspond to a real
 *  ``Account`` (e.g. the "Resultado do Exercício (período)" line
 *  injected into Patrimônio Líquido by the backend). Synthetic rows
 *  render in italic, hide the chevron / pencil, and don't try to
 *  load JEs — the underlying id is a negative sentinel. */
export interface AccountContribution {
  id: number
  name: string
  amount: number
  synthetic?: boolean
}

/** A statement line that may expand to show contributing accounts.
 *
 *  Two visual modes share the same component:
 *    * **Drillable** — ``accounts`` is non-empty. Clicking the row
 *      toggles a panel of contributing accounts; each account row in
 *      turn toggles a JE panel scoped to that account + the active
 *      period; each row also has a pencil icon that opens
 *      ``AccountWiringModal`` for in-place CoA wiring edits.
 *    * **Plain** — ``accounts`` empty / undefined. Renders just the
 *      label + value; identical to the previous ``StatementLine``.
 *      Used for derived totals (Receita Líquida, EBIT, …) where
 *      drilling is meaningless because the value is a sum of other
 *      lines, not of accounts.
 */
export function DrillableLine({
  label,
  value,
  currency,
  bold,
  indent,
  negative,
  accounts,
  date_from,
  date_to,
  entity,
  onEditAccount,
}: {
  label: string
  value?: number | null
  currency: string
  bold?: boolean
  indent?: number
  negative?: boolean
  accounts?: AccountContribution[]
  /** Active period — passed straight to the JE drill so the panel
   *  stays consistent with the report's date scope. */
  date_from?: string
  date_to?: string
  entity?: number
  /** Pencil-icon handler. Receives the account id of the row being
   *  edited; the parent owns the modal state and passes it the
   *  matching ``AccountLite`` from its accounts list. */
  onEditAccount?: (accountId: number) => void
}) {
  const [open, setOpen] = useState(false)
  const drillable = (accounts?.length ?? 0) > 0
  const display = value == null ? "—" : formatCurrency(value, currency)

  return (
    <>
      <div
        className={cn(
          "flex items-center justify-between border-b border-border/40 px-3 py-1.5 text-[12px]",
          bold && "border-b-foreground/30 bg-surface-3 font-semibold",
          drillable && "cursor-pointer transition-colors hover:bg-accent/20",
        )}
        style={{ paddingLeft: 12 + (indent ?? 0) * 16 }}
        onClick={drillable ? () => setOpen((v) => !v) : undefined}
      >
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          {drillable && (
            <ChevronDown
              className={cn(
                "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
                !open && "-rotate-90",
              )}
            />
          )}
          <span className="truncate">{label}</span>
          {drillable && (
            <span className="text-[10px] text-muted-foreground">
              · {accounts!.length} {accounts!.length === 1 ? "conta" : "contas"}
            </span>
          )}
        </div>
        <div
          className={cn(
            "tabular-nums",
            negative && value != null && value !== 0 && "text-destructive",
          )}
        >
          {display}
        </div>
      </div>
      {open && drillable && (
        <AccountList
          accounts={accounts!}
          currency={currency}
          indent={(indent ?? 0) + 1}
          date_from={date_from}
          date_to={date_to}
          entity={entity}
          onEditAccount={onEditAccount}
        />
      )}
    </>
  )
}

function AccountList({
  accounts,
  currency,
  indent,
  date_from,
  date_to,
  entity,
  onEditAccount,
}: {
  accounts: AccountContribution[]
  currency: string
  indent: number
  date_from?: string
  date_to?: string
  entity?: number
  onEditAccount?: (id: number) => void
}) {
  // Sort by absolute contribution so the largest movers come first —
  // operators usually want to audit the big swings, not the dust.
  const sorted = [...accounts].sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount))
  return (
    <div className="bg-surface-2/40">
      {sorted.map((a) => (
        <AccountDrillRow
          key={a.id}
          account={a}
          currency={currency}
          indent={indent}
          date_from={date_from}
          date_to={date_to}
          entity={entity}
          onEdit={onEditAccount}
        />
      ))}
    </div>
  )
}

function AccountDrillRow({
  account,
  currency,
  indent,
  date_from,
  date_to,
  entity,
  onEdit,
}: {
  account: AccountContribution
  currency: string
  indent: number
  date_from?: string
  date_to?: string
  entity?: number
  onEdit?: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  // Synthetic rows (e.g. Resultado do Exercício) don't have a real
  // Account underneath, so suppress the chevron / drill / wiring
  // edit and tag the row with a "(virtual)" hint so the operator
  // understands the entry isn't a JE-backed account. The amount
  // still renders normally so it visibly contributes to the
  // category total.
  if (account.synthetic) {
    return (
      <div
        className="flex items-center justify-between border-b border-border/30 px-3 py-1 text-[11px] italic text-muted-foreground"
        style={{ paddingLeft: 12 + indent * 16 + 18 /* match chevron offset */ }}
        title="Linha sintética: derivada do resultado do período (Lucro Líquido), não corresponde a uma conta com lançamentos."
      >
        <span className="truncate">
          {account.name} <span className="text-[10px] opacity-70">(virtual)</span>
        </span>
        <span className={cn("tabular-nums not-italic", account.amount < 0 && "text-destructive")}>
          {formatCurrency(account.amount, currency)}
        </span>
      </div>
    )
  }
  return (
    <>
      <div
        className="group flex cursor-pointer items-center justify-between border-b border-border/30 px-3 py-1 text-[11px] transition-colors hover:bg-accent/30"
        style={{ paddingLeft: 12 + indent * 16 }}
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
        <div
          className="border-b border-border/30 bg-background/40"
          style={{ paddingLeft: 12 + (indent + 1) * 16 }}
        >
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
