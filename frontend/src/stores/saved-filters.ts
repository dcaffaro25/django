import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface SavedFilter {
  id: string
  tableKey: string
  name: string
  params: Record<string, unknown>
  createdAt: number
}

interface SavedFiltersState {
  filters: SavedFilter[]
  save: (tableKey: string, name: string, params: Record<string, unknown>) => SavedFilter
  remove: (id: string) => void
  list: (tableKey: string) => SavedFilter[]
  rename: (id: string, name: string) => void
}

export const useSavedFilters = create<SavedFiltersState>()(
  persist(
    (set, get) => ({
      filters: [],
      save: (tableKey, name, params) => {
        const filter: SavedFilter = {
          id: `${tableKey}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          tableKey,
          name: name.trim() || "Sem nome",
          params,
          createdAt: Date.now(),
        }
        set((s) => ({ filters: [...s.filters, filter] }))
        return filter
      },
      remove: (id) => set((s) => ({ filters: s.filters.filter((f) => f.id !== id) })),
      list: (tableKey) =>
        get()
          .filters.filter((f) => f.tableKey === tableKey)
          .sort((a, b) => b.createdAt - a.createdAt),
      rename: (id, name) =>
        set((s) => ({
          filters: s.filters.map((f) => (f.id === id ? { ...f, name: name.trim() || f.name } : f)),
        })),
    }),
    { name: "nord.saved_filters" },
  ),
)
