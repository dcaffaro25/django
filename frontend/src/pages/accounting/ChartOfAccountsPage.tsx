import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { Drawer } from "vaul"
import {
  Plus, Trash2, Save, X, FileCog, Copy, Search, ChevronRight, ChevronDown, Lock, RefreshCw,
  Wallet, Banknote, Clock, AlertCircle, Tag, ListChecks, ExternalLink, Layers,
} from "lucide-react"
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { SectionHeader } from "@/components/ui/section-header"
import { DownloadXlsxButton } from "@/components/ui/download-xlsx-button"
import {
  useAccountHasEntries,
  useAccounts,
  useBankAccountsList,
  useCurrencies,
  useDeleteAccount,
  useSaveAccount,
} from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import { useUserRole } from "@/features/auth/useUserRole"
import type { AccountLite } from "@/features/reconciliation/types"
import {
  CATEGORY_CODES_BY_ORDER,
  REPORT_CATEGORY_STYLES,
  TAG_LABELS,
} from "@/features/reconciliation/taxonomy_labels"
import { cn, formatCurrency } from "@/lib/utils"

interface TreeNode {
  account: AccountLite
  children: TreeNode[]
}

/** Per-row + subtree-rolled-up balances. Computed once per render
 *  via a depth-first walk; non-leaf rows roll their children's deltas
 *  up. ``effectiveBalance`` = anchor + posted delta (the legacy
 *  ``current_balance`` semantics). */
interface NodeBalances {
  posted: number
  pending: number
  unreconciled: number
  effective: number  // anchor + posted -- the "current" balance
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
  const sortRec = (nodes: TreeNode[]) => {
    nodes.sort((x, y) => x.account.path.localeCompare(y.account.path, undefined, { numeric: true, sensitivity: "base" }))
    nodes.forEach((n) => sortRec(n.children))
  }
  sortRec(roots)
  return roots
}

/** Compute rolled-up balances for every node in the tree. Returns a
 *  map from account id to its subtree-summed balances. */
function computeRollups(accounts: AccountLite[]): Map<number, NodeBalances> {
  // Build child index in one pass.
  const childrenByParent = new Map<number, AccountLite[]>()
  for (const a of accounts) {
    const pid = a.parent ?? -1
    const arr = childrenByParent.get(pid) ?? []
    arr.push(a)
    childrenByParent.set(pid, arr)
  }
  const out = new Map<number, NodeBalances>()
  const num = (x: string | null | undefined) => Number(x ?? 0) || 0
  function walk(a: AccountLite): NodeBalances {
    const cached = out.get(a.id)
    if (cached) return cached
    const own = {
      posted: num(a.own_posted_delta),
      pending: num(a.own_pending_delta),
      unreconciled: num(a.own_unreconciled_delta),
    }
    const anchor = num(a.balance as string | null)
    let posted = own.posted
    let pending = own.pending
    let unreconciled = own.unreconciled
    let subtreeAnchor = 0
    const isLeaf = (childrenByParent.get(a.id) ?? []).length === 0
    if (isLeaf) {
      subtreeAnchor = anchor
    } else {
      // Non-leaves: aggregate children. Skip the row's own ``balance``
      // because it's an MPTT roll-up artifact, not a real anchor.
      for (const child of childrenByParent.get(a.id) ?? []) {
        const c = walk(child)
        posted += c.posted
        pending += c.pending
        unreconciled += c.unreconciled
        // For non-leaf parents we add child's effective balance back
        // through subtreeAnchor so we can compute effective at this
        // node. The child's effective already includes its own posted
        // delta; subtract to leave just the anchor portion.
        subtreeAnchor += c.effective - c.posted
      }
    }
    const balances: NodeBalances = {
      posted,
      pending,
      unreconciled,
      effective: subtreeAnchor + posted,
    }
    out.set(a.id, balances)
    return balances
  }
  for (const a of accounts) walk(a)
  return out
}

function filterTree(
  nodes: TreeNode[],
  query: string,
  categoryFilter: string,
  uncategorisedOnly: boolean,
): TreeNode[] {
  if (!query && !categoryFilter && !uncategorisedOnly) return nodes
  const q = query.toLowerCase()
  const match = (a: AccountLite) => {
    const queryHit = !q || (
      (a.name ?? "").toLowerCase().includes(q) ||
      (a.account_code ?? "").toLowerCase().includes(q) ||
      (a.path ?? "").toLowerCase().includes(q)
    )
    const cat = a.effective_category ?? null
    const categoryHit = !categoryFilter || cat === categoryFilter
    const uncategorisedHit = !uncategorisedOnly || cat == null
    return queryHit && categoryHit && uncategorisedHit
  }
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

interface ChartKpis {
  total: number
  categorised: number
  withBankLink: number
  uncategorised: number
  totalEffective: number
  totalPending: number
  totalUnreconciled: number
  primaryCurrency: string
}

function summarise(accounts: AccountLite[], _rollups: Map<number, NodeBalances>): ChartKpis {
  let total = 0
  let categorised = 0
  let withBankLink = 0
  let uncategorised = 0
  let totalEffective = 0
  let totalPending = 0
  let totalUnreconciled = 0
  // Aggregate at the LEAF level only -- otherwise rolling up parents
  // double-counts. ``rollups`` already has subtree-summed values for
  // each node; we sum LEAF own deltas to avoid the duplication.
  const childrenByParent = new Map<number, number>()
  for (const a of accounts) {
    childrenByParent.set(a.parent ?? -1, (childrenByParent.get(a.parent ?? -1) ?? 0) + 1)
  }
  const num = (x: string | number | null | undefined) => Number(x ?? 0) || 0
  for (const a of accounts) {
    total++
    if (a.effective_category) categorised++
    else uncategorised++
    if (a.bank_account != null) withBankLink++
    const isLeaf = !accounts.some((x) => x.parent === a.id)
    if (isLeaf) {
      totalEffective += num(a.balance as string | null) + num(a.own_posted_delta)
      totalPending += num(a.own_pending_delta)
      totalUnreconciled += num(a.own_unreconciled_delta)
    }
  }
  // Pick the most common currency code as "primary" for org-wide
  // aggregation labelling. Multi-currency tenants get the dominant
  // currency in the strip; the per-row column still uses each row's
  // own currency.
  const currencyCounts = new Map<string, number>()
  for (const a of accounts) {
    const code = a.currency?.code ?? "BRL"
    currencyCounts.set(code, (currencyCounts.get(code) ?? 0) + 1)
  }
  let primaryCurrency = "BRL"
  let max = 0
  for (const [code, n] of currencyCounts) {
    if (n > max) { primaryCurrency = code; max = n }
  }
  return {
    total, categorised, withBankLink, uncategorised,
    totalEffective, totalPending, totalUnreconciled, primaryCurrency,
  }
}

export function ChartOfAccountsPage() {
  const { data: accounts = [], isLoading, isFetching, refetch } = useAccounts()
  // ``canWrite`` gates every mutation surface on this page: the
  // "Nova conta" button, the row-hover edit/duplicate/delete actions,
  // and the bulk drawer's save/save+close. Viewers can still expand,
  // search, filter, and export the chart -- it's read-only-by-default
  // for them.
  const { canWrite } = useUserRole()
  const [editing, setEditing] = useState<AccountLite | "new" | null>(null)
  const [query, setQuery] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("")
  const [uncategorisedOnly, setUncategorisedOnly] = useState(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const tree = useMemo(() => buildTree(accounts), [accounts])
  const rollups = useMemo(() => computeRollups(accounts), [accounts])
  const filtered = useMemo(
    () => filterTree(tree, query, categoryFilter, uncategorisedOnly),
    [tree, query, categoryFilter, uncategorisedOnly],
  )
  const kpis = useMemo(() => summarise(accounts, rollups), [accounts, rollups])
  const categoryCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const a of accounts) {
      const cat = a.effective_category ?? "(sem categoria)"
      m.set(cat, (m.get(cat) ?? 0) + 1)
    }
    return Array.from(m.entries())
      .map(([code, n]) => ({
        code,
        n,
        label: REPORT_CATEGORY_STYLES[code]?.label ?? "Sem categoria",
        order: REPORT_CATEGORY_STYLES[code]?.order ?? 99,
      }))
      .sort((a, b) => a.order - b.order)
  }, [accounts])

  // Auto-expand under filter so matches stay visible.
  const isExpanded = (id: number) => (query || categoryFilter || uncategorisedOnly ? true : expanded.has(id))
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
        subtitle="Estrutura contábil hierárquica e taxonomia"
        actions={
          <>
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
              title="Atualizar"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Atualizar
            </button>
            <DownloadXlsxButton path="/api/accounts/export_xlsx/" />
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
            {canWrite && (
              <button
                onClick={() => setEditing("new")}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-3.5 w-3.5" /> Nova conta
              </button>
            )}
          </>
        }
      />

      <KpiStrip kpis={kpis} />

      <div className="grid gap-3 md:grid-cols-2">
        <CategoryDistributionChart
          counts={categoryCounts}
          activeCode={categoryFilter}
          onBarClick={(code) => setCategoryFilter(code)}
        />
        <ShortcutsCard />
      </div>

      <FilterBar
        query={query}
        onQueryChange={setQuery}
        categoryFilter={categoryFilter}
        onCategoryFilterChange={setCategoryFilter}
        uncategorisedOnly={uncategorisedOnly}
        onUncategorisedOnlyChange={setUncategorisedOnly}
        accountCount={accounts.length}
        filteredCount={filtered.length}
      />

      <div className="card-elevated overflow-hidden">
        <div className="hairline grid h-9 grid-cols-[1fr_140px_repeat(3,minmax(110px,140px))_80px] items-center gap-2 bg-surface-3 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          <div>Conta</div>
          <div className="truncate">Categoria · Tags</div>
          <div className="text-right tabular-nums">Atual</div>
          <div className="text-right tabular-nums" title="Pendente: efeito de lançamentos não postados">Pendente</div>
          <div className="text-right tabular-nums" title="Não-conciliado: efeito de lançamentos não conciliados">Não-conciliado</div>
          <div />
        </div>

        {isLoading ? (
          <div className="p-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="mb-2 h-8 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-[12px] text-muted-foreground">
            {query || categoryFilter || uncategorisedOnly ? "Nenhuma conta encontrada" : "Nenhuma conta cadastrada"}
          </div>
        ) : (
          <div className="max-h-[640px] overflow-y-auto">
            {filtered.map((n) => (
              <TreeRow
                key={n.account.id}
                node={n}
                depth={0}
                isExpanded={isExpanded}
                onToggle={toggleExpand}
                onEdit={canWrite ? (a) => setEditing(a) : undefined}
                onDuplicate={canWrite ? onDuplicate : undefined}
                onDelete={canWrite ? onDelete : undefined}
                rollups={rollups}
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

function KpiStrip({ kpis }: { kpis: ChartKpis }) {
  const pctCategorised = kpis.total > 0 ? Math.round(100 * kpis.categorised / kpis.total) : 0
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
      <Kpi
        icon={<ListChecks className="h-3.5 w-3.5" />}
        label="Contas"
        value={kpis.total.toString()}
        sub={`${kpis.withBankLink} com banco`}
      />
      <Kpi
        icon={<Tag className="h-3.5 w-3.5" />}
        label="% categorizadas"
        value={`${pctCategorised}%`}
        sub={kpis.uncategorised > 0 ? `${kpis.uncategorised} sem categoria` : "todas categorizadas"}
        valueClass={pctCategorised >= 90 ? "text-emerald-600" : pctCategorised >= 50 ? "text-amber-600" : "text-destructive"}
      />
      <Kpi
        icon={<Wallet className="h-3.5 w-3.5" />}
        label="Saldo atual"
        value={formatCurrency(kpis.totalEffective, kpis.primaryCurrency)}
      />
      <Kpi
        icon={<Clock className="h-3.5 w-3.5" />}
        label="Pendente"
        value={formatCurrency(kpis.totalPending, kpis.primaryCurrency)}
        valueClass={kpis.totalPending !== 0 ? "text-amber-600" : ""}
      />
      <Kpi
        icon={<AlertCircle className="h-3.5 w-3.5" />}
        label="Não-conciliado"
        value={formatCurrency(kpis.totalUnreconciled, kpis.primaryCurrency)}
        valueClass={kpis.totalUnreconciled !== 0 ? "text-amber-600" : ""}
      />
      <Kpi
        icon={<Banknote className="h-3.5 w-3.5" />}
        label="Moeda principal"
        value={kpis.primaryCurrency}
      />
    </div>
  )
}

function Kpi({
  icon, label, value, sub, valueClass,
}: { icon: React.ReactNode; label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="card-elevated p-2.5">
      <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {icon} {label}
      </div>
      <div className={cn("text-[16px] font-semibold tabular-nums", valueClass)}>{value}</div>
      {sub ? <div className="text-[10px] text-muted-foreground">{sub}</div> : null}
    </div>
  )
}

function CategoryDistributionChart({
  counts,
  activeCode,
  onBarClick,
}: {
  counts: Array<{ code: string; n: number; label: string; order: number }>
  /** Currently filtered category. Active row is highlighted; clicking
   *  the same row again clears the filter. */
  activeCode?: string
  /** Receive a category code on click. ``""`` means clear. */
  onBarClick?: (code: string) => void
}) {
  // Reuse the canonical palette so the chart bar colours match the
  // pill colours in each row -- visual continuity. Inactive rows fade
  // to ~40% saturation when *some* row is active, so the active row
  // pops without losing the at-a-glance distribution.
  const data = counts.map((c) => ({
    label: c.label,
    code: c.code,
    n: c.n,
    fill: hslFromCategory(c.code),
    dim: !!activeCode && activeCode !== c.code,
  }))
  const total = data.reduce((s, x) => s + x.n, 0)

  // Dynamic height: 28px per row + chrome. Beat the previous fixed
  // h-48 (192px / 14 cats = 13px/row, recharts truncated half the
  // labels). Clamps to 360px so it doesn't dominate the page when
  // there are many empty buckets.
  const rowPx = 28
  const chartHeight = Math.min(360, Math.max(160, data.length * rowPx + 20))

  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <Layers className="h-3.5 w-3.5 text-primary" /> Distribuição por categoria
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {activeCode && (
            <button
              type="button"
              onClick={() => onBarClick?.("")}
              className="rounded-md border border-border px-1.5 py-0.5 text-[9px] font-medium hover:text-destructive"
              title="Limpar filtro"
            >
              Limpar filtro
            </button>
          )}
          <span>{total} contas</span>
        </div>
      </div>
      {data.length === 0 ? (
        <div className="flex h-40 items-center justify-center text-[12px] text-muted-foreground">
          Sem dados
        </div>
      ) : (
        <div style={{ height: chartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 10 }}
                width={180}
                interval={0}
              />
              <Tooltip
                cursor={{ fill: "hsl(var(--accent))" }}
                contentStyle={{ fontSize: "11px", borderRadius: 6 }}
                formatter={(v: number) => [`${v} contas`, ""]}
                labelFormatter={(l) => String(l)}
              />
              <Bar
                dataKey="n"
                radius={[0, 4, 4, 0]}
                onClick={(d) => {
                  if (!onBarClick) return
                  const code = (d as { code?: string }).code
                  if (!code) return
                  onBarClick(activeCode === code ? "" : code)
                }}
                style={{ cursor: onBarClick ? "pointer" : "default" }}
              >
                {data.map((d) => (
                  <Cell key={d.code} fill={d.fill} fillOpacity={d.dim ? 0.35 : 1} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {onBarClick && (
        <div className="mt-1 text-[10px] text-muted-foreground">
          Clique em uma barra para filtrar a árvore. Clique novamente
          (ou em "Limpar filtro") para remover o filtro.
        </div>
      )}
    </div>
  )
}

function hslFromCategory(code: string): string {
  // Map Tailwind palette codes to HSL strings recharts can use. We
  // hand-pick to roughly match the badge classes, but recharts wants
  // a real CSS colour string (not a Tailwind class). Hard-coded in
  // one place here.
  const palette: Record<string, string> = {
    ativo_circulante: "hsl(160, 60%, 45%)",       // emerald
    ativo_nao_circulante: "hsl(170, 50%, 45%)",   // teal
    passivo_circulante: "hsl(25, 80%, 55%)",      // orange
    passivo_nao_circulante: "hsl(40, 80%, 55%)",  // amber
    patrimonio_liquido: "hsl(220, 70%, 55%)",     // blue
    receita_bruta: "hsl(140, 60%, 45%)",          // green
    deducao_receita: "hsl(345, 70%, 55%)",        // rose
    custo: "hsl(0, 70%, 55%)",                    // red
    despesa_operacional: "hsl(330, 65%, 55%)",    // pink
    receita_financeira: "hsl(190, 70%, 50%)",     // cyan
    despesa_financeira: "hsl(265, 60%, 60%)",     // violet
    outras_receitas: "hsl(215, 15%, 55%)",        // slate
    imposto_sobre_lucro: "hsl(45, 75%, 55%)",     // yellow
    memo: "hsl(220, 8%, 55%)",                    // zinc
    "(sem categoria)": "hsl(220, 8%, 70%)",
  }
  return palette[code] ?? "hsl(220, 8%, 70%)"
}

function ShortcutsCard() {
  return (
    <div className="card-elevated p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold">
        <ExternalLink className="h-3.5 w-3.5 text-primary" /> Atalhos
      </div>
      <div className="grid grid-cols-1 gap-1.5 text-[12px]">
        <ShortcutLink to="/accounting/transactions" label="Transações" sub="Lançamentos contábeis (transações)" />
        <ShortcutLink to="/accounting/journal-entries" label="Lançamentos" sub="Linhas de débito/crédito" />
        <ShortcutLink to="/accounting/bank-accounts" label="Contas bancárias" sub="Painel de contas bancárias" />
        <ShortcutLink to="/recon/workbench" label="Bancada de conciliação" sub="Conciliar bancárias × livro" />
        <ShortcutLink to="/reports/build" label="Construtor de demonstrativos" sub="DRE / BP / DFC" />
      </div>
    </div>
  )
}

function ShortcutLink({ to, label, sub }: { to: string; label: string; sub: string }) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between rounded-md border border-border px-2.5 py-1.5 hover:bg-accent/50"
    >
      <div className="min-w-0">
        <div className="font-medium">{label}</div>
        <div className="truncate text-[10px] text-muted-foreground">{sub}</div>
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}

function FilterBar({
  query, onQueryChange,
  categoryFilter, onCategoryFilterChange,
  uncategorisedOnly, onUncategorisedOnlyChange,
  accountCount, filteredCount,
}: {
  query: string
  onQueryChange: (v: string) => void
  categoryFilter: string
  onCategoryFilterChange: (v: string) => void
  uncategorisedOnly: boolean
  onUncategorisedOnlyChange: (v: boolean) => void
  accountCount: number
  filteredCount: number
}) {
  return (
    <div className="card-elevated flex flex-wrap items-center gap-3 p-3">
      <div className="relative min-w-[200px] flex-1">
        <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Buscar por nome, código ou caminho..."
          className="h-8 w-full rounded-md border border-border bg-background pl-7 pr-2 text-[12px] outline-none focus:border-ring"
        />
      </div>
      <select
        value={categoryFilter}
        onChange={(e) => onCategoryFilterChange(e.target.value)}
        className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
      >
        <option value="">Todas as categorias</option>
        {CATEGORY_CODES_BY_ORDER.map((code) => (
          <option key={code} value={code}>{REPORT_CATEGORY_STYLES[code].label}</option>
        ))}
      </select>
      <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={uncategorisedOnly}
          onChange={(e) => onUncategorisedOnlyChange(e.target.checked)}
          className="accent-primary"
        />
        só sem categoria
      </label>
      <span className="ml-auto text-[11px] text-muted-foreground">
        {filteredCount === accountCount ? `${accountCount} contas` : `${filteredCount} de ${accountCount}`}
      </span>
    </div>
  )
}

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) {
    return (
      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        sem categoria
      </span>
    )
  }
  const style = REPORT_CATEGORY_STYLES[category]
  if (!style) return <span className="text-[10px] text-muted-foreground">{category}</span>
  return (
    <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium", style.bgClass, style.fgClass)}>
      {style.label}
    </span>
  )
}

function TagPills({ tags }: { tags: string[] | null | undefined }) {
  const list = tags ?? []
  if (list.length === 0) return null
  // Show up to 3 inline; rest become "+N" tooltip.
  const shown = list.slice(0, 3)
  const overflow = list.length - shown.length
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((t) => (
        <span
          key={t}
          className="rounded bg-muted/60 px-1 py-px text-[9px] uppercase tracking-wider text-muted-foreground"
          title={TAG_LABELS[t] ?? t}
        >
          {TAG_LABELS[t] ?? t}
        </span>
      ))}
      {overflow > 0 ? (
        <span
          className="rounded bg-muted/40 px-1 py-px text-[9px] text-muted-foreground"
          title={list.slice(3).map((t) => TAG_LABELS[t] ?? t).join(", ")}
        >
          +{overflow}
        </span>
      ) : null}
    </div>
  )
}

function TreeRow({
  node, depth, isExpanded, onToggle, onEdit, onDuplicate, onDelete, rollups,
}: {
  node: TreeNode
  depth: number
  isExpanded: (id: number) => boolean
  onToggle: (id: number) => void
  /** Optional — viewers (read-only role) get ``undefined`` so the
   *  row falls back to expand-on-click and the edit/duplicate/delete
   *  buttons disappear from the hover toolbar. */
  onEdit?: (a: AccountLite) => void
  onDuplicate?: (a: AccountLite, e: React.MouseEvent) => void
  onDelete?: (a: AccountLite, e: React.MouseEvent) => void
  rollups: Map<number, NodeBalances>
}) {
  const hasChildren = node.children.length > 0
  const open = isExpanded(node.account.id)
  const a = node.account
  const balances = rollups.get(a.id) ?? { posted: 0, pending: 0, unreconciled: 0, effective: Number(a.balance ?? 0) || 0 }
  const cur = a.currency?.code ?? "BRL"

  return (
    <>
      <div
        onClick={() => {
          if (onEdit) onEdit(a)
          else if (hasChildren) onToggle(a.id)
        }}
        className={cn(
          "group grid h-9 grid-cols-[1fr_140px_repeat(3,minmax(110px,140px))_80px] items-center gap-2 border-t border-border/60 text-[12px] transition-colors hover:bg-accent/50",
          (onEdit || hasChildren) && "cursor-pointer",
        )}
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
        <div className="flex items-center gap-1.5 truncate">
          <CategoryBadge category={a.effective_category ?? null} />
          <TagPills tags={a.effective_tags} />
        </div>
        <div className="pr-1 text-right tabular-nums text-muted-foreground">
          {balances.effective !== 0 ? formatCurrency(balances.effective, cur) : "—"}
        </div>
        <div className={cn("pr-1 text-right tabular-nums", balances.pending !== 0 && "text-amber-600")}>
          {balances.pending !== 0 ? formatCurrency(balances.pending, cur) : "—"}
        </div>
        <div className={cn("pr-1 text-right tabular-nums", balances.unreconciled !== 0 && "text-amber-600")}>
          {balances.unreconciled !== 0 ? formatCurrency(balances.unreconciled, cur) : "—"}
        </div>
        <div className="flex items-center justify-end gap-1 pr-3 opacity-0 transition-opacity group-hover:opacity-100">
          <Link
            to={`/accounting/journal-entries?account=${a.id}`}
            onClick={(e) => e.stopPropagation()}
            className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            title="Ver lançamentos"
          >
            <ExternalLink className="h-3 w-3" />
          </Link>
          {onDuplicate && (
            <button
              onClick={(e) => onDuplicate(a, e)}
              className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              title="Duplicar"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => onDelete(a, e)}
              className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-danger/10 hover:text-danger"
              title="Excluir"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
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
          rollups={rollups}
        />
      ))}
    </>
  )
}

// ----------------------------------------------------------------------
// Editor drawer -- existing form, extended with category + tags fields
// ----------------------------------------------------------------------
interface AccountFormState {
  id?: number
  name: string
  account_code: string
  erp_id: string
  description: string
  parent: number | null
  currency: number | null
  bank_account: number | null
  account_direction: 1 | -1 | null
  balance: string
  balance_date: string
  key_words: string
  examples: string
  is_active: boolean
  report_category: string  // closed enum or "" for null
  tags: string[]
  company?: number
}

function blankForm(companyId?: number): AccountFormState {
  return {
    name: "",
    account_code: "",
    erp_id: "",
    description: "",
    parent: null,
    currency: null,
    bank_account: null,
    account_direction: null,
    balance: "0",
    balance_date: new Date().toISOString().slice(0, 10),
    key_words: "",
    examples: "",
    is_active: true,
    report_category: "",
    tags: [],
    company: companyId,
  }
}

function fromAccount(a: AccountLite): AccountFormState {
  return {
    id: a.id,
    name: a.name ?? "",
    account_code: a.account_code ?? "",
    erp_id: a.erp_id ?? "",
    description: a.description ?? "",
    parent: a.parent ?? null,
    currency: a.currency?.id ?? null,
    bank_account: a.bank_account ?? null,
    account_direction: (a.account_direction === 1 || a.account_direction === -1) ? a.account_direction : null,
    balance: a.balance != null ? String(a.balance) : "0",
    balance_date: a.balance_date ?? new Date().toISOString().slice(0, 10),
    key_words: a.key_words ?? "",
    examples: a.examples ?? "",
    is_active: a.is_active !== false,
    report_category: a.report_category ?? "",
    tags: a.tags ?? [],
  }
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
  const { data: bankAccounts = [] } = useBankAccountsList()
  const { tenant } = useTenant()
  const [form, setForm] = useState<AccountFormState>(() => blankForm(tenant?.id))
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (account) setForm(fromAccount(account))
    else setForm(blankForm(tenant?.id))
    setShowAdvanced(false)
  }, [account, open, tenant?.id])

  const { data: hasEntries } = useAccountHasEntries(account?.id ?? null)
  const directionLocked = !!account && hasEntries === true
  const isChildlessLeaf = useMemo(() => {
    if (!account) return true
    return !accounts.some((a) => a.parent === account.id)
  }, [account, accounts])

  const set = <K extends keyof AccountFormState>(key: K, value: AccountFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const toggleTag = (t: string) => {
    setForm((f) => {
      const has = f.tags.includes(t)
      return { ...f, tags: has ? f.tags.filter((x) => x !== t) : [...f.tags, t] }
    })
  }

  const onSave = () => {
    if (!form.name.trim()) { toast.error("Nome obrigatório"); return }
    if (form.account_direction !== 1 && form.account_direction !== -1) {
      toast.error("Direção da conta obrigatória (Débito ou Crédito).")
      return
    }
    const body: Record<string, unknown> = {
      name: form.name.trim(),
      account_code: form.account_code || null,
      erp_id: form.erp_id || null,
      description: form.description || null,
      parent: form.parent,
      currency: form.currency,
      bank_account: isChildlessLeaf ? form.bank_account : null,
      account_direction: form.account_direction,
      balance: form.balance || "0",
      balance_date: form.balance_date,
      key_words: form.key_words || null,
      examples: form.examples || null,
      is_active: form.is_active,
      report_category: form.report_category || null,
      tags: form.tags,
      company: form.company ?? tenant?.id,
    }
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
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[min(640px,92vw)] flex-col border-l border-border surface-2 outline-none">
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
                <input
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                />
              </Field>
              <Field label="Código">
                <input
                  value={form.account_code}
                  onChange={(e) => set("account_code", e.target.value)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums outline-none focus:border-ring"
                />
              </Field>
            </div>

            <Field label="Conta pai (opcional)">
              <select
                value={form.parent ?? ""}
                onChange={(e) => set("parent", e.target.value ? Number(e.target.value) : null)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
              >
                <option value="">— raiz —</option>
                {accounts
                  .filter((x) => x.id !== account?.id)
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.account_code ? `${x.account_code} · ` : ""}{x.path}
                    </option>
                  ))}
              </select>
            </Field>

            {/* Categoria + tags -- the new Phase 1 fields. */}
            <Field label="Categoria de relatório">
              <select
                value={form.report_category}
                onChange={(e) => set("report_category", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
              >
                <option value="">— herdar do pai —</option>
                {CATEGORY_CODES_BY_ORDER.map((code) => (
                  <option key={code} value={code}>{REPORT_CATEGORY_STYLES[code].label}</option>
                ))}
              </select>
            </Field>

            <Field label="Tags (clique para adicionar/remover)">
              <div className="flex flex-wrap gap-1">
                {Object.entries(TAG_LABELS).map(([code, label]) => {
                  const active = form.tags.includes(code)
                  return (
                    <button
                      type="button"
                      key={code}
                      onClick={() => toggleTag(code)}
                      className={cn(
                        "rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider transition-colors",
                        active
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:bg-accent",
                      )}
                    >
                      {label}
                    </button>
                  )
                })}
              </div>
            </Field>

            <Field label="Descrição">
              <textarea
                value={form.description}
                onChange={(e) => set("description", e.target.value)}
                rows={2}
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 outline-none focus:border-ring"
              />
            </Field>

            <Field label="ERP id (upsert key)">
              <input
                value={form.erp_id}
                onChange={(e) => set("erp_id", e.target.value)}
                placeholder="ex.: codigo_conta do ERP"
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field
                label={
                  <span className="flex items-center gap-1.5">
                    Direção
                    {directionLocked && (
                      <span className="inline-flex items-center gap-1 text-amber-500">
                        <Lock className="h-3 w-3" /> bloqueada
                      </span>
                    )}
                  </span>
                }
              >
                <select
                  value={form.account_direction ?? ""}
                  disabled={directionLocked}
                  onChange={(e) => {
                    const v = e.target.value
                    set("account_direction", v === "1" ? 1 : v === "-1" ? -1 : null)
                  }}
                  className={cn(
                    "h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring",
                    directionLocked && "opacity-60",
                  )}
                >
                  <option value="">—</option>
                  <option value="1">Débito (+1)</option>
                  <option value="-1">Crédito (-1)</option>
                </select>
              </Field>

              <Field label="Moeda">
                <select
                  value={form.currency ?? ""}
                  onChange={(e) => set("currency", e.target.value ? Number(e.target.value) : null)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                >
                  <option value="">—</option>
                  {currencies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} · {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="rounded-md border border-border p-3">
              <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Saldo inicial
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Data">
                  <input
                    type="date"
                    value={form.balance_date}
                    onChange={(e) => set("balance_date", e.target.value)}
                    className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                  />
                </Field>
                <Field label="Valor">
                  <input
                    type="number"
                    step="0.01"
                    value={form.balance}
                    onChange={(e) => set("balance", e.target.value)}
                    className="h-8 w-full rounded-md border border-border bg-background px-2 text-right tabular-nums outline-none focus:border-ring"
                  />
                </Field>
              </div>
            </div>

            {isChildlessLeaf && (
              <Field label="Conta bancária vinculada (opcional)">
                <select
                  value={form.bank_account ?? ""}
                  onChange={(e) => set("bank_account", e.target.value ? Number(e.target.value) : null)}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                >
                  <option value="">—</option>
                  {bankAccounts.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
                className="accent-primary"
              />
              Ativa
            </label>

            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground"
            >
              {showAdvanced ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Avançado
            </button>
            {showAdvanced && (
              <div className="space-y-3 rounded-md border border-dashed border-border p-3">
                <Field label="Palavras-chave">
                  <input
                    value={form.key_words}
                    onChange={(e) => set("key_words", e.target.value)}
                    placeholder="termos separados por vírgula"
                    className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                  />
                </Field>
                <Field label="Exemplos">
                  <input
                    value={form.examples}
                    onChange={(e) => set("examples", e.target.value)}
                    placeholder="frases exemplo que costumam cair nesta conta"
                    className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                  />
                </Field>
              </div>
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button
              onClick={onSave}
              disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {t("actions.save", { ns: "common" })}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
