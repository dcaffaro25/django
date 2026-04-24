import { ArrowRight } from "lucide-react"
import type { SubstitutionApplied } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Visible `old → new` badge for the "Substituições aplicadas" panel.
 *
 * The v2 backend collects every substitution that fired during analyze
 * into ``session.substitutions_applied``. Each item has ``field``,
 * ``from``, and ``to`` (plus optional extras like ``model`` / ``rule_id``).
 * This component renders one item as a compact chip so operators can
 * confirm at a glance what the engine rewrote before they commit.
 *
 * Values stringify naively — arrays / objects show as JSON so nothing
 * silently disappears, but the common case (scalar from → scalar to)
 * reads cleanly.
 */
function stringify(v: unknown): string {
  if (v === null || v === undefined) return "—"
  if (typeof v === "string") return v
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

export function SubstitutionAppliedBadge({
  sub,
  className,
}: {
  sub: SubstitutionApplied
  className?: string
}) {
  const field = typeof sub.field === "string" ? sub.field : "?"
  const from = stringify(sub.from)
  const to = stringify(sub.to)
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-surface-1 px-2 py-0.5 text-[11px]",
        className,
      )}
      title={`${field}: ${from} → ${to}`}
    >
      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
        {field}
      </span>
      <span className="truncate font-medium text-muted-foreground line-through">
        {from}
      </span>
      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="truncate font-medium text-foreground">{to}</span>
    </span>
  )
}
