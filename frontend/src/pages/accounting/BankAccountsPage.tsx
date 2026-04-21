import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Plus, Trash2, Save, X, Wallet, Copy, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import {
  useBanks,
  useBankAccountsList,
  useCurrencies,
  useDeleteBankAccount,
  useEntities,
  useSaveBankAccount,
} from "@/features/reconciliation"
import type { BankAccountFull, BankAccountWrite } from "@/features/reconciliation/types"
import { cn, formatCurrency } from "@/lib/utils"

export function BankAccountsPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: accounts = [], isLoading, isFetching, refetch } = useBankAccountsList()
  const [editing, setEditing] = useState<BankAccountFull | "new" | null>(null)

  const { sort, sorted, toggle: toggleSort } = useSortable(accounts, {
    initialKey: "name",
    initialDirection: "asc",
    accessors: {
      name: (r) => r.name,
      bank: (r) => r.bank?.name ?? "",
      entity: (r) => r.entity?.name ?? "",
      currency: (r) => r.currency?.code ?? "",
      account_number: (r) => r.account_number ?? "",
      current_balance: (r) => r.current_balance ?? 0,
    },
  })

  const columns: ColumnDef[] = useMemo(
    () => [
      { key: "name", label: "Nome", alwaysVisible: true },
      { key: "bank", label: "Banco" },
      { key: "entity", label: "Entidade" },
      { key: "currency", label: "Moeda" },
      { key: "account_number", label: "Conta" },
      { key: "branch_id", label: "Agência", defaultVisible: false },
      { key: "current_balance", label: "Saldo atual" },
    ],
    [],
  )
  const col = useColumnVisibility("accounting.bank_accounts", columns)

  const deleteBa = useDeleteBankAccount()
  const onDelete = (a: BankAccountFull, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir conta "${a.name}"?`)) return
    deleteBa.mutate(a.id, {
      onSuccess: () => toast.success("Conta excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (a: BankAccountFull, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...a, id: undefined as unknown as number, name: `${a.name} (cópia)` })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} conta${ids.length > 1 ? "s" : ""}?`)) return
    const res = await Promise.allSettled(ids.map((id) => deleteBa.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídas · ${failed} falharam`)
    else toast.success(`${ids.length} contas excluídas`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Contas bancárias"
        subtitle="Gerenciar contas, saldos e vínculos"
        actions={
          <>
            <ColumnMenu
              columns={columns}
              isVisible={col.isVisible}
              toggle={col.toggle}
              showAll={col.showAll}
              resetDefaults={col.resetDefaults}
              label={t("actions.columns", { ns: "common" })}
            />
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
              title={t("actions.refresh", { ns: "common" }) ?? ""}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              {t("actions.refresh", { ns: "common" })}
            </button>
            <button
              onClick={() => setEditing("new")}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> Nova conta
            </button>
          </>
        }
      />

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-9 w-10 px-3">
                <SelectAllCheckbox
                  allSelected={selection.allSelected(sortedIds)}
                  someSelected={selection.someSelected(sortedIds)}
                  onToggle={() => selection.toggleAll(sortedIds)}
                />
              </th>
              <th className="h-9 px-3"><SortableHeader columnKey="name" label="Nome" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("bank") && <th className="h-9 px-3"><SortableHeader columnKey="bank" label="Banco" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("entity") && <th className="h-9 px-3"><SortableHeader columnKey="entity" label="Entidade" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("currency") && <th className="h-9 px-3"><SortableHeader columnKey="currency" label="Moeda" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("account_number") && <th className="h-9 px-3"><SortableHeader columnKey="account_number" label="Conta" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("branch_id") && <th className="h-9 px-3">Agência</th>}
              {col.isVisible("current_balance") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="current_balance" align="right" label="Saldo atual" sort={sort} onToggle={toggleSort} /></th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={9} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={9} className="h-24 px-3 text-center text-muted-foreground">Nenhuma conta cadastrada</td>
              </tr>
            ) : (
              sorted.map((a) => (
                <tr key={a.id} onClick={() => setEditing(a)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(a.id) && "bg-primary/5",
                  )}>
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(a.id)} onToggle={() => selection.toggle(a.id)} />
                  </td>
                  <td className="h-10 px-3 font-medium">{a.name}</td>
                  {col.isVisible("bank") && <td className="h-10 px-3 text-muted-foreground">{a.bank?.name ?? "—"}</td>}
                  {col.isVisible("entity") && <td className="h-10 px-3 text-muted-foreground">{a.entity?.name ?? "—"}</td>}
                  {col.isVisible("currency") && <td className="h-10 px-3 text-muted-foreground">{a.currency?.code ?? "—"}</td>}
                  {col.isVisible("account_number") && <td className="h-10 px-3 font-mono text-muted-foreground">{a.account_number ?? "—"}</td>}
                  {col.isVisible("branch_id") && <td className="h-10 px-3 font-mono text-muted-foreground">{a.branch_id ?? "—"}</td>}
                  {col.isVisible("current_balance") && (
                    <td className="h-10 px-3 text-right tabular-nums">{formatCurrency(a.current_balance ?? 0, a.currency?.code ?? "BRL")}</td>
                  )}
                  <RowActionsCell>
                    <RowAction icon={<Copy className="h-3.5 w-3.5" />} label="Duplicar" onClick={(e) => onDuplicate(a, e)} />
                    <RowAction icon={<Trash2 className="h-3.5 w-3.5" />} label="Excluir" variant="danger" onClick={(e) => onDelete(a, e)} />
                  </RowActionsCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <BankAccountEditor
        open={editing !== null}
        account={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

const BLANK: BankAccountWrite = {
  name: "",
  bank: 0,
  entity: 0,
  currency: 0,
  account_number: "",
  branch_id: "",
  balance: "0.00",
  balance_date: null,
  account_type: "",
}

function BankAccountEditor({
  open, account, onClose,
}: {
  open: boolean
  account: BankAccountFull | null
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveBankAccount()
  const { data: banks = [] } = useBanks()
  const { data: entities = [] } = useEntities()
  const { data: currencies = [] } = useCurrencies()
  const [form, setForm] = useState<BankAccountWrite>(BLANK)

  useEffect(() => {
    if (account) {
      setForm({
        id: account.id,
        name: account.name,
        bank: account.bank?.id ?? 0,
        entity: account.entity?.id ?? 0,
        currency: account.currency?.id ?? 0,
        account_number: account.account_number ?? "",
        branch_id: account.branch_id ?? "",
        balance: account.balance ?? "0.00",
        balance_date: account.balance_date ?? null,
        account_type: account.account_type ?? "",
      })
    } else {
      setForm({ ...BLANK })
    }
  }, [account, open])

  const set = <K extends keyof BankAccountWrite>(key: K, value: BankAccountWrite[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.name || !form.bank || !form.entity || !form.currency) {
      toast.error("Preencha nome, banco, entidade e moeda")
      return
    }
    save.mutate(
      { id: account?.id, body: form },
      {
        onSuccess: () => { toast.success("Conta salva"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
              {account ? `Editar conta #${account.id}` : "Nova conta bancária"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <Field label="Nome">
              <input value={form.name} onChange={(e) => set("name", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Banco">
                <select value={form.bank} onChange={(e) => set("bank", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {banks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.bank_code ? `${b.bank_code} · ` : ""}{b.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Moeda">
                <select value={form.currency} onChange={(e) => set("currency", Number(e.target.value))}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                  <option value={0}>—</option>
                  {currencies.map((c) => (
                    <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Entidade">
              <select value={form.entity} onChange={(e) => set("entity", Number(e.target.value))}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                <option value={0}>—</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>{e.path ?? e.name}</option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Número da conta">
                <input value={form.account_number ?? ""} onChange={(e) => set("account_number", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Agência">
                <input value={form.branch_id ?? ""} onChange={(e) => set("branch_id", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring" />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Saldo inicial">
                <input type="number" step="0.01" value={form.balance ?? "0.00"} onChange={(e) => set("balance", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring" />
              </Field>
              <Field label="Data saldo">
                <input type="date" value={form.balance_date ?? ""} onChange={(e) => set("balance_date", e.target.value || null)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
              </Field>
            </div>

            <Field label="Tipo (opcional)">
              <input value={form.account_type ?? ""} onChange={(e) => set("account_type", e.target.value)} placeholder="Corrente, Poupança..."
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button onClick={onSave} disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-3.5 w-3.5" />
              {t("actions.save", { ns: "common" })}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
