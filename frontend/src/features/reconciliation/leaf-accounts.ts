import { useMemo } from "react"
import { useAccounts } from "./hooks"
import type { AccountLite } from "./types"

/**
 * Leaf accounts are the only legitimate posting targets — an operator
 * picking a group/parent in the conciliation flows would create journal
 * entries that violate the CoA rollups.
 *
 * We derive leaf-ness client-side because the serializer doesn't expose
 * an `is_leaf` flag. The important detail is that **only active children
 * count** when deciding whether an account is a parent: an inactive
 * dangling child was enough to silently hide its parent from the picker
 * (reported against the "evolat" tenant, where "Descontos Obtidos
 * Matéria-Prima" never showed up because of an inactive leftover child).
 */
export function useLeafAccounts(): AccountLite[] {
  const { data: accounts = [] } = useAccounts()
  return useMemo(() => {
    const parents = new Set<number>()
    for (const a of accounts) {
      if (a.parent != null && a.is_active !== false) parents.add(a.parent)
    }
    return (accounts as AccountLite[])
      .filter((a) => a.is_active !== false && !parents.has(a.id))
      .sort(
        (a, b) =>
          (a.account_code ?? "").localeCompare(b.account_code ?? "", undefined, { numeric: true }) ||
          (a.path ?? "").localeCompare(b.path ?? "", undefined, { numeric: true }),
      )
  }, [accounts])
}
