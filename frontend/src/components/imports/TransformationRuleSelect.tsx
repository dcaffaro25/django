import { useEffect, useMemo, useRef, useState } from "react"
import { Check, ChevronDown, Loader2, Search, X } from "lucide-react"
import { transformationRulesApi } from "@/features/imports/api"
import type { ImportTransformationRuleSummary } from "@/features/imports/types"
import { cn } from "@/lib/utils"

/**
 * Searchable dropdown + details card for picking an
 * ``ImportTransformationRule`` in the ETL v2 flow.
 *
 * Replaces the raw "type the ID" number input. Fetches the operator's
 * rules once on mount, filters client-side (typical tenant has <50
 * rules — no server-side search needed). The details card beneath the
 * dropdown shows the rule's source sheet, target model, a preview of
 * column_mappings, and the erp_duplicate_behavior so the operator
 * confirms they picked the right one before analyzing.
 *
 * Accepts a ``value`` (string, to mirror the underlying form state
 * that used to drive a plain ``<input type="number">``) and emits
 * string values on change. Numeric coercion happens at the caller.
 */

export function TransformationRuleSelect({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (id: string) => void
  disabled?: boolean
}) {
  const [rules, setRules] = useState<ImportTransformationRuleSummary[] | null>(
    null,
  )
  const [loadError, setLoadError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch rules once. Refetch only on an explicit reload (future work —
  // operators rarely edit rules while picking one to import against).
  useEffect(() => {
    let cancelled = false
    transformationRulesApi
      .list()
      .then((items) => {
        if (!cancelled) {
          setRules(items)
          setLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? (err instanceof Error ? err.message : "erro")
        setLoadError(msg)
        setRules([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!containerRef.current) return
      if (!containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const selected = useMemo(() => {
    if (!value) return null
    const n = Number(value)
    if (!Number.isFinite(n)) return null
    return rules?.find((r) => r.id === n) ?? null
  }, [rules, value])

  const filtered = useMemo(() => {
    if (!rules) return []
    const needle = q.trim().toLowerCase()
    const active = rules.filter((r) => r.is_active !== false)
    if (!needle) return active
    return active.filter((r) => {
      const hay = [
        r.name,
        r.description,
        r.source_sheet_name,
        r.target_model,
        String(r.id),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return hay.includes(needle)
    })
  }, [rules, q])

  const isLoading = rules === null && !loadError

  const label = selected
    ? `${selected.name} — ${selected.source_sheet_name} → ${selected.target_model}`
    : value && !rules
      ? `(carregando… ID ${value})`
      : value
        ? `(ID ${value} não encontrado)`
        : "Selecionar regra"

  return (
    <div className="w-full">
      <div ref={containerRef} className="relative w-full">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((o) => !o)}
          className={cn(
            "inline-flex h-8 w-full items-center justify-between gap-2 rounded-md border border-border bg-background px-2 text-[12px] hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60",
            !selected && "text-muted-foreground",
          )}
          title={selected ? `transformation_rule_id = ${selected.id}` : undefined}
        >
          <span className="truncate">{label}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </button>
        {open && (
          <div className="absolute z-50 mt-1 w-[min(640px,95vw)] rounded-md border border-border bg-popover p-1 shadow-xl">
            <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2">
              <Search className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar por nome, aba, modelo ou ID…"
                className="h-8 flex-1 bg-transparent text-[12px] outline-none"
              />
              {q && (
                <button
                  onClick={() => setQ("")}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Limpar busca"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <div className="mt-1 max-h-72 overflow-y-auto">
              {isLoading ? (
                <div className="flex items-center gap-2 px-2 py-3 text-[12px] text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Carregando regras…
                </div>
              ) : loadError ? (
                <div className="px-2 py-3 text-[12px] text-destructive">
                  Falha ao carregar regras: {loadError}
                </div>
              ) : filtered.length === 0 ? (
                <div className="px-2 py-3 text-center text-[12px] text-muted-foreground">
                  Nenhuma regra encontrada.
                </div>
              ) : (
                filtered.slice(0, 50).map((r) => {
                  const isPicked = String(r.id) === value
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => {
                        onChange(String(r.id))
                        setOpen(false)
                        setQ("")
                      }}
                      className={cn(
                        "flex w-full flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left hover:bg-accent",
                        isPicked && "bg-accent",
                      )}
                    >
                      <span className="flex w-full items-baseline gap-2 text-[12px] font-medium">
                        {isPicked && (
                          <Check className="h-3 w-3 shrink-0 text-primary" />
                        )}
                        <span className="truncate">{r.name}</span>
                        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                          #{r.id}
                        </span>
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        <code className="font-mono">{r.source_sheet_name}</code>{" "}
                        →{" "}
                        <code className="font-mono">{r.target_model}</code>
                      </span>
                    </button>
                  )
                })
              )}
              {filtered.length > 50 && (
                <div className="px-2 py-1 text-center text-[11px] text-muted-foreground">
                  Mostrando 50 de {filtered.length} — refine a busca.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {selected && (
        <TransformationRuleDetails rule={selected} />
      )}
    </div>
  )
}

function TransformationRuleDetails({
  rule,
}: {
  rule: ImportTransformationRuleSummary
}) {
  const mappings = rule.column_mappings ?? {}
  const mappingCount = Object.keys(mappings).length
  return (
    <div className="mt-2 rounded-md border border-border bg-muted/20 p-2 text-[11px]">
      <div className="mb-1 flex flex-wrap items-center gap-2 font-semibold">
        <span className="font-mono text-[10px] text-muted-foreground">
          #{rule.id}
        </span>
        <span>{rule.name}</span>
        {rule.erp_duplicate_behavior && (
          <span
            className="ml-auto inline-flex h-4 items-center rounded border border-border bg-background px-1.5 font-mono text-[9px] uppercase text-muted-foreground"
            title="Comportamento quando um registro existente já tem o mesmo erp_id"
          >
            dup: {rule.erp_duplicate_behavior}
          </span>
        )}
      </div>
      {rule.description && (
        <div className="mb-1 text-muted-foreground">{rule.description}</div>
      )}
      <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[10px]">
        <span className="text-muted-foreground">Aba origem</span>
        <code className="font-mono">{rule.source_sheet_name}</code>
        <span className="text-muted-foreground">Modelo alvo</span>
        <code className="font-mono">{rule.target_model}</code>
        <span className="text-muted-foreground">Mapeamentos</span>
        <span>
          {mappingCount > 0 ? (
            <span className="flex flex-wrap gap-1">
              {Object.entries(mappings)
                .slice(0, 6)
                .map(([from, to]) => (
                  <code
                    key={from}
                    className="rounded bg-background px-1 font-mono"
                    title={`${from} → ${to}`}
                  >
                    {from} → {to}
                  </code>
                ))}
              {mappingCount > 6 && (
                <span className="text-muted-foreground">
                  +{mappingCount - 6} outros
                </span>
              )}
            </span>
          ) : (
            <span className="italic text-muted-foreground">
              (nenhum mapeamento configurado — a regra pode ainda usar
              column_concatenations / computed_columns / default_values)
            </span>
          )}
        </span>
      </div>
    </div>
  )
}
