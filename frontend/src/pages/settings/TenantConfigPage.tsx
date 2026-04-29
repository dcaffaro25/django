import { Link } from "react-router-dom"
import { Building2, Users, Brain, CreditCard, FileBarChart, Settings, Boxes, ChevronDown, ChevronRight, Palette, Pencil } from "lucide-react"
import { useState } from "react"
import { SectionHeader } from "@/components/ui/section-header"
import { useBankAccountsDashboardKpis } from "@/features/reconciliation"
import { useAccounts, useEntities } from "@/features/reconciliation"
import {
  CATEGORY_CODES_BY_ORDER,
  REPORT_CATEGORY_STYLES,
} from "@/features/reconciliation/taxonomy_labels"
import { useTenant } from "@/providers/TenantProvider"
import { cn, formatCurrency } from "@/lib/utils"
import type { AccountLite } from "@/features/reconciliation/types"
import { TenantThemeEditor } from "@/components/theme/TenantThemeEditor"
import { CompanyInfoEditor } from "@/components/settings/CompanyInfoEditor"

/**
 * Tenant configuration landing page.
 *
 * Shows tenant identity + high-level KPIs and links to the per-tenant
 * configuration surfaces. Right now this is mostly a navigation hub --
 * each linked page is owned by an existing module. The intent is to
 * give operators ONE place to find every tenant-scoped knob without
 * memorising 12 sidebar links.
 *
 * Sections:
 *   * Identity: name, subdomain, primary currency
 *   * Health: account count, % categorised, total balance
 *   * Configuration links: Entidades, Usuários, IA, Faturamento, Modelos de demonstrativos
 */
export function TenantConfigPage() {
  const { tenant } = useTenant()
  const { data: kpis } = useBankAccountsDashboardKpis()
  const { data: accounts = [] } = useAccounts()
  const [themeEditorOpen, setThemeEditorOpen] = useState(false)
  const [companyEditorOpen, setCompanyEditorOpen] = useState(false)

  // ``kpis.account_count`` is the BANK-account count from
  // ``/dashboard-kpis/`` -- NOT the chart-of-accounts count. Use the
  // accounts list length for the % categorised denominator and keep
  // the bank-account count as a separate KPI tile.
  const bankAccountCount = kpis?.account_count ?? 0
  const accountCount = accounts.length
  const primaryCurrency = kpis?.currency_codes?.[0] ?? "BRL"
  const totalBalance = Number(kpis?.balance_by_currency?.[primaryCurrency] ?? "0") || 0
  const categorised = accounts.filter((a) => a.effective_category).length
  const pctCategorised = accountCount > 0 ? Math.round(100 * categorised / accountCount) : 0

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Configuração da empresa"
        subtitle="Parâmetros e entidades por inquilino"
        actions={
          // Both edit drawers are visible to anyone who reaches the
          // page; the actual write is gated server-side by the
          // middleware role check (viewers get a friendly 403 toast
          // via the api-client interceptor). Showing them
          // unconditionally avoids hiding the entry point during
          // the brief window before /api/core/me/ resolves on boot.
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCompanyEditorOpen(true)}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              <Pencil className="h-3.5 w-3.5 text-primary" />
              Editar empresa
            </button>
            <button
              onClick={() => setThemeEditorOpen(true)}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              <Palette className="h-3.5 w-3.5 text-primary" />
              Editar tema
            </button>
          </div>
        }
      />

      {/* Identity card */}
      <div className="card-elevated flex items-center gap-4 p-4">
        <div className="grid h-14 w-14 shrink-0 place-items-center rounded-lg text-[20px] font-bold text-primary-foreground" style={{ background: "hsl(220 65% 50%)" }}>
          {(tenant?.name ?? "N")[0].toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[18px] font-semibold leading-tight">{tenant?.name ?? "—"}</div>
          <div className="mt-0.5 flex items-center gap-3 text-[11px] text-muted-foreground">
            <span>subdomínio: {tenant?.subdomain ?? "—"}</span>
            <span>·</span>
            <span>moeda principal: {primaryCurrency}</span>
            <span>·</span>
            <span>id: {tenant?.id ?? "—"}</span>
          </div>
        </div>
      </div>

      {/* Health KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KpiTile label="Contas no PdC" value={String(accountCount)} hint={`${categorised} categorizadas`} />
        <KpiTile
          label="% categorizadas"
          value={`${pctCategorised}%`}
          hint={pctCategorised >= 90 ? "ótima cobertura" : pctCategorised >= 50 ? "bom" : "ainda baixa"}
          tone={pctCategorised >= 90 ? "ok" : pctCategorised >= 50 ? "warn" : "danger"}
        />
        <KpiTile label="Contas bancárias" value={String(bankAccountCount)} />
        <KpiTile
          label={`Saldo (${primaryCurrency})`}
          value={formatCurrency(totalBalance, primaryCurrency)}
        />
        <KpiTile
          label="Não-conciliado"
          value={String(kpis?.stale_unreconciled_count ?? "—")}
          hint={kpis?.stale_unreconciled_count ? "pendentes > 30d" : "sem pendências"}
          tone={(kpis?.stale_unreconciled_count ?? 0) > 0 ? "warn" : "ok"}
        />
      </div>

      {/* Entities + Chart of accounts: read-only summary tables.
          Entities table uses existing fields (CNPJ + endereço come in
          a follow-up migration). CoA table strips balance columns --
          this is a quick "what does this tenant's chart look like"
          glance, not the operational tree at /accounting/accounts. */}
      <div className="grid gap-3 lg:grid-cols-2">
        <EntitiesSummary />
        <ChartOfAccountsSummary accounts={accounts} />
      </div>

      {/* Configuration sections */}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        <ConfigCard
          icon={<Building2 className="h-4 w-4" />}
          title="Entidades"
          subtitle="Estrutura jurídica e centros de custo"
          to="/settings/entities"
        />
        <ConfigCard
          icon={<Users className="h-4 w-4" />}
          title="Usuários e permissões"
          subtitle="Acesso e papéis (em breve)"
          to="/admin/users"
        />
        <ConfigCard
          icon={<FileBarChart className="h-4 w-4" />}
          title="Modelos de demonstrativos"
          subtitle="DRE, Balanço, DFC personalizados"
          to="/reports"
        />
        <ConfigCard
          icon={<Brain className="h-4 w-4" />}
          title="Uso da IA"
          subtitle="Tokens, custos, limites"
          to="/settings/ai-usage"
        />
        <ConfigCard
          icon={<CreditCard className="h-4 w-4" />}
          title="Faturamento"
          subtitle="Plano, uso, faturas"
          to="/billing"
        />
        <ConfigCard
          icon={<Boxes className="h-4 w-4" />}
          title="Importações"
          subtitle="Templates, regras de substituição"
          to="/imports"
        />
        <ConfigCard
          icon={<Settings className="h-4 w-4" />}
          title="Outros parâmetros"
          subtitle="Ajustes gerais da empresa"
          to="/settings"
        />
      </div>

      <TenantThemeEditor open={themeEditorOpen} onClose={() => setThemeEditorOpen(false)} />
      <CompanyInfoEditor open={companyEditorOpen} onClose={() => setCompanyEditorOpen(false)} />
    </div>
  )
}

function KpiTile({
  label, value, hint, tone,
}: { label: string; value: string; hint?: string; tone?: "ok" | "warn" | "danger" }) {
  const valueClass =
    tone === "ok" ? "text-emerald-600"
    : tone === "warn" ? "text-amber-600"
    : tone === "danger" ? "text-destructive"
    : ""
  return (
    <div className="card-elevated p-3">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-[18px] font-semibold tabular-nums", valueClass)}>{value}</div>
      {hint ? <div className="mt-0.5 text-[10px] text-muted-foreground">{hint}</div> : null}
    </div>
  )
}

/** Entities summary table. Today the ``Entity`` model only carries
 *  name + parent + erp_id. The CNPJ / endereço / inscrição estadual
 *  columns referenced in the ask are pending a model migration; this
 *  component wires up the table layout and empty-cell placeholders so
 *  the migration lands behind a UI that's already shipped. */
function EntitiesSummary() {
  const { data: entities = [], isLoading } = useEntities()
  // MPTT lineage path. We don't get ``path`` from the lite endpoint
  // so we walk parent_id locally — fine for the typical tenant size
  // (10s of entities, not thousands).
  const byId = new Map(entities.map((e) => [e.id, e]))
  const pathOf = (eid: number): string => {
    const out: string[] = []
    let cur: { id: number; name: string; parent_id?: number | null } | undefined = byId.get(eid)
    const seen = new Set<number>()
    while (cur && !seen.has(cur.id)) {
      seen.add(cur.id)
      out.unshift(cur.name)
      cur = cur.parent_id != null ? byId.get(cur.parent_id) : undefined
    }
    return out.join(" › ")
  }
  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <Building2 className="h-3.5 w-3.5 text-primary" /> Entidades
        </div>
        <Link
          to="/settings/entities"
          className="text-[10px] text-muted-foreground hover:text-primary"
        >
          Editar
        </Link>
      </div>
      <div className="grid grid-cols-[1fr_120px_60px] items-center gap-2 border-b border-border/50 bg-surface-3 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div>Nome / Caminho</div>
        <div>CNPJ</div>
        <div className="text-right">Nível</div>
      </div>
      {isLoading ? (
        <div className="space-y-1 p-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-6 animate-pulse rounded bg-muted/40" />
          ))}
        </div>
      ) : entities.length === 0 ? (
        <div className="px-3 py-4 text-[11px] text-muted-foreground">
          Nenhuma entidade cadastrada para este tenant.
        </div>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          {entities.map((e) => (
            <div
              key={e.id}
              className="grid grid-cols-[1fr_120px_60px] items-center gap-2 border-b border-border/30 px-3 py-1.5 text-[11px] hover:bg-accent/30"
            >
              <div className="truncate" title={pathOf(e.id)}>
                <span className="font-medium">{e.name}</span>
                {e.parent_id != null ? (
                  <span className="ml-1 text-[10px] text-muted-foreground">
                    {pathOf(e.id)}
                  </span>
                ) : null}
              </div>
              <div className="truncate font-mono text-[10px] tabular-nums text-muted-foreground">
                {formatCnpj(e.cnpj) ?? "—"}
              </div>
              <div className="text-right text-[10px] tabular-nums text-muted-foreground">
                {e.level ?? 0}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="border-t border-border/40 bg-surface-2 px-3 py-1 text-[10px] text-muted-foreground">
        {entities.length} {entities.length === 1 ? "entidade" : "entidades"}
        {" · "}
        <Link to="/settings/entities" className="hover:text-primary">
          Editar campos completos
        </Link>
      </div>
    </div>
  )
}

/** Format a 14-digit CNPJ string as ``00.000.000/0000-00``. Returns
 *  ``null`` for nullable / partial values so the caller can fall
 *  back to its own placeholder. The model stores 14 digits with no
 *  mask (the ``Entity.clean()`` strips it on save), so this is the
 *  display-side counterpart. */
function formatCnpj(raw: string | null | undefined): string | null {
  if (!raw) return null
  const digits = raw.replace(/\D/g, "")
  if (digits.length !== 14) return raw  // show as-is if non-canonical
  return (
    digits.slice(0, 2) +
    "." + digits.slice(2, 5) +
    "." + digits.slice(5, 8) +
    "/" + digits.slice(8, 12) +
    "-" + digits.slice(12, 14)
  )
}

/** Read-only chart of accounts table. Strips balance / pending /
 *  unreconciled columns -- this view is a "what's wired up" snapshot,
 *  not the operational tree. Categories badge inline so the operator
 *  can scan classification at a glance. */
function ChartOfAccountsSummary({ accounts }: { accounts: AccountLite[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Group by ``effective_category`` (declared order from
  // CATEGORY_CODES_BY_ORDER). Uncategorised accounts go in their own
  // bucket at the bottom.
  const byCat = new Map<string, AccountLite[]>()
  for (const a of accounts) {
    const cat = a.effective_category ?? "(sem categoria)"
    const list = byCat.get(cat) ?? []
    list.push(a)
    byCat.set(cat, list)
  }
  // Stable order: declared categories first in their canonical order,
  // then "(sem categoria)" tail bucket.
  const ordered: Array<[string, AccountLite[]]> = []
  for (const code of CATEGORY_CODES_BY_ORDER) {
    if (byCat.has(code)) ordered.push([code, byCat.get(code)!])
  }
  if (byCat.has("(sem categoria)")) {
    ordered.push(["(sem categoria)", byCat.get("(sem categoria)")!])
  }

  const toggle = (cat: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })

  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold">
          <FileBarChart className="h-3.5 w-3.5 text-primary" /> Plano de contas
        </div>
        <Link
          to="/accounting/accounts"
          className="text-[10px] text-muted-foreground hover:text-primary"
        >
          Abrir completo
        </Link>
      </div>
      {accounts.length === 0 ? (
        <div className="px-3 py-4 text-[11px] text-muted-foreground">
          Nenhuma conta cadastrada.
        </div>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          {ordered.map(([cat, items]) => {
            const isOpen = expanded.has(cat)
            const label = REPORT_CATEGORY_STYLES[cat]?.label ?? "Sem categoria"
            return (
              <div key={cat}>
                <button
                  type="button"
                  onClick={() => toggle(cat)}
                  className="flex w-full items-center justify-between border-b border-border/40 bg-surface-3/40 px-3 py-1.5 text-[11px] font-semibold transition-colors hover:bg-accent/30"
                >
                  <span className="flex items-center gap-1.5">
                    {isOpen ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                    {label}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {items.length} {items.length === 1 ? "conta" : "contas"}
                  </span>
                </button>
                {isOpen &&
                  items.map((a) => (
                    <div
                      key={a.id}
                      className="grid grid-cols-[80px_1fr] items-center gap-2 border-b border-border/30 px-3 py-1 text-[11px] hover:bg-accent/20"
                      style={{ paddingLeft: 28 }}
                    >
                      <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                        {a.account_code ?? "—"}
                      </span>
                      <span className="truncate" title={a.name}>{a.name}</span>
                    </div>
                  ))}
              </div>
            )
          })}
        </div>
      )}
      <div className="border-t border-border/40 bg-surface-2 px-3 py-1 text-[10px] text-muted-foreground">
        {accounts.length} {accounts.length === 1 ? "conta" : "contas"}
        {" · "}
        <span className="italic">Visualização. Saldos no Plano de contas.</span>
      </div>
    </div>
  )
}

function ConfigCard({
  icon, title, subtitle, to,
}: { icon: React.ReactNode; title: string; subtitle: string; to: string }) {
  return (
    <Link
      to={to}
      className="group flex items-start gap-3 rounded-md border border-border bg-surface-2 p-3 transition-colors hover:bg-accent/50"
    >
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[13px] font-semibold leading-tight group-hover:text-primary">{title}</div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{subtitle}</div>
      </div>
    </Link>
  )
}
