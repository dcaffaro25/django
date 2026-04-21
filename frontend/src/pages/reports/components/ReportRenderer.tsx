import { useMemo, useState } from "react"
import { HelpCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ReportResult, TemplateDocument } from "@/features/reports"
import { LineSparkline } from "./LineSparkline"
import { ExplainPopover } from "./ExplainPopover"

/**
 * Renders a ``ReportResult`` as a multi-column table. Single render path
 * across the builder preview, history view, and print mode. No server HTML.
 *
 * Optional ``document`` enables the per-cell "explain this number" popover.
 * Omit it on read-only instance views where AI access isn't available.
 */
export function ReportRenderer({
  result,
  document,
  printMode = false,
}: {
  result: ReportResult | null
  document?: TemplateDocument | null
  printMode?: boolean
}) {
  const [explain, setExplain] = useState<{
    blockId: string
    periodId: string
    rect: DOMRect
  } | null>(null)

  // Concrete (non-variance) periods are the ones that form a meaningful
  // trend line — sparklines only make sense for these. Computed here so
  // the Decision to render a sparkline is cheap per row.
  const trendPeriodIds = useMemo(() => {
    if (!result) return [] as string[]
    return result.periods
      .filter((p) => p.type === "range" || p.type === "as_of")
      .map((p) => p.id)
  }, [result])

  if (!result) {
    return (
      <div className="flex h-[240px] items-center justify-center text-[12px] text-muted-foreground">
        Clique em "Calcular" para ver a pré-visualização
      </div>
    )
  }

  const periods = result.periods
  const lines = result.lines
  const canExplain = document != null
  const showSparklines = trendPeriodIds.length >= 3

  return (
    <div className={cn("min-h-[280px]", printMode && "bg-white p-6 text-black")}>
      <div className="mb-4">
        <h2 className="text-[16px] font-semibold">{result.template?.name}</h2>
        <p className="text-[11px] text-muted-foreground">
          {result.template?.report_type && formatReportType(result.template.report_type)}
        </p>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-8 px-3 font-medium">Linha</th>
              {periods.map((p) => (
                <th key={p.id} className="h-8 px-3 text-right font-medium">
                  {p.label}
                </th>
              ))}
              {showSparklines && (
                <th className="h-8 px-3 font-medium">Tendência</th>
              )}
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              if (line.type === "spacer") {
                return (
                  <tr key={line.id} className="h-2">
                    <td colSpan={periods.length + (showSparklines ? 2 : 1)} />
                  </tr>
                )
              }
              const isSection = line.type === "section"
              const isBoldRow =
                line.bold || line.type === "subtotal" || line.type === "total" || isSection
              const hasBorderTop = line.type === "total" || line.type === "subtotal"

              const trend = showSparklines
                ? trendPeriodIds.map((pid) => ({
                    label: pid,
                    value: Number(line.values[pid] ?? 0),
                  }))
                : []

              return (
                <tr
                  key={line.id}
                  className={cn(
                    "group border-b border-border/50",
                    isBoldRow && "font-semibold",
                    hasBorderTop && "border-t border-foreground/30",
                    isSection && "bg-surface-2/60",
                    line.type === "header" && "bg-surface-3/60",
                  )}
                >
                  <td
                    className="h-8 px-3"
                    style={{ paddingLeft: `${0.75 + (line.indent ?? 0) * 1}rem` }}
                  >
                    {line.label ?? line.id}
                  </td>
                  {periods.map((p) => {
                    const val = line.values[p.id]
                    const explainable =
                      canExplain
                      && line.type !== "header"
                      && line.type !== "spacer"
                      && !p.type.startsWith("variance")
                    return (
                      <td
                        key={p.id}
                        className="relative h-8 px-3 text-right tabular-nums"
                      >
                        <div className="inline-flex items-center justify-end gap-1">
                          <ValueCell periodType={p.type} value={val} />
                          {explainable && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setExplain({
                                  blockId: line.id,
                                  periodId: p.id,
                                  rect: (e.currentTarget as HTMLElement).getBoundingClientRect(),
                                })
                              }}
                              title="Explicar este valor"
                              className="grid h-4 w-4 place-items-center rounded-sm text-muted-foreground/0 transition-opacity hover:text-foreground group-hover:text-muted-foreground"
                            >
                              <HelpCircle className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </td>
                    )
                  })}
                  {showSparklines && (
                    <td className="h-8 px-3">
                      {line.type !== "header" && line.type !== "section" && trend.length >= 2 && (
                        <LineSparkline data={trend} />
                      )}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <ExplainPopover
        open={explain !== null}
        document={document ?? null}
        result={result}
        blockId={explain?.blockId ?? null}
        periodId={explain?.periodId ?? null}
        anchorRect={explain?.rect ?? null}
        onClose={() => setExplain(null)}
      />

      {result.warnings && result.warnings.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px]">
          <div className="mb-1 font-semibold text-amber-700 dark:text-amber-400">
            Avisos ({result.warnings.length})
          </div>
          <ul className="list-disc space-y-0.5 pl-4">
            {result.warnings.map((w, i) => (
              <li key={i}>
                {w.block_id && <code className="mr-1 text-[10px]">{w.block_id}</code>}
                {w.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ValueCell({
  periodType,
  value,
}: {
  periodType: string
  value: number | null | undefined
}) {
  if (value == null || Number.isNaN(value)) return <span className="text-muted-foreground">—</span>

  if (periodType === "variance_pct" || periodType === "variance_pp") {
    const neg = value < 0
    return (
      <span className={cn(neg ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400")}>
        {value.toFixed(2)}%
      </span>
    )
  }

  if (periodType === "variance_abs") {
    const neg = value < 0
    return (
      <span className={cn(neg ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400")}>
        {fmt(value)}
      </span>
    )
  }

  return <>{fmt(value)}</>
}

function fmt(v: number): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

function formatReportType(t: string): string {
  const map: Record<string, string> = {
    income_statement: "Demonstração de Resultado (DRE)",
    balance_sheet: "Balanço Patrimonial",
    cash_flow: "Fluxo de Caixa",
    trial_balance: "Balancete",
    general_ledger: "Razão",
    custom: "Relatório Personalizado",
  }
  return map[t] ?? t
}
