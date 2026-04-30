import { useState } from "react"
import type { LucideIcon } from "lucide-react"

/**
 * Generic collapsible "related items" list used inside the BP and PS
 * edit drawers. Header shows title + live count + open/close toggle;
 * body is the consumer's <li> rows inside a max-height scroll area.
 *
 * Auto-opens when count is between 1 and 10 (small enough to not
 * overwhelm), stays closed when count is 0 or > 10 — operator can
 * always toggle.
 */
export function CollapsibleRelatedList({
  title,
  subtitle,
  icon: Icon,
  count,
  loading,
  empty,
  children,
}: {
  title: string
  subtitle?: string
  icon: LucideIcon
  count: number
  loading: boolean
  empty: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(count > 0 && count <= 10)
  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] font-medium hover:bg-muted/30"
      >
        <span className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <span>{title}</span>
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
            {loading ? "…" : count}
          </span>
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {open ? "fechar" : "abrir"}
        </span>
      </button>
      {subtitle ? (
        <p className="border-t border-border/50 bg-muted/20 px-3 py-1 text-[11px] text-muted-foreground">
          {subtitle}
        </p>
      ) : null}
      {open ? (
        <div className="border-t border-border/50">
          {loading ? (
            <p className="p-3 text-center text-[12px] text-muted-foreground">Carregando…</p>
          ) : count === 0 ? (
            <p className="p-3 text-center text-[12px] text-muted-foreground">{empty}</p>
          ) : (
            <ul className="max-h-[280px] overflow-auto">{children}</ul>
          )}
        </div>
      ) : null}
    </div>
  )
}
