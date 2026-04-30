import { useEffect, useMemo, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import { Link as LinkIcon, Plus, Search, X, AlertCircle } from "lucide-react"
import { useAccounts, useSaveAccount } from "@/features/reconciliation"
import type { AccountLite, BankAccountFull } from "@/features/reconciliation/types"
import { cn } from "@/lib/utils"

/** Modal that wires a ``BankAccount`` to a Plano de Contas (CoA)
 *  ``Account``. Surfaced from the bank-accounts page when the row's
 *  ``linked_account_ids`` is empty (the daily-balance service then
 *  emits flat zeros for that bank account, flattening the aggregate
 *  book line).
 *
 *  Two paths share the same modal:
 *    * **Vincular existente** — search the CoA, pick a leaf, PATCH
 *      its ``bank_account`` FK to point at this row.
 *    * **Criar nova conta** — POST a fresh ``Account`` with sensible
 *      defaults (Ativo Circulante / cash + bank_account tags / leaf
 *      under the suggested parent / direction = +1) and the FK
 *      already set. Operator can adjust before saving.
 *
 *  Both paths invalidate the bank-accounts list on success so the
 *  warning badge disappears immediately. */
export function BankAccountWireModal({
  open,
  bankAccount,
  onClose,
}: {
  open: boolean
  bankAccount: BankAccountFull | null
  onClose: () => void
}) {
  const [mode, setMode] = useState<"link" | "create">("link")
  // Reset whenever the modal re-opens against a different bank
  // account; keeps stale form state from leaking between rows.
  useEffect(() => {
    if (open) setMode("link")
  }, [open, bankAccount?.id])

  if (!bankAccount) return null

  return (
    <Drawer.Root open={open} onOpenChange={(v) => !v && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Drawer.Content
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-background shadow-2xl"
          aria-describedby={undefined}
        >
          <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <Drawer.Title className="text-[14px] font-semibold">
                Vincular ao Plano de Contas
              </Drawer.Title>
              <Drawer.Description className="mt-0.5 text-[11px] text-muted-foreground">
                <span className="font-medium text-foreground">{bankAccount.name}</span>
                {bankAccount.bank?.name ? ` · ${bankAccount.bank.name}` : ""} ·{" "}
                {bankAccount.currency?.code ?? "—"}
              </Drawer.Description>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-muted-foreground hover:bg-accent"
              aria-label="Fechar"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          {/* Mode toggle. Two paths kept side-by-side because operators
              consistently want to scan the CoA first ("does the
              account already exist?") before deciding to create one.
              Bias matches the recommended workflow. */}
          <div className="flex items-center gap-1 border-b border-border bg-surface-2 px-3 py-2">
            <ModeButton
              active={mode === "link"}
              onClick={() => setMode("link")}
              icon={<LinkIcon className="h-3.5 w-3.5" />}
              label="Vincular conta existente"
            />
            <ModeButton
              active={mode === "create"}
              onClick={() => setMode("create")}
              icon={<Plus className="h-3.5 w-3.5" />}
              label="Criar nova conta"
            />
          </div>

          <div className="flex-1 overflow-y-auto p-4 text-[12px]">
            {mode === "link" ? (
              <LinkExistingPanel bankAccount={bankAccount} onDone={onClose} />
            ) : (
              <CreateNewPanel bankAccount={bankAccount} onDone={onClose} />
            )}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function ModeButton({
  active, onClick, icon, label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium transition-colors",
        active
          ? "border-primary/40 bg-primary/10 text-primary"
          : "border-transparent bg-background text-muted-foreground hover:text-foreground",
      )}
    >
      {icon}
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------
// Link-to-existing path
// ---------------------------------------------------------------------

function LinkExistingPanel({
  bankAccount,
  onDone,
}: {
  bankAccount: BankAccountFull
  onDone: () => void
}) {
  const { data: accounts = [], isLoading } = useAccounts()
  const save = useSaveAccount()
  const [filter, setFilter] = useState("")
  const [showAlreadyLinked, setShowAlreadyLinked] = useState(false)

  // Surface leaf accounts first because that's the only valid wiring
  // target — the daily-balance service reads JE flow from leaf rows
  // (parent rows aggregate via MPTT walk and don't carry their own
  // JEs). Non-leaves stay in the data but get filtered out by
  // default; an operator can still see them via the toggle if they
  // want context.
  const parentIds = useMemo(() => {
    const s = new Set<number>()
    for (const a of accounts) if (a.parent != null) s.add(a.parent)
    return s
  }, [accounts])
  const isLeaf = (a: AccountLite) => !parentIds.has(a.id)

  const f = filter.trim().toLowerCase()
  const filtered = useMemo(() => {
    return accounts
      .filter((a) => isLeaf(a))
      .filter((a) => {
        if (!showAlreadyLinked && a.bank_account != null) return false
        return true
      })
      .filter((a) => {
        if (!f) return true
        return (
          a.name.toLowerCase().includes(f) ||
          (a.path ?? "").toLowerCase().includes(f) ||
          (a.account_code ?? "").toLowerCase().includes(f)
        )
      })
      // Suggested matches first: ativo_circulante + cash/bank_account
      // tag → very likely a real bank account row already in the CoA.
      .sort((a, b) => {
        const score = (x: AccountLite) => {
          const cat = x.report_category ?? ""
          const tags = (x.tags ?? []).join(",")
          let s = 0
          if (cat === "ativo_circulante") s += 10
          if (tags.includes("cash") || tags.includes("bank_account")) s += 5
          if (
            x.name.toLowerCase().includes((bankAccount.name || "").toLowerCase().slice(0, 6))
          ) s += 3
          return -s
        }
        return score(a) - score(b)
      })
      .slice(0, 100)
  }, [accounts, parentIds, f, showAlreadyLinked, bankAccount.name])

  const onLink = async (acc: AccountLite) => {
    if (acc.bank_account != null && acc.bank_account !== bankAccount.id) {
      const ok = window.confirm(
        `"${acc.name}" já está vinculada a outra conta bancária (id ${acc.bank_account}). Reapontar para "${bankAccount.name}"?`,
      )
      if (!ok) return
    }
    try {
      await save.mutateAsync({ id: acc.id, body: { bank_account: bankAccount.id } })
      toast.success(`Vinculado: ${acc.name}`)
      onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao vincular")
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-md border border-border bg-surface-2 px-2 py-1.5">
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Buscar por nome, caminho ou código..."
          className="flex-1 bg-transparent text-[12px] outline-none"
          autoFocus
        />
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={showAlreadyLinked}
          onChange={(e) => setShowAlreadyLinked(e.target.checked)}
          className="h-3 w-3 cursor-pointer accent-primary"
        />
        Mostrar contas já vinculadas a outras contas bancárias
      </label>

      {isLoading ? (
        <div className="space-y-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-9 animate-pulse rounded bg-muted/40" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-center text-[11px] text-muted-foreground">
          Nenhuma conta folha disponível.{" "}
          {f ? "Refine a busca" : "Use 'Criar nova conta' para criar uma."}
        </div>
      ) : (
        <ul className="space-y-1">
          {filtered.map((a) => {
            const suggested =
              a.report_category === "ativo_circulante" &&
              (a.tags ?? []).some((t) => t === "cash" || t === "bank_account")
            return (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onLink(a)}
                  disabled={save.isPending}
                  className="group flex w-full items-center justify-between gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-left text-[12px] transition-colors hover:bg-accent/40 disabled:opacity-60"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium">{a.name}</span>
                      {suggested && (
                        <span className="rounded bg-emerald-500/10 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
                          Sugerido
                        </span>
                      )}
                      {a.bank_account != null && (
                        <span className="rounded bg-amber-500/10 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                          Já vinculada
                        </span>
                      )}
                    </div>
                    <div className="truncate text-[10px] text-muted-foreground">
                      {a.path ?? "—"}
                    </div>
                  </div>
                  <LinkIcon className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------
// Create-new path
// ---------------------------------------------------------------------

function CreateNewPanel({
  bankAccount,
  onDone,
}: {
  bankAccount: BankAccountFull
  onDone: () => void
}) {
  const { data: accounts = [] } = useAccounts()
  const save = useSaveAccount()

  // Default name = bank account name; default parent = nearest
  // ``ativo_circulante`` ancestor (preferring one with the ``cash``
  // tag if any). If we can't find one, leave parent unset and let
  // the operator pick.
  const defaultParent = useMemo(() => {
    // First pass: a parent already tagged cash or bank_account.
    for (const a of accounts) {
      const tags = a.tags ?? []
      if (
        a.report_category === "ativo_circulante" &&
        (tags.includes("cash") || tags.includes("bank_account"))
      ) {
        return a
      }
    }
    // Second pass: any ativo_circulante root-ish parent.
    for (const a of accounts) {
      if (a.report_category === "ativo_circulante" && (a.level ?? 0) <= 2) {
        return a
      }
    }
    return null
  }, [accounts])

  const [form, setForm] = useState({
    name: bankAccount.name,
    parent: defaultParent?.id ?? null,
    report_category: "ativo_circulante",
    tagsCsv: "cash,bank_account",
    balance: "0.00",
    balance_date: new Date().toISOString().slice(0, 10),
  })
  // Re-default parent when the accounts list arrives (initial render
  // happens before the React Query cache hydrates).
  useEffect(() => {
    if (defaultParent && form.parent == null) {
      setForm((f) => ({ ...f, parent: defaultParent.id }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultParent?.id])

  const parentOptions = useMemo(
    () =>
      accounts
        .filter((a) => a.report_category != null || a.level === 0)
        .sort((a, b) => (a.path ?? "").localeCompare(b.path ?? "")),
    [accounts],
  )

  const onCreate = async () => {
    if (!form.name) {
      toast.error("Informe o nome")
      return
    }
    const tags = form.tagsCsv
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
    try {
      await save.mutateAsync({
        body: {
          name: form.name,
          parent: form.parent ?? null,
          report_category: form.report_category || null,
          tags,
          // Bank-cash accounts are debit-natural assets.
          account_direction: 1,
          // The new account becomes the leaf that the daily-balance
          // service reads. Setting bank_account = bankAccount.id is
          // the whole point of this modal.
          bank_account: bankAccount.id,
          // Pre-fill anchor balance + date so the new leaf has a
          // clean starting point. Operator can edit later via the
          // CoA page if needed.
          balance: form.balance || "0.00",
          balance_date: form.balance_date || null,
          currency: bankAccount.currency
            ? { id: bankAccount.currency.id, code: bankAccount.currency.code, name: bankAccount.currency.name }
            : undefined,
        } as Record<string, unknown> as Parameters<typeof save.mutateAsync>[0]["body"],
      })
      toast.success(`Conta "${form.name}" criada e vinculada`)
      onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao criar conta")
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-md border border-border bg-surface-2 p-2.5 text-[11px] text-muted-foreground">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
        <p>
          Cria uma nova conta folha no Plano de Contas, já marcada como{" "}
          <span className="font-medium text-foreground">Ativo Circulante</span>{" "}
          com tags <code className="text-[10px]">cash</code> +{" "}
          <code className="text-[10px]">bank_account</code>, e a vincula a esta
          conta bancária. O saldo inicial é definido como zero por padrão —
          ajuste se houver saldo de abertura.
        </p>
      </div>

      <Field label="Nome">
        <input
          type="text"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none"
        />
      </Field>

      <Field label="Conta-pai">
        <select
          value={form.parent ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, parent: e.target.value ? Number(e.target.value) : null }))}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none"
        >
          <option value="">— sem pai (raiz) —</option>
          {parentOptions.map((a) => (
            <option key={a.id} value={a.id}>
              {a.path ?? a.name}
            </option>
          ))}
        </select>
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Categoria de relatório">
          <select
            value={form.report_category}
            onChange={(e) => setForm((f) => ({ ...f, report_category: e.target.value }))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none"
          >
            <option value="ativo_circulante">Ativo Circulante</option>
            <option value="ativo_nao_circulante">Ativo Não Circulante</option>
            <option value="">— herdar do pai —</option>
          </select>
        </Field>
        <Field label="Tags (CSV)">
          <input
            type="text"
            value={form.tagsCsv}
            onChange={(e) => setForm((f) => ({ ...f, tagsCsv: e.target.value }))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] font-mono outline-none"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Saldo inicial">
          <input
            type="text"
            inputMode="decimal"
            value={form.balance}
            onChange={(e) => setForm((f) => ({ ...f, balance: e.target.value }))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] tabular-nums outline-none"
          />
        </Field>
        <Field label="Data do saldo (balance_date)">
          <input
            type="date"
            value={form.balance_date}
            onChange={(e) => setForm((f) => ({ ...f, balance_date: e.target.value }))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none [color-scheme:dark]"
          />
        </Field>
      </div>

      <div className="flex justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={onDone}
          className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={onCreate}
          disabled={save.isPending}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90",
            save.isPending && "opacity-60",
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          {save.isPending ? "Criando..." : "Criar e vincular"}
        </button>
      </div>
    </div>
  )
}

function Field({
  label, children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      {children}
    </label>
  )
}
