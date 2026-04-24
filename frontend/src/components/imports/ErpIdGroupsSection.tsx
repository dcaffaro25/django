import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Layers3 } from "lucide-react"
import type { ImportSession, ImportTransactionGroup } from "@/features/imports/types"

/**
 * ETL-only view: shows how the transformed Transaction rows cluster
 * by ``__erp_id``. One row per group, with count and status
 * (OK / tem conflito aberto). Per the Option-B / 2a semantics shipped
 * in Phases 1–3, N rows with the same erp_id collapse to ONE
 * Transaction + N opposing JournalEntries + 1 aggregated bank JE —
 * this panel is how the operator confirms the grouping before
 * committing.
 *
 * Source of truth is ``session.transaction_groups`` — populated by the
 * serializer so ``parsed_payload`` stays internal. The backend
 * canonicalises missing/empty erp_id into a sentinel (``null``) bucket,
 * and flags each group's ``has_conflict`` from matching
 * ``open_issues.erp_id_conflict`` entries.
 *
 * Render order: groups with conflicts first (red badge), then by row
 * count descending, then by erp_id alphabetical — so the operator's
 * attention lands on what needs action.
 */

function orderGroups(groups: ImportTransactionGroup[]): ImportTransactionGroup[] {
  return [...groups].sort((a, b) => {
    if (a.has_conflict !== b.has_conflict) return a.has_conflict ? -1 : 1
    if (a.row_count !== b.row_count) return b.row_count - a.row_count
    return String(a.erp_id ?? "").localeCompare(String(b.erp_id ?? ""))
  })
}

export function ErpIdGroupsSection({ session }: { session: ImportSession }) {
  const [open, setOpen] = useState(true)
  const [expanded, setExpanded] = useState<Set<string | null>>(new Set())

  const groups = useMemo(
    () => orderGroups(session.transaction_groups ?? []),
    [session.transaction_groups],
  )

  if (groups.length === 0) return null

  const splitCount = groups.filter((g) => g.row_count > 1).length
  const totalRows = groups.reduce((acc, g) => acc + g.row_count, 0)

  const toggleExpand = (erpId: string | null) =>
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(erpId)) next.delete(erpId)
      else next.add(erpId)
      return next
    })

  return (
    <div className="card-elevated overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/30"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <Layers3 className="h-3.5 w-3.5 text-primary" />
        <span className="text-[13px] font-semibold">
          Grupos de <code className="font-mono">erp_id</code>
        </span>
        <span className="text-[11px] text-muted-foreground">
          {groups.length} grupo{groups.length === 1 ? "" : "s"}
          {splitCount > 0
            ? ` · ${splitCount} com linhas múltiplas`
            : ""}
          {" · "}
          {totalRows} linha{totalRows === 1 ? "" : "s"}
        </span>
      </button>
      {open && (
        <div className="border-t border-border bg-surface-3">
          <table className="w-full text-[11px]">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-7 px-3 w-8"></th>
                <th className="h-7 px-3">erp_id</th>
                <th className="h-7 px-3">Linhas</th>
                <th className="h-7 px-3">Status</th>
                <th className="h-7 px-3">Observação</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const key = g.erp_id
                const isExpanded = expanded.has(key)
                return (
                  <ErpIdGroupRow
                    key={String(key ?? "∅")}
                    group={g}
                    expanded={isExpanded}
                    onToggle={() => toggleExpand(key)}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ErpIdGroupRow({
  group,
  expanded,
  onToggle,
}: {
  group: ImportTransactionGroup
  expanded: boolean
  onToggle: () => void
}) {
  const { erp_id: erpId, row_count: rowCount, has_conflict: hasConflict, rows } = group
  const isSingleRow = rowCount === 1
  const isSplit = rowCount > 1
  return (
    <>
      <tr className="border-t border-border/60">
        <td className="px-3 py-1.5">
          <button
            onClick={onToggle}
            className="text-muted-foreground hover:text-foreground"
            aria-label={expanded ? "Recolher linhas" : "Expandir linhas"}
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        </td>
        <td className="px-3 py-1.5">
          {erpId == null ? (
            <span className="italic text-muted-foreground">
              (sem erp_id)
            </span>
          ) : (
            <code className="font-mono text-[10px]">{erpId}</code>
          )}
        </td>
        <td className="px-3 py-1.5 tabular-nums">{rowCount}</td>
        <td className="px-3 py-1.5">
          {hasConflict ? (
            <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
              CONFLITO
            </span>
          ) : isSplit ? (
            <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
              GRUPO
            </span>
          ) : (
            <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600">
              OK
            </span>
          )}
        </td>
        <td className="px-3 py-1.5 text-[10px] text-muted-foreground">
          {hasConflict
            ? "Campos divergem entre linhas do grupo — ver cartão abaixo."
            : isSplit
              ? "Será 1 Transaction com N JournalEntries (perna agregada no banco)."
              : isSingleRow
                ? "Transaction simples."
                : ""}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td></td>
          <td colSpan={4} className="px-3 pb-2">
            <div className="max-h-60 overflow-auto rounded border border-border bg-background">
              <table className="w-full text-[10px]">
                <thead className="sticky top-0 bg-muted/30">
                  <tr>
                    <th className="h-5 px-2 text-left">__row_id</th>
                    <th className="h-5 px-2 text-left">Campos</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="px-2 py-1 font-mono text-muted-foreground">
                        {String(r["__row_id"] ?? "—")}
                      </td>
                      <td className="px-2 py-1">
                        <code className="whitespace-pre-wrap break-all text-[10px]">
                          {JSON.stringify(
                            Object.fromEntries(
                              Object.entries(r).filter(
                                ([k]) => !k.startsWith("__"),
                              ),
                            ),
                          )}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
