import { useMemo, useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Loader2,
} from "lucide-react"
import type {
  ImportPreview,
  PreviewRowResult,
} from "@/features/imports/types"
import { importsV2 } from "@/features/imports/api"
import { cn } from "@/lib/utils"

/**
 * "Prévia da importação" — what commit is expected to write, as far as
 * the analyze phase could determine.
 *
 * Source of truth is ``session.preview`` (populated by the backend
 * serializer from ``parsed_payload.preview``). Two sections render:
 *
 *  1. Per-model summary table (would_create / would_update / would_fail).
 *  2. Per-row detail table (since the per-row dry-run fix shipped):
 *     every error is shown verbatim; successes are sampled at evenly-
 *     spaced indices up to a backend cap (100/sheet by default). When
 *     the operator wants the full picture, the "Baixar Excel completo"
 *     button hits the xlsx download endpoint and gets every row,
 *     including the original input data per row for grep-friendly
 *     auditing.
 *
 * Returns null when the preview is empty so the host page stays quiet.
 */

function sumByModel(counts: Record<string, number> | undefined): number {
  if (!counts) return 0
  return Object.values(counts).reduce((acc, n) => acc + (n || 0), 0)
}

export function AnalyzePreviewPanel({
  preview,
  sessionId,
  sessionFilename,
  mode,
}: {
  preview: ImportPreview | undefined
  /** Required for the xlsx download. When omitted the button stays
   *  hidden — host pages that render previews without a session ID
   *  (e.g. mocked snapshots) won't get a broken button. */
  sessionId?: number
  sessionFilename?: string
  /** Used for the download URL prefix. Falls back to "template" — the
   *  shared download endpoint is identical between modes, only the URL
   *  prefix differs. */
  mode?: "template" | "etl"
}) {
  const [open, setOpen] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const wouldCreate = preview?.would_create ?? {}
  const wouldFail = preview?.would_fail ?? {}
  const wouldUpdate = preview?.would_update ?? {}
  const rowResults: PreviewRowResult[] = preview?.row_results ?? []
  const fullRowCount = preview?.full_row_count ?? 0
  const hasFullDownload = preview?.has_full_download ?? false
  const displayTruncated = preview?.display_truncated ?? false

  const createTotal = useMemo(() => sumByModel(wouldCreate), [wouldCreate])
  const updateTotal = useMemo(() => sumByModel(wouldUpdate), [wouldUpdate])
  const failTotal = useMemo(() => sumByModel(wouldFail), [wouldFail])
  const grandTotal =
    preview?.total_rows ?? createTotal + updateTotal + failTotal

  // Quiet if we have nothing to show (template mode pre-dry-run, ETL
  // sessions with no preview, etc.).
  if (
    createTotal + updateTotal + failTotal === 0 &&
    rowResults.length === 0
  ) {
    return null
  }

  // Union of model names across the three per-model counts so every
  // mentioned model shows up in the table with zeros where missing.
  const modelNames = Array.from(
    new Set([
      ...Object.keys(wouldCreate),
      ...Object.keys(wouldUpdate),
      ...Object.keys(wouldFail),
    ]),
  ).sort()

  async function onDownloadXlsx() {
    if (sessionId == null) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const ns = mode === "etl" ? "etl" : "template"
      await importsV2[ns].downloadPreviewXlsx(
        sessionId,
        sessionFilename
          ? `${sessionFilename.replace(/\.xlsx$/i, "")}-preview.xlsx`
          : undefined,
      )
    } catch (err) {
      // Surface a brief inline message rather than bubbling up — the
      // download is non-critical, the operator can retry.
      const msg =
        err instanceof Error
          ? err.message
          : "Falha ao baixar a prévia. Tente novamente."
      setDownloadError(msg)
    } finally {
      setDownloading(false)
    }
  }

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
        <FileText className="h-3.5 w-3.5 text-primary" />
        <span className="text-[13px] font-semibold">Prévia da importação</span>
        <span className="text-[11px] text-muted-foreground">
          {createTotal > 0 && (
            <span>
              <span className="text-emerald-600">{createTotal}</span> criações
            </span>
          )}
          {updateTotal > 0 && (
            <>
              {createTotal > 0 ? " · " : ""}
              <span className="text-primary">{updateTotal}</span> atualizações
            </>
          )}
          {failTotal > 0 && (
            <>
              {(createTotal > 0 || updateTotal > 0) ? " · " : ""}
              <span className="text-destructive">{failTotal}</span> falhariam
            </>
          )}
          {" · "}
          {grandTotal} linha{grandTotal === 1 ? "" : "s"} no total
        </span>
      </button>
      {open && (
        <div className="border-t border-border bg-surface-3">
          {/* Per-model count table (existing). */}
          {modelNames.length > 0 && (
            <table className="w-full text-[11px]">
              <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="h-7 px-3">Modelo</th>
                  <th className="h-7 px-3 text-right">Criar</th>
                  <th className="h-7 px-3 text-right">Atualizar</th>
                  <th className="h-7 px-3 text-right">Falharia</th>
                </tr>
              </thead>
              <tbody>
                {modelNames.map((name) => {
                  const c = wouldCreate[name] ?? 0
                  const u = wouldUpdate[name] ?? 0
                  const f = wouldFail[name] ?? 0
                  return (
                    <tr key={name} className="border-t border-border/60">
                      <td className="px-3 py-1.5">
                        <code className="font-mono">{name}</code>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {c > 0 ? (
                          <span className="text-emerald-600">{c}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {u > 0 ? (
                          <span className="text-primary">{u}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {f > 0 ? (
                          <span className="text-destructive">{f}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}

          {/* Per-row detail table (new — preserves the messages the
              dry-run pipeline produces, instead of silently dropping
              them as the previous tally-only logic did). */}
          {rowResults.length > 0 && (
            <PreviewRowResultsTable
              rows={rowResults}
              fullRowCount={fullRowCount}
              displayTruncated={displayTruncated}
            />
          )}

          {/* Footer — explanation + xlsx download. */}
          <div className="border-t border-border bg-muted/20 px-3 py-2 text-[10px] text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex-1 min-w-[200px]">
                Contagens vêm do dry-run do pipeline
                (<code className="font-mono">commit=False</code>) — linhas com
                erro estão listadas como pendências acima e bloqueiam o
                commit.
                {displayTruncated && (
                  <>
                    {" "}
                    Mostrando uma amostra dos sucessos —{" "}
                    <strong>{rowResults.length}</strong> de{" "}
                    <strong>{fullRowCount}</strong> linhas. Baixe o Excel
                    completo para auditar todas.
                  </>
                )}
              </div>
              {hasFullDownload && sessionId != null && (
                <button
                  onClick={onDownloadXlsx}
                  disabled={downloading}
                  className={cn(
                    "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent",
                    downloading && "opacity-50 cursor-not-allowed",
                  )}
                  title="Baixar arquivo Excel com todas as linhas + dados originais"
                >
                  {downloading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Download className="h-3 w-3" />
                  )}
                  {downloading ? "Baixando…" : "Baixar prévia (Excel)"}
                </button>
              )}
            </div>
            {downloadError && (
              <div className="mt-1 text-destructive">{downloadError}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Per-row dry-run results table. Rows are already organised by the
 * backend (errors first within each model, then sampled successes);
 * we just render with sticky-ish styling and a small status icon per
 * row. Caps the visible viewport so a 5k-row sample doesn't blow the
 * page layout — the operator scrolls within the panel.
 */
function PreviewRowResultsTable({
  rows,
  fullRowCount,
  displayTruncated,
}: {
  rows: PreviewRowResult[]
  fullRowCount: number
  displayTruncated: boolean
}) {
  const errorCount = rows.filter((r) => r.status === "error").length
  const successCount = rows.length - errorCount
  return (
    <div className="border-t border-border">
      <div className="flex items-center gap-3 px-3 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>Linhas</span>
        <span>·</span>
        {errorCount > 0 && (
          <span className="text-destructive">{errorCount} com erro</span>
        )}
        {errorCount > 0 && successCount > 0 && <span>·</span>}
        {successCount > 0 && (
          <span className="text-emerald-600">{successCount} ok</span>
        )}
        {displayTruncated && (
          <span className="ml-auto normal-case tracking-normal">
            (amostra de {rows.length} de {fullRowCount} linhas)
          </span>
        )}
      </div>
      <div className="max-h-[360px] overflow-auto">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-7 w-7 px-2"></th>
              <th className="h-7 px-2">Modelo</th>
              <th className="h-7 px-2">Linha</th>
              <th className="h-7 px-2">Ação</th>
              <th className="h-7 px-2">Mensagem</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const isError = r.status === "error"
              return (
                <tr
                  key={`${r.model}-${r.__row_id ?? i}-${i}`}
                  className={cn(
                    "border-t border-border/40",
                    isError && "bg-destructive/5",
                  )}
                >
                  <td className="px-2 py-1 align-top">
                    {isError ? (
                      <AlertCircle className="h-3 w-3 text-destructive" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                    )}
                  </td>
                  <td className="px-2 py-1 align-top">
                    <code className="font-mono">{r.model}</code>
                  </td>
                  <td className="px-2 py-1 align-top tabular-nums text-muted-foreground">
                    {r.__row_id ?? "—"}
                  </td>
                  <td className="px-2 py-1 align-top text-muted-foreground">
                    {r.action ?? "—"}
                  </td>
                  <td className="px-2 py-1 align-top">
                    {r.message ? (
                      <span
                        className={cn(
                          isError ? "text-destructive" : "text-muted-foreground",
                        )}
                      >
                        {r.message}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
