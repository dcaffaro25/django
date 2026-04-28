import { useMemo } from "react"
import { Link, Outlet, useSearchParams } from "react-router-dom"
import { FileBarChart, Sparkles, Wallet, Receipt, FileText, ListChecks } from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"
import { useAccounts } from "@/features/reconciliation"
import {
  REPORT_CATEGORY_STYLES,
} from "@/features/reconciliation/taxonomy_labels"
import { cn, formatCurrency } from "@/lib/utils"
import type { AccountLite } from "@/features/reconciliation/types"

/** Read the ``?include_pending=1`` switch from the URL so every tab
 *  shares the same value without prop drilling. The flag flows into
 *  ``useAccounts({ include_pending })`` and from there to the
 *  ``/api/accounts/?include_pending=1`` query, which makes the
 *  backend add ``own_pending_delta`` to ``current_balance``. */
function useIncludePendingFromUrl(): boolean {
  const [params] = useSearchParams()
  const v = (params.get("include_pending") ?? "").toLowerCase()
  return v === "1" || v === "true" || v === "yes"
}

/**
 * The Demonstrativos hub: tabbed shell with the four standard
 * Brazilian financial statements (DRE, Balanço Patrimonial, DFC) plus
 * a "Personalizados" tab that surfaces user-built templates from the
 * existing /reports/build flow.
 *
 * Each standard tab is a pure-frontend computation over the chart of
 * accounts -- it groups leaves by ``effective_category`` and rolls
 * subtree balances. No AI calls, no extra backend endpoints, sub-second
 * once the accounts list is in cache.
 */
export function StandardReportsPage() {
  const [params, setParams] = useSearchParams()
  const includePending = useIncludePendingFromUrl()

  const toggle = () => {
    const next = new URLSearchParams(params)
    if (includePending) {
      next.delete("include_pending")
    } else {
      next.set("include_pending", "1")
    }
    setParams(next, { replace: true })
  }

  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Demonstrativos"
        subtitle="DRE · Balanço · DFC · Modelos personalizados"
        actions={
          <label
            className={cn(
              "inline-flex cursor-pointer select-none items-center gap-2 rounded-md border border-border px-2.5 py-1 text-[11px] transition-colors",
              includePending
                ? "border-primary/40 bg-primary/10 text-primary"
                : "bg-surface-2 text-muted-foreground hover:text-foreground",
            )}
            title="Inclui lançamentos em estado 'pending' no saldo de cada conta. Útil para tenants cujos JEs ainda não foram contabilizados (posted)."
          >
            <input
              type="checkbox"
              className="h-3 w-3 cursor-pointer accent-primary"
              checked={includePending}
              onChange={toggle}
            />
            Incluir pendentes
          </label>
        }
        tabs={[
          { to: "/reports", end: true, label: "DRE", icon: FileBarChart },
          { to: "/reports/balanco", label: "Balanço Patrimonial", icon: Wallet },
          { to: "/reports/dfc", label: "Fluxo de Caixa", icon: Receipt },
          { to: "/reports/custom", label: "Personalizados", icon: Sparkles },
          { to: "/reports/history", label: "Histórico", icon: ListChecks },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}

// ---------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------

interface CategorySum {
  category: string
  label: string
  total: number
  accounts: Array<{ id: number; name: string; balance: number }>
}

/** Group leaf accounts by effective_category and sum the
 *  ``current_balance`` for each category. */
function summariseByCategory(accounts: AccountLite[]): Map<string, CategorySum> {
  // Determine leaves (accounts with no children in the loaded list)
  const childCount = new Map<number, number>()
  for (const a of accounts) {
    if (a.parent != null) {
      childCount.set(a.parent, (childCount.get(a.parent) ?? 0) + 1)
    }
  }
  const map = new Map<string, CategorySum>()
  for (const a of accounts) {
    const isLeaf = (childCount.get(a.id) ?? 0) === 0
    if (!isLeaf) continue
    const cat = a.effective_category
    if (!cat) continue
    const balance = Number(a.current_balance ?? 0) || 0
    const bucket = map.get(cat) ?? {
      category: cat,
      label: REPORT_CATEGORY_STYLES[cat]?.label ?? cat,
      total: 0,
      accounts: [],
    }
    bucket.total += balance
    bucket.accounts.push({ id: a.id, name: a.name, balance })
    map.set(cat, bucket)
  }
  return map
}

function StatementLine({
  label, value, currency, bold, indent, negative,
}: {
  label: string
  value?: number | null
  currency: string
  bold?: boolean
  indent?: number
  negative?: boolean
}) {
  const display = value == null ? "—" : formatCurrency(value, currency)
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-border/40 px-3 py-1.5 text-[12px]",
        bold && "border-b-foreground/30 bg-surface-3 font-semibold",
      )}
      style={{ paddingLeft: 12 + (indent ?? 0) * 16 }}
    >
      <div className="truncate">{label}</div>
      <div
        className={cn(
          "tabular-nums",
          negative && value != null && value !== 0 && "text-destructive",
        )}
      >
        {display}
      </div>
    </div>
  )
}

function StatementSkeleton() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-7 animate-pulse rounded bg-muted/40" />
      ))}
    </div>
  )
}

function NotEnoughDataNotice() {
  return (
    <div className="card-elevated p-4 text-[12px] text-muted-foreground">
      <p className="mb-1 font-medium text-foreground">Sem dados suficientes</p>
      <p>
        As contas ainda não foram categorizadas. Vá ao{" "}
        <Link to="/accounting/accounts" className="text-primary hover:underline">
          Plano de contas
        </Link>{" "}
        para definir <code>report_category</code> nos nós principais (Ativo
        Circulante, Despesas Operacionais, etc.). Os descendentes herdam a
        categoria automaticamente.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: DRE
// ---------------------------------------------------------------------

export function DreTab() {
  const includePending = useIncludePendingFromUrl()
  const { data: accounts = [], isLoading } = useAccounts({ include_pending: includePending })
  const cats = useMemo(() => summariseByCategory(accounts), [accounts])
  const currency = accounts[0]?.currency?.code ?? "BRL"

  if (isLoading) return <StatementSkeleton />
  if (cats.size === 0) return <NotEnoughDataNotice />

  // Pull the DRE-relevant categories. Account_direction handles sign
  // (revenue accounts have direction=-1 so their natural balance is
  // already a negative debit-stored number; we display them as
  // positive revenue by the math below).
  const get = (k: string) => cats.get(k)?.total ?? 0
  const receitaBruta = get("receita_bruta")
  const deducoes = get("deducao_receita")
  const receitaLiquida = receitaBruta + deducoes  // deducoes natural sign already negative
  const custos = get("custo")
  const lucroBruto = receitaLiquida + custos
  const despesasOp = get("despesa_operacional")
  const ebit = lucroBruto + despesasOp
  const receitaFin = get("receita_financeira")
  const despesaFin = get("despesa_financeira")
  const resultadoFin = receitaFin + despesaFin
  const outras = get("outras_receitas")
  const lair = ebit + resultadoFin + outras
  const impostoLucro = get("imposto_sobre_lucro")
  const lucroLiq = lair + impostoLucro

  return (
    <div className="card-elevated overflow-hidden text-[12px]">
      <div className="flex items-center justify-between border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div>Linha</div>
        <div className="tabular-nums">{currency}</div>
      </div>
      <StatementLine label="Receita Bruta" value={receitaBruta} currency={currency} bold />
      <StatementLine label="(-) Deduções da Receita" value={deducoes} currency={currency} indent={1} negative />
      <StatementLine label="Receita Líquida" value={receitaLiquida} currency={currency} bold />
      <StatementLine label="(-) Custos" value={custos} currency={currency} indent={1} negative />
      <StatementLine label="Lucro Bruto" value={lucroBruto} currency={currency} bold />
      <StatementLine label="(-) Despesas Operacionais" value={despesasOp} currency={currency} indent={1} negative />
      <StatementLine label="EBIT (Lucro Operacional)" value={ebit} currency={currency} bold />
      <StatementLine label="(+) Receitas Financeiras" value={receitaFin} currency={currency} indent={1} />
      <StatementLine label="(-) Despesas Financeiras" value={despesaFin} currency={currency} indent={1} negative />
      <StatementLine label="(+/-) Outras Receitas/Despesas" value={outras} currency={currency} indent={1} />
      <StatementLine label="Resultado Financeiro" value={resultadoFin} currency={currency} indent={1} />
      <StatementLine label="LAIR (Lucro antes IR)" value={lair} currency={currency} bold />
      <StatementLine label="(-) IRPJ + CSLL" value={impostoLucro} currency={currency} indent={1} negative />
      <StatementLine label="Lucro Líquido do Exercício" value={lucroLiq} currency={currency} bold />
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: Balanço Patrimonial
// ---------------------------------------------------------------------

export function BalancoTab() {
  const includePending = useIncludePendingFromUrl()
  const { data: accounts = [], isLoading } = useAccounts({ include_pending: includePending })
  const cats = useMemo(() => summariseByCategory(accounts), [accounts])
  const currency = accounts[0]?.currency?.code ?? "BRL"
  if (isLoading) return <StatementSkeleton />
  if (cats.size === 0) return <NotEnoughDataNotice />

  const get = (k: string) => cats.get(k)?.total ?? 0
  const ativoCirc = get("ativo_circulante")
  const ativoNc = get("ativo_nao_circulante")
  const totalAtivo = ativoCirc + ativoNc
  const passCirc = get("passivo_circulante")
  const passNc = get("passivo_nao_circulante")
  const pl = get("patrimonio_liquido")
  const totalPassivoPl = passCirc + passNc + pl
  const balanced = Math.abs(totalAtivo - totalPassivoPl) < 0.01

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Ativo
        </div>
        <StatementLine label="Ativo Circulante" value={ativoCirc} currency={currency} indent={0} />
        <StatementLine label="Ativo Não Circulante" value={ativoNc} currency={currency} indent={0} />
        <StatementLine label="Total do Ativo" value={totalAtivo} currency={currency} bold />
      </div>
      <div className="card-elevated overflow-hidden text-[12px]">
        <div className="border-b border-border bg-surface-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Passivo + Patrimônio Líquido
        </div>
        <StatementLine label="Passivo Circulante" value={passCirc} currency={currency} indent={0} />
        <StatementLine label="Passivo Não Circulante" value={passNc} currency={currency} indent={0} />
        <StatementLine label="Patrimônio Líquido" value={pl} currency={currency} indent={0} />
        <StatementLine label="Total Passivo + PL" value={totalPassivoPl} currency={currency} bold />
      </div>
      <div className={cn(
        "md:col-span-2 rounded-md border p-3 text-[12px]",
        balanced
          ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/5 text-destructive",
      )}>
        {balanced ? (
          <>✓ Balanço fecha: Total Ativo = Total Passivo + PL</>
        ) : (
          <>
            ⚠ Diferença: {formatCurrency(totalAtivo - totalPassivoPl, currency)}.
            Verifique se as contas estão classificadas corretamente.
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: DFC (Fluxo de Caixa Indireto, simplified MVP)
// ---------------------------------------------------------------------

export function DfcTab() {
  const includePending = useIncludePendingFromUrl()
  const { data: accounts = [], isLoading } = useAccounts({ include_pending: includePending })
  if (isLoading) return <StatementSkeleton />

  // Cash subset: leaves with tag "cash" or "restricted_cash" inherited.
  const cashTotal = accounts.reduce((s, a) => {
    const tags = a.effective_tags ?? []
    if (!tags.includes("cash") && !tags.includes("bank_account")) return s
    // Skip non-leaves (parents would double-count)
    const hasChildren = accounts.some((c) => c.parent === a.id)
    if (hasChildren) return s
    return s + (Number(a.current_balance ?? 0) || 0)
  }, 0)

  const currency = accounts[0]?.currency?.code ?? "BRL"

  return (
    <div className="space-y-4">
      <div className="card-elevated p-3">
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Saldo de Caixa (atual)
        </div>
        <div className="text-[20px] font-semibold tabular-nums">
          {formatCurrency(cashTotal, currency)}
        </div>
        <div className="mt-1 text-[10px] text-muted-foreground">
          Soma das contas marcadas com tag <code>cash</code> ou <code>bank_account</code>.
        </div>
      </div>

      <div className="card-elevated p-4 text-[12px] text-muted-foreground">
        <div className="mb-2 flex items-center gap-1.5 font-semibold text-foreground">
          <FileText className="h-3.5 w-3.5" />
          Demonstração do Fluxo de Caixa (em construção)
        </div>
        <p className="mb-2">
          A versão completa da DFC indireta (Lucro Líquido + ajustes não-caixa
          + variações de capital de giro = FCO; FCI; FCF; Variação Líquida)
          requer dados de período (data inicial e final) que a versão estática
          atual não calcula. Para gerar a DFC completa, use o construtor
          customizado em <Link to="/reports/build" className="text-primary hover:underline">/reports/build</Link>.
        </p>
        <p>
          Os pré-requisitos já estão prontos: contas de capital de giro
          marcadas com <code>working_capital</code>, contas de imobilizado
          com <code>fixed_asset</code>, dívidas com <code>debt</code>,
          itens não-caixa com <code>non_cash</code> / <code>ebitda_addback</code>.
          A próxima entrega usa esses tags + o engine de cálculo de relatórios
          para emitir a DFC indireta automaticamente.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------
// Tab: Custom (links to existing builder + history)
// ---------------------------------------------------------------------

export function CustomReportsTab() {
  return (
    <div className="space-y-3">
      <div className="card-elevated p-4 text-[12px]">
        <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
          <Sparkles className="h-4 w-4 text-amber-500" />
          Modelos personalizados
        </div>
        <p className="mb-3 text-muted-foreground">
          Construa um demonstrativo customizado com IA ou manualmente. O
          construtor aceita seletores por <code>report_category</code>,
          <code> tags</code> ou <code>account_ids</code>, e tem suporte para
          fórmulas, subtotais, comparativos por período e exportação.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/reports/build"
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Sparkles className="h-3.5 w-3.5" /> Abrir construtor
          </Link>
          <Link
            to="/reports/history"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            <ListChecks className="h-3.5 w-3.5" /> Histórico
          </Link>
        </div>
      </div>
    </div>
  )
}
