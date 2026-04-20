import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ChevronRight, Home } from "lucide-react"

const LABEL_BY_SEGMENT: Record<string, string> = {
  recon: "nav.reconciliation",
  workbench: "nav.reconciliation_workbench",
  tasks: "nav.reconciliation_tasks",
  suggestions: "nav.reconciliation_suggestions",
  configs: "nav.reconciliation_configs",
  pipelines: "nav.reconciliation_pipelines",
  balances: "nav.reconciliation_balances",
  accounting: "nav.accounting",
  "bank-transactions": "nav.bank_transactions",
  transactions: "nav.transactions",
  "journal-entries": "nav.journal_entries",
  accounts: "nav.accounts",
  statements: "nav.financial_statements",
  templates: "nav.templates",
  billing: "nav.billing",
  hr: "nav.hr",
  inventory: "nav.inventory",
  settings: "nav.settings",
}

export function Breadcrumbs() {
  const { pathname } = useLocation()
  const { t } = useTranslation()
  const segments = pathname.split("/").filter(Boolean)

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[13px] text-muted-foreground">
      <Link to="/" className="grid h-6 w-6 place-items-center rounded hover:bg-accent hover:text-foreground">
        <Home className="h-3.5 w-3.5" />
      </Link>
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1
        const href = "/" + segments.slice(0, i + 1).join("/")
        const labelKey = LABEL_BY_SEGMENT[seg]
        const label = labelKey ? t(labelKey) : seg
        return (
          <span key={href} className="flex items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
            {isLast ? (
              <span className="font-medium text-foreground">{label}</span>
            ) : (
              <Link to={href} className="hover:text-foreground">{label}</Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
