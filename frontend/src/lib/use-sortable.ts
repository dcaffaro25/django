import { useMemo, useState } from "react"

export type SortDirection = "asc" | "desc"

export interface SortState {
  key: string | null
  direction: SortDirection
}

export type SortAccessor<T> = (row: T) => string | number | null | undefined

export interface UseSortableOpts<T> {
  initialKey?: string | null
  initialDirection?: SortDirection
  accessors: Record<string, SortAccessor<T>>
}

export function useSortable<T>(rows: T[], opts: UseSortableOpts<T>) {
  const [sort, setSort] = useState<SortState>({
    key: opts.initialKey ?? null,
    direction: opts.initialDirection ?? "desc",
  })

  const sorted = useMemo(() => {
    if (!sort.key) return rows
    const accessor = opts.accessors[sort.key]
    if (!accessor) return rows
    const mult = sort.direction === "asc" ? 1 : -1
    const arr = [...rows]
    arr.sort((a, b) => {
      const va = accessor(a)
      const vb = accessor(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * mult
      return String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: "base" }) * mult
    })
    return arr
  }, [rows, sort.key, sort.direction, opts.accessors])

  const toggle = (key: string) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, direction: "asc" }
      if (prev.direction === "asc") return { key, direction: "desc" }
      return { key: null, direction: "asc" }
    })
  }

  return { sort, sorted, toggle }
}
