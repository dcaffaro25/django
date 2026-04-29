import { create } from "zustand"
import { persist } from "zustand/middleware"
import { DEFAULT_THEME, type ThemeId } from "@/lib/themes"

interface AppState {
  sidebarCollapsed: boolean
  commandOpen: boolean
  theme: "dark" | "light"
  /** Palette / theme family (id from @/lib/themes). Mode (dark/light) is separate. */
  palette: ThemeId
  /**
   * "View as viewer" preview mode. When true, ``useUserRole`` reports
   * the role as ``viewer`` regardless of the user's actual tenant
   * membership, so every role-aware bit of UI (sidebar visibility,
   * write buttons, edit drawers) renders the viewer surface. This is
   * a CLIENT-SIDE simulation only -- backend permissions are not
   * altered. Intended for manager+/superuser operators who want to
   * verify what their external tenant users actually see.
   * Per-session: not persisted, so a hard reload always brings the
   * operator back to their normal surface. Switching to a tenant
   * where the operator isn't manager+ also clears the preview
   * effect (``useUserRole`` requires the actual role to permit it).
   */
  viewAsViewer: boolean
  setSidebarCollapsed: (v: boolean) => void
  toggleSidebar: () => void
  setCommandOpen: (v: boolean) => void
  setTheme: (t: "dark" | "light") => void
  setPalette: (p: ThemeId) => void
  setViewAsViewer: (v: boolean) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      commandOpen: false,
      theme: "dark",
      palette: DEFAULT_THEME,
      viewAsViewer: false,
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setCommandOpen: (v) => set({ commandOpen: v }),
      setTheme: (t) => set({ theme: t }),
      setPalette: (p) => set({ palette: p }),
      setViewAsViewer: (v) => set({ viewAsViewer: v }),
    }),
    {
      name: "nord.app",
      // ``viewAsViewer`` intentionally NOT persisted -- preview mode
      // is per-session, not per-device. Reload = back to your real
      // surface. Avoids the "I forgot I was in preview yesterday"
      // failure mode.
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        theme: s.theme,
        palette: s.palette,
      }),
    },
  ),
)
