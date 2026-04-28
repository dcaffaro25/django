import { Link } from "react-router-dom"
import { Building2, Users, Brain, CreditCard, FileBarChart, Settings, Boxes } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useBankAccountsDashboardKpis } from "@/features/reconciliation"
import { useAccounts } from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import { cn, formatCurrency } from "@/lib/utils"

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
