import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { Drawer } from "vaul"
import {
  Plus, Trash2, Save, X, FileCog, Copy, Search, ChevronRight, ChevronDown,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useAccounts, useCurrencies, useDeleteAccount, useSaveAccount } from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import type { AccountLite } from "@/features/reconciliation/types"
import { cn, formatCurrency } from "@/lib/utils"

interface TreeNode {
  account: AccountLite
  children: TreeNode[]
}

function buildTree(accounts: AccountLite[]): TreeNode[] {
  const byId = new Map<number, TreeNode>()
  accounts.forEach((a) => byId.set(a.id, { account: a, children: [] }))
  const roots: TreeNode[] = []
  accounts.forEach((a) => {
    const node = byId.get(a.id)!
    if (a.parent && byId.has(a.parent)) byId.get(a.parent)!.children.push(node)
    else roots.push(node)
  })
  // sort children alphabetically by path
  const sortRec = (nodes: TreeNode[]) => {
    nodes.sort((x, y) => x.account.path.localeCompare(y.account.path, undefined, { numeric: true, sensitivity: "base" }))
    nodes.forEach((n) => sortRec(n.children))
  }
  sortRec(roots)
  return roots
}

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  if (!query) return nodes
  const q = query.toLowerCase()
  const match = (a: AccountLite) =>
    (a.name ?? "").toLowerCase().includes(q) ||
    (a.account_code ?? "").toLowerCase().includes(q) ||
    (a.path ?? "").toLowerCase().includes(q)
  const walk = (ns: TreeNode[]): TreeNode[] =>
    ns.flatMap((n) => {
      const childMatches = walk(n.children)
      if (match(n.account) || childMatches.length > 0) {
        return [{ account: n.account, children: childMatches }]
      }
      return []
    })
  return walk(nodes)
}

export function ChartOfAccountsPage() {
  const { data: accounts = [], isLoading } = useAccounts()
  const [editing, setEditing] = useState<AccountLite | "new" | null>(null)
  const [query, setQuery] = useState("")
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const tree = useMemo(() => buildTree(accounts), [accounts])
  const filtered = useMemo(() => filterTree(tree, query), [tree, query])

  // Auto-expand everything when filtering (so matches are visible)
  const isExpanded = (id: number) => (query ? true : expanded.has(id))
  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const expandAll = () => setExpanded(new Set(accounts.map((a) => a.id)))
  const collapseAll = () => setExpanded(new Set())

  const del = useDeleteAccount()
  const onDelete = (a: AccountLite, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir conta "${a.name}"?`)) return
    del.mutate(a.id, {
      onSuccess: () => toast.success("Conta excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (a: AccountLite, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({ ...a, id: undefined as unknown as number, name: `${a.name} (cópia)`, path: "" })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Plano de contas"
        subtitle="Estrutura contábil hierárquica"
        actions={
          <>
            <button
              onClick={expandAll}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              <ChevronDown className="h-3.5 w-3.5" /> Expandir
            </button>
            <button
              onClick={collapseAll}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              <ChevronRight className="h-3.5 w-3.5" /> Colapsar
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

      <div className="card-elevated flex items-center gap-3 p-3">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por nome, código ou caminho..."
            className="h-8 w-full rounded-md border border-border bg-background pl-7 pr-2 text-[12px] outline-none focus:border-ring"
          />
        </div>
        <span className="text-[11px] text-muted-foreground">{accounts.length} contas</span>
      </div>

      <div className="card-elevated overflow-hidden">
        <div className="hairline flex h-9 items-center bg-surface-3 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          <div className="flex-1">Conta</div>
          <div className="w-24 text-right tabular-nums">Saldo</div>
          <div className="w-px" />
        </div>

        {isLoading ? (
          <div className="p-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="mb-2 h-8 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-[12px] text-muted-foreground">
            {query ? "Nenhuma conta encontrada" : "Nenhuma conta cadastrada"}
          </div>
        ) : (
          <div className="max-h-[600px] overflow-y-auto">
            {filtered.map((n) => (
              <TreeRow
                key={n.account.id}
                node={n}
                depth={0}
                isExpanded={isExpanded}
                onToggle={toggleExpand}
                onEdit={(a) => setEditing(a)}
                onDuplicate={onDuplicate}
                onDelete={onDelete}
              />
            ))}
          </div>
        )}
      </div>

      <AccountEditor
        open={editing !== null}
        account={editing === "new" ? null : editing}
        accounts={accounts}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

function TreeRow({
  node, depth, isExpanded, onToggle, onEdit, onDuplicate, onDelete,
}: {
  node: TreeNode
  depth: number
  isExpanded: (id: number) => boolean
  onToggle: (id: number) => void
  onEdit: (a: AccountLite) => void
  onDuplicate: (a: AccountLite, e: React.MouseEvent) => void
  onDelete: (a: AccountLite, e: React.MouseEvent) => void
}) {
  const hasChildren = node.children.length > 0
  const open = isExpanded(node.account.id)
  const a = node.account

  return (
    <>
      <div
        onClick={() => onEdit(a)}
        className="group flex h-9 cursor-pointer items-center gap-2 border-t border-border/60 text-[12px] transition-colors hover:bg-accent/50"
      >
        <div className="flex items-center" style={{ paddingLeft: 12 + depth * 16 }}>
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); onToggle(a.id) }}
              className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          ) : (
            <span className="inline-block h-5 w-5" />
          )}
          {a.account_code && (
            <span className="mr-2 font-mono text-[10px] text-muted-foreground tabular-nums">{a.account_code}</span>
          )}
          <span className={cn("truncate", depth === 0 && "font-semibold")}>{a.name}</span>
        </div>
        <div className="flex-1" />
        <div className="w-24 pr-3 text-right tabular-nums text-muted-foreground">
          {a.current_balance != null ? formatCurrency(a.current_balance, a.currency?.code ?? "BRL") : "—"}
        </div>
        <div className="flex w-[80px] items-center justify-end gap-1 pr-3 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={(e) => onDuplicate(a, e)}
            className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            title="Duplicar"
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={(e) => onDelete(a, e)}
            className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-danger/10 hover:text-danger"
            title="Excluir"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      {hasChildren && open && node.children.map((c) => (
        <TreeRow
          key={c.account.id}
          node={c}
          depth={depth + 1}
          isExpanded={isExpanded}
          onToggle={onToggle}
          onEdit={onEdit}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />
      ))}
    </>
  )
}

function AccountEditor({
  open, account, accounts, onClose,
}: {
  open: boolean
  account: AccountLite | null
  accounts: AccountLite[]
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveAccount()
  const { data: currencies = [] } = useCurrencies()
  const { tenant } = useTenant()
  const [form, setForm] = useState<Partial<AccountLite> & { company?: number; parent?: number | null }>({
    name: "",
    parent: null,
    account_code: "",
    is_active: true,
  })

  useEffect(() => {
    if (account) {
      setForm({ ...account, parent: account.parent ?? null })
    } else {
      setForm({
        name: "",
        parent: null,
        account_code: "",
        is_active: true,
        company: tenant?.id,
      })
    }
  }, [account, open, tenant?.id])

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.name) { toast.error("Nome obrigatório"); return }
    const body = { ...form, company: form.company ?? tenant?.id }
    save.mutate(
      { id: account?.id, body },
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
              <FileCog className="h-3.5 w-3.5 text-muted-foreground" />
              {account ? `Editar conta #${account.id}` : "Nova conta"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <div className="grid grid-cols-[1fr_140px] gap-3">
              <Field label="Nome">
                <input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
              </Field>
              <Field label="Código">
                <input value={form.account_code ?? ""} onChange={(e) => set("account_code", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring" />
              </Field>
            </div>

            <Field label="Conta pai (opcional)">
              <select value={form.parent ?? ""} onChange={(e) => set("parent", e.target.value ? Number(e.target.value) : null)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                <option value="">— raiz —</option>
                {accounts
                  .filter((x) => x.id !== account?.id)
                  .map((x) => (
                    <option key={x.id} value={x.id}>{x.account_code ? `${x.account_code} · ` : ""}{x.path}</option>
                  ))}
              </select>
            </Field>

            <Field label="Moeda">
              <select value={form.currency?.id ?? ""}
                onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null
                  const cur = id ? currencies.find((c) => c.id === id) : null
                  set("currency", cur ? { id: cur.id, code: cur.code, name: cur.name } : null)
                }}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                <option value="">—</option>
                {currencies.map((c) => (
                  <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
                ))}
              </select>
            </Field>

            <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
              <input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} className="accent-primary" />
              Ativa
            </label>
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
