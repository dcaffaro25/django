import { useEffect, type ReactNode } from "react"
import { useAppStore } from "@/stores/app-store"
import { getTheme } from "@/lib/themes"

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

  // Palette — always set data-theme so the [data-theme="<id>"] block in
  // styles/themes.css wins over the :root vars in index.css. The previous
  // "strip attribute for default" optimisation meant non-brand defaults
  // (e.g. graphite) silently fell back to the :root palette.
  useEffect(() => {
    const root = document.documentElement
    const resolved = getTheme(palette).id
    root.setAttribute("data-theme", resolved)
  }, [palette])

  return <>{children}</>
}
