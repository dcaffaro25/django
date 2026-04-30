import { useNavigate } from "react-router-dom"
import { Check, ChevronsUpDown, Settings2, Tag, Wallet } from "lucide-react"
import { useBankAccountsDashboardKpis } from "@/features/reconciliation"
import { useTenant } from "@/providers/TenantProvider"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency } from "@/lib/utils"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

/**
 * Top-of-sidebar tenant identification card.
 *
 * Doubles as the tenant switcher: the entire card is a dropdown
 * trigger. The menu has THREE click targets per row (so the same
 * dropdown handles "open this tenant's config", "switch to that
 * tenant but stay on the current page", and "switch + open that
 * tenant's config" without needing a separate UI per intent):
 *
 *   1. **"Abrir configuração"** at the top -- opens the active
 *      tenant's config without changing tenant. Highest position
 *      because it's the most-used path from this menu.
 *   2. **Tenant row click** -- switches to that tenant, stays on
 *      the same route. The pre-65e4a6c default behaviour, kept.
 *   3. **Settings icon next to a non-active tenant** -- switches
 *      AND navigates to /settings/tenant. The fast path for
 *      operators who manage several tenants and want to jump
 *      between their config screens.
 *
 * Avatar prefers ``theme.logo_url`` (set in the TenantThemeEditor)
 * when available; otherwise falls back to a deterministic letter
 * avatar so each tenant looks distinct without an explicit logo.
 *
 * In the collapsed sidebar we fall back to just the avatar trigger.
 */
export function TenantCard({ collapsed }: { collapsed: boolean }) {
  const { tenant, tenants, switchTenant } = useTenant()
  const { theme: tenantTheme, me, canWrite } = useUserRole()
  const { data: kpis } = useBankAccountsDashboardKpis()
  const navigate = useNavigate()

  const initial = (tenant?.name?.[0] ?? "N").toUpperCase()
  const subdomain = tenant?.subdomain ?? ""
  const name = tenant?.name ?? "Nord"
  const avatarColour = colourForSubdomain(subdomain)
  const useDarkLogo = !!me?.prefer_dark_mode && !!tenantTheme?.logo_dark_url
  const logoUrl = useDarkLogo ? tenantTheme?.logo_dark_url : tenantTheme?.logo_url

  const accountCount = kpis?.account_count ?? null
  const primaryCurrency = kpis?.currency_codes?.[0] ?? "BRL"
  const balanceMap = kpis?.balance_by_currency ?? {}
  const totalBalanceStr = balanceMap[primaryCurrency] ?? "0"
  const totalBalance = Number(totalBalanceStr) || 0

  const onSwitchAndConfig = (sub: string) => {
    switchTenant(sub)
    navigate("/settings/tenant")
  }
  const onOpenCurrentConfig = () => {
    navigate("/settings/tenant")
  }

  // Viewers (and operators in view-as-viewer preview) see a STATIC
  // card with the current tenant's identity -- no dropdown, no
  // switcher. External clients are scoped to a single tenant and
  // shouldn't see other tenants in a menu, even if they technically
  // have membership elsewhere; switching tenants is an account-level
  // action, not a per-session UI affordance.
  const switcherEnabled = canWrite

  if (collapsed) {
    const avatar = (
      <span
        className="mx-auto mt-2 grid h-9 w-9 place-items-center overflow-hidden rounded-md text-[12px] font-bold text-primary-foreground"
        style={logoUrl ? undefined : { background: avatarColour }}
      >
        {logoUrl ? (
          <img src={logoUrl} alt={name} className="h-full w-full object-cover" />
        ) : (
          initial
        )}
      </span>
    )

    if (!switcherEnabled) {
      return (
        <div title={`${name} (${subdomain || "—"})`}>{avatar}</div>
      )
    }

    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            title={`${name} (${subdomain || "—"}) — trocar empresa`}
            className="mx-auto mt-2 grid h-9 w-9 place-items-center overflow-hidden rounded-md text-[12px] font-bold text-primary-foreground transition-transform hover:scale-105"
            style={logoUrl ? undefined : { background: avatarColour }}
          >
            {logoUrl ? (
              <img src={logoUrl} alt={name} className="h-full w-full object-cover" />
            ) : (
              initial
            )}
          </button>
        </DropdownMenuTrigger>
        <TenantSwitcherMenu
          tenants={tenants}
          activeId={tenant?.id}
          onSwitch={switchTenant}
          onSwitchAndConfig={onSwitchAndConfig}
          onOpenCurrentConfig={onOpenCurrentConfig}
          canConfigure={canWrite}
        />
      </DropdownMenu>
    )
  }

  // Expanded card content -- shared between the interactive (dropdown
  // trigger) and static (viewer) variants so both surfaces stay
  // visually identical.
  const cardBody = (
    <>
      <div className="flex items-center gap-3">
        {/* Avatar/logo at the same scale as the identity card on
            /settings/tenant (h-14) so both surfaces feel like the
            same thing. */}
        <div
          className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-lg text-[20px] font-bold text-primary-foreground shadow-sm"
          style={logoUrl ? undefined : { background: avatarColour }}
        >
          {logoUrl ? (
            <img src={logoUrl} alt={name} className="h-full w-full object-contain" />
          ) : (
            initial
          )}
        </div>
        {/* Name + subdomain stacked to the right of the icon.
            Bigger weight than before so the tenant identity is
            unmistakable at a glance. */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-semibold leading-tight">{name}</div>
          {subdomain ? (
            <div className="truncate text-[11px] text-muted-foreground">{subdomain}</div>
          ) : null}
        </div>
        {switcherEnabled && (
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-border/50 pt-2 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1" title="Total de contas no plano de contas">
          <Tag className="h-3 w-3" /> {accountCount ?? "—"} contas
        </span>
        <span className="inline-flex items-center gap-1 tabular-nums" title="Saldo total na moeda principal">
          <Wallet className="h-3 w-3" /> {formatCurrency(totalBalance, primaryCurrency)}
        </span>
      </div>
    </>
  )

  if (!switcherEnabled) {
    return (
      <div
        className="mx-2 mt-2 block w-[calc(100%-1rem)] rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-left"
        title={`${name} (${subdomain || "—"})`}
      >
        {cardBody}
      </div>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            "group mx-2 mt-2 block w-[calc(100%-1rem)] rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-left transition-colors hover:bg-accent/50",
          )}
          title="Trocar empresa ou abrir configuração"
        >
          {cardBody}
        </button>
      </DropdownMenuTrigger>
      <TenantSwitcherMenu
        tenants={tenants}
        activeId={tenant?.id}
        onSwitch={switchTenant}
        onSwitchAndConfig={onSwitchAndConfig}
        onOpenCurrentConfig={onOpenCurrentConfig}
        canConfigure={canWrite}
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
  tenants, activeId, onSwitch, onSwitchAndConfig, onOpenCurrentConfig, canConfigure,
}: {
  tenants: TenantOption[]
  activeId: number | undefined
  onSwitch: (subdomain: string) => void
  onSwitchAndConfig: (subdomain: string) => void
  onOpenCurrentConfig: () => void
  /** When false (viewer / view-as-viewer preview), hide the
   *  config entries. The tenant switcher itself stays visible
   *  -- a viewer might still belong to multiple tenants. */
  canConfigure: boolean
}) {
  return (
    <DropdownMenuContent align="start" className="w-72">
      {/* Primary action FIRST -- most-used path from this menu.
          Hidden in viewer mode: viewers can't edit, so showing
          them a config link that 403s on every action would just
          confuse. */}
      {canConfigure && (
        <>
          <DropdownMenuItem onClick={onOpenCurrentConfig} className="cursor-pointer">
            <Settings2 className="mr-2 h-4 w-4 text-primary" />
            <span>Abrir configuração</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
        </>
      )}
      <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Trocar empresa
      </DropdownMenuLabel>
      {tenants.length === 0 ? (
        <div className="px-2 py-1.5 text-xs text-muted-foreground">
          Nenhuma empresa disponível
        </div>
      ) : tenants.map((ten) => {
        const isActive = activeId === ten.id
        return (
          <DropdownMenuItem
            key={ten.id}
            onClick={() => { if (!isActive) onSwitch(ten.subdomain) }}
            className={cn("cursor-pointer", isActive && "opacity-90")}
          >
            <span className="mr-2 inline-flex h-4 w-4 items-center justify-center">
              {isActive && <Check className="h-3.5 w-3.5 text-primary" />}
            </span>
            <span className="truncate">{ten.name}</span>
            <span className="ml-2 truncate text-[10px] text-muted-foreground">{ten.subdomain}</span>
            {/* Per-tenant shortcut: switch AND open that tenant's
                config in one click. Hidden on the active tenant
                (its config is the top entry) and on viewer accounts
                (the target page would 403 every action anyway). */}
            {!isActive && canConfigure && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  e.preventDefault()
                  onSwitchAndConfig(ten.subdomain)
                }}
                title="Trocar para esta empresa e abrir sua configuração"
                aria-label={`Abrir configuração de ${ten.name}`}
                className="ml-auto grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <Settings2 className="h-3.5 w-3.5" />
              </button>
            )}
          </DropdownMenuItem>
        )
      })}
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
