import { NavLink } from "react-router-dom"
import { 
  LayoutDashboard, 
  FileText, 
  BookOpen, 
  CreditCard, 
  RefreshCw, 
  Settings,
  ChevronLeft,
  ChevronRight,
  Receipt,
  Banknote,
  TrendingUp,
  Building2,
  MessageSquare
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useTenant } from "@/providers/TenantProvider"
import { Skeleton } from "@/components/ui/skeleton"

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

const navigation = [
  {
    title: "Accounting",
    items: [
      { label: "Transactions", path: "/accounting/transactions", icon: Receipt },
      { label: "Journal Entries", path: "/accounting/journal-entries", icon: BookOpen },
      { label: "Chart of Accounts", path: "/accounting/accounts", icon: FileText },
    ],
  },
  {
    title: "Banking & Reconciliation",
    items: [
      { label: "Bank Transactions", path: "/banking/bank-transactions", icon: Banknote },
      { label: "Reconciliation Dashboard", path: "/banking/reconciliation-dashboard", icon: LayoutDashboard },
      { label: "Reconciliation Tasks", path: "/banking/reconciliation-tasks", icon: RefreshCw },
      { label: "Reconciliation Configs", path: "/banking/reconciliation-configs", icon: Settings },
      { label: "Reconciliation Pipelines", path: "/banking/reconciliation-pipelines", icon: Settings },
    ],
  },
  {
    title: "Financial Statements",
    items: [
      { label: "Statements", path: "/financial-statements/statements", icon: TrendingUp },
      { label: "Templates", path: "/financial-statements/templates", icon: FileText },
    ],
  },
  {
    title: "AI & Tools",
    items: [
      { label: "AI Chat", path: "/chat", icon: MessageSquare },
      { label: "AI Template Test", path: "/ai-template-test", icon: FileText },
    ],
  },
  {
    title: "Other",
    items: [
      { label: "Billing", path: "/billing", icon: CreditCard },
      { label: "HR", path: "/hr", icon: Settings },
      { label: "Settings", path: "/settings", icon: Settings },
    ],
  },
]

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { tenant, tenants, isLoading, setTenant } = useTenant()

  return (
    <div
      className={cn(
        "flex flex-col border-r bg-gradient-to-b from-background to-muted/20 transition-all duration-300 shadow-sm",
        collapsed ? "w-20" : "w-72"
      )}
    >
      {/* Logo/Brand Section */}
      <div className="flex h-20 items-center justify-between border-b px-6">
        {!collapsed ? (
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <span className="text-lg font-bold">N</span>
            </div>
            <div className="flex flex-col">
              <h1 className="text-lg font-bold tracking-tight">NORD</h1>
              <p className="text-xs text-muted-foreground">Accounting</p>
            </div>
          </div>
        ) : (
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground mx-auto">
            <span className="text-lg font-bold">N</span>
          </div>
        )}
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={onToggle}
          className="h-8 w-8 hover:bg-accent"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
      
      {/* Tenant Selector */}
      {!collapsed && (
        <div className="border-b bg-muted/30 px-6 py-4">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Workspace
          </label>
          {isLoading ? (
            <Skeleton className="h-11 w-full rounded-lg" />
          ) : (
            <Select
              value={tenant?.subdomain || ""}
              onValueChange={(value) => {
                const selected = tenants.find((t) => t.subdomain === value)
                if (selected) setTenant(selected)
              }}
            >
              <SelectTrigger className="h-11 bg-background shadow-sm hover:bg-accent">
                <Building2 className="mr-2.5 h-4 w-4 text-muted-foreground" />
                <SelectValue placeholder="Select workspace" />
              </SelectTrigger>
              <SelectContent>
                {Array.isArray(tenants) && tenants.length > 0 ? (
                  tenants.map((t) => (
                    <SelectItem key={t.id} value={t.subdomain}>
                      {t.name}
                    </SelectItem>
                  ))
                ) : (
                  <div className="px-2 py-1.5 text-sm text-muted-foreground">No tenants available</div>
                )}
              </SelectContent>
            </Select>
          )}
        </div>
      )}
      
      {/* Navigation */}
      <nav className="flex-1 space-y-2 overflow-y-auto px-4 py-6">
        {navigation.map((section, sectionIdx) => (
          <div key={section.title} className={cn("space-y-1", sectionIdx > 0 && "mt-6")}>
            {!collapsed && (
              <h2 className="mb-2 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                {section.title}
              </h2>
            )}
            {section.items.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    cn(
                      "group flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all duration-200",
                      "hover:bg-accent hover:text-accent-foreground",
                      collapsed && "justify-center px-2",
                      isActive
                        ? "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90"
                        : "text-muted-foreground"
                    )
                  }
                >
                  <Icon className={cn(
                    "h-5 w-5 flex-shrink-0 transition-transform group-hover:scale-110",
                    collapsed && "mx-auto"
                  )} />
                  {!collapsed && (
                    <span className="truncate">{item.label}</span>
                  )}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
    </div>
  )
}

