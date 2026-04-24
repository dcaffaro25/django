import { useMemo, useState } from "react"
import { LinkIcon } from "lucide-react"
import type { ImportIssue, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Card for ``unmatched_reference`` and ``fk_ambiguous`` issues. They
 * share the same resolution surface: pick a DB row to map to, optionally
 * stage a ``SubstitutionRule`` so next time the value maps automatically.
 *
 * Expected issue shape:
 *
 *   {
 *     type: "unmatched_reference" | "fk_ambiguous",
 *     location: { sheet, field, value, row_ids?[] },
 *     context:  { related_model, candidates?: [{id, label}], ... }
 *   }
 *
 * If ``context.candidates`` is non-empty, we render them as a pick-list
 * (common for ``fk_ambiguous``). Otherwise the operator types a numeric
 * target_id — tight but works for v1; future iteration could wire a
 * full account/entity picker here.
 *
 * Match-type dropdown exposes ``exact | regex | caseless`` — the three
 * types the ``SubstitutionRule`` model actually supports today. Adding
 * ``startswith`` / ``contains`` later would be a backend migration +
 * one option on this dropdown.
 */

type Candidate = { id: number | string; label?: string }

export function IssueCardUnmatchedReference({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (r: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const sheet = (issue.location?.sheet as string) ?? "—"
  const field = (issue.location?.field as string) ?? "—"
  const originalValue = (issue.location?.value ?? issue.context?.value) as
    | string
    | number
    | null
    | undefined
  const relatedModel = (issue.context?.related_model as string) ?? "—"
  const candidates: Candidate[] = useMemo(() => {
    const raw = issue.context?.candidates as unknown
    if (!Array.isArray(raw)) return []
    return raw.filter(
      (c): c is Candidate => c != null && typeof c === "object" && "id" in c,
    )
  }, [issue.context])

  // Form state — operator choices before firing resolve.
  const [targetId, setTargetId] = useState<string>(
    candidates[0] ? String(candidates[0].id) : "",
  )
  const [createRule, setCreateRule] = useState(false)
  const [matchType, setMatchType] = useState<"exact" | "regex" | "caseless">(
    "exact",
  )
  const [matchValue, setMatchValue] = useState<string>(
    originalValue != null ? String(originalValue) : "",
  )
  const [ruleTitle, setRuleTitle] = useState<string>(
    originalValue != null ? `Auto: ${originalValue} → ${relatedModel}` : "",
  )

  const canMap = issue.proposed_actions.includes("map_to_existing")
  const canIgnore = issue.proposed_actions.includes("ignore_row")
  const canAbort = issue.proposed_actions.includes("abort")

  const parsedTarget = (() => {
    const n = Number(targetId)
    return Number.isFinite(n) && n > 0 ? n : null
  })()

  const submitMap = async () => {
    if (parsedTarget == null) return
    const params: Record<string, unknown> = { target_id: parsedTarget }
    if (createRule) {
      params.create_substitution_rule = true
      params.rule = {
        match_type: matchType,
        match_value: matchValue,
        title: ruleTitle || null,
      }
    }
    await onResolve([
      {
        issue_id: issue.issue_id,
        action: "map_to_existing",
        params,
      },
    ])
  }

  return (
    <div className="rounded-md border border-destructive/40 bg-background p-3">
      <div className="flex items-start gap-2">
        <LinkIcon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2 text-[12px]">
          <div>
            <span className="font-semibold">
              <code className="font-mono text-[11px]">
                {originalValue == null ? "(vazio)" : String(originalValue)}
              </code>
            </span>{" "}
            <span className="text-muted-foreground">
              em <code className="font-mono">{sheet}.{field}</code> — nenhum{" "}
              <code className="font-mono">{relatedModel}</code> correspondente.
            </span>
          </div>
          {issue.message && (
            <div className="text-[11px] text-muted-foreground">
              {issue.message}
            </div>
          )}

          {canMap && (
            <div className="space-y-2 rounded border border-border bg-muted/20 p-2">
              <div className="text-[11px] font-medium text-muted-foreground">
                Mapear para um {relatedModel} existente:
              </div>
              {candidates.length > 0 ? (
                <select
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                >
                  {candidates.map((c) => (
                    <option key={String(c.id)} value={String(c.id)}>
                      #{c.id}
                      {c.label ? ` — ${c.label}` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  inputMode="numeric"
                  placeholder="ID do registro-alvo"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                />
              )}

              <label className="flex items-center gap-2 pt-1 text-[11px]">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={createRule}
                  onChange={(e) => setCreateRule(e.target.checked)}
                />
                <span>
                  Criar regra de substituição para automatizar nas próximas importações
                </span>
              </label>

              {createRule && (
                <div className="space-y-1.5 rounded border border-border bg-background p-2">
                  <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                    <label className="text-[11px] text-muted-foreground">
                      Tipo
                    </label>
                    <select
                      value={matchType}
                      onChange={(e) =>
                        setMatchType(
                          e.target.value as "exact" | "regex" | "caseless",
                        )
                      }
                      className="h-7 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    >
                      <option value="exact">Exato</option>
                      <option value="caseless">
                        Ignorar maiúsc./minúsc. e acentos
                      </option>
                      <option value="regex">Regex</option>
                    </select>
                    <label className="text-[11px] text-muted-foreground">
                      Padrão
                    </label>
                    <input
                      value={matchValue}
                      onChange={(e) => setMatchValue(e.target.value)}
                      className="h-7 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    />
                    <label className="text-[11px] text-muted-foreground">
                      Título
                    </label>
                    <input
                      value={ruleTitle}
                      onChange={(e) => setRuleTitle(e.target.value)}
                      placeholder="(opcional)"
                      className="h-7 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    />
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    A regra é criada ao clicar em "Importar" — pode ainda
                    editar acima antes disso.
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {canMap && (
              <button
                disabled={isResolving || parsedTarget == null}
                onClick={submitMap}
                className={cn(
                  "inline-flex h-7 items-center rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90",
                  (isResolving || parsedTarget == null) &&
                    "opacity-50 cursor-not-allowed",
                )}
              >
                Mapear
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
