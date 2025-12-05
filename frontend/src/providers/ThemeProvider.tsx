import { createContext, useContext, useEffect, useState, ReactNode } from "react"
import { useTenant } from "./TenantProvider"

interface ThemeConfig {
  primary: string
  secondary: string
  success: string
  danger: string
  warning: string
  info: string
  background: string
  foreground: string
}

interface ThemeContextType {
  theme: ThemeConfig
  isTenantTheme: boolean
}

const defaultTheme: ThemeConfig = {
  primary: "#025736",
  secondary: "#025736",
  success: "#059669",
  danger: "#dc2626",
  warning: "#cd6f00",
  info: "#3170f9",
  background: "#ffffff",
  foreground: "#0d0d0d",
}

const ThemeContext = createContext<ThemeContextType>({
  theme: defaultTheme,
  isTenantTheme: false,
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { tenant } = useTenant()
  const [theme, setTheme] = useState<ThemeConfig>(defaultTheme)
  const [isTenantTheme, setIsTenantTheme] = useState(false)

  useEffect(() => {
    // TODO: When backend supports branding, fetch tenant theme
    // For now, use default theme
    // if (tenant?.id) {
    //   const branding = await fetchTenantBranding(tenant.id)
    //   if (branding) {
    //     setTheme({
    //       primary: branding.primary_color || defaultTheme.primary,
    //       secondary: branding.secondary_color || defaultTheme.secondary,
    //       ...defaultTheme,
    //     })
    //     setIsTenantTheme(true)
    //   } else {
    //     setTheme(defaultTheme)
    //     setIsTenantTheme(false)
    //   }
    // } else {
    setTheme(defaultTheme)
    setIsTenantTheme(false)
    // }

    // Apply CSS variables
    const root = document.documentElement
    root.style.setProperty("--primary", theme.primary)
    root.style.setProperty("--secondary", theme.secondary)
    root.style.setProperty("--success", theme.success)
    root.style.setProperty("--danger", theme.danger)
    root.style.setProperty("--warning", theme.warning)
    root.style.setProperty("--info", theme.info)
    root.style.setProperty("--background", theme.background)
    root.style.setProperty("--foreground", theme.foreground)
  }, [tenant, theme])

  return (
    <ThemeContext.Provider value={{ theme, isTenantTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}

