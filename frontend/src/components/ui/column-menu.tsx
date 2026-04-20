import { Columns, Check } from "lucide-react"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import type { ColumnDef } from "@/stores/column-visibility"

interface ColumnMenuProps {
  columns: ColumnDef[]
  isVisible: (key: string) => boolean
  toggle: (key: string) => void
  showAll: () => void
  resetDefaults: () => void
  label?: string
}

export function ColumnMenu({
  columns,
  isVisible,
  toggle,
  showAll,
  resetDefaults,
  label = "Colunas",
}: ColumnMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
          <Columns className="h-3.5 w-3.5" />
          {label}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {columns.map((c) => (
          <DropdownMenuItem
            key={c.key}
            onSelect={(e) => { e.preventDefault(); toggle(c.key) }}
            disabled={c.alwaysVisible}
            className={cn("flex cursor-pointer items-center gap-2", c.alwaysVisible && "opacity-60")}
          >
            <span className="inline-flex h-4 w-4 items-center justify-center">
              {isVisible(c.key) && <Check className="h-3.5 w-3.5 text-primary" />}
            </span>
            <span className="flex-1 truncate">{c.label}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={(e) => { e.preventDefault(); showAll() }} className="cursor-pointer text-[12px]">
          Mostrar todas
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={(e) => { e.preventDefault(); resetDefaults() }} className="cursor-pointer text-[12px]">
          Restaurar padrão
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
