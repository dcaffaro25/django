import { useEffect, useMemo, type ReactNode } from "react"
import { useUserRole, type BrandPalette } from "@/features/auth/useUserRole"
import { useAppStore } from "@/stores/app-store"
import { hexToHslVar } from "@/lib/color-utils"

/**
 * Map from backend brand-palette keys (snake_case, hex values) to
 * the CSS custom-property names already declared in
 * ``index.css`` / ``styles/themes.css``. Anything not in this map
 * is ignored -- the bridge is intentionally tolerant of new
 * server-side keys so we don't break when the design vocabulary
 * grows.
 */
const TOKEN_MAP: Record<string, string> = {
  primary: "--primary",
  primary_foreground: "--primary-foreground",
  accent: "--accent",
  accent_foreground: "--accent-foreground",
  background: "--background",
  foreground: "--foreground",
  muted: "--muted",
  muted_foreground: "--muted-foreground",
  border: "--border",
  ring: "--ring",
  good: "--success",
  warn: "--warning",
  bad: "--danger",
}

/** Inline CSS variables the bridge wrote on its last pass, so we
 *  can clear them cleanly when the user disables tenant theming. */
const APPLIED_KEYS = Object.values(TOKEN_MAP)

function clearAppliedVars() {
  const root = document.documentElement
  for (const cssVar of APPLIED_KEYS) {
    root.style.removeProperty(cssVar)
  }
  // Category palette -- variable count up to 20 covers the 14 the
  // backend ships plus headroom for tenants that customise.
  for (let i = 0; i < 20; i++) {
    root.style.removeProperty(`--brand-cat-${i}`)
  }
}

function applyBrandPalette(palette: BrandPalette) {
  const root = document.documentElement
  for (const [key, value] of Object.entries(palette)) {
    const cssVar = TOKEN_MAP[key]
    if (!cssVar) continue
    const hsl = hexToHslVar(value)
    if (hsl) root.style.setProperty(cssVar, hsl)
  }
}

function applyCategoryPalette(palette: string[]) {
  const root = document.documentElement
  palette.forEach((hex, i) => {
    // Category palette is consumed both as raw hex (recharts) and as
    // HSL components (CSS vars). Expose both shapes so charts and
    // utility classes stay in sync.
    root.style.setProperty(`--brand-cat-${i}`, hex)
    const hsl = hexToHslVar(hex)
    if (hsl) root.style.setProperty(`--brand-cat-${i}-hsl`, hsl)
  })
}

/**
 * Layered on top of the existing ``<ThemeProvider>`` (which
 * handles palette / dark-mode driven by Zustand). This bridge
 * lives inside the auth + tenant providers so it can read
 * ``useUserRole()`` and decide which palette to push onto
 * ``document.documentElement``.
 *
 * Behaviour:
 *   * ``user.prefer_dark_mode`` syncs into ``app-store.theme`` so
 *     the existing ``<ThemeProvider>`` toggles ``.dark`` on the
 *     html element. No double-source-of-truth: server is canon.
 *   * ``user.use_tenant_theme = true`` AND a tenant theme is
 *     loaded -> inline CSS vars override the index.css defaults.
 *   * ``user.use_tenant_theme = false`` (or no tenant theme) ->
 *     clear inline vars; the existing palette infra wins.
 *
 * Mounted as a wrapper component (not a hook) so it can render
 * children unconditionally and not re-mount the app on theme
 * changes.
 */
export function TenantThemeBridge({ children }: { children: ReactNode }) {
  const { me, theme: tenantTheme, isLoading } = useUserRole()
  const setTheme = useAppStore((s) => s.setTheme)
  const currentMode = useAppStore((s) => s.theme)

  // Resolve the EFFECTIVE dark-mode flag. The user's
  // ``prefer_dark_mode`` only wins after they've explicitly clicked
  // the toggle (``prefer_dark_mode_explicit``). Until then, the
  // tenant theme's ``default_mode`` is the source of truth -- which
  // avoids the model-default ``prefer_dark_mode=False`` from
  // silently flipping every operator to light mode the first time
  // /api/core/me/ resolves after a deploy.
  const effectiveDark = useMemo(() => {
    if (!me) return null
    if (me.prefer_dark_mode_explicit) return !!me.prefer_dark_mode
    if (tenantTheme?.default_mode) return tenantTheme.default_mode === "dark"
    // No tenant theme yet -- fall back to whatever app-store has
    // (preserves the operator's previous local choice instead of
    // forcing light).
    return currentMode === "dark"
  }, [me, tenantTheme?.default_mode, currentMode])

  // Mirror the resolved dark/light into the existing app-store so
  // ThemeProvider keeps applying ``.dark`` on the html element.
  useEffect(() => {
    if (effectiveDark === null) return
    const desired = effectiveDark ? "dark" : "light"
    if (desired !== currentMode) setTheme(desired)
  }, [effectiveDark, currentMode, setTheme])

  useEffect(() => {
    if (isLoading) return
    if (!me?.use_tenant_theme || !tenantTheme) {
      clearAppliedVars()
      return
    }
    const isDark = effectiveDark === true
    applyBrandPalette(isDark ? tenantTheme.brand_palette_dark : tenantTheme.brand_palette_light)
    applyCategoryPalette(isDark ? tenantTheme.category_palette_dark : tenantTheme.category_palette_light)
  }, [isLoading, me?.use_tenant_theme, effectiveDark, tenantTheme])

  return <>{children}</>
}
