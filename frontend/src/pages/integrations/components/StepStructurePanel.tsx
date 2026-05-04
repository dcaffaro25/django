import { useEffect, useState } from "react"
import { Loader2, RefreshCw, Link2 } from "lucide-react"
import { useRunSandbox } from "@/features/integrations"
import type { SandboxStep } from "@/features/integrations"

/**
 * Phase-3 Sandbox enhancement: auto-probe.
 *
 * When the operator selects an API in a step, we silently fire a single-
 * step preview-only sandbox call (max_pages=1, max_fanout=1) so the
 * structure panel can show the column list. This is the data the operator
 * needs to wire the next step's binding.
 *
 * The component re-probes whenever ``apiDefinitionId`` changes; not on
 * every keystroke of ``extraParamsText`` (the operator clicks Re-amostrar
 * after editing params, to avoid hammering the upstream API).
 *
 * On a column click, ``onBindColumn`` fires (when provided) — this is how
 * the visual join builder ties into the existing bindings array on the
 * next step.
 */
export type InferredColumn = {
  path: string
  type: string
  samples: unknown[]
}

export function StepStructurePanel({
  connectionId,
  apiDefinitionId,
  stepOrder,
  extraParams,
  onBindColumn,
  hasNextStep,
}: {
  connectionId: number | null
  apiDefinitionId: number | null
  stepOrder: number
  extraParams: Record<string, unknown>
  onBindColumn?: (path: string) => void
  hasNextStep: boolean
}) {
  const probe = useRunSandbox()
  const [columns, setColumns] = useState<InferredColumn[] | null>(null)
  const [rowCount, setRowCount] = useState<number | null>(null)

  const canProbe = connectionId != null && apiDefinitionId != null

  // Trigger probe automatically when the API selection becomes valid.
  useEffect(() => {
    if (!canProbe) {
      setColumns(null)
      setRowCount(null)
      return
    }
    runProbe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId, apiDefinitionId])

  const runProbe = () => {
    if (!canProbe) return
    const step: SandboxStep = {
      order: 1,  // single-step probe always runs at order=1
      api_definition_id: apiDefinitionId!,
      extra_params: extraParams,
      param_bindings: [],
      select_fields: null,
    }
    probe.mutate(
      {
        connection_id: connectionId!,
        steps: [step],
        max_steps: 1,
        max_pages_per_step: 1,
        max_fanout: 1,
      },
      {
        onSuccess: (res) => {
          const rows = res.preview_by_step?.[0]?.rows ?? []
          setRowCount(rows.length)
          setColumns(inferColumns(rows))
        },
        onError: () => {
          setColumns([])
          setRowCount(0)
        },
      },
    )
  }

  const isPending = probe.isPending

  if (!canProbe) {
    return (
      <div className="rounded-md border border-dashed border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
        Selecione uma API acima e a estrutura aparece aqui.
      </div>
    )
  }

  return (
    <div className="rounded-md border border-border bg-muted/20 p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Estrutura inferida
          {rowCount != null ? (
            <span className="ml-2 font-normal normal-case">
              ({rowCount} linha{rowCount === 1 ? "" : "s"} amostradas)
            </span>
          ) : null}
        </span>
        <button
          onClick={runProbe}
          disabled={isPending}
          className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          title="Re-amostrar"
        >
          {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {isPending ? "Amostrando…" : "Re-amostrar"}
        </button>
      </div>

      {isPending && columns == null ? (
        <div className="py-3 text-center text-[11px] text-muted-foreground">Carregando estrutura…</div>
      ) : columns == null ? (
        <div className="py-3 text-center text-[11px] text-muted-foreground">Aguardando…</div>
      ) : columns.length === 0 ? (
        <div className="py-3 text-center text-[11px] text-muted-foreground">
          Sem colunas detectadas. Verifique o records_path da definição.
        </div>
      ) : (
        <div className="max-h-48 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-muted/40 text-left text-[9px] uppercase text-muted-foreground">
              <tr>
                <th className="px-2 py-1">Coluna</th>
                <th className="px-2 py-1">Tipo</th>
                <th className="px-2 py-1">Exemplos</th>
                {hasNextStep ? <th className="px-2 py-1 w-16"></th> : null}
              </tr>
            </thead>
            <tbody>
              {columns.map((c) => (
                <tr key={c.path} className="border-t border-border/40 hover:bg-accent/30">
                  <td className="px-2 py-1 font-mono">{c.path}</td>
                  <td className="px-2 py-1 text-muted-foreground">{c.type}</td>
                  <td className="px-2 py-1 text-muted-foreground truncate max-w-[200px]">
                    {c.samples.slice(0, 3).map((s) => formatSample(s)).join(", ")}
                  </td>
                  {hasNextStep ? (
                    <td className="px-2 py-1 text-right">
                      {onBindColumn ? (
                        <button
                          onClick={() => onBindColumn(c.path)}
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-primary hover:bg-primary/10"
                          title={`Vincular ao próximo passo (binding com source_step=${stepOrder}, expression=${c.path})`}
                        >
                          <Link2 className="h-3 w-3" />
                          Vincular
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------

function formatSample(v: unknown): string {
  if (v == null) return "null"
  if (typeof v === "object") {
    const s = JSON.stringify(v)
    return s.length > 30 ? s.slice(0, 27) + "…" : s
  }
  const s = String(v)
  return s.length > 30 ? s.slice(0, 27) + "…" : s
}

function guessType(v: unknown): string {
  if (v === null || v === undefined) return "null"
  if (typeof v === "boolean") return "boolean"
  if (typeof v === "number") return Number.isInteger(v) ? "int" : "number"
  if (typeof v === "string") return "string"
  if (Array.isArray(v)) return "array"
  if (typeof v === "object") return "object"
  return "unknown"
}

function flattenKeys(obj: unknown, prefix = "", maxDepth = 2): Array<[string, unknown]> {
  const out: Array<[string, unknown]> = []
  if (maxDepth < 0) return out
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const path = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === "object" && !Array.isArray(v) && maxDepth > 0) {
        out.push(...flattenKeys(v, path, maxDepth - 1))
      } else {
        out.push([path, v])
      }
    }
  }
  return out
}

function inferColumns(rows: Array<Record<string, unknown>>): InferredColumn[] {
  const map = new Map<string, InferredColumn>()
  // Scan up to 12 rows to fill samples.
  for (const row of rows.slice(0, 12)) {
    if (!row || typeof row !== "object") continue
    for (const [path, value] of flattenKeys(row, "", 2)) {
      const col = map.get(path) ?? { path, type: guessType(value), samples: [] as unknown[] }
      if (col.samples.length < 3 && value !== null && value !== undefined) {
        col.samples.push(value)
      }
      map.set(path, col)
    }
  }
  return Array.from(map.values())
}
