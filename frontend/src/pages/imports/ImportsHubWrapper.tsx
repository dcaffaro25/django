import { Outlet } from "react-router-dom"
import { UploadCloud, FileSpreadsheet, Shuffle } from "lucide-react"
import { TabbedShell } from "@/components/layout/TabbedShell"

/**
 * Wrapper page for the Importações section. Three sub-pages are
 * exposed as tabs under ``/imports`` instead of as separate sidebar
 * entries.
 */
export function ImportsHubWrapper() {
  return (
    <div className="h-full p-4">
      <TabbedShell
        title="Importações"
        subtitle="Hub · Templates · Substituições"
        tabs={[
          { to: "/imports", end: true, label: "Hub", icon: UploadCloud },
          { to: "/imports/templates", label: "Templates", icon: FileSpreadsheet },
          { to: "/imports/substitutions", label: "Substituições", icon: Shuffle },
        ]}
      >
        <Outlet />
      </TabbedShell>
    </div>
  )
}
