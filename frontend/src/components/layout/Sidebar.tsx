import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard, ArrowLeftRight, ListChecks, Sparkles, SlidersHorizontal, Workflow,
  Scale, Wallet, Receipt, BookOpen, FileBarChart, FileCog, CreditCard, Users, Boxes,
  Settings, ChevronLeft, PanelLeftOpen, Building2, CheckCircle2, Brain, Zap,
  FileSpreadsheet, Shuffle, UploadCloud, ShieldCheck, Activity, GitBranch, AlertTriangle,
  Bug,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"
import { useAuth } from "@/providers/AuthProvider"
import { useRunningImportCount } from "@/features/imports"

type NavItem = { key: string; path: string; icon: typeof LayoutDashboard }
type NavGroup = { key: string; items: NavItem[]; /** Rendered only when the predicate is true. */
  visible?: (ctx: { isSuperuser: boolean }) => boolean }

const GROUPS: NavGroup[] = [
  {
    key: "reconciliation",
    items: [
      { key: "reconciliation_dashboard", path: "/recon", icon: LayoutDashboard },
      { key: "reconciliation_workbench", path: "/recon/workbench", icon: ArrowLeftRight },
      { key: "reconciliation_matches", path: "/recon/matches", icon: CheckCircle2 },
      { key: "reconciliation_tasks", path: "/recon/tasks", icon: ListChecks },
      { key: "reconciliation_suggestions", path: "/recon/suggestions", icon: Sparkles },
      { key: "reconciliation_configs", path: "/recon/configs", icon: SlidersHorizontal },
      { key: "reconciliation_pipelines", path: "/recon/pipelines", icon: Workflow },
      { key: "reconciliation_embeddings", path: "/recon/embeddings", icon: Brain },
      { key: "reconciliation_balances", path: "/recon/balances", icon: Scale },
    ],
  },
  {
    key: "accounting",
    items: [
      { key: "bank_accounts", path: "/accounting/bank-accounts", icon: Wallet },
      { key: "bank_transactions", path: "/accounting/bank-transactions", icon: Wallet },
      { key: "transactions", path: "/accounting/transactions", icon: Receipt },
      { key: "journal_entries", path: "/accounting/journal-entries", icon: BookOpen },
      { key: "accounts", path: "/accounting/accounts", icon: FileCog },
    ],
  },
  {
    key: "financial_statements",
    items: [
      { key: "statements", path: "/statements", icon: FileBarChart },
      { key: "templates", path: "/statements/templates", icon: FileCog },
    ],
  },
  {
    key: "reports_beta",
    items: [
      { key: "reports_build", path: "/reports/build", icon: FileBarChart },
      { key: "reports_history", path: "/reports/history", icon: ListChecks },
      { key: "ai_usage", path: "/settings/ai-usage", icon: Brain },
    ],
  },
  {
    key: "integrations",
    items: [
      { key: "integrations_sandbox", path: "/integrations/sandbox", icon: Zap },
    ],
  },
  {
    key: "other",
    items: [
      { key: "billing", path: "/billing", icon: CreditCard },
      { key: "hr", path: "/hr", icon: Users },
      { key: "inventory", path: "/inventory", icon: Boxes },
      { key: "entities", path: "/settings/entities", icon: Building2 },
      { key: "settings", path: "/settings", icon: Settings },
    ],
  },
  // Import/utility shortcuts pinned at the bottom of the sidebar so operator
  // flows (conciliação, contabilidade) aren't pushed down by these.
  {
    key: "imports",
    items: [
      { key: "imports_hub", path: "/imports", icon: UploadCloud },
      { key: "imports_templates", path: "/imports/templates", icon: FileSpreadsheet },
      { key: "imports_substitutions", path: "/imports/substitutions", icon: Shuffle },
    ],
  },
  // Platform-admin area. Hidden entirely from non-superusers — no
  // "coming soon" teasing, no 403 click — matching the backend's
  // IsSuperUser check on /api/admin/*.
  {
    key: "admin",
    visible: ({ isSuperuser }) => isSuperuser,
    items: [
      { key: "admin_home", path: "/admin", icon: ShieldCheck },
      { key: "admin_users", path: "/admin/users", icon: Users },
      { key: "admin_activity", path: "/admin/activity", icon: Activity },
      { key: "admin_activity_funnels", path: "/admin/activity/funnels", icon: GitBranch },
      { key: "admin_activity_friction", path: "/admin/activity/friction", icon: AlertTriangle },
      { key: "admin_activity_errors", path: "/admin/activity/errors", icon: Bug },
    ],
  },
]

export function Sidebar() {
  const { t } = useTranslation()
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)
  const { isSuperuser } = useAuth()
  const visibleGroups = GROUPS.filter((g) => !g.visible || g.visible({ isSuperuser }))

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-border surface-1 transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div className={cn("flex h-12 items-center justify-between gap-2 px-3", collapsed && "justify-center px-0")}>
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-primary text-primary-foreground text-[11px] font-bold tracking-tight">
            N
          </div>
          {!collapsed && (
            <div className="flex flex-col leading-tight">
              <span className="text-[13px] font-semibold">{t("app.name")}</span>
              <span className="text-[10px] text-muted-foreground">{t("app.tagline")}</span>
            </div>
          )}
        </div>
        {!collapsed && (
          <button
            onClick={toggle}
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Collapse sidebar"
            title="Collapse (⌘B)"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="mx-3 my-1 h-px bg-border" />

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {visibleGroups.map((g, gi) => (
          <div key={g.key} className={cn("space-y-0.5", gi > 0 && "mt-3")}>
            {!collapsed && (
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {t(`nav.${g.key}`)}
              </div>
            )}
            {g.items.map((item) => {
              const Icon = item.icon
              const showImportBadge =
                item.key === "imports_hub" || item.key === "imports_templates"
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.path === "/recon"}
                  title={collapsed ? t(`nav.${item.key}`) ?? undefined : undefined}
                  className={({ isActive }) =>
                    cn(
                      "group relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
                      collapsed && "justify-center px-0",
                      isActive
                        ? "bg-primary/15 text-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-primary")} />
                      {!collapsed && <span className="truncate">{t(`nav.${item.key}`)}</span>}
                      {showImportBadge && <ImportsRunningBadge collapsed={collapsed} />}
                    </>
                  )}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>

      {collapsed && (
        <button
          onClick={toggle}
          className="mx-auto mb-2 grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Expand sidebar"
          title="Expand (⌘B)"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
      )}
    </aside>
  )
}

/**
 * Sidebar badge for the Imports nav items (Phase 6.z-b).
 *
 * Renders nothing while the count is zero. When non-zero, shows the
 * number in a small pill next to the label (expanded sidebar) or as
 * a dot on the icon (collapsed sidebar). Colour intent:
 *
 *   - **Red** when any session is ``awaiting_resolve`` (operator
 *     attention needed).
 *   - **Amber** otherwise (background work — analyze / commit in
 *     flight).
 *
 * Hover tooltip breaks down the three buckets.
 */
function ImportsRunningBadge({ collapsed }: { collapsed: boolean }) {
  const { data } = useRunningImportCount()
  if (!data || data.total === 0) return null

  const needsAttention = data.awaiting_resolve > 0
  const tone = needsAttention
    ? "bg-destructive text-destructive-foreground"
    : "bg-amber-500 text-white"

  const tooltip = [
    data.awaiting_resolve > 0
      ? `${data.awaiting_resolve} aguardando resolução`
      : null,
    data.analyzing > 0 ? `${data.analyzing} analisando` : null,
    data.committing > 0 ? `${data.committing} importando` : null,
  ]
    .filter(Boolean)
    .join(" · ")

  if (collapsed) {
    return (
      <span
        className={cn(
          "absolute right-1 top-1 h-2 w-2 rounded-full ring-2 ring-background",
          tone,
        )}
        title={tooltip}
        aria-label={tooltip}
      />
    )
  }

  return (
    <span
      className={cn(
        "ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 text-[10px] font-bold leading-none",
        tone,
      )}
      title={tooltip}
      aria-label={tooltip}
    >
      {data.total}
    </span>
  )
}
