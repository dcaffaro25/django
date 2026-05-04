import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard, FileBarChart, FileCog, CreditCard, Users, Boxes,
  Settings, ChevronLeft, PanelLeftOpen, Zap, UploadCloud, Wallet,
  Activity,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"
import { useUserRole } from "@/features/auth/useUserRole"
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
  /** True when the section requires write access. Hidden from
   *  ``viewer`` role accounts (read-only external users). */
  requiresWrite?: boolean
}

type NavGroup = {
  key: string
  /** Display heading above the items (or null for ungrouped). */
  label: string | null
  items: NavItem[]
  /** Rendered only when the predicate is true. */
  visible?: (ctx: { isSuperuser: boolean; canWrite: boolean }) => boolean
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
      // Read-only viewers see Conciliação dashboards, the chart of
      // accounts (read-only) and the financial statements. They do
      // NOT see Importações — that's a write-heavy section.
      { key: "reconciliation", label: "Conciliação", path: "/recon", icon: LayoutDashboard },
      { key: "accounting", label: "Contabilidade", path: "/accounting/accounts", icon: Wallet },
      { key: "reports", label: "Demonstrativos", path: "/reports", icon: FileBarChart },
      // Cross-domain "what's broken in our pipelines" dashboard. Lives
      // under /operacao/saude (top-level), with /billing/saude kept as
      // a bookmark-compatible alias.
      { key: "data_health", label: "Saúde dos Dados", path: "/operacao/saude", icon: Activity },
      { key: "imports", label: "Importações", path: "/imports", icon: UploadCloud, requiresWrite: true },
    ],
  },
  {
    key: "tools",
    label: "Ferramentas",
    // Sandbox is a developer tool — only show to operators+.
    visible: ({ canWrite }) => canWrite,
    items: [
      { key: "integrations_sandbox", label: "Sandbox de API", path: "/integrations/sandbox", icon: Zap, requiresWrite: true },
      // Phase-1 do plano Sandbox API: catálogo estruturado.
      { key: "integrations_api_defs", label: "Definições de API", path: "/integrations/api-definitions", icon: FileCog, requiresWrite: true },
    ],
  },
  {
    key: "other",
    label: "Outros",
    items: [
      // Billing visible to viewers (they may want to see invoices).
      // HR / Inventory are write-heavy modules; hide for viewers.
      { key: "billing", label: "Faturamento", path: "/billing", icon: CreditCard },
      { key: "hr", label: "RH", path: "/hr", icon: Users, requiresWrite: true },
      { key: "inventory", label: "Estoque", path: "/inventory", icon: Boxes, requiresWrite: true },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    // Whole config section is operator+ — viewer can't change tenant
    // settings or report templates.
    visible: ({ canWrite }) => canWrite,
    items: [
      { key: "tenant", label: "Empresa", path: "/settings/tenant", icon: Settings, requiresWrite: true },
      { key: "templates", label: "Modelos legados", path: "/statements/templates", icon: FileCog, requiresWrite: true },
    ],
  },
]

export function Sidebar() {
  const { t } = useTranslation()
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)
  // ``isSuperuser`` here MUST come from useUserRole, not useAuth.
  // The view-as-viewer overlay flips the useUserRole role to
  // "viewer", which makes isSuperuser=false in the role hook --
  // but useAuth().isSuperuser is the raw Django auth flag and is
  // unaffected by the overlay. Reading useAuth here meant
  // ``effectiveCanWrite`` stayed true for Django superusers in
  // preview mode, defeating the entire feature.
  const { canWrite, isLoading: roleLoading, role, isSuperuser } = useUserRole()
  // While the role is loading we render the full sidebar (so the
  // page doesn't flicker for operators+). Once loaded, viewers
  // (canWrite=false, role!=null) see a trimmed sidebar.
  const effectiveCanWrite = isSuperuser || canWrite || roleLoading || !role
  const visibleGroups = GROUPS
    .filter((g) => !g.visible || g.visible({ isSuperuser, canWrite: effectiveCanWrite }))
    .map((g) => ({
      ...g,
      // Filter individual items inside each group too — a group may
      // have a mix of read-only and write items.
      items: g.items.filter((i) => !i.requiresWrite || effectiveCanWrite),
    }))
    .filter((g) => g.items.length > 0)

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
            <span className="text-[13px] font-semibold leading-tight">{t("app.name")}</span>
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
