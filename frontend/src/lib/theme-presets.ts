/**
 * Three paths to construct a tenant theme:
 *   1. **Preset** -- pick a named brand archetype, all tokens
 *      populate at once (both light & dark, both palettes).
 *   2. **Seed colour** -- give one brand colour; derive a full
 *      palette via HSL operations (analogous accent, surface
 *      tints, neutralised greys, even-spread category hues).
 *   3. **Image** -- extract dominant colours from a logo upload;
 *      promote the top hits as primary + accent and drop the
 *      rest into the category palette.
 *
 * The manual token editor is the refinement layer underneath.
 *
 * Implementation note: dependency-free on purpose. Material
 * Color Utilities (HCT) would give a more perceptually uniform
 * tonal scale, but it's ~30 KB; for a brand palette generator
 * that gets used a handful of times per tenant, plain HSL is
 * fine and ships zero kB.
 */

import type { BrandPalette, CategoryPalette } from "@/features/auth/useUserRole"
import { contrastForeground, hexToHsl, hslToHex } from "@/lib/color-utils"

export interface ThemeSet {
  brand_palette_light: BrandPalette
  brand_palette_dark: BrandPalette
  category_palette_light: CategoryPalette
  category_palette_dark: CategoryPalette
}

/** Universal status colours -- kept consistent across themes so
 *  green/amber/red retain their semantic meaning regardless of
 *  brand seed. Operators can still override them in the manual
 *  editor. */
const STATUS_LIGHT = { good: "#16A34A", warn: "#F59E0B", bad: "#DC2626" }
const STATUS_DARK = { good: "#22C55E", warn: "#F59E0B", bad: "#EF4444" }

/**
 * Generate a full brand palette from a single seed colour for the
 * given mode. The seed maps to ``primary`` directly; everything
 * else is derived via HSL math:
 *   - accent: hue + 30° (analogous), preserved chroma
 *   - background / surfaces: very-low-chroma tint of the seed
 *     (light = ~98% L; dark = ~9% L)
 *   - foreground / text: contrast-driven near-black or near-white
 *   - muted greys: low-chroma greys with a hint of the seed hue
 *     so they don't clash
 *   - border / ring: same hue as primary, scaled by mode
 *   - good / warn / bad: fixed status pivots (universal semantics)
 */
export function deriveBrandPalette(seedHex: string, mode: "light" | "dark"): BrandPalette {
  const hsl = hexToHsl(seedHex) ?? [220, 60, 40]
  const [h, s] = hsl
  const isDark = mode === "dark"
  // Cap saturation so a neon seed doesn't make every surface
  // glow. The brand identity stays in `primary` / `accent`.
  const safeS = Math.min(s, 80)
  const accentHex = hslToHex((h + 30) % 360, safeS, isDark ? 55 : 50)
  const status = isDark ? STATUS_DARK : STATUS_LIGHT

  if (isDark) {
    return {
      primary: seedHex,
      primary_foreground: contrastForeground(seedHex),
      accent: accentHex,
      accent_foreground: contrastForeground(accentHex),
      background: hslToHex(h, 18, 9),
      foreground: hslToHex(h, 8, 92),
      muted: hslToHex(h, 14, 16),
      muted_foreground: hslToHex(h, 8, 62),
      border: hslToHex(h, 10, 22),
      ring: seedHex,
      ...status,
    }
  }
  return {
    primary: seedHex,
    primary_foreground: contrastForeground(seedHex),
    accent: accentHex,
    accent_foreground: contrastForeground(accentHex),
    background: "#FFFFFF",
    foreground: hslToHex(h, 18, 14),
    muted: hslToHex(h, 8, 96),
    muted_foreground: hslToHex(h, 8, 42),
    border: hslToHex(h, 5, 84),
    ring: seedHex,
    ...status,
  }
}

/**
 * Build a 14-colour category palette from a seed hue. Hues are
 * spread evenly around the wheel starting from the seed, so the
 * tenant's brand colour appears as the first chart series and
 * everything else stays distinguishable.
 */
export function deriveCategoryPalette(seedHex: string, mode: "light" | "dark"): CategoryPalette {
  const hsl = hexToHsl(seedHex) ?? [220, 60, 50]
  const [h0] = hsl
  const isDark = mode === "dark"
  const sat = isDark ? 60 : 65
  const lit = isDark ? 60 : 50
  const N = 14
  const out: string[] = []
  for (let i = 0; i < N; i++) {
    // Subtle saturation/lightness wobble so adjacent hues don't
    // look like the same colour twice.
    const sJitter = (i % 2 === 0) ? 0 : -8
    const lJitter = (i % 3 === 0) ? -4 : 4
    out.push(hslToHex((h0 + (i * 360 / N)) % 360, sat + sJitter, lit + lJitter))
  }
  return out
}

/**
 * One-shot generator: from a seed colour, produce the full
 * theme set (both modes, both palettes). Used by the seed-colour
 * path AND consumed internally by the preset list below.
 */
export function deriveThemeSetFromSeed(seedHex: string): ThemeSet {
  return {
    brand_palette_light: deriveBrandPalette(seedHex, "light"),
    brand_palette_dark: deriveBrandPalette(seedHex, "dark"),
    category_palette_light: deriveCategoryPalette(seedHex, "light"),
    category_palette_dark: deriveCategoryPalette(seedHex, "dark"),
  }
}

export interface ThemePreset {
  id: string
  name: string
  seed: string
  description: string
}

/**
 * Curated brand archetypes. Each one is just a labelled seed --
 * the full theme is generated on demand via
 * ``deriveThemeSetFromSeed`` so we don't have to hand-tune 14
 * tokens × 2 modes × N presets.
 *
 * The seeds correspond to common brand identities (Nord forest,
 * Vinci copper, etc.) so a tenant can land on something close
 * to their style with one click.
 */
export const THEME_PRESETS: ThemePreset[] = [
  { id: "nord-forest", name: "Floresta Nord", seed: "#015736", description: "Verde escuro institucional, alinhado à identidade Nord." },
  { id: "vinci-copper", name: "Cobre Vinci", seed: "#D5642F", description: "Terracota quente, ideal para marcas industriais ou financeiras tradicionais." },
  { id: "graphite", name: "Grafite", seed: "#525B70", description: "Cinza-azulado neutro; foco em conteúdo, marca discreta." },
  { id: "deep-ocean", name: "Oceano profundo", seed: "#0E7490", description: "Teal corporativo; passa confiabilidade e escala." },
  { id: "royal", name: "Royal", seed: "#5B21B6", description: "Roxo profundo; bom para fintechs e criativas premium." },
  { id: "sunset", name: "Pôr do sol", seed: "#F59E0B", description: "Âmbar enérgico; consumer brands, vibe de hospitalidade." },
  { id: "rose", name: "Rosé", seed: "#BE185D", description: "Magenta sóbrio; cosméticos, lifestyle, varejo premium." },
  { id: "midnight", name: "Meia-noite", seed: "#1E40AF", description: "Azul-marinho clássico; bancos, advocacia, B2B." },
]

/**
 * Resolve a preset id to a full theme set. Cached implicitly via
 * ``Object.freeze`` so each preset is generated once per session.
 */
export function getPresetThemeSet(preset: ThemePreset): ThemeSet {
  return deriveThemeSetFromSeed(preset.seed)
}
