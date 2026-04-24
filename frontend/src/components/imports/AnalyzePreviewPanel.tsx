import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, FileText } from "lucide-react"
import type { ImportPreview } from "@/features/imports/types"

/**
 * "Prévia da importação" — what commit is expected to write, as far as
 * the analyze phase could determine.
 *
 * Source of truth is ``session.preview`` (populated by the backend
 * serializer from ``parsed_payload.preview``). For ETL sessions it's
 * filled from ``ETLPipelineService.execute(commit=False)``'s
 * ``would_create`` / ``would_fail`` / ``total_rows``. For template
 * sessions it's currently empty (commit=False dry-run isn't wired at
 * analyze yet — separate commit).
 *
 * Renders three columns: per-model rows that would CREATE, rows that
 * would FAIL (with the failure reasons surfaced elsewhere as issues),
 * and the total. Nothing to do when preview is empty — the component
 * returns null so the host page stays quiet.
 */

function sumByModel(counts: Record<string, number> | undefined): number {
  if (!counts) return 0
  return Object.values(counts).reduce((acc, n) => acc + (n || 0), 0)
}

export function AnalyzePreviewPanel({ preview }: { preview: ImportPreview | undefined }) {
  const [open, setOpen] = useState(true)

  const wouldCreate = preview?.would_create ?? {}
  const wouldFail = preview?.would_fail ?? {}
  const wouldUpdate = preview?.would_update ?? {}

  const createTotal = useMemo(() => sumByModel(wouldCreate), [wouldCreate])
  const updateTotal = useMemo(() => sumByModel(wouldUpdate), [wouldUpdate])
  const failTotal = useMemo(() => sumByModel(wouldFail), [wouldFail])
  const grandTotal =
    preview?.total_rows ?? createTotal + updateTotal + failTotal

  // Quiet if we have nothing to show (template mode, or backend didn't
  // populate preview for this session).
  if (createTotal + updateTotal + failTotal === 0) return null

  // Union of model names across the three per-model counts so every
  // mentioned model shows up in the table with zeros where missing.
  const modelNames = Array.from(
    new Set([
      ...Object.keys(wouldCreate),
      ...Object.keys(wouldUpdate),
      ...Object.keys(wouldFail),
    ]),
  ).sort()

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
          <div className="border-t border-border bg-muted/20 px-3 py-1.5 text-[10px] text-muted-foreground">
            Contagens vêm do dry-run do pipeline
            (<code className="font-mono">commit=False</code>) — linhas com erro
            já estão listadas como pendências acima, onde você pode
            resolvê-las antes do commit.
          </div>
        </div>
      )}
    </div>
  )
}
