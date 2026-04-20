import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import type { SortState } from "@/lib/use-sortable"

export function SortableHeader({
  columnKey, label, sort, onToggle, align = "left", className,
}: {
  columnKey: string
  label: string
  sort: SortState
  onToggle: (key: string) => void
  align?: "left" | "right" | "center"
  className?: string
}) {
  const active = sort.key === columnKey
  const Icon = !active ? ChevronsUpDown : sort.direction === "asc" ? ChevronUp : ChevronDown
  return (
    <button
      type="button"
      onClick={() => onToggle(columnKey)}
      className={cn(
        "group inline-flex items-center gap-1 text-left transition-colors hover:text-foreground",
        active ? "text-foreground" : "text-muted-foreground",
        align === "right" && "flex-row-reverse",
        align === "center" && "justify-center",
        className,
      )}
    >
      <span>{label}</span>
      <Icon
        className={cn(
          "h-3 w-3 shrink-0 transition-opacity",
          active ? "opacity-100" : "opacity-40 group-hover:opacity-70",
        )}
      />
    </button>
  )
}
