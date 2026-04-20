import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"
import type { ReconTaskStatus } from "@/features/reconciliation/types"

/**
 * Tone policy: reserve saturated color for *noteworthy* or *exceptional* states.
 * Expected/terminal-success states ("completed", "matched", "approved", "pending", "cancelled",
 * "queued") use a neutral gray pill — green is reserved for actions worth calling out.
 */
const TONE: Record<string, string> = {
  // Neutral (default, expected states)
  queued: "bg-muted text-muted-foreground border-transparent",
  cancelled: "bg-muted text-muted-foreground border-transparent",
  pending: "bg-muted text-muted-foreground border-transparent",
  completed: "bg-muted text-muted-foreground border-transparent",
  matched: "bg-muted text-muted-foreground border-transparent",
  approved: "bg-muted text-muted-foreground border-transparent",

  // Active — subtle info
  running: "bg-info/10 text-info border-info/20",

  // Noteworthy / needs attention
  open: "bg-warning/10 text-warning border-warning/30",
  review: "bg-warning/10 text-warning border-warning/30",

  // Exceptional / bad
  failed: "bg-danger/10 text-danger border-danger/30",
  unmatched: "bg-danger/10 text-danger border-danger/30",
}

export function StatusBadge({ status, className }: { status: ReconTaskStatus | string; className?: string }) {
  const { t } = useTranslation()
  const key = String(status)
  const tone = TONE[key] ?? "bg-muted text-muted-foreground border-transparent"
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded-full border px-2 text-[11px] font-medium capitalize",
        tone,
        className,
      )}
    >
      {key === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-info" />}
      {t(`status.${key}`, key)}
    </span>
  )
}
