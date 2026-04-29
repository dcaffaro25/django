import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import {
  Activity, AlertTriangle, Bug, Building2, Check, ChevronsUpDown,
  GitBranch, LogOut, Moon, Palette, Search, Server, ShieldCheck, Sun, Users,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"
import { useAuth } from "@/providers/AuthProvider"
import { useTenant } from "@/providers/TenantProvider"
import { useUserRole } from "@/features/auth/useUserRole"
import { useUpdatePreferences } from "@/features/auth/usePreferences"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Breadcrumbs } from "./Breadcrumbs"
import { NotificationBell } from "./NotificationBell"
import { ThemePicker } from "./ThemePicker"

/**
 * Platform-admin entries. Rendered inside the user dropdown — not
 * the sidebar — because they're operator-tooling for superusers,
 * not part of the day-to-day tenant workflow. Visibility is
 * gated on ``isSuperuser`` at the menu level; each route is also
 * protected by ``SuperuserGuard`` + the backend's ``IsSuperUser``
 * permission class, so this is UX gating, not authorization.
 */
const ADMIN_LINKS = [
  { to: "/admin", label: "Administração", icon: ShieldCheck },
  { to: "/admin/users", label: "Usuários", icon: Users },
  { to: "/admin/activity", label: "Atividade", icon: Activity },
  { to: "/admin/activity/funnels", label: "Funis", icon: GitBranch },
  { to: "/admin/activity/friction", label: "Fricção", icon: AlertTriangle },
  { to: "/admin/activity/errors", label: "Erros", icon: Bug },
  { to: "/admin/runtime", label: "Runtime", icon: Server },
] as const

export function Topbar() {
  const { t } = useTranslation()
  const { user, logout, isSuperuser } = useAuth()
  const { tenant, tenants, switchTenant } = useTenant()
  const setCommandOpen = useAppStore((s) => s.setCommandOpen)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const { me } = useUserRole()
  const updatePrefs = useUpdatePreferences()

  const onToggleDark = () => {
    const next = theme === "dark" ? "light" : "dark"
    setTheme(next)
    if (me) updatePrefs.mutate({ prefer_dark_mode: next === "dark" })
  }

  const onToggleTenantTheme = () => {
    if (!me) return
    updatePrefs.mutate({ use_tenant_theme: !me.use_tenant_theme })
  }

  const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform)
  const kbd = isMac ? "⌘K" : "Ctrl+K"

  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border surface-1 px-4">
      <div className="flex min-w-0 items-center gap-3">
        <Breadcrumbs />
      </div>

      <button
        onClick={() => setCommandOpen(true)}
        className={cn(
          "group flex h-8 w-[360px] max-w-[50vw] items-center gap-2 rounded-md border border-border bg-background px-2.5 text-[13px] text-muted-foreground transition-colors hover:border-ring/40",
        )}
      >
        <Search className="h-3.5 w-3.5" />
        <span className="truncate">{t("command.placeholder")}</span>
        <span className="ml-auto text-kbd">{kbd}</span>
      </button>

      <div className="flex items-center gap-1.5">
        {/* Tenant switcher */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-[13px] hover:bg-accent">
              <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="max-w-[140px] truncate font-medium">{tenant?.name ?? t("tenant.select")}</span>
              <ChevronsUpDown className="h-3 w-3 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>{t("tenant.workspace")}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {tenants.length === 0 ? (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">{t("tenant.no_tenants")}</div>
            ) : tenants.map((ten) => (
              <DropdownMenuItem
                key={ten.id}
                onClick={() => switchTenant(ten.subdomain)}
                className="cursor-pointer"
              >
                <span className="mr-2 inline-flex h-4 w-4 items-center justify-center">
                  {tenant?.id === ten.id && <Check className="h-3.5 w-3.5 text-primary" />}
                </span>
                <span className="truncate">{ten.name}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">{ten.subdomain}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Notifications */}
        <NotificationBell />

        {/* Palette picker */}
        <ThemePicker />

        {/* Light/dark toggle — also persists to /api/core/me/preferences/
            so the choice follows the user across devices. */}
        <button
          onClick={onToggleDark}
          className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {/* User */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="grid h-8 w-8 place-items-center rounded-full bg-primary/15 text-[12px] font-semibold text-primary hover:bg-primary/25">
              {(user?.username?.[0] ?? "U").toUpperCase()}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-sm font-medium">
                  {user?.display_name ?? user?.username ?? "—"}
                </span>
                {user?.email && <span className="text-xs text-muted-foreground">{user.email}</span>}
              </div>
            </DropdownMenuLabel>
            {/* Display preferences — every authenticated user can
                flip between system colours and the active tenant's
                brand palette. The toggle is hidden when /api/core/me/
                hasn't loaded yet to avoid a flicker on app boot. */}
            {me && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onToggleTenantTheme} className="cursor-pointer">
                  <Palette className="mr-2 h-4 w-4" />
                  <span className="flex-1">
                    {me.use_tenant_theme ? "Cores do tenant" : "Cores do sistema"}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {me.use_tenant_theme ? "tenant" : "sistema"}
                  </span>
                </DropdownMenuItem>
              </>
            )}
            {/* Admin entries — superuser only. Non-superusers don't
                see the group at all (not just disabled), matching the
                backend's "hide, don't tease" policy on admin routes. */}
            {isSuperuser && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Administração da plataforma
                </DropdownMenuLabel>
                {ADMIN_LINKS.map(({ to, label, icon: Icon }) => (
                  <DropdownMenuItem key={to} asChild className="cursor-pointer">
                    <Link to={to} className="flex items-center">
                      <Icon className="mr-2 h-4 w-4" />
                      {label}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="cursor-pointer text-destructive focus:text-destructive">
              <LogOut className="mr-2 h-4 w-4" />
              {t("auth.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
