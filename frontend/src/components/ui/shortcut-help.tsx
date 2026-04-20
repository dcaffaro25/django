import { useEffect, useState } from "react"
import { useHotkeys } from "react-hotkeys-hook"
import { X, Keyboard } from "lucide-react"
import { cn } from "@/lib/utils"

type Section = { title: string; items: Array<{ keys: string[]; label: string }> }

/**
 * Global keyboard-shortcut help modal. Triggered by `?`.
 * Pass `sections` to extend with page-specific shortcuts; global shortcuts are always shown.
 */
export function ShortcutHelp({ extra = [] }: { extra?: Section[] }) {
  const [open, setOpen] = useState(false)

  useHotkeys("shift+/", (e) => { e.preventDefault(); setOpen((v) => !v) }, { enableOnFormTags: false })
  useHotkeys("escape", () => setOpen(false), { enabled: open })

  useEffect(() => {
    if (!open) return
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = "" }
  }, [open])

  if (!open) return null

  const globalSections: Section[] = [
    {
      title: "Global",
      items: [
        { keys: ["⌘", "K"], label: "Abrir palheta de comandos / busca global" },
        { keys: ["⌘", "B"], label: "Recolher / expandir menu lateral" },
        { keys: ["?"], label: "Mostrar esta ajuda" },
        { keys: ["Esc"], label: "Fechar drawer / diálogo" },
      ],
    },
  ]
  const all = [...globalSections, ...extra]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setOpen(false)}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-[560px] max-w-[92vw] animate-slide-up overflow-hidden rounded-xl border border-border surface-2 shadow-elev",
        )}
      >
        <div className="flex h-11 items-center justify-between border-b border-border px-4">
          <div className="flex items-center gap-2 text-[13px] font-semibold">
            <Keyboard className="h-3.5 w-3.5 text-muted-foreground" />
            Atalhos de teclado
          </div>
          <button onClick={() => setOpen(false)} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[480px] overflow-y-auto p-4 text-[12px]">
          {all.map((s) => (
            <div key={s.title} className="mb-4 last:mb-0">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80">{s.title}</div>
              <dl className="space-y-1.5">
                {s.items.map((it, i) => (
                  <div key={i} className="flex items-center justify-between gap-3">
                    <dt className="text-muted-foreground">{it.label}</dt>
                    <dd className="flex shrink-0 items-center gap-1">
                      {it.keys.map((k, j) => (
                        <span key={j} className="text-kbd min-w-[24px] px-1.5">{k}</span>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
