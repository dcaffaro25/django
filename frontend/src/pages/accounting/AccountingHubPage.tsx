import { Outlet } from "react-router-dom"
import { Wallet, Receipt, BookOpen, FileCog } from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"

/**
 * Wrapper page for the Contabilidade section. Five sub-pages are
 * exposed as tabs under ``/accounting`` instead of as separate
 * sidebar entries.
 */
export function AccountingHubPage() {
  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Contabilidade"
        subtitle="Plano de contas · Bancárias · Transações · Lançamentos"
        tabs={[
          { to: "/accounting/accounts", label: "Plano de contas", icon: FileCog },
          { to: "/accounting/bank-accounts", label: "Contas bancárias", icon: Wallet },
          { to: "/accounting/bank-transactions", label: "Extratos", icon: Wallet },
          { to: "/accounting/transactions", label: "Transações", icon: Receipt },
          { to: "/accounting/journal-entries", label: "Lançamentos", icon: BookOpen },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}
