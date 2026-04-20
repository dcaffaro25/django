import { type ReactNode } from "react"
import { cn } from "@/lib/utils"

interface KpiCardProps {
  label: string
  value: ReactNode
  hint?: ReactNode
  trend?: { value: number; positive?: boolean } | null
  icon?: ReactNode
  tone?: "default" | "success" | "warning" | "danger" | "info" | "primary"
}

const TONE: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
  primary: "text-primary",
}

export function KpiCard({ label, value, hint, trend, icon, tone = "default" }: KpiCardProps) {
  return (
    <div className="card-elevated flex flex-col justify-between gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </div>
      <div className={cn("text-2xl font-semibold tabular-nums tracking-tight", TONE[tone])}>{value}</div>
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        {trend && (
          <span
            className={cn(
              "inline-flex items-center rounded-sm px-1 py-0.5 font-medium tabular-nums",
              trend.positive ? "bg-success/10 text-success" : "bg-danger/10 text-danger",
            )}
          >
            {trend.positive ? "▲" : "▼"} {Math.abs(trend.value).toFixed(1)}%
          </span>
        )}
        {hint}
      </div>
    </div>
  )
}
