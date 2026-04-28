import { NavLink, useLocation } from "react-router-dom"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Tab strip used at the top of consolidated landing pages
 * (``/recon``, ``/accounting``, ``/reports``, ``/imports``,
 * ``/settings``). Renders one ``NavLink`` per tab and lets the router
 * resolve the active state. Wraps the per-tab page below.
 *
 * Why a strip instead of a Radix Tabs component: we want each tab to
 * be a real URL so deep links, browser back/forward, and the
 * ⌘K command palette all work. Radix Tabs is local state only.
 */
export interface TabDef {
  /** Path the tab navigates to. Typically a sibling route under the
   *  same parent. ``end`` controls whether trailing routes match. */
  to: string
  /** Display label (translation key resolved by the caller). */
  label: string
  /** Optional icon on the tab. */
  icon?: LucideIcon
  /** Match exactly (useful for the parent route that should not
   *  highlight when a child route is active). */
  end?: boolean
  /** Optional small badge / count next to the label. */
  badge?: number | string | null
}

export function TabbedShell({
  title,
  subtitle,
  actions,
  tabs,
  children,
}: {
  title?: string
  subtitle?: string
  actions?: React.ReactNode
  tabs: TabDef[]
  children: React.ReactNode
}) {
  // Preserve the URL search string when navigating between tabs.
  // Several hubs use ``?param=…`` as shared state across tabs (e.g.
  // ``/reports?include_pending=1`` toggles a flag every tab consumes
  // via ``useSearchParams``). Without this, NavLink emits a location
  // with empty ``search`` and the flag is lost on click.
  const { search } = useLocation()
  return (
    <div className="flex h-full flex-col">
      {(title || subtitle || actions) && (
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            {title ? (
              <h1 className="text-[20px] font-bold leading-none tracking-tight">
                {title}
              </h1>
            ) : null}
            {subtitle ? (
              <p className="mt-1 text-[12px] text-muted-foreground">{subtitle}</p>
            ) : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      )}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-border">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <NavLink
              key={tab.to}
              to={{ pathname: tab.to, search }}
              end={tab.end}
              className={({ isActive }) =>
                cn(
                  "relative flex h-9 shrink-0 items-center gap-1.5 px-3 text-[12px] font-medium transition-colors",
                  isActive
                    ? "text-foreground after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-primary"
                    : "text-muted-foreground hover:text-foreground",
                )
              }
            >
              {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
              <span className="truncate">{tab.label}</span>
              {tab.badge != null && tab.badge !== 0 ? (
                <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold leading-none text-muted-foreground">
                  {tab.badge}
                </span>
              ) : null}
            </NavLink>
          )
        })}
      </div>
      <div className="mt-4 min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  )
}
