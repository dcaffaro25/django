import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard, FileBarChart, FileCog, CreditCard, Users, Boxes,
  Settings, ChevronLeft, PanelLeftOpen, Zap, UploadCloud, Wallet,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"
import { useAuth } from "@/providers/AuthProvider"
import { useRunningImportCount } from "@/features/imports"
import { TenantCard } from "./TenantCard"

type NavItem = {
  key: string
  /** Display label (Portuguese, hard-coded -- the i18n keys lagged behind
   *  the UI redesign). */
  label: string
  /** Path the link navigates to. Each item is the index of a section
   *  whose sub-pages live under tabs in the destination. */
  path: string
  icon: typeof LayoutDashboard
  /** When set, the NavLink uses ``end`` matching so a deeper child
   *  route doesn't make the parent appear active. */
  end?: boolean
}

type NavGroup = {
  key: string
  /** Display heading above the items (or null for ungrouped). */
  label: string | null
  items: NavItem[]
  /** Rendered only when the predicate is true. */
  visible?: (ctx: { isSuperuser: boolean }) => boolean
}

// Each group corresponds to a single sidebar section. Many sub-pages
// previously listed here moved into tabbed shells inside the destination
// page (see TabbedShell + the wrapper pages under /recon, /accounting,
// /reports). The sidebar now surfaces ONE entry per section.
const GROUPS: NavGroup[] = [
  {
    key: "operations",
    label: "Operação",
    items: [
      { key: "reconciliation", label: "Conciliação", path: "/recon", icon: LayoutDashboard },
      { key: "accounting", label: "Contabilidade", path: "/accounting/accounts", icon: Wallet },
      { key: "reports", label: "Demonstrativos", path: "/reports", icon: FileBarChart },
      { key: "imports", label: "Importações", path: "/imports", icon: UploadCloud },
    ],
  },
  {
    key: "tools",
    label: "Ferramentas",
    items: [
      { key: "integrations_sandbox", label: "Sandbox de API", path: "/integrations/sandbox", icon: Zap },
    ],
  },
  {
    key: "other",
    label: "Outros",
    items: [
      { key: "billing", label: "Faturamento", path: "/billing", icon: CreditCard },
      { key: "hr", label: "RH", path: "/hr", icon: Users },
      { key: "inventory", label: "Estoque", path: "/inventory", icon: Boxes },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    items: [
      { key: "tenant", label: "Empresa", path: "/settings/tenant", icon: Settings },
      { key: "templates", label: "Modelos legados", path: "/statements/templates", icon: FileCog },
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

      {/* Tenant identity card -- click-through to /settings/tenant. */}
      <TenantCard collapsed={collapsed} />

      <div className="mx-3 my-2 h-px bg-border" />

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {visibleGroups.map((g, gi) => (
          <div key={g.key} className={cn("space-y-0.5", gi > 0 && "mt-3")}>
            {!collapsed && g.label ? (
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {g.label}
              </div>
            ) : null}
            {g.items.map((item) => {
              const Icon = item.icon
              const showImportBadge = item.key === "imports"
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.end}
                  title={collapsed ? item.label : undefined}
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
                      {!collapsed && <span className="truncate">{item.label}</span>}
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
