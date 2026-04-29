import { Eye, X } from "lucide-react"
import { useAppStore } from "@/stores/app-store"
import { useUserRole } from "@/features/auth/useUserRole"

/**
 * Sticky banner shown while the operator is in "view as viewer"
 * preview mode. Renders nothing in the normal case so the layout
 * stays unchanged for everyone who isn't actively previewing.
 *
 * The banner is the ONLY way out of preview (besides hard-reload),
 * so its exit button has to be unmistakable -- kept high-contrast
 * (amber background, dark text) and pinned at the top of the app
 * shell above the topbar.
 */
export function ViewAsViewerBanner() {
  const { isPreviewingViewer, actualRole } = useUserRole()
  const setViewAsViewer = useAppStore((s) => s.setViewAsViewer)

  if (!isPreviewingViewer) return null

  return (
    <div className="flex h-8 shrink-0 items-center justify-center gap-3 bg-amber-400 px-4 text-[12px] font-medium text-amber-950">
      <Eye className="h-3.5 w-3.5" />
      <span>
        Visualizando como <strong>viewer</strong> — botões de edição e seções
        de configuração estão ocultas, como aparecem para um cliente externo.
      </span>
      <button
        onClick={() => setViewAsViewer(false)}
        className="ml-2 inline-flex h-6 items-center gap-1 rounded-md bg-amber-950/15 px-2 text-[11px] font-semibold hover:bg-amber-950/25"
        title={`Sair do preview e voltar à visão de ${actualRole}`}
      >
        <X className="h-3 w-3" />
        Sair do preview
      </button>
    </div>
  )
}
