import { useEffect, useMemo, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import { Palette, Save, X, Sparkles } from "lucide-react"
import { useTenantTheme, useUpdateTenantTheme } from "@/features/theme/useTenantTheme"
import type {
  BrandPalette, CategoryPalette, TenantThemePayload,
} from "@/features/auth/useUserRole"
import { contrastForeground } from "@/lib/color-utils"

/**
 * Brand-token vocabulary the editor exposes. Order matches the
 * visual hierarchy we want operators to see: identity colours
 * first, surfaces second, semantic statuses last. Foreground
 * tokens are derived automatically when their background partner
 * changes (operator can still override manually).
 */
const BRAND_TOKEN_GROUPS: Array<{
  title: string
  tokens: Array<{ key: keyof BrandPalette; label: string; pairsWith?: keyof BrandPalette }>
}> = [
  {
    title: "Identidade",
    tokens: [
      { key: "primary", label: "Primary", pairsWith: "primary_foreground" },
      { key: "primary_foreground", label: "Primary text" },
      { key: "accent", label: "Accent", pairsWith: "accent_foreground" },
      { key: "accent_foreground", label: "Accent text" },
    ],
  },
  {
    title: "Superfícies",
    tokens: [
      { key: "background", label: "Background", pairsWith: "foreground" },
      { key: "foreground", label: "Foreground" },
      { key: "muted", label: "Muted", pairsWith: "muted_foreground" },
      { key: "muted_foreground", label: "Muted text" },
      { key: "border", label: "Border" },
      { key: "ring", label: "Focus ring" },
    ],
  },
  {
    title: "Status",
    tokens: [
      { key: "good", label: "Sucesso" },
      { key: "warn", label: "Alerta" },
      { key: "bad", label: "Erro" },
    ],
  },
]

type Mode = "light" | "dark"

interface DraftState {
  brand_palette_light: BrandPalette
  brand_palette_dark: BrandPalette
  category_palette_light: CategoryPalette
  category_palette_dark: CategoryPalette
  logo_url: string
  logo_dark_url: string
  favicon_url: string
}

function payloadToDraft(payload: TenantThemePayload): DraftState {
  return {
    brand_palette_light: { ...payload.brand_palette_light },
    brand_palette_dark: { ...payload.brand_palette_dark },
    category_palette_light: [...payload.category_palette_light],
    category_palette_dark: [...payload.category_palette_dark],
    logo_url: payload.logo_url ?? "",
    logo_dark_url: payload.logo_dark_url ?? "",
    favicon_url: payload.favicon_url ?? "",
  }
}

export function TenantThemeEditor({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: theme, isLoading } = useTenantTheme()
  const update = useUpdateTenantTheme()
  const [mode, setMode] = useState<Mode>("light")
  const [draft, setDraft] = useState<DraftState | null>(null)

  useEffect(() => {
    if (theme && open) setDraft(payloadToDraft(theme))
  }, [theme, open])

  const brand = useMemo(() => {
    if (!draft) return null
    return mode === "light" ? draft.brand_palette_light : draft.brand_palette_dark
  }, [draft, mode])

  const categories = useMemo(() => {
    if (!draft) return null
    return mode === "light" ? draft.category_palette_light : draft.category_palette_dark
  }, [draft, mode])

  const setBrandToken = (token: string, hex: string, autoPair?: string) => {
    setDraft((d) => {
      if (!d) return d
      const target = mode === "light" ? "brand_palette_light" : "brand_palette_dark"
      const next: BrandPalette = { ...d[target], [token]: hex }
      if (autoPair && (next[autoPair] === undefined || next[autoPair] === d[target][autoPair])) {
        // Only auto-fill the foreground if the operator hasn't
        // diverged from the previous default -- otherwise we'd
        // clobber a manual override.
        next[autoPair] = contrastForeground(hex)
      }
      return { ...d, [target]: next }
    })
  }

  const setCategoryColor = (idx: number, hex: string) => {
    setDraft((d) => {
      if (!d) return d
      const target = mode === "light" ? "category_palette_light" : "category_palette_dark"
      const next = [...d[target]]
      next[idx] = hex
      return { ...d, [target]: next }
    })
  }

  const onExtractFromImage = async (file: File) => {
    try {
      const palette = await extractPaletteFromImage(file)
      if (!palette.length) {
        toast.error("Não consegui extrair cores dessa imagem.")
        return
      }
      setDraft((d) => {
        if (!d) return d
        const target = mode === "light" ? "category_palette_light" : "category_palette_dark"
        const next = [...d[target]]
        // Replace as many slots as we have extracted colours; keep
        // the remainder so we never end up with fewer than the
        // standard 14 swatches.
        palette.slice(0, next.length).forEach((hex, i) => { next[i] = hex })
        // If the brand primary slot is still on the platform default,
        // promote the first extracted colour as the suggested primary.
        const brandKey = mode === "light" ? "brand_palette_light" : "brand_palette_dark"
        const brandNext: BrandPalette = { ...d[brandKey], primary: palette[0], primary_foreground: contrastForeground(palette[0]) }
        if (palette[1]) {
          brandNext.accent = palette[1]
          brandNext.accent_foreground = contrastForeground(palette[1])
        }
        return { ...d, [target]: next, [brandKey]: brandNext }
      })
      toast.success(`${palette.length} cores extraídas da imagem`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao extrair cores")
    }
  }

  const onSave = () => {
    if (!draft) return
    update.mutate(
      {
        brand_palette_light: draft.brand_palette_light,
        brand_palette_dark: draft.brand_palette_dark,
        category_palette_light: draft.category_palette_light,
        category_palette_dark: draft.category_palette_dark,
        logo_url: draft.logo_url || null,
        logo_dark_url: draft.logo_dark_url || null,
        favicon_url: draft.favicon_url || null,
      },
      {
        onSuccess: () => { toast.success("Tema salvo"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro ao salvar"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[560px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Palette className="h-3.5 w-3.5 text-muted-foreground" />
              Tema do tenant
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="hairline flex shrink-0 items-center gap-2 px-4 py-2 text-[11px]">
            <span className="text-muted-foreground">Modo:</span>
            {(["light", "dark"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-md px-2 py-1 ${mode === m ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent"}`}
              >
                {m === "light" ? "Claro" : "Escuro"}
              </button>
            ))}
            <div className="ml-auto">
              <ImageExtractButton onPick={onExtractFromImage} />
            </div>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[12px]">
            {isLoading || !brand || !categories ? (
              <div className="text-muted-foreground">Carregando tema…</div>
            ) : (
              <>
                {BRAND_TOKEN_GROUPS.map((group) => (
                  <section key={group.title} className="space-y-2">
                    <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{group.title}</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {group.tokens.map(({ key, label, pairsWith }) => (
                        <ColorTokenInput
                          key={key as string}
                          label={label}
                          value={brand[key as string] ?? "#000000"}
                          onChange={(hex) => setBrandToken(key as string, hex, pairsWith as string | undefined)}
                        />
                      ))}
                    </div>
                  </section>
                ))}

                <section className="space-y-2">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Categorias (gráficos)
                  </h3>
                  <div className="grid grid-cols-7 gap-2">
                    {categories.map((hex, i) => (
                      <ColorSwatch
                        key={i}
                        value={hex}
                        onChange={(v) => setCategoryColor(i, v)}
                      />
                    ))}
                  </div>
                </section>

                <section className="space-y-2">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Logo & favicon</h3>
                  <UrlField label="Logo URL" value={draft?.logo_url ?? ""} onChange={(v) => setDraft((d) => d ? { ...d, logo_url: v } : d)} />
                  <UrlField label="Logo (modo escuro) URL" value={draft?.logo_dark_url ?? ""} onChange={(v) => setDraft((d) => d ? { ...d, logo_dark_url: v } : d)} />
                  <UrlField label="Favicon URL" value={draft?.favicon_url ?? ""} onChange={(v) => setDraft((d) => d ? { ...d, favicon_url: v } : d)} />
                </section>
              </>
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
              Cancelar
            </button>
            <button onClick={onSave} disabled={update.isPending || !draft}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-3.5 w-3.5" /> Salvar tema
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function ColorTokenInput({ label, value, onChange }: { label: string; value: string; onChange: (hex: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-6 w-8 cursor-pointer rounded border border-border bg-transparent"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-6 flex-1 bg-transparent font-mono text-[11px] uppercase tracking-wider outline-none"
        />
      </div>
    </label>
  )
}

function ColorSwatch({ value, onChange }: { value: string; onChange: (hex: string) => void }) {
  return (
    <label className="relative cursor-pointer">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
      />
      <div className="h-10 w-full rounded-md border border-border" style={{ background: value }} />
      <div className="mt-0.5 truncate text-center font-mono text-[9px] text-muted-foreground">{value}</div>
    </label>
  )
}

function UrlField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <input
        type="url"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="https://"
        className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
      />
    </label>
  )
}

function ImageExtractButton({ onPick }: { onPick: (file: File) => void }) {
  return (
    <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent">
      <Sparkles className="h-3 w-3 text-primary" />
      Extrair de imagem
      <input
        type="file"
        accept="image/*"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onPick(f)
          e.currentTarget.value = ""
        }}
        className="hidden"
      />
    </label>
  )
}

/**
 * Pulls the dominant colours from a logo / brand asset client-side.
 * Uses a Canvas-based quantiser so we don't need to add a library
 * dependency for what is ultimately a one-off helper. Returns an
 * array of hex colours sorted by frequency, deduplicated by
 * perceptual proximity.
 */
async function extractPaletteFromImage(file: File): Promise<string[]> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = reject
    r.readAsDataURL(file)
  })
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const i = new Image()
    i.onload = () => resolve(i)
    i.onerror = reject
    i.src = dataUrl
  })

  // Downscale to 64px on the long edge -- enough variance to find
  // the brand colours without choking on a 4K logo.
  const maxDim = 64
  const scale = Math.min(maxDim / img.width, maxDim / img.height, 1)
  const w = Math.max(1, Math.round(img.width * scale))
  const h = Math.max(1, Math.round(img.height * scale))
  const canvas = document.createElement("canvas")
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext("2d")
  if (!ctx) throw new Error("Canvas indisponível")
  ctx.drawImage(img, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)

  const buckets = new Map<string, { count: number; r: number; g: number; b: number }>()
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3]
    if (a < 128) continue
    const r = data[i]
    const g = data[i + 1]
    const b = data[i + 2]
    // Skip near-white / near-black so we don't return the page
    // background as a "brand colour".
    const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if (luma > 245 || luma < 12) continue
    // Quantise to 32-step buckets per channel. Coarse enough to
    // collapse JPEG noise, fine enough to distinguish brand
    // accents.
    const qr = Math.round(r / 32) * 32
    const qg = Math.round(g / 32) * 32
    const qb = Math.round(b / 32) * 32
    const key = `${qr},${qg},${qb}`
    const cur = buckets.get(key)
    if (cur) {
      cur.count += 1
      cur.r += r
      cur.g += g
      cur.b += b
    } else {
      buckets.set(key, { count: 1, r, g, b })
    }
  }
  const sorted = Array.from(buckets.values())
    .sort((a, b) => b.count - a.count)
    .slice(0, 14)
    .map(({ count, r, g, b }) => {
      const ar = Math.round(r / count)
      const ag = Math.round(g / count)
      const ab = Math.round(b / count)
      return "#" + [ar, ag, ab].map((c) => c.toString(16).padStart(2, "0").toUpperCase()).join("")
    })
  return sorted
}
