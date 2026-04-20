/* ---------------------------------------------------------------------------
   Theme registry.

   The palette is a CSS concern — variable overrides per theme live in
   styles/themes.css keyed by [data-theme="<id>"]. This file is just the
   metadata needed to (1) populate the picker UI and (2) apply the right
   data attribute to <html>.

   To add a theme:
     1. Append a block to styles/themes.css with the [data-theme="<id>"]
        overrides for light, and a matching [data-theme="<id>"].dark block.
     2. Register it here with id, label, and a short blurb.
--------------------------------------------------------------------------- */

export type ThemeId =
  | "brand"
  | "brand-plus"
  | "graphite"
  | "legacy"
  | "midnight-forest"
  | "parchment"
  | "mist"
  | "copper-earth"

export interface ThemeDefinition {
  id: ThemeId
  label: string
  description: string
  /** Short tag — shown next to the name in the picker. */
  tag?: string
  /** Small visual swatches for the preview dots, in CSS `hsl(...)` form. */
  swatches: { bg: string; primary: string; accent: string }
}

export const THEMES: ThemeDefinition[] = [
  {
    id: "brand",
    label: "Brand",
    description:
      "Palette do manual — floresta #015736, charcoal quente, Roboto. Padrão atual.",
    tag: "default",
    swatches: {
      bg: "hsl(222 20% 9%)",
      primary: "hsl(152 60% 28%)",
      accent: "hsl(44 82% 55%)",
    },
  },
  {
    id: "brand-plus",
    label: "Brand+",
    description:
      "Brand com correções de contraste: bordas mais visíveis, primary e ícone ativo com leitura melhor em dark.",
    tag: "recommended",
    swatches: {
      bg: "hsl(222 20% 9%)",
      primary: "hsl(152 58% 34%)",
      accent: "hsl(212 78% 62%)",
    },
  },
  {
    id: "graphite",
    label: "Graphite",
    description:
      "Minimalista monocromático estilo shadcn. Sem verde no chrome — primary é tom (preto/branco invertido), cor só em status.",
    tag: "minimal",
    swatches: {
      bg: "hsl(240 10% 4%)",
      primary: "hsl(0 0% 98%)",
      accent: "hsl(215 85% 65%)",
    },
  },
  {
    id: "midnight-forest",
    label: "Midnight Forest",
    description:
      "Dark profundo quase-preto, verde floresta vivo como destaque. Raios menores, postura mais séria.",
    swatches: {
      bg: "hsl(200 28% 4%)",
      primary: "hsl(150 78% 44%)",
      accent: "hsl(168 70% 48%)",
    },
  },
  {
    id: "parchment",
    label: "Parchment",
    description:
      "Papel quente, floresta profunda, tipografia serifada para leitura longa (relatórios, demonstrações).",
    swatches: {
      bg: "hsl(40 32% 97%)",
      primary: "hsl(155 92% 18%)",
      accent: "hsl(38 88% 40%)",
    },
  },
  {
    id: "mist",
    label: "Mist",
    description:
      "Neutro frio dessaturado. Floresta mais sage, menos tinta. SaaS minimalista.",
    swatches: {
      bg: "hsl(215 24% 11%)",
      primary: "hsl(152 48% 42%)",
      accent: "hsl(210 72% 46%)",
    },
  },
  {
    id: "copper-earth",
    label: "Copper Earth",
    description:
      "Família de superfícies em barro/cobre quente, floresta primária mantida, acentos ocre/terracota.",
    swatches: {
      bg: "hsl(22 18% 8%)",
      primary: "hsl(150 58% 36%)",
      accent: "hsl(14 76% 60%)",
    },
  },
  {
    id: "legacy",
    label: "Legacy",
    description:
      "Paleta pré-manual: fundo azul-escuro frio, verde neon, Inter, raios maiores. Mantida para comparação.",
    tag: "archive",
    swatches: {
      bg: "hsl(225 15% 7%)",
      primary: "hsl(150 70% 42%)",
      accent: "hsl(215 85% 65%)",
    },
  },
]

export const DEFAULT_THEME: ThemeId = "brand"

export function getTheme(id: string | null | undefined): ThemeDefinition {
  return (
    THEMES.find((t) => t.id === id) ??
    THEMES.find((t) => t.id === DEFAULT_THEME)!
  )
}
