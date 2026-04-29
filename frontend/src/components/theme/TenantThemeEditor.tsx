import { useEffect, useMemo, useRef, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import {
  ChevronDown, ChevronRight, Image as ImageIcon, Palette,
  Pipette, Save, Sparkles, Wand2, X,
} from "lucide-react"
import { useTenantTheme, useUpdateTenantTheme } from "@/features/theme/useTenantTheme"
import type {
  BrandPalette, CategoryPalette, TenantThemePayload,
} from "@/features/auth/useUserRole"
import { contrastForeground } from "@/lib/color-utils"
import {
  THEME_PRESETS, deriveThemeSetFromSeed, getPresetThemeSet,
  type ThemePreset, type ThemeSet,
} from "@/lib/theme-presets"
import { cn } from "@/lib/utils"

/**
 * Brand-token vocabulary the manual editor exposes. Order
 * matches the visual hierarchy: identity colours first,
 * surfaces second, semantic statuses last. Foreground tokens
 * auto-derive when their background partner changes (operator
 * override is preserved on second edit).
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
type BuilderTab = "preset" | "seed" | "image"

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
  const [builder, setBuilder] = useState<BuilderTab>("preset")
  const [seed, setSeed] = useState("#015736")
  const [tuneOpen, setTuneOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    if (theme) {
      setDraft(payloadToDraft(theme))
    } else if (!isLoading) {
      // Backend hasn't shipped a TenantTheme yet (fresh tenant or
      // dev env without the migration applied). Seed the editor
      // with the platform-default palette so the operator can
      // start designing immediately -- they save it back via the
      // normal PATCH flow once the server side is up.
      setDraft({
        ...deriveThemeSetFromSeed("#015736"),
        logo_url: "",
        logo_dark_url: "",
        favicon_url: "",
      })
    }
  }, [theme, open, isLoading])

  // -------- Path 1: preset --------
  const onApplyPreset = (preset: ThemePreset) => {
    const set = getPresetThemeSet(preset)
    applyThemeSet(set)
    toast.success(`Preset "${preset.name}" aplicado — ajuste fino abaixo se quiser.`)
  }

  // -------- Path 2: seed colour --------
  const onApplySeed = () => {
    const set = deriveThemeSetFromSeed(seed)
    applyThemeSet(set)
    toast.success("Paleta gerada a partir da cor da marca.")
  }

  // -------- Path 3: image --------
  const onExtractFromImage = async (file: File) => {
    try {
      const palette = await extractPaletteFromImage(file)
      if (!palette.length) {
        toast.error("Não consegui extrair cores dessa imagem.")
        return
      }
      // Promote the top-1 colour as the brand seed and regenerate
      // a balanced palette from it, then layer the remaining
      // extracted hues into the category swatches. This makes the
      // image path behave like seed-with-suggestions instead of
      // dumping raw image colours into every UI token.
      const set = deriveThemeSetFromSeed(palette[0])
      // Override category swatches with the actual extracted hues
      // for both modes, keeping the seed-derived swatches as
      // fallback when fewer than 14 colours come back.
      set.category_palette_light = palette.concat(set.category_palette_light).slice(0, 14)
      set.category_palette_dark = palette.concat(set.category_palette_dark).slice(0, 14)
      applyThemeSet(set)
      // If the image gave us a strong second colour, use it as
      // the accent so we don't waste it.
      if (palette[1]) {
        setDraft((d) => {
          if (!d) return d
          return {
            ...d,
            brand_palette_light: { ...d.brand_palette_light, accent: palette[1], accent_foreground: contrastForeground(palette[1]) },
            brand_palette_dark: { ...d.brand_palette_dark, accent: palette[1], accent_foreground: contrastForeground(palette[1]) },
          }
        })
      }
      toast.success(`${palette.length} cores extraídas — paleta gerada.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao extrair cores")
    }
  }

  const applyThemeSet = (set: ThemeSet) => {
    setDraft((d) => ({
      logo_url: d?.logo_url ?? "",
      logo_dark_url: d?.logo_dark_url ?? "",
      favicon_url: d?.favicon_url ?? "",
      ...set,
    }))
  }

  // -------- Manual edit (Ajuste fino) --------
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
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[600px] flex-col border-l border-border surface-2 outline-none">
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
            <span className="text-muted-foreground">Visualizar:</span>
            {(["light", "dark"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-md px-2 py-1",
                  mode === m ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent",
                )}
              >
                {m === "light" ? "Modo claro" : "Modo escuro"}
              </button>
            ))}
            <span className="ml-auto text-[10px] text-muted-foreground">
              Geradores aplicam ambos os modos.
            </span>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[12px]">
            {!draft || !brand || !categories ? (
              <div className="text-muted-foreground">Carregando tema…</div>
            ) : (
              <>
                {/* === BUILDERS === */}
                <section className="rounded-lg border border-border bg-surface-1 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <Wand2 className="h-3.5 w-3.5 text-primary" />
                    <h3 className="text-[12px] font-semibold">Como construir o tema</h3>
                  </div>
                  <p className="mb-3 text-[11px] text-muted-foreground">
                    Comece por um destes três caminhos. Os geradores preenchem ambos
                    os modos (claro e escuro) e a paleta de categorias de uma vez.
                    Você ainda pode ajustar tokens individualmente em <em>Ajuste fino</em> abaixo.
                  </p>
                  <div className="mb-3 flex gap-1">
                    <BuilderTabButton active={builder === "preset"} onClick={() => setBuilder("preset")} icon={<Sparkles className="h-3 w-3" />} label="Preset" />
                    <BuilderTabButton active={builder === "seed"} onClick={() => setBuilder("seed")} icon={<Pipette className="h-3 w-3" />} label="Cor da marca" />
                    <BuilderTabButton active={builder === "image"} onClick={() => setBuilder("image")} icon={<ImageIcon className="h-3 w-3" />} label="Da imagem" />
                  </div>

                  {builder === "preset" && (
                    <div className="grid grid-cols-2 gap-2">
                      {THEME_PRESETS.map((p) => (
                        <PresetCard key={p.id} preset={p} onPick={() => onApplyPreset(p)} />
                      ))}
                    </div>
                  )}

                  {builder === "seed" && (
                    <div className="space-y-2">
                      <p className="text-[11px] text-muted-foreground">
                        Escolha uma única cor — geramos primary, accent, superfícies,
                        bordas e 14 swatches de categoria a partir dela.
                      </p>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={seed}
                          onChange={(e) => setSeed(e.target.value)}
                          className="h-9 w-12 cursor-pointer rounded-md border border-border bg-transparent"
                        />
                        <input
                          type="text"
                          value={seed}
                          onChange={(e) => setSeed(e.target.value)}
                          placeholder="#015736"
                          className="h-9 flex-1 rounded-md border border-border bg-background px-2 font-mono text-[12px] uppercase outline-none focus:border-ring"
                        />
                        <button
                          onClick={onApplySeed}
                          className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
                        >
                          <Wand2 className="h-3.5 w-3.5" /> Gerar
                        </button>
                      </div>
                    </div>
                  )}

                  {builder === "image" && (
                    <div className="space-y-2">
                      <p className="text-[11px] text-muted-foreground">
                        Atalho para quando o único insumo de marca é um logo PNG.
                        Extraímos as cores dominantes, promovemos a primeira como
                        primary e usamos as demais nos gráficos.
                      </p>
                      <ImagePickerButton onPick={onExtractFromImage} />
                    </div>
                  )}
                </section>

                {/* === LIVE PREVIEW === */}
                <ThemePreviewCard brand={brand} categories={categories} />

                {/* === MANUAL EDIT === */}
                <Collapsible
                  title="Ajuste fino"
                  hint="Edite tokens individuais. Use após escolher um caminho acima."
                  open={tuneOpen}
                  onToggle={() => setTuneOpen((v) => !v)}
                >
                  <div className="space-y-5 pt-3">
                    {BRAND_TOKEN_GROUPS.map((group) => (
                      <section key={group.title} className="space-y-2">
                        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{group.title}</h4>
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
                      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Categorias (gráficos)
                      </h4>
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
                  </div>
                </Collapsible>

                {/* === LOGO / FAVICON === */}
                <section className="space-y-2">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Logo & favicon</h3>
                  <UrlField label="Logo URL" value={draft.logo_url} onChange={(v) => setDraft((d) => d ? { ...d, logo_url: v } : d)} />
                  <UrlField label="Logo (modo escuro) URL" value={draft.logo_dark_url} onChange={(v) => setDraft((d) => d ? { ...d, logo_dark_url: v } : d)} />
                  <UrlField label="Favicon URL" value={draft.favicon_url} onChange={(v) => setDraft((d) => d ? { ...d, favicon_url: v } : d)} />
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

function BuilderTabButton({
  active, onClick, icon, label,
}: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "border border-border bg-background text-muted-foreground hover:text-foreground",
      )}
    >
      {icon}
      {label}
    </button>
  )
}

function PresetCard({ preset, onPick }: { preset: ThemePreset; onPick: () => void }) {
  return (
    <button
      onClick={onPick}
      className="group flex flex-col gap-1.5 rounded-md border border-border bg-background p-2 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <div className="flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-md text-[10px] font-bold text-primary-foreground" style={{ background: preset.seed }}>
          {preset.name[0]}
        </span>
        <span className="truncate text-[11px] font-semibold">{preset.name}</span>
      </div>
      <span className="line-clamp-2 text-[10px] leading-snug text-muted-foreground">{preset.description}</span>
    </button>
  )
}

function ThemePreviewCard({ brand, categories }: { brand: BrandPalette; categories: CategoryPalette }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Pré-visualização</h3>
      <div
        className="overflow-hidden rounded-lg border"
        style={{ background: brand.background, color: brand.foreground, borderColor: brand.border }}
      >
        <div className="flex items-center gap-2 border-b px-3 py-2 text-[11px]" style={{ borderColor: brand.border }}>
          <span className="grid h-5 w-5 place-items-center rounded text-[10px] font-bold" style={{ background: brand.primary, color: brand.primary_foreground }}>T</span>
          <span className="font-semibold">Demonstrativos</span>
          <span className="ml-auto inline-flex items-center gap-1 rounded px-1.5 text-[10px]" style={{ background: brand.accent, color: brand.accent_foreground }}>Accent</span>
        </div>
        <div className="space-y-2 p-3 text-[11px]">
          <div className="flex items-center gap-2">
            <button className="rounded px-2 py-1 text-[10px]" style={{ background: brand.primary, color: brand.primary_foreground }}>Primary</button>
            <button className="rounded border px-2 py-1 text-[10px]" style={{ borderColor: brand.border, color: brand.foreground }}>Secundário</button>
            <span className="ml-auto" style={{ color: brand.muted_foreground }}>texto secundário</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {categories.slice(0, 14).map((c, i) => (
              <span key={i} className="h-3 w-3 rounded" style={{ background: c }} />
            ))}
          </div>
          <div className="flex gap-2 text-[10px]">
            <span className="rounded px-1.5 py-0.5" style={{ background: brand.good, color: "#fff" }}>OK</span>
            <span className="rounded px-1.5 py-0.5" style={{ background: brand.warn, color: "#000" }}>!</span>
            <span className="rounded px-1.5 py-0.5" style={{ background: brand.bad, color: "#fff" }}>Erro</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function Collapsible({
  title, hint, open, onToggle, children,
}: { title: string; hint?: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/40"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
        <span className="text-[12px] font-semibold">{title}</span>
        {hint && <span className="ml-2 truncate text-[10px] text-muted-foreground">{hint}</span>}
      </button>
      {open && <div className="border-t border-border px-3 pb-3">{children}</div>}
    </section>
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

function ImagePickerButton({ onPick }: { onPick: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <>
      <button
        onClick={() => inputRef.current?.click()}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
      >
        <ImageIcon className="h-3.5 w-3.5 text-primary" /> Selecionar imagem
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onPick(f)
          e.currentTarget.value = ""
        }}
        className="hidden"
      />
    </>
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
    const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if (luma > 245 || luma < 12) continue
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
