import { Outlet } from "react-router-dom"
import {
  Bot, Database, FlaskConical, LayoutDashboard, PlugZap, SearchCode,
} from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"

export function IntegrationsHubPage() {
  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Integrações ERP"
        subtitle="APIs, sandbox, automações e registros salvos"
        tabs={[
          { to: "/integrations", end: true, label: "Visão geral", icon: LayoutDashboard },
          { to: "/integrations/api-definitions", label: "APIs", icon: PlugZap },
          { to: "/integrations/api-definitions/discover", label: "Descobrir", icon: SearchCode },
          { to: "/integrations/sandbox", label: "Sandbox", icon: FlaskConical },
          { to: "/integrations/rotinas", label: "Automações", icon: Bot },
          { to: "/integrations/registros", label: "Registros", icon: Database },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}
