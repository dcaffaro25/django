import { create } from "zustand"
import { persist } from "zustand/middleware"

type Visibility = Record<string, boolean>
type TableState = Record<string, Visibility>

interface ColumnState {
  tables: TableState
  setColumn: (tableKey: string, columnKey: string, visible: boolean) => void
  setAll: (tableKey: string, values: Visibility) => void
  reset: (tableKey: string) => void
}

export const useColumnStore = create<ColumnState>()(
  persist(
    (set) => ({
      tables: {},
      setColumn: (tableKey, columnKey, visible) =>
        set((s) => ({
          tables: {
            ...s.tables,
            [tableKey]: { ...(s.tables[tableKey] ?? {}), [columnKey]: visible },
          },
        })),
      setAll: (tableKey, values) =>
        set((s) => ({ tables: { ...s.tables, [tableKey]: values } })),
      reset: (tableKey) =>
        set((s) => {
          const next = { ...s.tables }
          delete next[tableKey]
          return { tables: next }
        }),
    }),
    { name: "nord.columns" },
  ),
)

export interface ColumnDef {
  key: string
  label: string
  alwaysVisible?: boolean
  defaultVisible?: boolean
}

export function useColumnVisibility(tableKey: string, columns: ColumnDef[]) {
  const stored = useColumnStore((s) => s.tables[tableKey] ?? {})
  const setColumn = useColumnStore((s) => s.setColumn)
  const setAll = useColumnStore((s) => s.setAll)
  const reset = useColumnStore((s) => s.reset)

  const visible: Visibility = Object.fromEntries(
    columns.map((c) => {
      if (c.alwaysVisible) return [c.key, true]
      if (c.key in stored) return [c.key, stored[c.key]!]
      return [c.key, c.defaultVisible !== false]
    }),
  )

  const isVisible = (key: string) => visible[key] !== false

  const toggle = (key: string) => {
    const col = columns.find((c) => c.key === key)
    if (!col || col.alwaysVisible) return
    setColumn(tableKey, key, !isVisible(key))
  }

  const showAll = () =>
    setAll(tableKey, Object.fromEntries(columns.map((c) => [c.key, true])))
  const resetDefaults = () => reset(tableKey)

  return { visible, isVisible, toggle, showAll, resetDefaults }
}
