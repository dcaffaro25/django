import { type ReactNode } from "react"
import { useHotkeys } from "react-hotkeys-hook"
import { Sidebar } from "./Sidebar"
import { Topbar } from "./Topbar"
import { CommandPalette } from "./CommandPalette"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { useAppStore } from "@/stores/app-store"
import { useActivityBeacon } from "@/hooks/useActivityBeacon"
import { cn } from "@/lib/utils"

export function AppShell({ children }: { children: ReactNode }) {
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)
  const setCommandOpen = useAppStore((s) => s.setCommandOpen)
  // Drives per-tab activity tracking: installs the singleton beacon
  // on first authenticated render, emits page_view on each route
  // change, and tears down on logout. All fire-and-forget.
  useActivityBeacon()

  useHotkeys("mod+k", (e) => { e.preventDefault(); setCommandOpen(true) }, { enableOnFormTags: true })
  useHotkeys("mod+b", (e) => { e.preventDefault(); toggleSidebar() })

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className={cn("flex min-w-0 flex-1 flex-col")}>
        <Topbar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1440px] px-6 py-6">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </main>
      </div>
      <CommandPalette />
    </div>
  )
}
