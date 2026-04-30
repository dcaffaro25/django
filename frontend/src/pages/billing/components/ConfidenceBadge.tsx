import { cn } from "@/lib/utils"

/**
 * Tone bands for match confidence:
 *   ≥ 0.85    high     — green (acceptable to auto-accept)
 *   0.6–0.85  medium   — amber (review)
 *   < 0.6     low      — gray (skeptical / regex-only)
 */
export function ConfidenceBadge({
  value,
  className,
}: {
  value: string | number
  className?: string
}) {
  const v = Number(value) || 0
  const pct = Math.round(v * 100)
  const tone =
    v >= 0.85
      ? "bg-success/10 text-success border-success/30"
      : v >= 0.6
        ? "bg-warning/10 text-warning border-warning/30"
        : "bg-muted text-muted-foreground border-transparent"
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full border px-2 text-[11px] font-medium tabular-nums",
        tone,
        className,
      )}
      title={`Confiança: ${v.toFixed(3)}`}
    >
      {pct}%
    </span>
  )
}
