import { useMemo, useState } from "react"
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Info,
  Loader2,
} from "lucide-react"
import { AnalyzePreviewPanel } from "./AnalyzePreviewPanel"
import { ProgressStrip } from "./ProgressStrip"
import { SubstitutionAppliedBadge } from "./SubstitutionAppliedBadge"
import { IssueCardErpIdConflict } from "./IssueCardErpIdConflict"
import { IssueCardUnmatchedReference } from "./IssueCardUnmatchedReference"
import { IssueCardEditValue } from "./IssueCardEditValue"
import { IssueCardMissingParam } from "./IssueCardMissingParam"
import { IssueCardGeneric } from "./IssueCardGeneric"
import type { ImportIssue, ImportSession, ImportResolutionInput } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Diagnostics panel rendered below a v2 analyze preview. Splits the
 * session's open issues by ``type`` and hands each group to the right
 * renderer. A single "Substituições aplicadas" section shows the
 * ``badge: old → new`` list for operator review.
 *
 * ``onResolve`` is the single side-effect wired by the host page —
 * every card receives it and calls it with a single-item resolutions
 * batch when the operator picks an action. The host is responsible
 * for issuing the actual ``POST /resolve/<id>/`` call; this component
 * only orchestrates the UI.
 *
 * Unknown issue types fall through to ``IssueCardGeneric`` which
 * renders the raw dict plus an "Abortar" button so a misbehaving
 * detector can never lock a session up completely.
 */

const ISSUE_LABELS: Record<string, string> = {
  erp_id_conflict: "Conflitos de erp_id",
  unmatched_reference: "Referências não mapeadas",
  fk_ambiguous: "Referências ambíguas",
  bad_date_format: "Datas inválidas",
  negative_amount: "Valores negativos",
  je_balance_mismatch: "Lançamentos desequilibrados",
  missing_etl_parameter: "Parâmetros ausentes (ETL)",
}

function groupByType(issues: ImportIssue[]): Map<string, ImportIssue[]> {
  const m = new Map<string, ImportIssue[]>()
  for (const i of issues) {
    const t = i.type || "unknown"
    if (!m.has(t)) m.set(t, [])
    m.get(t)!.push(i)
  }
  return m
}

export function DiagnosticsPanel({
  session,
  onResolve,
  isResolving,
  onCommit,
  isCommitting,
}: {
  session: ImportSession
  onResolve: (resolutions: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
  onCommit?: () => Promise<void>
  isCommitting?: boolean
}) {
  const groups = useMemo(
    () => groupByType(session.open_issues ?? []),
    [session.open_issues],
  )
  const subs = session.substitutions_applied ?? []
  const blocking = session.open_issues?.some((i) => i.severity === "error") ?? false
  const totalIssues = session.open_issues?.length ?? 0
  // Phase 6.z-a — analyze/commit run in a Celery worker. While the
  // worker is still chewing the file, the session status is
  // ``analyzing`` (first pass) or ``committing`` (during write). The
  // host page polls and re-renders; we just flag the state here so
  // the header shows "Analisando no servidor…" instead of a
  // misleading "Pronto para importar".
  const workerBusy = session.status === "analyzing" || session.status === "committing"

  return (
    <div className="space-y-4">
      {/* Live progress strip (Phase 6.z-e) — only visible while the
          worker is chewing. Renders null on terminal sessions. */}
      <ProgressStrip progress={session.progress} variant="card" />

      {/* Header summary: counts + overall commit state. */}
      <div
        className={cn(
          "card-elevated flex items-center gap-3 px-4 py-3 text-[12px]",
          workerBusy
            ? "border-l-4 border-l-blue-500"
            : blocking
              ? "border-l-4 border-l-destructive"
              : "border-l-4 border-l-emerald-500",
        )}
      >
        {workerBusy ? (
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-blue-500" />
        ) : blocking ? (
          <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
        )}
        <div className="flex-1">
          <div className="font-semibold">
            {workerBusy
              ? session.status === "committing"
                ? "Importando no servidor…"
                : "Analisando no servidor…"
              : blocking
                ? "Existem problemas que precisam ser resolvidos antes de importar."
                : "Pronto para importar."}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {workerBusy
              ? "Isso roda em um worker Celery. Você pode acompanhar aqui ou voltar depois — a sessão não se perde."
              : (
                <>
                  {totalIssues > 0
                    ? `${totalIssues} diagnóstico${totalIssues === 1 ? "" : "s"} aberto${totalIssues === 1 ? "" : "s"} · `
                    : ""}
                  {session.summary?.sheets
                    ? `${Object.entries(session.summary.sheets)
                        .map(([name, n]) => `${name}: ${n} linha${n === 1 ? "" : "s"}`)
                        .join(" · ")}`
                    : ""}
                </>
              )}
          </div>
        </div>
        {onCommit && !workerBusy && (
          <button
            onClick={onCommit}
            disabled={!session.is_committable || isCommitting}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90",
              (!session.is_committable || isCommitting) && "opacity-50 cursor-not-allowed",
            )}
          >
            {isCommitting ? "Importando…" : "Importar"}
          </button>
        )}
      </div>

      {/* Import preview — what commit will write. Renders null when
          the backend didn't populate preview counts (template mode
          today; ETL mode always has them after Phase 6.x). Placed
          before substitutions so the operator sees the bottom line
          first. */}
      <AnalyzePreviewPanel preview={session.preview} />

      {/* Substitutions applied — only shown if any. */}
      {subs.length > 0 && (
        <SubstitutionsAppliedSection subs={subs} />
      )}

      {/* One section per issue type. */}
      {[...groups.entries()].map(([type, items]) => (
        <IssueGroupSection
          key={type}
          type={type}
          issues={items}
          onResolve={onResolve}
          isResolving={isResolving}
        />
      ))}

      {/* When there are no issues + no subs + session is clean, keep the
          panel silent — the host's own commit button takes over. */}
    </div>
  )
}

function SubstitutionsAppliedSection({
  subs,
}: {
  subs: ImportSession["substitutions_applied"]
}) {
  const [open, setOpen] = useState(true)
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
        <Info className="h-3.5 w-3.5 text-primary" />
        <span className="text-[13px] font-semibold">
          Substituições aplicadas
        </span>
        <span className="text-[11px] text-muted-foreground">
          {subs.length} substituição{subs.length === 1 ? "" : "ões"}
        </span>
      </button>
      {open && (
        <div className="flex flex-wrap gap-2 border-t border-border bg-surface-3 p-3">
          {subs.map((s, i) => (
            <SubstitutionAppliedBadge key={i} sub={s} />
          ))}
        </div>
      )}
    </div>
  )
}

function IssueGroupSection({
  type,
  issues,
  onResolve,
  isResolving,
}: {
  type: string
  issues: ImportIssue[]
  onResolve: (resolutions: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  const [open, setOpen] = useState(true)
  const label = ISSUE_LABELS[type] ?? type
  const hasError = issues.some((i) => i.severity === "error")

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
        {hasError ? (
          <AlertCircle className="h-3.5 w-3.5 text-destructive" />
        ) : (
          <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
        )}
        <span
          className={cn(
            "text-[13px] font-semibold",
            hasError ? "text-destructive" : "text-amber-600",
          )}
        >
          {label}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {issues.length}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border bg-surface-3 p-3">
          {issues.map((issue) => (
            <IssueCard
              key={issue.issue_id}
              issue={issue}
              onResolve={onResolve}
              isResolving={isResolving}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** Dispatch to the right card by issue.type. */
function IssueCard({
  issue,
  onResolve,
  isResolving,
}: {
  issue: ImportIssue
  onResolve: (resolutions: ImportResolutionInput[]) => Promise<void>
  isResolving?: boolean
}) {
  switch (issue.type) {
    case "erp_id_conflict":
      return <IssueCardErpIdConflict issue={issue} onResolve={onResolve} isResolving={isResolving} />
    case "unmatched_reference":
    case "fk_ambiguous":
      return (
        <IssueCardUnmatchedReference
          issue={issue}
          onResolve={onResolve}
          isResolving={isResolving}
        />
      )
    case "bad_date_format":
    case "negative_amount":
      return <IssueCardEditValue issue={issue} onResolve={onResolve} isResolving={isResolving} />
    case "missing_etl_parameter":
      return <IssueCardMissingParam issue={issue} onResolve={onResolve} isResolving={isResolving} />
    default:
      return <IssueCardGeneric issue={issue} onResolve={onResolve} isResolving={isResolving} />
  }
}
