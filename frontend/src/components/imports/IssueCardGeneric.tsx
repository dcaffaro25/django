import { useState } from "react"
import { AlertCircle } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Fallback card for unknown issue types. Never hides the issue —
 * shows the raw shape and always offers "Abortar" so a misbehaving
 * detector can never lock an operator out of recovering their session.
 */
export function IssueCardGeneric({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const [showRaw, setShowRaw] = useState(false)
  const canAbort = issue.proposed_actions.includes("abort")

  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-1 text-[12px]">
          <div className="font-semibold">{issue.type}</div>
          {issue.message && (
            <div className="text-[11px] text-muted-foreground">{issue.message}</div>
          )}
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-[11px] text-primary underline"
          >
            {showRaw ? "Ocultar detalhes" : "Ver detalhes"}
          </button>
          {showRaw && (
            <pre className="mt-1 overflow-auto rounded bg-muted p-2 text-[10px]">
              {JSON.stringify({ location: issue.location, context: issue.context }, null, 2)}
            </pre>
          )}
        </div>
        {canAbort && (
          <button
            onClick={() =>
              onResolve([{ issue_id: issue.issue_id, action: "abort" }])
            }
            disabled={isResolving}
            className={cn(
              "inline-flex h-7 shrink-0 items-center rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-destructive hover:bg-accent",
              isResolving && "opacity-50",
            )}
          >
            Abortar
          </button>
        )}
      </div>
    </div>
  )
}
