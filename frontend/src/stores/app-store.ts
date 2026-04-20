import { create } from "zustand"
import { persist } from "zustand/middleware"
import { DEFAULT_THEME, type ThemeId } from "@/lib/themes"

interface AppState {
  sidebarCollapsed: boolean
  commandOpen: boolean
  theme: "dark" | "light"
  /** Palette / theme family (id from @/lib/themes). Mode (dark/light) is separate. */
  palette: ThemeId
  setSidebarCollapsed: (v: boolean) => void
  toggleSidebar: () => void
  setCommandOpen: (v: boolean) => void
  setTheme: (t: "dark" | "light") => void
  setPalette: (p: ThemeId) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      commandOpen: false,
      theme: "dark",
      palette: DEFAULT_THEME,
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setCommandOpen: (v) => set({ commandOpen: v }),
      setTheme: (t) => set({ theme: t }),
      setPalette: (p) => set({ palette: p }),
    }),
    {
      name: "nord.app",
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        theme: s.theme,
        palette: s.palette,
      }),
    },
  ),
)
