import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAccounts } from "@/features/reconciliation"
import type { AccountsSelector } from "@/features/reports"

/**
 * MPTT-aware account picker. Two co-existing selection modes:
 *
 * 1. **Pattern mode** — user types a code prefix (e.g. "4.01"). We show a
 *    live count of matching accounts and persist it as ``code_prefix`` on
 *    the selector. Great for stable patterns.
 * 2. **Manual mode** — user expands the tree and ticks individual accounts.
 *    Persists as ``account_ids``.
 *
 * The modes are mutually exclusive on save: whichever has content wins
 * (pattern takes precedence). Mixing both in one selector is legal backend-
 * side but confusing UX — we nudge users toward one or the other.
 */
export function AccountTreePicker({
  value,
  onChange,
}: {
  value: AccountsSelector | null | undefined
  onChange: (next: AccountsSelector | null) => void
}) {
  const { data: accounts = [], isLoading } = useAccounts()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const selectedIds = new Set(value?.account_ids ?? [])
  const codePrefix = value?.code_prefix ?? ""

  // Build a tree from the flat MPTT-leveled list. AccountLite comes sorted
  // by path in the default listing, so a simple parent-lookup map works.
  const tree = useMemo(() => buildTree(accounts), [accounts])

  const patternMatchCount = useMemo(() => {
    if (!codePrefix) return 0
    return accounts.filter((a) => a.account_code?.startsWith(codePrefix)).length
  }, [accounts, codePrefix])

  const filtered = useMemo(() => {
    if (!query.trim()) return null
    const q = query.toLowerCase()
    return accounts.filter(
      (a) =>
        a.path.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q) ||
        (a.account_code ?? "").toLowerCase().includes(q),
    )
  }, [accounts, query])

  const toggleExpanded = (id: number) => {
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelected = (id: number) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    if (next.size === 0) {
      // Fully cleared
      onChange(codePrefix ? { code_prefix: codePrefix, include_descendants: true } : null)
    } else {
      onChange({
        account_ids: [...next],
        code_prefix: null, // switching to manual mode clears the pattern
        include_descendants: true,
      })
    }
  }

  const setPrefix = (p: string) => {
    if (!p && selectedIds.size === 0) {
      onChange(null)
      return
    }
    onChange({
      code_prefix: p || null,
      account_ids: p ? [] : value?.account_ids,
      include_descendants: value?.include_descendants ?? true,
    })
  }

  const summary =
    codePrefix
      ? `prefixo "${codePrefix}" (${patternMatchCount})`
      : selectedIds.size
        ? `${selectedIds.size} conta${selectedIds.size === 1 ? "" : "s"}`
        : "sem contas"

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex h-6 items-center gap-1 rounded-md border px-1.5 text-[11px]",
          codePrefix || selectedIds.size > 0
            ? "border-primary/50 bg-primary/10"
            : "border-border bg-background",
        )}
      >
        <span className="text-muted-foreground">Contas:</span>
        <span className="tabular-nums font-medium">{summary}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] z-30 w-[min(560px,95vw)] rounded-md border border-border bg-popover p-2 shadow-md">
          {/* Panel widened 380→560 so search-mode rows can render the
              full account path on a second line. Tree mode still relies
              on indentation to show hierarchy, but a ``title`` attr on
              each row keeps the path accessible on hover. */}
          <div className="flex items-center justify-between pb-2">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Selecionar contas
            </span>
            <button
              onClick={() => setOpen(false)}
              className="grid h-5 w-5 place-items-center rounded-md text-muted-foreground hover:bg-accent"
            >
              <X className="h-3 w-3" />
            </button>
          </div>

          {/* Pattern mode */}
          <div className="space-y-1.5 rounded-md border border-border bg-background/50 p-2">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Padrão (código)
            </label>
            <div className="flex items-center gap-2">
              <input
                value={codePrefix}
                onChange={(e) => setPrefix(e.target.value)}
                placeholder="ex. 4.01"
                className="h-6 w-full rounded-md border border-border bg-background px-1.5 font-mono text-[11px]"
              />
              <span
                className={cn(
                  "rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                  codePrefix
                    ? patternMatchCount > 0
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                      : "bg-red-500/15 text-red-600"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {codePrefix ? `${patternMatchCount}` : "—"}
              </span>
            </div>
            <div className="text-[10px] text-muted-foreground">
              Reutilizado automaticamente para novas contas com o mesmo prefixo.
            </div>
          </div>

          <div className="my-2 flex items-center gap-2">
            <div className="h-px flex-1 bg-border" />
            <span className="text-[10px] text-muted-foreground">ou</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          {/* Manual mode */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <Search className="h-3 w-3" /> Seleção manual
            </label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="buscar conta..."
              className="h-6 w-full rounded-md border border-border bg-background px-1.5 text-[11px]"
            />
            <div className="max-h-[240px] overflow-y-auto rounded-md border border-border/50">
              {isLoading ? (
                <div className="p-3 text-center text-[10px] text-muted-foreground">Carregando...</div>
              ) : filtered ? (
                filtered.length === 0 ? (
                  <div className="p-3 text-center text-[10px] text-muted-foreground">
                    Nenhuma conta encontrada
                  </div>
                ) : (
                  filtered.slice(0, 100).map((a) => (
                    <AccountRow
                      key={a.id}
                      depth={0}
                      account={a}
                      selected={selectedIds.has(a.id)}
                      onToggle={() => toggleSelected(a.id)}
                      disabled={!!codePrefix}
                    />
                  ))
                )
              ) : (
                <TreeView
                  nodes={tree}
                  expanded={expanded}
                  onExpandToggle={toggleExpanded}
                  selectedIds={selectedIds}
                  onSelectToggle={toggleSelected}
                  disabled={!!codePrefix}
                />
              )}
            </div>
            {codePrefix && (
              <div className="rounded-md bg-amber-500/10 p-1.5 text-[10px] text-amber-700 dark:text-amber-400">
                Remova o padrão acima para escolher contas manualmente.
              </div>
            )}
          </div>

          <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
            <button
              onClick={() => onChange(null)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
            >
              Limpar
            </button>
            <button
              onClick={() => setOpen(false)}
              className="inline-flex h-6 items-center rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
            >
              OK
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ------- Tree machinery -------

interface TreeNode {
  account: { id: number; name: string; account_code?: string | null; path: string; level: number }
  children: TreeNode[]
}

function buildTree(list: Array<{ id: number; parent?: number | null; name: string; account_code?: string | null; path: string; level: number }>): TreeNode[] {
  const byId = new Map<number, TreeNode>()
  for (const a of list) byId.set(a.id, { account: a, children: [] })
  const roots: TreeNode[] = []
  for (const a of list) {
    const node = byId.get(a.id)!
    if (a.parent != null && byId.has(a.parent)) {
      byId.get(a.parent)!.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

function TreeView({
  nodes,
  expanded,
  onExpandToggle,
  selectedIds,
  onSelectToggle,
  disabled,
}: {
  nodes: TreeNode[]
  expanded: Set<number>
  onExpandToggle: (id: number) => void
  selectedIds: Set<number>
  onSelectToggle: (id: number) => void
  disabled: boolean
}) {
  const rows: React.ReactNode[] = []
  function emit(node: TreeNode, depth: number) {
    const id = node.account.id
    const isOpen = expanded.has(id)
    const hasChildren = node.children.length > 0
    rows.push(
      <div
        key={id}
        className="flex items-center gap-1 px-1 py-0.5 hover:bg-accent/40"
        style={{ paddingLeft: `${4 + depth * 12}px` }}
        title={node.account.path}
      >
        <button
          onClick={() => hasChildren && onExpandToggle(id)}
          className={cn(
            "grid h-3.5 w-3.5 place-items-center",
            !hasChildren && "opacity-0",
          )}
        >
          {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        <input
          type="checkbox"
          checked={selectedIds.has(id)}
          onChange={() => onSelectToggle(id)}
          disabled={disabled}
          className="h-3 w-3"
        />
        <span className="font-mono text-[10px] text-muted-foreground">
          {node.account.account_code ?? "—"}
        </span>
        <span className="truncate text-[11px]">{node.account.name}</span>
      </div>,
    )
    if (isOpen) {
      for (const child of node.children) emit(child, depth + 1)
    }
  }
  for (const n of nodes) emit(n, 0)
  return <>{rows}</>
}

function AccountRow({
  account,
  selected,
  onToggle,
  disabled,
  depth,
}: {
  account: { id: number; name: string; account_code?: string | null; path: string }
  selected: boolean
  onToggle: () => void
  disabled: boolean
  depth: number
}) {
  // Search-mode row (vs. the tree-mode row above): indentation no longer
  // communicates hierarchy, so we render the full path on a second,
  // muted line. Without this the operator can't tell apart duplicate
  // leaf names like "Banco do Brasil" appearing under different parents.
  return (
    <div
      className="flex items-start gap-1 px-1 py-1 hover:bg-accent/40"
      style={{ paddingLeft: `${4 + depth * 12}px` }}
      title={account.path}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        disabled={disabled}
        className="mt-0.5 h-3 w-3 shrink-0"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-[10px] text-muted-foreground">
            {account.account_code ?? "—"}
          </span>
          <span className="truncate text-[11px] font-medium">{account.name}</span>
        </div>
        {account.path && account.path !== account.name && (
          <span className="block break-words text-[10px] leading-snug text-muted-foreground">
            {account.path}
          </span>
        )}
      </div>
    </div>
  )
}
