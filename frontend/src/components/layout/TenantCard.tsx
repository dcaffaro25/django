import { Link } from "react-router-dom"
import { ChevronRight, Wallet, Tag } from "lucide-react"
import { useBankAccountsDashboardKpis } from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import { cn, formatCurrency } from "@/lib/utils"

/**
 * Top-of-sidebar tenant identification card.
 *
 * Replaces the static Nord logo + tagline with a tenant-aware tile:
 *
 *   * Tenant name + first-letter avatar (colour derived from
 *     subdomain hash so each tenant looks distinct without fetching
 *     a real logo).
 *   * Two compact KPIs: account count and primary-currency total
 *     balance, sourced from ``useBankAccountsDashboardKpis`` so they
 *     piggyback on the same React Query cache the dashboard already
 *     populates.
 *   * Click target navigates to ``/settings/tenant`` for the
 *     full-page tenant config (entities, users, AI usage, billing).
 *
 * In the collapsed sidebar we fall back to just the avatar.
 */
export function TenantCard({ collapsed }: { collapsed: boolean }) {
  const { tenant } = useTenant()
  const { data: kpis } = useBankAccountsDashboardKpis()

  const initial = (tenant?.name?.[0] ?? "N").toUpperCase()
  const subdomain = tenant?.subdomain ?? ""
  const name = tenant?.name ?? "Nord"
  const avatarColour = colourForSubdomain(subdomain)

  const accountCount = kpis?.account_count ?? null
  const primaryCurrency = kpis?.currency_codes?.[0] ?? "BRL"
  const balanceMap = kpis?.balance_by_currency ?? {}
  const totalBalanceStr = balanceMap[primaryCurrency] ?? "0"
  const totalBalance = Number(totalBalanceStr) || 0

  if (collapsed) {
    return (
      <Link
        to="/settings/tenant"
        title={`${name} (${subdomain || "—"}) — abrir configuração`}
        className="mx-auto mt-2 grid h-9 w-9 place-items-center rounded-md text-[12px] font-bold text-primary-foreground transition-transform hover:scale-105"
        style={{ background: avatarColour }}
      >
        {initial}
      </Link>
    )
  }

  return (
    <Link
      to="/settings/tenant"
      className={cn(
        "group mx-2 mt-2 block rounded-lg border border-border bg-surface-2 px-3 py-2 transition-colors hover:bg-accent/50",
      )}
      title="Abrir configuração da empresa"
    >
      <div className="flex items-center gap-2">
        <div
          className="grid h-8 w-8 place-items-center rounded-md text-[12px] font-bold text-primary-foreground"
          style={{ background: avatarColour }}
        >
          {initial}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold leading-none">{name}</div>
          {subdomain ? (
            <div className="truncate text-[10px] text-muted-foreground">{subdomain}</div>
          ) : null}
        </div>
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 border-t border-border/50 pt-1.5 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1" title="Total de contas no plano de contas">
          <Tag className="h-3 w-3" /> {accountCount ?? "—"} contas
        </span>
        <span className="inline-flex items-center gap-1 tabular-nums" title="Saldo total na moeda principal">
          <Wallet className="h-3 w-3" /> {formatCurrency(totalBalance, primaryCurrency)}
        </span>
      </div>
    </Link>
  )
}

/** Deterministic colour from a subdomain string -- so the same tenant
 *  always gets the same avatar colour without fetching a real logo. */
function colourForSubdomain(s: string): string {
  if (!s) return "hsl(220 60% 55%)"
  let hash = 0
  for (let i = 0; i < s.length; i++) {
    hash = (hash << 5) - hash + s.charCodeAt(i)
    hash |= 0
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue} 65% 50%)`
}
