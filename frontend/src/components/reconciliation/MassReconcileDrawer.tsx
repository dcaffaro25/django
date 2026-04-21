import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  Check,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Search,
  Wand2,
  X,
  XCircle,
} from "lucide-react"
import { useAccounts, useCreateSuggestions } from "@/features/reconciliation"
import type { AccountLite, BankTransaction } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/* ---------------- Helpers ---------------- */

/**
 * For a 1-to-1 match, the complementing journal entry must produce an
 * effective amount equal to the bank transaction amount so the
 * reconciliation's bank_sum − book_sum delta is zero:
 *
 *   effective = (debit − credit) × direction
 *   ⇒ we need effective == bank.amount
 *
 * Given an account's natural direction, this solves to a single
 * (side, amount) pair:
 *
 *   tilt = bank.amount × direction
 *   side = tilt ≥ 0 ? "debit" : "credit"
 *   amt  = |bank.amount|
 *
 * (For tilt = 0, i.e. bank.amount = 0, we arbitrarily pick debit.)
 */
function resolveSide(
  bankAmount: number,
  direction: number,
): { side: "debit" | "credit"; amount: number } {
  const tilt = Number(bankAmount) * (direction || 1)
  return {
    side: tilt >= 0 ? "debit" : "credit",
    amount: Math.abs(Number(bankAmount)),
  }
}

/* ---------------- Searchable account dropdown ---------------- */

/**
 * Minimal searchable select. Intentionally built from scratch (no cmdk)
 * so the accounts list stays rendered inline in a scrollable popup
 * without stealing focus to a command palette. The `value` is the
 * account id; we render `code · path` so operators can find accounts
 * by either column.
 */
function SearchableAccountSelect({
  accounts,
  value,
  onChange,
  placeholder = "Conta",
  compact = false,
  buttonClassName,
}: {
  accounts: AccountLite[]
  value: number | null
  onChange: (id: number | null) => void
  placeholder?: string
  /** Compact mode is used inside table cells. */
  compact?: boolean
  buttonClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = value != null ? accounts.find((a) => a.id === value) : null

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return accounts
    return accounts.filter((a) => {
      const hay = [a.account_code, a.name, a.path].filter(Boolean).join(" ").toLowerCase()
      return hay.includes(qq)
    })
  }, [q, accounts])

  // Close on click-outside
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!containerRef.current) return
      if (!containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  // Focus search input on open
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const label = selected
    ? `${selected.account_code ? `${selected.account_code} · ` : ""}${selected.path ?? selected.name}`
    : placeholder

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2 text-[12px] hover:bg-accent",
          compact ? "h-7 w-full" : "h-8 min-w-[260px]",
          !selected && "text-muted-foreground",
          buttonClassName,
        )}
      >
        <span className="truncate">{label}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-[min(480px,90vw)] rounded-md border border-border bg-popover p-1 shadow-xl">
          <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por código, nome ou caminho…"
              className="h-8 flex-1 bg-transparent text-[12px] outline-none"
            />
            {q && (
              <button onClick={() => setQ("")} className="text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="mt-1 max-h-72 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-[12px] text-muted-foreground">
                Nenhuma conta encontrada.
              </div>
            ) : (
              filtered.slice(0, 300).map((a) => (
                <button
                  type="button"
                  key={a.id}
                  onClick={() => {
                    onChange(a.id)
                    setOpen(false)
                    setQ("")
                  }}
                  className={cn(
                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[12px] hover:bg-accent",
                    value === a.id && "bg-accent",
                  )}
                >
                  {a.account_code && (
                    <span className="font-mono text-[11px] text-muted-foreground">{a.account_code}</span>
                  )}
                  <span className="truncate">{a.path ?? a.name}</span>
                </button>
              ))
            )}
            {filtered.length > 300 && (
              <div className="px-2 py-1 text-center text-[11px] text-muted-foreground">
                Mostrando 300 de {filtered.length} — refine a busca.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------------- Drawer ---------------- */

type MassRow = {
  bank: BankTransaction
  account_id: number | null
  /** YYYY-MM-DD — defaults to bank.date, editable per-row. */
  date: string
  /** Whether this row is included in the header-level "Set Account" apply. */
  selected: boolean
}

export function MassReconcileDrawer({
  open,
  onClose,
  bankItems,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  bankItems: BankTransaction[]
  onCreated: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: accounts = [] } = useAccounts()
  const createSuggestions = useCreateSuggestions()

  // Only leaf, active accounts are legitimate posting targets. Mass-match
  // makes this extra important — an operator applying a group account to
  // 20 rows in one click would create 20 invalid journal entries.
  const leafAccounts = useMemo<AccountLite[]>(() => {
    const parents = new Set<number>()
    for (const a of accounts) {
      if (a.parent != null) parents.add(a.parent)
    }
    return (accounts as AccountLite[])
      .filter((a) => a.is_active !== false && !parents.has(a.id))
      .sort(
        (a, b) =>
          (a.account_code ?? "").localeCompare(b.account_code ?? "", undefined, { numeric: true }) ||
          (a.path ?? "").localeCompare(b.path ?? "", undefined, { numeric: true }),
      )
  }, [accounts])

  const accountDirById = useMemo<Record<number, number>>(() => {
    const map: Record<number, number> = {}
    for (const a of accounts) {
      if (a.account_direction != null) map[a.id] = a.account_direction
    }
    return map
  }, [accounts])

  const [rows, setRows] = useState<MassRow[]>([])
  const [headerAccount, setHeaderAccount] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Re-seed rows when the drawer is opened (or the selection changes
  // outside). All rows start selected so "Set Account" applies widely
  // by default — operators can uncheck outliers before applying.
  useEffect(() => {
    if (open) {
      setRows(
        bankItems.map((b) => ({
          bank: b,
          account_id: null,
          date: b.date ?? "",
          selected: true,
        })),
      )
      setHeaderAccount(null)
    }
  }, [open, bankItems])

  const update = (i: number, patch: Partial<MassRow>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const allSelected = rows.length > 0 && rows.every((r) => r.selected)
  const someSelected = rows.some((r) => r.selected)
  const toggleAll = () => {
    const next = !allSelected
    setRows((rs) => rs.map((r) => ({ ...r, selected: next })))
  }

  const applyHeaderAccount = () => {
    if (headerAccount == null) {
      toast.error("Escolha uma conta primeiro")
      return
    }
    const n = rows.filter((r) => r.selected).length
    if (!n) {
      toast.error("Selecione ao menos 1 linha")
      return
    }
    setRows((rs) => rs.map((r) => (r.selected ? { ...r, account_id: headerAccount } : r)))
    toast.success(`Conta aplicada a ${n} linha${n > 1 ? "s" : ""}`)
  }

  // A row is "balanced" (1:1 will match cleanly) once it has an account
  // and a date — resolveSide() then deterministically picks the side
  // and full amount. This check is kept cheap so the table stays
  // responsive on a few hundred rows.
  const rowBalanced = (r: MassRow) => r.account_id != null && !!r.date && !!r.bank.amount

  const balancedCount = rows.filter(rowBalanced).length
  const readyCount = rows.filter((r) => rowBalanced(r)).length

  const submit = async () => {
    if (readyCount === 0) {
      toast.error("Atribua uma conta em pelo menos uma linha")
      return
    }
    setSubmitting(true)
    // Build one create_new suggestion per row. Each produces its own
    // Transaction + single JE + Reconciliation — exactly the "1:1 for
    // every line" contract the operator asked for.
    const suggestions = rows
      .filter((r) => rowBalanced(r))
      .map((r) => {
        const dir = r.account_id != null ? (accountDirById[r.account_id] ?? 1) : 1
        const { side, amount } = resolveSide(Number(r.bank.amount), dir)
        return {
          suggestion_type: "create_new" as const,
          bank_transaction_id: r.bank.id,
          transaction: {
            date: r.date,
            entity_id: r.bank.entity ?? null,
            description: r.bank.description,
            amount: String(Math.abs(Number(r.bank.amount))),
            currency_id: r.bank.currency,
            state: "pending",
          },
          journal_entries: [
            {
              account_id: r.account_id as number,
              debit_amount: side === "debit" ? String(amount) : null,
              credit_amount: side === "credit" ? String(amount) : null,
              description: r.bank.description,
              date: r.date,
              cost_center_id: null,
            },
          ],
        }
      })

    try {
      await createSuggestions.mutateAsync({ suggestions })
      toast.success(`${suggestions.length} conciliação(ões) criada(s)`)
      onCreated()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao criar")
    } finally {
      setSubmitting(false)
    }
  }

  const selectedCount = rows.filter((r) => r.selected).length

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[960px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Wand2 className="h-3.5 w-3.5 text-muted-foreground" />
              Conciliação em massa ({bankItems.length})
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Header controls — searchable account dropdown + Set Account */}
          <div className="shrink-0 border-b border-border/60 bg-muted/20 p-3">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Aplicar conta às linhas marcadas ({selectedCount}/{rows.length})
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SearchableAccountSelect
                accounts={leafAccounts}
                value={headerAccount}
                onChange={setHeaderAccount}
                placeholder="Escolha uma conta contábil…"
              />
              <button
                onClick={applyHeaderAccount}
                disabled={headerAccount == null || !someSelected}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" />
                Aplicar conta
              </button>
              <span className="ml-auto text-[11px] text-muted-foreground">
                {balancedCount}/{rows.length} prontas · 1 conciliação será criada por linha
              </span>
            </div>
          </div>

          {/* Rows table */}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 z-10 border-b border-border bg-surface-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="w-8 px-2 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      className="h-3.5 w-3.5 accent-primary"
                      aria-label="Selecionar todas"
                    />
                  </th>
                  <th className="px-2 py-2 text-left">#</th>
                  <th className="px-2 py-2 text-left">Data</th>
                  <th className="px-2 py-2 text-left">Descrição</th>
                  <th className="px-2 py-2 text-right">Valor</th>
                  <th className="px-2 py-2 text-left">Conta contábil</th>
                  <th className="w-20 px-2 py-2 text-center">Balanço</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const balanced = rowBalanced(r)
                  return (
                    <tr
                      key={r.bank.id}
                      className={cn("border-b border-border/60", r.selected && "bg-primary/5")}
                    >
                      <td className="px-2 py-1.5 text-center">
                        <input
                          type="checkbox"
                          checked={r.selected}
                          onChange={(e) => update(i, { selected: e.target.checked })}
                          className="h-3.5 w-3.5 accent-primary"
                        />
                      </td>
                      <td className="px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
                        #{r.bank.id}
                      </td>
                      <td className="px-2 py-1.5">
                        <input
                          type="date"
                          value={r.date}
                          onChange={(e) => update(i, { date: e.target.value })}
                          className="h-7 w-[130px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring [color-scheme:dark]"
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="max-w-[260px] truncate" title={r.bank.description}>
                          {r.bank.description}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          {formatDate(r.bank.date)}
                        </div>
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
                        {formatCurrency(Number(r.bank.amount))}
                      </td>
                      <td className="px-2 py-1.5">
                        <SearchableAccountSelect
                          accounts={leafAccounts}
                          value={r.account_id}
                          onChange={(id) => update(i, { account_id: id })}
                          placeholder="—"
                          compact
                        />
                      </td>
                      <td className="px-2 py-1.5 text-center">
                        {balanced ? (
                          <span
                            className="inline-flex items-center gap-1 rounded-md bg-success/10 px-1.5 py-0.5 text-[11px] font-medium text-success"
                            title="Pronto para criar"
                          >
                            <CheckCircle2 className="h-3 w-3" /> OK
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-1 rounded-md bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning"
                            title="Atribua uma conta"
                          >
                            <XCircle className="h-3 w-3" /> —
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button
              onClick={submit}
              disabled={submitting || readyCount === 0}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Criar {readyCount} {readyCount === 1 ? "conciliação" : "conciliações"}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
