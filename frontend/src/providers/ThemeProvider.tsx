import { useEffect, type ReactNode } from "react"
import { useAppStore } from "@/stores/app-store"
import { DEFAULT_THEME, getTheme } from "@/lib/themes"

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useAppStore((s) => s.theme)
  const palette = useAppStore((s) => s.palette)

  // Mode (dark/light) — toggled via the .dark class on <html>.
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", theme === "dark")
    root.classList.toggle("light", theme === "light")
    root.style.colorScheme = theme
  }, [theme])

  // Palette — swapped via data-theme on <html>. Defaults to brand (which
  // is the :root block in index.css), so no attribute is set for brand.
  useEffect(() => {
    const root = document.documentElement
    const resolved = getTheme(palette).id
    if (resolved === DEFAULT_THEME) {
      root.removeAttribute("data-theme")
    } else {
      root.setAttribute("data-theme", resolved)
    }
  }, [palette])

  return <>{children}</>
}
