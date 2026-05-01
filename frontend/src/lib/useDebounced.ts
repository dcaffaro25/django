import { useEffect, useState } from "react"

/**
 * Returns a debounced copy of ``value`` that only updates after ``ms``
 * milliseconds of no further changes. Use to keep an ``<input>`` snappy
 * while typing — bind the input to local state synchronously, but feed
 * the debounced version into expensive consumers (server fetches, large
 * client filters, URL writes that re-render the whole page).
 *
 * Example:
 *   const [search, setSearch] = useState("")
 *   const debounced = useDebounced(search, 200)
 *   const filtered = useMemo(() => rows.filter(matches(debounced)), [rows, debounced])
 *   <Input value={search} onChange={(e) => setSearch(e.target.value)} />
 *
 * Defaults to 200 ms — the empirical sweet spot from CommandPalette /
 * UsersPage where it was first dialed in. Long enough to coalesce
 * burst typing, short enough to feel instant on results.
 */
export function useDebounced<T>(value: T, ms = 200): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}
