import { useState } from "react"
import { Bookmark, Check, Plus, Trash2 } from "lucide-react"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useSavedFilters, type SavedFilter } from "@/stores/saved-filters"
import { cn } from "@/lib/utils"

interface Props<T extends Record<string, unknown>> {
  tableKey: string
  currentParams: T
  onApply: (params: T) => void
  /** Compare fn to decide if the current filters match a saved preset (used to mark active one) */
  isActive?: (saved: SavedFilter, current: T) => boolean
}

export function SavedFiltersMenu<T extends Record<string, unknown>>({
  tableKey, currentParams, onApply, isActive,
}: Props<T>) {
  const list = useSavedFilters((s) => s.filters.filter((f) => f.tableKey === tableKey))
  const save = useSavedFilters((s) => s.save)
  const remove = useSavedFilters((s) => s.remove)
  const [naming, setNaming] = useState(false)
  const [draftName, setDraftName] = useState("")

  const onSave = () => {
    const name = draftName.trim()
    if (!name) return
    save(tableKey, name, currentParams)
    setNaming(false)
    setDraftName("")
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
          <Bookmark className="h-3.5 w-3.5" />
          Visões{list.length > 0 ? ` · ${list.length}` : ""}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>Visões salvas</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {list.length === 0 ? (
          <div className="px-2 py-2 text-[11px] text-muted-foreground">Nenhuma visão salva ainda.</div>
        ) : (
          list
            .sort((a, b) => b.createdAt - a.createdAt)
            .map((f) => {
              const active = isActive ? isActive(f, currentParams) : false
              return (
                <DropdownMenuItem
                  key={f.id}
                  onSelect={(e) => { e.preventDefault(); onApply(f.params as T) }}
                  className="flex cursor-pointer items-center gap-2"
                >
                  <span className="inline-flex h-4 w-4 items-center justify-center">
                    {active && <Check className="h-3.5 w-3.5 text-primary" />}
                  </span>
                  <span className="flex-1 truncate">{f.name}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); remove(f.id) }}
                    className={cn(
                      "grid h-5 w-5 place-items-center rounded text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger",
                    )}
                    title="Remover"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </DropdownMenuItem>
              )
            })
        )}
        <DropdownMenuSeparator />
        {!naming ? (
          <DropdownMenuItem
            onSelect={(e) => { e.preventDefault(); setNaming(true); setDraftName("") }}
            className="flex cursor-pointer items-center gap-2 text-primary"
          >
            <Plus className="h-3.5 w-3.5" />
            Salvar visão atual...
          </DropdownMenuItem>
        ) : (
          <div className="p-1.5" onClick={(e) => e.stopPropagation()}>
            <input
              autoFocus
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") onSave(); if (e.key === "Escape") { setNaming(false); setDraftName("") } }}
              placeholder="Nome da visão..."
              className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
            />
            <div className="mt-1 flex items-center justify-end gap-1">
              <button
                onClick={() => { setNaming(false); setDraftName("") }}
                className="h-6 rounded-md px-2 text-[11px] text-muted-foreground hover:bg-accent"
              >Cancelar</button>
              <button
                onClick={onSave}
                disabled={!draftName.trim()}
                className="h-6 rounded-md bg-primary px-2 text-[11px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >Salvar</button>
            </div>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
