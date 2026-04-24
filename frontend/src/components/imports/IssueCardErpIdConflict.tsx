import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Card for ``erp_id_conflict`` issues. Actions:
 *
 *   * ``pick_row``   — operator picks one row_id from the conflict; the
 *                     handler drops the others and re-runs detection.
 *   * ``skip_group`` — drop every row of the conflicted erp_id from the
 *                     parsed payload.
 *   * ``abort``      — mark session ``error``.
 *
 * Issue shape (from the backend detector):
 *
 *   {
 *     type: "erp_id_conflict",
 *     location: { sheet: "Transaction", erp_id: "OMIE-1", row_ids: [...] },
 *     context:  { fields: { date: ["2026-01-01", "2026-01-02"], ... } }
 *   }
 *
 * The ``fields`` map carries every shared column that disagrees across
 * the conflict group; the card renders a tiny "which row is right?"
 * table so operators can decide without leaving the page.
 */

type PickState = { rowId: string | number | null }

export function IssueCardErpIdConflict({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const sheet = (issue.location?.sheet as string) ?? "—"
  const erpId = (issue.location?.erp_id as string) ?? "—"
  const rowIds = (issue.location?.row_ids as (string | number)[] | undefined) ?? []
  const fields = (issue.context?.fields as Record<string, unknown[]> | undefined) ?? {}

  const [picked, setPicked] = useState<PickState>({ rowId: rowIds[0] ?? null })

  const canPick = issue.proposed_actions.includes("pick_row")
  const canSkip = issue.proposed_actions.includes("skip_group")
  const canAbort = issue.proposed_actions.includes("abort")

  return (
    <div className="rounded-md border border-destructive/40 bg-background p-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2 text-[12px]">
          <div>
            <span className="font-semibold">
              <code className="font-mono text-[11px]">{erpId}</code>
            </span>{" "}
            <span className="text-muted-foreground">
              em <code className="font-mono">{sheet}</code>, {rowIds.length}{" "}
              linha{rowIds.length === 1 ? "" : "s"}.
            </span>
          </div>

          {Object.keys(fields).length > 0 && (
            <div className="rounded border border-border bg-muted/30 p-2 text-[11px]">
              <div className="mb-1 font-medium text-muted-foreground">
                Campos em conflito
              </div>
              <table className="w-full">
                <tbody>
                  {Object.entries(fields).map(([field, values]) => (
                    <tr key={field}>
                      <td className="py-0.5 pr-2 font-mono text-[10px] text-muted-foreground">
                        {field}
                      </td>
                      <td className="py-0.5">
                        {(values as unknown[]).map((v, i) => (
                          <span key={i} className="mr-2">
                            <code className="rounded bg-surface-1 px-1 text-[10px]">
                              {v === null ? "null" : String(v)}
                            </code>
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pick-row form */}
          {canPick && rowIds.length > 0 && (
            <div className="space-y-1 border-t border-border pt-2">
              <div className="font-medium text-[11px]">Manter apenas uma linha:</div>
              <div className="flex flex-wrap gap-1">
                {rowIds.map((rid) => (
                  <label
                    key={String(rid)}
                    className={cn(
                      "inline-flex cursor-pointer items-center gap-1 rounded border px-2 py-1 text-[11px]",
                      String(picked.rowId) === String(rid)
                        ? "border-primary bg-primary/10"
                        : "border-border bg-background",
                    )}
                  >
                    <input
                      type="radio"
                      className="h-3 w-3"
                      checked={String(picked.rowId) === String(rid)}
                      onChange={() => setPicked({ rowId: rid })}
                    />
                    <code className="font-mono text-[10px]">
                      row_id={String(rid)}
                    </code>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {canPick && (
              <button
                disabled={isResolving || picked.rowId == null}
                onClick={() =>
                  onResolve([
                    {
                      issue_id: issue.issue_id,
                      action: "pick_row",
                      params: { row_id: picked.rowId },
                    },
                  ])
                }
                className={cn(
                  "inline-flex h-7 items-center rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90",
                  (isResolving || picked.rowId == null) && "opacity-50 cursor-not-allowed",
                )}
              >
                Manter esta linha
              </button>
            )}
            {canSkip && (
              <button
                disabled={isResolving}
                onClick={() =>
                  onResolve([
                    { issue_id: issue.issue_id, action: "skip_group" },
                  ])
                }
                className={cn(
                  "inline-flex h-7 items-center rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent",
                  isResolving && "opacity-50",
                )}
              >
                Ignorar grupo inteiro
              </button>
            )}
            {canAbort && (
              <button
                disabled={isResolving}
                onClick={() =>
                  onResolve([{ issue_id: issue.issue_id, action: "abort" }])
                }
                className={cn(
                  "inline-flex h-7 items-center rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-destructive hover:bg-accent",
                  isResolving && "opacity-50",
                )}
              >
                Abortar
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
