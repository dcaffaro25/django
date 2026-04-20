import { type ReactNode } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

export function BulkActionsBar({
  count, onClear, children, className,
}: {
  count: number
  onClear: () => void
  children: ReactNode
  className?: string
}) {
  if (count === 0) return null
  return (
    <div
      className={cn(
        "sticky top-0 z-20 -mx-1 flex animate-slide-up items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 shadow-soft backdrop-blur",
        className,
      )}
    >
      <span className="inline-flex items-center gap-1.5 rounded-md bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary">
        {count} selecionado{count > 1 ? "s" : ""}
      </span>
      <div className="ml-2 flex flex-1 items-center gap-2">{children}</div>
      <button
        onClick={onClear}
        className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <X className="h-3 w-3" /> Limpar seleção
      </button>
    </div>
  )
}

export function BulkAction({
  icon, label, onClick, variant = "default", disabled,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
  variant?: "default" | "danger" | "primary"
  disabled?: boolean
}) {
  const tone =
    variant === "danger"
      ? "border-danger/30 bg-danger/10 text-danger hover:bg-danger/15"
      : variant === "primary"
      ? "bg-primary text-primary-foreground hover:bg-primary/90"
      : "border-border bg-background hover:bg-accent"
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[11px] font-medium transition-colors disabled:opacity-50",
        variant !== "primary" && "border",
        tone,
      )}
    >
      {icon}
      {label}
    </button>
  )
}

export function SelectAllCheckbox({
  allSelected, someSelected, onToggle,
}: {
  allSelected: boolean
  someSelected: boolean
  onToggle: () => void
}) {
  return (
    <input
      type="checkbox"
      checked={allSelected}
      ref={(el) => {
        if (el) el.indeterminate = someSelected
      }}
      onChange={onToggle}
      onClick={(e) => e.stopPropagation()}
      className="h-3.5 w-3.5 accent-primary"
    />
  )
}

export function RowCheckbox({
  checked, onToggle,
}: {
  checked: boolean
  onToggle: () => void
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onToggle}
      onClick={(e) => e.stopPropagation()}
      className="h-3.5 w-3.5 accent-primary"
    />
  )
}
