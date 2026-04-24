import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Hash,
  Loader2,
  User,
  X,
} from "lucide-react"
import { DiagnosticsPanel } from "./DiagnosticsPanel"
import { importsV2 } from "@/features/imports/api"
import type { ImportSession } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Inline detail panel rendered below the selected queue row (Phase 6.z-c).
 *
 * Fetches the full ``ImportSession`` via ``GET /v2/sessions/<id>/``,
 * auto-refreshes every 2s while the status is non-terminal so an
 * operator who opens a still-running session sees progress live.
 * Wraps ``DiagnosticsPanel`` in read-only mode — the interactive
 * resolve/commit flow lives on the upload page (for now — a future
 * iteration can lift it onto the queue).
 *
 * Keeps the queue audit-focused: "what did this file do?". The
 * view also surfaces the raw session header (filename, mode,
 * operator, timestamps) above the diagnostics so operators don't
 * need to cross-reference the queue row.
 */
export function SessionDetailView({
  sessionId,
  onClose,
}: {
  sessionId: number
  onClose?: () => void
}) {
  const { data, isLoading, isError } = useQuery<ImportSession>({
    queryKey: ["imports", "v2", "session-detail", sessionId],
    queryFn: () => importsV2.template.getSession(sessionId),
    refetchInterval: (q) => {
      const s = q.state.data
      if (!s) return 2000
      const running =
        s.status === "analyzing" || s.status === "committing"
      return running ? 2000 : false
    },
    staleTime: 0,
  })

  return (
    <section className="card-elevated">
      <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <FileText className="h-4 w-4 shrink-0 text-primary" />
            <span className="truncate" title={data?.file_name}>
              {data?.file_name ?? `Sessão #${sessionId}`}
            </span>
            {data?.mode && (
              <span className="inline-flex shrink-0 rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                {data.mode}
              </span>
            )}
          </div>
          {data && (
            <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
              <SessionHeaderStat
                icon={Clock}
                label="Criada"
                value={new Date(data.created_at ?? "").toLocaleString("pt-BR")}
              />
              {data.committed_at && (
                <SessionHeaderStat
                  icon={Clock}
                  label="Importada"
                  value={new Date(data.committed_at).toLocaleString("pt-BR")}
                />
              )}
              <SessionHeaderStat
                icon={User}
                label="Operador"
                value={extractOperator(data) ?? "—"}
              />
              {data.file_hash && (
                <SessionHeaderStat
                  icon={Hash}
                  label="SHA-256"
                  value={`${data.file_hash.slice(0, 10)}…`}
                  title={data.file_hash}
                />
              )}
            </div>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar detalhes"
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent/50 hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </header>

      <div className="p-4">
        {isLoading && (
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Carregando sessão…
          </div>
        )}
        {isError && (
          <div className="text-[12px] text-destructive">
            Falha ao carregar a sessão. Verifique se ela ainda existe.
          </div>
        )}
        {data && (
          <div className="space-y-4">
            {/* Interactive handlers (resolve/commit) are wired by the
                upload page today — the queue detail view renders the
                session read-only. Future iteration can lift those
                handlers here so operators resolve directly from the
                queue. */}
            <DiagnosticsPanel
              session={data}
              onResolve={noopResolve}
              isResolving={false}
            />
            {data.result && Object.keys(data.result).length > 0 && (
              <RawResultJson result={data.result} />
            )}
          </div>
        )}
      </div>
    </section>
  )
}

function SessionHeaderStat({
  icon: Icon,
  label,
  value,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  title?: string
}) {
  return (
    <span className="inline-flex items-center gap-1" title={title ?? value}>
      <Icon className="h-3 w-3" />
      <span className="font-medium text-foreground/70">{label}:</span>
      <span className="truncate">{value}</span>
    </span>
  )
}

/**
 * Collapsible JSON viewer for ``session.result``. Committed sessions
 * carry per-model counts + substitution_rules_created; errored
 * sessions carry the diagnostic. Both worth surfacing for
 * troubleshooting without polluting the main panel.
 */
function RawResultJson({ result }: { result: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const pretty = useMemo(() => JSON.stringify(result, null, 2), [result])
  return (
    <div className="card-elevated overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] hover:bg-accent/30"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span className="font-semibold">Resultado bruto (JSON)</span>
      </button>
      {open && (
        <pre
          className={cn(
            "overflow-x-auto border-t border-border bg-surface-3 p-3",
            "font-mono text-[11px] text-foreground/80 whitespace-pre",
          )}
        >
          {pretty}
        </pre>
      )}
    </div>
  )
}

/** No-op resolve — the queue detail view is read-only for now. */
async function noopResolve(): Promise<void> {
  // Intentional: queue detail doesn't expose resolve/commit yet.
}

/**
 * Best-effort operator name pulled from ``session.result`` if the
 * backend stashed it there (common for committed sessions where
 * ``created_by`` was recorded at analyze time). Otherwise ``null``.
 * The queue's list serializer already computes ``operator_name`` but
 * the full session detail doesn't surface it as a field — this
 * helper keeps the UI honest when the data isn't available.
 */
function extractOperator(session: ImportSession): string | null {
  const raw = session.result as { operator_name?: unknown } | undefined
  if (raw && typeof raw.operator_name === "string") {
    return raw.operator_name
  }
  return null
}

