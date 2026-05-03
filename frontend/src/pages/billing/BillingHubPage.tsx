import { Outlet } from "react-router-dom"
import {
  FileText, Receipt, Link as LinkIcon, Settings as SettingsIcon,
  Users, Package, Network, Clock, Activity,
} from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"
import { useGroupMemberships, useHealthChecks, useNfTxLinks } from "@/features/billing"

/**
 * Hub page for the Faturamento module.
 *
 * Tabs:
 *   - Faturas       (/billing): list + detail of Invoices
 *   - Notas Fiscais (/billing/nfe): list of NotaFiscal docs
 *   - Vínculos      (/billing/links): NF↔Tx review queue (badge = suggested count)
 *   - Configurações (/billing/settings): tenant flags + posting defaults
 *
 * Children render via <Outlet/>.
 */
export function BillingHubPage() {
  // Pull the count of pending NF↔Tx suggestions for the Vínculos tab badge —
  // operators land here precisely to clear that queue.
  const pending = useNfTxLinks({ review_status: "suggested" })
  const pendingCount = pending.data?.length ?? 0
  // Same idea for the Grupos tab — surface pending suggestions count.
  const groupSuggestions = useGroupMemberships({ review_status: "suggested" })
  const groupSuggestionCount = groupSuggestions.data?.length ?? 0
  // Saúde tab badge: total of warning + danger checks. Operators see
  // the count without opening the page; the page itself ranks them.
  const health = useHealthChecks()
  const healthBadge =
    (health.data?.by_severity.danger ?? 0) +
    (health.data?.by_severity.warning ?? 0)

  return (
    <TabbedShell
      title="Faturamento"
      subtitle="Faturas, notas fiscais e vínculos com a contabilidade."
      tabs={[
        { to: "/billing", label: "Faturas", icon: FileText, end: true },
        { to: "/billing/nfe", label: "Notas Fiscais", icon: Receipt },
        { to: "/billing/parceiros", label: "Parceiros", icon: Users },
        { to: "/billing/produtos", label: "Produtos", icon: Package },
        {
          to: "/billing/links",
          label: "Vínculos NF↔Tx",
          icon: LinkIcon,
          badge: pendingCount > 0 ? pendingCount : null,
        },
        {
          to: "/billing/grupos",
          label: "Grupos",
          icon: Network,
          badge: groupSuggestionCount > 0 ? groupSuggestionCount : null,
        },
        { to: "/billing/dso", label: "DSO", icon: Clock },
        {
          to: "/billing/saude",
          label: "Saúde",
          icon: Activity,
          badge: healthBadge > 0 ? healthBadge : null,
        },
        { to: "/billing/settings", label: "Configurações", icon: SettingsIcon },
      ]}
    >
      <Outlet />
    </TabbedShell>
  )
}
