import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard, ArrowLeftRight, ListChecks, Sparkles, SlidersHorizontal, Workflow,
  Scale, Wallet, Receipt, BookOpen, FileBarChart, FileCog, CreditCard, Users, Boxes,
  Settings, ChevronLeft, PanelLeftOpen, Building2, CheckCircle2, Brain, Zap,
  FileSpreadsheet, FileText, FileCode, Shuffle, UploadCloud,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"

type NavItem = { key: string; path: string; icon: typeof LayoutDashboard }
type NavGroup = { key: string; items: NavItem[] }

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
    key: "integrations",
    items: [
      { key: "integrations_sandbox", path: "/integrations/sandbox", icon: Zap },
    ],
  },
  {
    key: "imports",
    items: [
      { key: "imports_etl", path: "/imports/etl", icon: UploadCloud },
      { key: "imports_ofx", path: "/imports/ofx", icon: FileText },
      { key: "imports_nf", path: "/imports/nf", icon: FileCode },
      { key: "imports_templates", path: "/imports/templates", icon: FileSpreadsheet },
      { key: "imports_substitutions", path: "/imports/substitutions", icon: Shuffle },
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
]

export function Sidebar() {
  const { t } = useTranslation()
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)

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
        {GROUPS.map((g, gi) => (
          <div key={g.key} className={cn("space-y-0.5", gi > 0 && "mt-3")}>
            {!collapsed && (
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {t(`nav.${g.key}`)}
              </div>
            )}
            {g.items.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.path === "/recon"}
                  title={collapsed ? t(`nav.${item.key}`) ?? undefined : undefined}
                  className={({ isActive }) =>
                    cn(
                      "group flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
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
