import { useCallback, useMemo } from "react"
import { useSearchParams } from "react-router-dom"

/**
 * Sync a plain key/value filter object with the URL search params.
 * Keys with empty/undefined values are removed from the URL, keeping it clean.
 * Non-string values are passed through String(...) for serialization.
 */
export function useUrlFilters<T extends object>(
  defaults: T,
): [T, (patch: Partial<T>) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo<T>(() => {
    const result = { ...defaults } as T
    for (const key of Object.keys(defaults as object) as (keyof T & string)[]) {
      const v = searchParams.get(key)
      if (v != null) {
        const def = (defaults as Record<string, unknown>)[key]
        if (typeof def === "number") {
          const n = Number(v)
          ;(result as Record<string, unknown>)[key] = Number.isFinite(n) ? n : def
        } else {
          ;(result as Record<string, unknown>)[key] = v
        }
      }
    }
    return result
  }, [searchParams, defaults])

  const setFilters = useCallback(
    (patch: Partial<T>) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(patch)) {
          const def = (defaults as Record<string, unknown>)[k]
          if (v === "" || v == null || v === def) {
            next.delete(k)
          } else {
            next.set(k, String(v))
          }
        }
        return next
      }, { replace: true })
    },
    [setSearchParams, defaults],
  )

  return [filters, setFilters]
}
