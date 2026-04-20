import { type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Wraps table rows to render hover-only action icons at the end.
 * Usage:
 *   <RowActionsCell>
 *     <RowAction icon={<Copy/>} label="Duplicar" onClick={...} />
 *     <RowAction icon={<Trash2/>} label="Excluir" onClick={...} variant="danger" />
 *   </RowActionsCell>
 */

export function RowActionsCell({ children }: { children: ReactNode }) {
  return (
    <td className="h-10 w-px whitespace-nowrap px-3 text-right">
      <div
        className={cn(
          "flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100",
        )}
      >
        {children}
      </div>
    </td>
  )
}

export function RowAction({
  icon, label, onClick, variant = "default",
}: {
  icon: ReactNode
  label: string
  onClick: (e: React.MouseEvent) => void
  variant?: "default" | "danger"
}) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick(e) }}
      title={label}
      aria-label={label}
      className={cn(
        "grid h-6 w-6 place-items-center rounded-md border border-transparent transition-colors",
        variant === "danger"
          ? "text-muted-foreground hover:border-danger/30 hover:bg-danger/10 hover:text-danger"
          : "text-muted-foreground hover:border-border hover:bg-accent hover:text-foreground",
      )}
    >
      {icon}
    </button>
  )
}
