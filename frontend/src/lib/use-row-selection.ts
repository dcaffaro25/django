import { useCallback, useMemo, useState } from "react"

export interface RowSelection<ID extends number | string = number> {
  selected: Set<ID>
  count: number
  isSelected: (id: ID) => boolean
  toggle: (id: ID) => void
  toggleAll: (ids: ID[]) => void
  clear: () => void
  setSelected: (ids: ID[]) => void
  allSelected: (ids: ID[]) => boolean
  someSelected: (ids: ID[]) => boolean
}

export function useRowSelection<ID extends number | string = number>(): RowSelection<ID> {
  const [selected, setSelectedSet] = useState<Set<ID>>(new Set())

  const toggle = useCallback((id: ID) => {
    setSelectedSet((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback((ids: ID[]) => {
    setSelectedSet((prev) => {
      const allOn = ids.every((id) => prev.has(id))
      if (allOn) return new Set<ID>()
      const next = new Set(prev)
      ids.forEach((id) => next.add(id))
      return next
    })
  }, [])

  const clear = useCallback(() => setSelectedSet(new Set()), [])

  const setSelected = useCallback((ids: ID[]) => setSelectedSet(new Set(ids)), [])

  return useMemo<RowSelection<ID>>(
    () => ({
      selected,
      count: selected.size,
      isSelected: (id) => selected.has(id),
      toggle,
      toggleAll,
      clear,
      setSelected,
      allSelected: (ids) => ids.length > 0 && ids.every((id) => selected.has(id)),
      someSelected: (ids) => ids.some((id) => selected.has(id)) && !ids.every((id) => selected.has(id)),
    }),
    [selected, toggle, toggleAll, clear, setSelected],
  )
}
