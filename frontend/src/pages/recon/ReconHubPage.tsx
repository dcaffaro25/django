import { Outlet } from "react-router-dom"
import {
  LayoutDashboard, ArrowLeftRight, ListChecks, SlidersHorizontal, Workflow,
  Scale, CheckCircle2, Brain,
} from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"

/**
 * Wrapper page for the Conciliação section. Replaces the 9 separate
 * sidebar entries with a single nav target (``/recon``); the previous
 * sub-pages live as tabs under the same parent route.
 *
 * Each child page is rendered via ``<Outlet />`` so deep links like
 * ``/recon/workbench`` still resolve to the same component as before --
 * we just stack a tabbed shell above them.
 */
export function ReconHubPage() {
  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Conciliação"
        subtitle="Painel · Bancada · Configurações"
        tabs={[
          { to: "/recon", end: true, label: "Painel", icon: LayoutDashboard },
          { to: "/recon/workbench", label: "Bancada", icon: ArrowLeftRight },
          { to: "/recon/matches", label: "Conciliações", icon: CheckCircle2 },
          { to: "/recon/tasks", label: "Execuções", icon: ListChecks },
          { to: "/recon/configs", label: "Configurações", icon: SlidersHorizontal },
          { to: "/recon/pipelines", label: "Pipelines", icon: Workflow },
          { to: "/recon/embeddings", label: "Embeddings", icon: Brain },
          { to: "/recon/balances", label: "Saldos", icon: Scale },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}
