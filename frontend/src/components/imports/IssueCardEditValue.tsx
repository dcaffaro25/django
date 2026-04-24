import { useState } from "react"
import { Pencil } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Card for ``bad_date_format`` and ``negative_amount`` issues. Single
 * resolution surface: type the corrected value inline, submit,
 * re-detect.
 *
 * Expected issue shape:
 *
 *   {
 *     type: "bad_date_format" | "negative_amount",
 *     location: { sheet, row_id, field },
 *     context:  { value, ... },
 *   }
 *
 * Input type hint: date-like fields use ``<input type="date">`` so the
 * browser gives operators a calendar picker; amount fields use
 * ``<input type="number">``. Everything else falls back to text.
 *
 * The backend re-runs detection after the resolution; if the operator
 * types an equally-invalid replacement they'll see the same issue
 * appear again (with a fresh ``issue_id``).
 */

export function IssueCardEditValue({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const sheet = (issue.location?.sheet as string) ?? "—"
  const rowId = issue.location?.row_id as string | number | undefined
  const field = (issue.location?.field as string) ?? "—"
  const oldValue = issue.context?.value as unknown

  const isDate = issue.type === "bad_date_format"
  const isAmount = issue.type === "negative_amount"

  const [value, setValue] = useState<string>(
    oldValue == null ? "" : String(oldValue),
  )

  const canEdit = issue.proposed_actions.includes("edit_value")
  const canIgnore = issue.proposed_actions.includes("ignore_row")
  const canAbort = issue.proposed_actions.includes("abort")

  const submitEdit = async () => {
    const parsed: unknown = isAmount
      ? Number(value)
      : isDate
        ? value // ISO yyyy-mm-dd — backend parses same as analyze
        : value
    if (isAmount && !Number.isFinite(parsed)) return
    await onResolve([
      {
        issue_id: issue.issue_id,
        action: "edit_value",
        params: { row_id: rowId, field, new_value: parsed },
      },
    ])
  }

  return (
    <div className="rounded-md border border-destructive/40 bg-background p-3">
      <div className="flex items-start gap-2">
        <Pencil className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2 text-[12px]">
          <div>
            <code className="font-mono text-[11px]">
              {sheet}.{field}
            </code>{" "}
            <span className="text-muted-foreground">
              (row_id <code className="font-mono">{String(rowId ?? "?")}</code>):
              valor atual{" "}
              <code className="rounded bg-surface-1 px-1 text-[10px]">
                {oldValue == null ? "null" : String(oldValue)}
              </code>
            </span>
          </div>
          {issue.message && (
            <div className="text-[11px] text-muted-foreground">
              {issue.message}
            </div>
          )}

          {canEdit && (
            <div className="flex items-center gap-2">
              <label className="text-[11px] text-muted-foreground">
                Novo valor:
              </label>
              <input
                type={isDate ? "date" : isAmount ? "number" : "text"}
                step={isAmount ? "any" : undefined}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="h-7 flex-1 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {canEdit && (
              <button
                disabled={isResolving || !value}
                onClick={submitEdit}
                className={cn(
                  "inline-flex h-7 items-center rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90",
                  (isResolving || !value) && "opacity-50 cursor-not-allowed",
                )}
              >
                Corrigir
              </button>
            )}
            {canIgnore && (
              <button
                disabled={isResolving}
                onClick={() =>
                  onResolve([
                    { issue_id: issue.issue_id, action: "ignore_row" },
                  ])
                }
                className={cn(
                  "inline-flex h-7 items-center rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent",
                  isResolving && "opacity-50",
                )}
              >
                Ignorar linha
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
