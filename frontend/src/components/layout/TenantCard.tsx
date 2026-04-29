import { Link } from "react-router-dom"
import { Check, ChevronsUpDown, Settings2, Tag, Wallet } from "lucide-react"
import { useBankAccountsDashboardKpis } from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import { cn, formatCurrency } from "@/lib/utils"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

/**
 * Top-of-sidebar tenant identification card.
 *
 * Doubles as the tenant switcher: the entire card is a dropdown
 * trigger that lists every tenant the user belongs to, with the
 * active one marked. A "Abrir configuração" entry at the bottom of
 * the menu replaces the previous click-to-config behaviour, so the
 * card now has TWO clear roles: identity (visual) + switching (menu).
 *
 *   * Tenant name + first-letter avatar (colour derived from
 *     subdomain hash so each tenant looks distinct without fetching
 *     a real logo).
 *   * Two compact KPIs: account count and primary-currency total
 *     balance, sourced from ``useBankAccountsDashboardKpis`` so they
 *     piggyback on the same React Query cache the dashboard already
 *     populates.
 *
 * In the collapsed sidebar we fall back to just the avatar trigger.
 */
export function TenantCard({ collapsed }: { collapsed: boolean }) {
  const { tenant, tenants, switchTenant } = useTenant()
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
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            title={`${name} (${subdomain || "—"}) — trocar empresa`}
            className="mx-auto mt-2 grid h-9 w-9 place-items-center rounded-md text-[12px] font-bold text-primary-foreground transition-transform hover:scale-105"
            style={{ background: avatarColour }}
          >
            {initial}
          </button>
        </DropdownMenuTrigger>
        <TenantSwitcherMenu
          tenants={tenants}
          activeId={tenant?.id}
          onSwitch={switchTenant}
        />
      </DropdownMenu>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            "group mx-2 mt-2 block w-[calc(100%-1rem)] rounded-lg border border-border bg-surface-2 px-3 py-2 text-left transition-colors hover:bg-accent/50",
          )}
          title="Trocar empresa ou abrir configuração"
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
            <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground transition-colors group-hover:text-foreground" />
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-border/50 pt-1.5 text-[10px] text-muted-foreground">
            <span className="inline-flex items-center gap-1" title="Total de contas no plano de contas">
              <Tag className="h-3 w-3" /> {accountCount ?? "—"} contas
            </span>
            <span className="inline-flex items-center gap-1 tabular-nums" title="Saldo total na moeda principal">
              <Wallet className="h-3 w-3" /> {formatCurrency(totalBalance, primaryCurrency)}
            </span>
          </div>
        </button>
      </DropdownMenuTrigger>
      <TenantSwitcherMenu
        tenants={tenants}
        activeId={tenant?.id}
        onSwitch={switchTenant}
      />
    </DropdownMenu>
  )
}

interface TenantOption {
  id: number
  name: string
  subdomain: string
}

function TenantSwitcherMenu({
  tenants, activeId, onSwitch,
}: {
  tenants: TenantOption[]
  activeId: number | undefined
  onSwitch: (subdomain: string) => void
}) {
  return (
    <DropdownMenuContent align="start" className="w-64">
      <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Empresas
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      {tenants.length === 0 ? (
        <div className="px-2 py-1.5 text-xs text-muted-foreground">
          Nenhuma empresa disponível
        </div>
      ) : tenants.map((ten) => (
        <DropdownMenuItem
          key={ten.id}
          onClick={() => onSwitch(ten.subdomain)}
          className="cursor-pointer"
        >
          <span className="mr-2 inline-flex h-4 w-4 items-center justify-center">
            {activeId === ten.id && <Check className="h-3.5 w-3.5 text-primary" />}
          </span>
          <span className="truncate">{ten.name}</span>
          <span className="ml-auto text-[10px] text-muted-foreground">{ten.subdomain}</span>
        </DropdownMenuItem>
      ))}
      <DropdownMenuSeparator />
      <DropdownMenuItem asChild className="cursor-pointer">
        <Link to="/settings/tenant" className="flex items-center">
          <Settings2 className="mr-2 h-4 w-4" />
          Abrir configuração
        </Link>
      </DropdownMenuItem>
    </DropdownMenuContent>
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
