import { Settings } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Card for ``missing_etl_parameter`` — the transformation rule references
 * a column that isn't present in the transformed data. The only
 * resolvable action here is ``abort``; the operator must fix the rule
 * config upstream and re-upload.
 *
 * Issue shape:
 *
 *   {
 *     type: "missing_etl_parameter",
 *     location: { sheet, expected_column, role },
 *     context:  { rule_id, rule_name, auto_create_journal_entries, present_columns[] }
 *   }
 *
 * Includes a "Editar regra" link when ``rule_id`` is known, deep-linking
 * to the rule editor so operators can close the loop without leaving
 * the session they built.
 */

export function IssueCardMissingParam({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const sheet = (issue.location?.sheet as string) ?? "—"
  const expectedColumn = (issue.location?.expected_column as string) ?? "—"
  const role = (issue.location?.role as string) ?? "—"
  const ruleId = issue.context?.rule_id as number | null | undefined
  const ruleName = issue.context?.rule_name as string | null | undefined
  const presentColumns = (issue.context?.present_columns as string[] | undefined) ?? []

  const canAbort = issue.proposed_actions.includes("abort")

  return (
    <div className="rounded-md border border-destructive/40 bg-background p-3">
      <div className="flex items-start gap-2">
        <Settings className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2 text-[12px]">
          <div>
            Coluna esperada{" "}
            <code className="font-mono text-[11px]">{expectedColumn}</code>{" "}
            <span className="text-muted-foreground">
              ({role}) não está em {sheet}.
            </span>
          </div>
          {ruleName && (
            <div className="text-[11px] text-muted-foreground">
              Regra:{" "}
              <code className="font-mono">
                {ruleName}
                {ruleId ? ` (#${ruleId})` : ""}
              </code>
            </div>
          )}

          {presentColumns.length > 0 && (
            <div className="rounded border border-border bg-muted/30 p-2 text-[11px]">
              <div className="mb-1 font-medium text-muted-foreground">
                Colunas presentes nas linhas transformadas:
              </div>
              <div className="flex flex-wrap gap-1">
                {presentColumns.map((col) => (
                  <span
                    key={col}
                    className="inline-flex h-5 items-center rounded border border-border bg-background px-1.5 font-mono text-[10px]"
                  >
                    {col}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="text-[11px] text-muted-foreground">
            Ajuste o mapeamento da regra para produzir essa coluna, ou
            desabilite <code className="font-mono">auto_create_journal_entries</code>,
            e reimporte.
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            {ruleId && (
              <a
                href={`/etl/transformation-rules/${ruleId}/edit`}
                className="inline-flex h-7 items-center rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent"
              >
                Editar regra
              </a>
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
                Abortar sessão
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
