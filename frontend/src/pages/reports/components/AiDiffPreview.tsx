import { X, Check, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { AiRefineSummary, TemplateDocument } from "@/features/reports"

/**
 * Side-by-side summary of a refine result. Intentionally lightweight: shows
 * block-level added/removed/renamed counts from the backend plus a preview
 * of the new document's block tree. Users accept or reject wholesale — per-
 * block accept lands in PR9 alongside the detail drawer.
 */
export function AiDiffPreview({
  open,
  oldDoc,
  newDoc,
  summary,
  onAccept,
  onReject,
}: {
  open: boolean
  oldDoc: TemplateDocument | null
  newDoc: TemplateDocument | null
  summary: AiRefineSummary | null
  onAccept: () => void
  onReject: () => void
}) {
  if (!open || !newDoc || !summary) return null

  const totalChanges =
    summary.added_ids.length + summary.removed_ids.length + summary.renamed.length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-[720px] flex-col rounded-lg border border-border bg-surface-1 shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Revisar alterações da IA
          </h2>
          <button
            onClick={onReject}
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4 text-[12px]">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Adicionadas" count={summary.added_ids.length} color="emerald" />
            <Stat label="Removidas" count={summary.removed_ids.length} color="red" />
            <Stat label="Renomeadas" count={summary.renamed.length} color="amber" />
          </div>

          {totalChanges === 0 && (
            <div className="rounded-md bg-muted/50 p-3 text-center text-muted-foreground">
              A IA não propôs mudanças estruturais — os valores podem ter
              mudado em detalhes não listados aqui.
            </div>
          )}

          {summary.added_ids.length > 0 && (
            <ChangeList
              title="Blocos adicionados"
              accent="emerald"
              items={summary.added_ids.map((id) => ({ text: id }))}
            />
          )}
          {summary.removed_ids.length > 0 && (
            <ChangeList
              title="Blocos removidos"
              accent="red"
              items={summary.removed_ids.map((id) => ({ text: id }))}
            />
          )}
          {summary.renamed.length > 0 && (
            <ChangeList
              title="Rótulos alterados"
              accent="amber"
              items={summary.renamed.map((r) => ({
                text: `${r.id}`,
                sub: `${r.from} → ${r.to}`,
              }))}
            />
          )}

          <details className="rounded-md border border-border bg-background/50 p-2">
            <summary className="cursor-pointer select-none text-[11px] font-medium text-muted-foreground">
              Pré-visualização da estrutura proposta ({summary.new_count}{" "}
              blocos, antes {summary.old_count})
            </summary>
            <pre className="mt-2 max-h-[240px] overflow-auto rounded bg-muted/30 p-2 font-mono text-[10px]">
              {renderTree(newDoc)}
            </pre>
          </details>

          {oldDoc && oldDoc.name !== newDoc.name && (
            <div className="text-[11px] text-muted-foreground">
              Nome: <s>{oldDoc.name}</s> → <strong>{newDoc.name}</strong>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          <button
            onClick={onReject}
            className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            Rejeitar
          </button>
          <button
            onClick={onAccept}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-emerald-600 px-3 text-[12px] font-medium text-white hover:bg-emerald-600/90"
          >
            <Check className="h-3.5 w-3.5" /> Aplicar
          </button>
        </div>
      </div>
    </div>
  )
}

function Stat({
  label, count, color,
}: {
  label: string
  count: number
  color: "emerald" | "red" | "amber"
}) {
  const tone = {
    emerald: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    red: "bg-red-500/10 text-red-600",
    amber: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  }[color]
  return (
    <div className={cn("rounded-md p-2 text-center", tone)}>
      <div className="text-[18px] font-semibold tabular-nums">{count}</div>
      <div className="text-[10px] uppercase tracking-wider">{label}</div>
    </div>
  )
}

function ChangeList({
  title, accent, items,
}: {
  title: string
  accent: "emerald" | "red" | "amber"
  items: Array<{ text: string; sub?: string }>
}) {
  const dot = {
    emerald: "bg-emerald-500",
    red: "bg-red-500",
    amber: "bg-amber-500",
  }[accent]
  return (
    <div>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      <div className="rounded-md border border-border">
        {items.map((it, i) => (
          <div
            key={i}
            className="flex items-start gap-2 border-b border-border/50 px-2 py-1.5 last:border-b-0"
          >
            <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full shrink-0", dot)} />
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[11px]">{it.text}</div>
              {it.sub && <div className="truncate text-[10px] text-muted-foreground">{it.sub}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function renderTree(doc: TemplateDocument): string {
  const lines: string[] = []
  function walk(blocks: TemplateDocument["blocks"], depth: number) {
    for (const b of blocks) {
      const pad = "  ".repeat(depth)
      const label = (b as { label?: string }).label
      lines.push(`${pad}${b.type.padEnd(9)} ${b.id}${label ? ` — ${label}` : ""}`)
      if (b.type === "section") walk(b.children, depth + 1)
    }
  }
  walk(doc.blocks, 0)
  return lines.join("\n")
}
