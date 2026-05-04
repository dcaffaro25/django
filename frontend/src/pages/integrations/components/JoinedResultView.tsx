import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import type { SandboxResult } from "@/features/integrations"

/**
 * Phase-3 Sandbox enhancement: client-side joined preview.
 *
 * Takes the per-step preview rows + diagnostics produced by the sandbox
 * executor and joins them into a single flat table:
 *
 *  - Last step's rows are the "leaf" — each becomes one output row.
 *  - Earlier steps contribute prefixed columns: ``step{N}_<key>``.
 *  - Pairing rule: when step N+1 used a fanout binding referencing
 *    step N, we align rows by invocation index. Otherwise we broadcast
 *    step N's first row to all step N+1 rows. Approximate but matches
 *    the operator's mental model of how the chain ran.
 *
 * Pure presentation — no extra fetch. ``ResultPane`` shows this as one
 * tab alongside the existing per-step previews.
 */
export function JoinedResultView({ result }: { result: SandboxResult }) {
  const previews = result.preview_by_step ?? []
  const diagnostics = result.diagnostics?.steps ?? []

  const joined = useMemo(
    () => buildJoinedRows(previews, diagnostics),
    [previews, diagnostics],
  )

  const [mode, setMode] = useState<"table" | "json">("table")

  if (previews.length === 0 || joined.rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[12px] text-muted-foreground">
        Sem linhas para juntar — rode o pipeline primeiro.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] text-muted-foreground">
          {joined.rows.length} linha(s) consolidadas · {joined.columns.length} coluna(s)
        </div>
        <div className="flex gap-1 text-[11px]">
          <button
            onClick={() => setMode("table")}
            className={cn(
              "rounded px-1.5 py-0.5",
              mode === "table" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            Tabela
          </button>
          <button
            onClick={() => setMode("json")}
            className={cn(
              "rounded px-1.5 py-0.5",
              mode === "json" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            JSON
          </button>
        </div>
      </div>

      {mode === "table" ? (
        <div className="overflow-auto rounded-md border border-border" style={{ maxHeight: 400 }}>
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {joined.columns.map((c) => (
                  <th key={c} className="h-7 whitespace-nowrap px-2 font-medium">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {joined.rows.slice(0, 200).map((r, i) => (
                <tr key={i} className="border-t border-border">
                  {joined.columns.map((c) => (
                    <td key={c} className="h-7 max-w-[220px] truncate px-2 font-mono">
                      {formatCell(r[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre className="max-h-[400px] overflow-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-[11px]">
          {JSON.stringify(joined.rows.slice(0, 50), null, 2)}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------
// Join logic
// ---------------------------------------------------------------------

type StepDiag = {
  order: number
  fanout?: { source_step: number; expression: string; into: string; value_count: number } | null
  invocations?: Array<Record<string, unknown>>
}

type StepPreview = {
  order: number
  api_call: string
  rows: Array<Record<string, unknown>>
}

type JoinedResult = {
  columns: string[]
  rows: Array<Record<string, unknown>>
}

function buildJoinedRows(
  previews: StepPreview[],
  diagnostics: StepDiag[],
): JoinedResult {
  if (previews.length === 0) return { columns: [], rows: [] }

  // Sort steps by order to be safe.
  const ordered = [...previews].sort((a, b) => a.order - b.order)
  const diagByOrder = new Map<number, StepDiag>()
  for (const d of diagnostics) diagByOrder.set(d.order, d)

  // Start with the LAST step's rows as the leaves.
  const last = ordered[ordered.length - 1]
  let workingRows: Array<{ stepRows: Map<number, Record<string, unknown>> }> = last.rows.map((r) => ({
    stepRows: new Map([[last.order, r]]),
  }))

  // Walk backwards, pairing each leaf row to a parent row.
  for (let i = ordered.length - 2; i >= 0; i--) {
    const parent = ordered[i]
    const child = ordered[i + 1]
    const childDiag = diagByOrder.get(child.order)

    workingRows = workingRows.map((wr, idx) => {
      const parentRow = pickParentRow(parent.rows, childDiag, idx, last.rows.length)
      if (parentRow) wr.stepRows.set(parent.order, parentRow)
      return wr
    })
  }

  // Flatten to {step{N}_col: value, ...}.
  const columns: string[] = []
  const seen = new Set<string>()
  const flatRows: Array<Record<string, unknown>> = []

  for (const wr of workingRows) {
    const out: Record<string, unknown> = {}
    for (const step of ordered) {
      const row = wr.stepRows.get(step.order)
      if (!row) continue
      for (const [k, v] of Object.entries(row)) {
        const col = `step${step.order}_${k}`
        out[col] = formatScalar(v)
        if (!seen.has(col)) {
          seen.add(col)
          columns.push(col)
        }
      }
    }
    flatRows.push(out)
  }

  return { columns, rows: flatRows }
}

function pickParentRow(
  parentRows: Array<Record<string, unknown>>,
  childDiag: StepDiag | undefined,
  leafIndex: number,
  leafCount: number,
): Record<string, unknown> | null {
  if (parentRows.length === 0) return null
  // Fanout: invocations align 1:1 with parent rows. Distribute leaf
  // rows across parent rows by ratio (when fanout produces multiple
  // children per parent, leafCount > parent.length).
  if (childDiag?.fanout && childDiag.fanout.value_count > 0) {
    const ratio = leafCount / Math.max(1, parentRows.length)
    const parentIdx = Math.min(parentRows.length - 1, Math.floor(leafIndex / Math.max(1, ratio)))
    return parentRows[parentIdx] ?? null
  }
  // No fanout: broadcast first parent row to all leaves.
  return parentRows[0] ?? null
}

function formatScalar(v: unknown): unknown {
  if (v === null || v === undefined) return v
  if (typeof v === "object") return JSON.stringify(v)
  return v
}

function formatCell(v: unknown): string {
  if (v == null) return ""
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}
