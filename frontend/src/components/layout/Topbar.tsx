import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import {
  Activity, AlertTriangle, Bug, Eye,
  GitBranch, LogOut, Moon, Palette, Search, Server, ShieldCheck, Sun, Users,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"
import { useAuth } from "@/providers/AuthProvider"
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
  const { user, logout } = useAuth()
  const setCommandOpen = useAppStore((s) => s.setCommandOpen)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const viewAsViewer = useAppStore((s) => s.viewAsViewer)
  const setViewAsViewer = useAppStore((s) => s.setViewAsViewer)
  // ``isSuperuser`` MUST come from useUserRole (not useAuth) so the
  // view-as-viewer overlay correctly hides the Administração section
  // -- a Django superuser previewing as viewer should see what
  // their viewer sees, with no admin links bleeding through.
  // ``actualRole`` is unaffected by the overlay so the preview
  // toggle item itself stays available.
  const { me, actualRole, isSuperuser, canWrite } = useUserRole()
  const updatePrefs = useUpdatePreferences()
  const canPreviewAsViewer =
    actualRole === "manager" || actualRole === "owner" || actualRole === "superuser"

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
        {/* Notifications */}
        <NotificationBell />

        {/* Palette picker — internal/operator tooling. Hidden from
            viewers (and from operators in view-as-viewer preview) so
            external clients see the locked-in tenant look without a
            "select a different palette" affordance. */}
        {canWrite && <ThemePicker />}

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
                {/* "View as viewer" preview -- only offered to
                    managers / owners / superusers (lower roles
                    already see the viewer surface). The actual
                    backend role is untouched; this just shapes the
                    UI client-side so operators can verify what an
                    external tenant user sees. */}
                {canPreviewAsViewer && (
                  <DropdownMenuItem onClick={() => setViewAsViewer(!viewAsViewer)} className="cursor-pointer">
                    <Eye className="mr-2 h-4 w-4" />
                    <span className="flex-1">
                      {viewAsViewer ? "Sair do preview de cliente" : "Ver como cliente"}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {viewAsViewer ? "ativo" : "viewer"}
                    </span>
                  </DropdownMenuItem>
                )}
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
