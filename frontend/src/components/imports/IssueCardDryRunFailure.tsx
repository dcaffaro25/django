import { AlertOctagon } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Card for ``dry_run_failure`` — emitted when ``execute_import_job
 * (commit=False)`` reports any rows would fail. One issue per affected
 * sheet (template mode); a single aggregate issue (ETL mode).
 *
 * Issue shape:
 *
 *   {
 *     type: "dry_run_failure",
 *     severity: "error",
 *     location: { sheet: <model name> | null },
 *     context: {
 *       model: <model name> | null,
 *       fail_count: 408,
 *       sample_messages: ["FK entity not found...", ...],
 *
 *       // ETL-only extras:
 *       python_errors?: 2,
 *       database_errors?: 1,
 *       substitution_errors?: 0,
 *     },
 *     proposed_actions: ["abort"],
 *     message: "408 linha(s) falhariam..."
 *   }
 *
 * Per-row detail lives in the AnalyzePreviewPanel above this card —
 * we only summarise here. The only resolvable action is abort; the
 * operator fixes the source file offline and reuploads.
 */

export function IssueCardDryRunFailure({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const sheet = (issue.location?.sheet as string | null | undefined) ?? null
  const model = (issue.context?.model as string | null | undefined) ?? null
  const failCount = (issue.context?.fail_count as number | undefined) ?? 0
  const sampleMessages =
    (issue.context?.sample_messages as string[] | undefined) ?? []
  const pythonErrors = issue.context?.python_errors as number | undefined
  const databaseErrors = issue.context?.database_errors as number | undefined
  const substitutionErrors = issue.context?.substitution_errors as
    | number
    | undefined
  const isEtl =
    pythonErrors !== undefined ||
    databaseErrors !== undefined ||
    substitutionErrors !== undefined

  const canAbort = issue.proposed_actions.includes("abort")

  return (
    <div className="rounded-md border border-destructive/40 bg-background p-3">
      <div className="flex items-start gap-2">
        <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2 text-[12px]">
          <div className="font-semibold text-destructive">
            {failCount} linha{failCount === 1 ? "" : "s"} falhariam
            {sheet || model ? (
              <>
                {" "}em{" "}
                <code className="font-mono text-[11px]">
                  {sheet ?? model}
                </code>
              </>
            ) : null}
          </div>

          {issue.message && (
            <div className="text-[11px] text-muted-foreground">
              {issue.message}
            </div>
          )}

          {isEtl && (
            <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
              {(databaseErrors ?? 0) > 0 && (
                <span>
                  <span className="text-destructive">{databaseErrors}</span>{" "}
                  banco
                </span>
              )}
              {(pythonErrors ?? 0) > 0 && (
                <span>
                  <span className="text-destructive">{pythonErrors}</span>{" "}
                  python
                </span>
              )}
              {(substitutionErrors ?? 0) > 0 && (
                <span>
                  <span className="text-destructive">
                    {substitutionErrors}
                  </span>{" "}
                  substituição
                </span>
              )}
            </div>
          )}

          {sampleMessages.length > 0 && (
            <div className="rounded border border-border bg-muted/30 p-2 text-[11px]">
              <div className="mb-1 font-medium text-muted-foreground">
                Mensagens mais frequentes:
              </div>
              <ul className="space-y-1">
                {sampleMessages.map((msg, i) => (
                  <li key={i} className="font-mono text-[10px] text-destructive">
                    {msg}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-[11px] text-muted-foreground">
            Veja a tabela de prévia acima para a lista completa de linhas
            com erro. Corrija o arquivo de origem e reenvie — não há
            correção automática para falhas detectadas pelo pipeline.
          </div>

          {canAbort && (
            <div className="flex flex-wrap gap-2 pt-1">
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
                Abortar sessão
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
