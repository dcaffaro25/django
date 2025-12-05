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
  Building2
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
        "flex flex-col border-r bg-card transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      <div className="flex h-16 items-center justify-between border-b px-4">
        {!collapsed && <h1 className="text-lg font-semibold">NORD</h1>}
        <Button variant="ghost" size="icon" onClick={onToggle}>
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
      
      {/* Tenant Selector */}
      {!collapsed && (
        <div className="border-b p-4">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Tenant
          </label>
          {isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <Select
              value={tenant?.subdomain || ""}
              onValueChange={(value) => {
                const selected = tenants.find((t) => t.subdomain === value)
                if (selected) setTenant(selected)
              }}
            >
              <SelectTrigger>
                <Building2 className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Select tenant" />
              </SelectTrigger>
              <SelectContent>
                {tenants.map((t) => (
                  <SelectItem key={t.id} value={t.subdomain}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      )}
      <nav className="flex-1 space-y-1 overflow-y-auto p-4">
        {navigation.map((section) => (
          <div key={section.title} className="space-y-1">
            {!collapsed && (
              <h2 className="px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
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
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                      collapsed && "justify-center"
                    )
                  }
                >
                  <Icon className="h-5 w-5 flex-shrink-0" />
                  {!collapsed && <span>{item.label}</span>}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
    </div>
  )
}

