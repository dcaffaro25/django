import { Palette, Check } from "lucide-react"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAppStore } from "@/stores/app-store"
import { THEMES, getTheme, type ThemeId } from "@/lib/themes"
import { cn } from "@/lib/utils"

export function ThemePicker() {
  const palette = useAppStore((s) => s.palette)
  const setPalette = useAppStore((s) => s.setPalette)
  const current = getTheme(palette)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Selecionar paleta"
          title={`Paleta: ${current.label}`}
        >
          <Palette className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Paleta</span>
          <span className="text-[10px] font-normal text-muted-foreground">
            claro/escuro separado
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {THEMES.map((t) => {
          const isActive = t.id === (current.id as ThemeId)
          return (
            <DropdownMenuItem
              key={t.id}
              onClick={() => setPalette(t.id)}
              className={cn(
                "cursor-pointer items-start gap-2 py-2",
                isActive && "bg-accent",
              )}
            >
              <div className="mt-0.5 flex shrink-0 items-center gap-1">
                <Swatch color={t.swatches.bg} />
                <Swatch color={t.swatches.primary} />
                <Swatch color={t.swatches.accent} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[13px] font-medium">{t.label}</span>
                  {t.tag && (
                    <span className="rounded-sm bg-muted px-1 text-[9px] uppercase tracking-wide text-muted-foreground">
                      {t.tag}
                    </span>
                  )}
                </div>
                <p className="text-[11px] leading-snug text-muted-foreground">
                  {t.description}
                </p>
              </div>
              <span className="ml-1 inline-flex h-4 w-4 shrink-0 items-center justify-center">
                {isActive && <Check className="h-3.5 w-3.5 text-primary" />}
              </span>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Swatch({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-3 w-3 rounded-full border border-border"
      style={{ backgroundColor: color }}
      aria-hidden
    />
  )
}
