import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Plus, Trash2, Save, X, Search, ChevronDown, ChevronRight, ArrowRight, RefreshCw } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useDeleteSubstitutionRule,
  useSaveSubstitutionRule,
  useSubstitutionRules,
  type SubstitutionMatchType,
  type SubstitutionRule,
} from "@/features/imports"
import { useTenant } from "@/providers/TenantProvider"
import { cn } from "@/lib/utils"

// UX: de-para rules are noisy at scale (we just saw 187 records on a real
// tenant). Group by model_name by default and let operators drill into
// the field or model they care about. Full CRUD available via the drawer.

type Draft = Partial<SubstitutionRule> & { company?: number }

const MATCH_TYPES: SubstitutionMatchType[] = ["exact", "prefix", "suffix", "contains", "regex"]

export function SubstitutionRulesPage() {
  const { data: rules = [], isLoading, isFetching, refetch } = useSubstitutionRules()
  const save = useSaveSubstitutionRule()
  const del = useDeleteSubstitutionRule()
  const { tenant } = useTenant()

  const [search, setSearch] = useState("")
  const [modelFilter, setModelFilter] = useState<string>("")
  const [matchFilter, setMatchFilter] = useState<string>("")
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [editing, setEditing] = useState<Draft | null>(null)

  // Unique model names for the filter dropdown + group headers.
  const models = useMemo(() => {
    const s = new Set<string>()
    for (const r of rules) s.add(r.model_name ?? "—")
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [rules])

  // Apply the filters and then group by model_name so operators can
  // collapse sections. Grouping also surfaces "how many rules do we
  // have for Entity / Account / …" at a glance.
  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = rules.filter((r) => {
      if (modelFilter && r.model_name !== modelFilter) return false
      if (matchFilter && r.match_type !== matchFilter) return false
      if (!q) return true
      return (
        (r.match_value ?? "").toLowerCase().includes(q) ||
        (r.substitution_value ?? "").toLowerCase().includes(q) ||
        (r.field_name ?? "").toLowerCase().includes(q) ||
        (r.model_name ?? "").toLowerCase().includes(q)
      )
    })
    const map = new Map<string, SubstitutionRule[]>()
    for (const r of filtered) {
      const key = r.model_name ?? "—"
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [rules, search, modelFilter, matchFilter])

  const onNew = () =>
    setEditing({
      model_name: modelFilter || "",
      field_name: "",
      match_type: "exact",
      match_value: "",
      substitution_value: "",
      company: tenant?.id,
    })

  const onEdit = (r: SubstitutionRule) => setEditing({ ...r })

  const onSave = () => {
    if (!editing) return
    const { model_name, field_name, match_type, match_value, substitution_value } = editing
    if (!model_name || !field_name) {
      toast.error("Modelo e campo são obrigatórios.")
      return
    }
    if (!match_type) {
      toast.error("Selecione o tipo de match.")
      return
    }
    if (match_value == null || String(match_value).length === 0) {
      toast.error("Valor original é obrigatório.")
      return
    }
    const { id, ...body } = editing
    save.mutate(
      {
        id,
        body: {
          ...body,
          company: body.company ?? tenant?.id,
          match_type: match_type as SubstitutionMatchType,
          match_value: String(match_value),
          substitution_value: String(substitution_value ?? ""),
        },
      },
      {
        onSuccess: () => {
          toast.success(id ? "Regra atualizada." : "Regra criada.")
          setEditing(null)
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : "erro"),
      },
    )
  }

  const onDelete = (r: SubstitutionRule, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir regra ${r.model_name}.${r.field_name}: ${r.match_value}?`)) return
    del.mutate(r.id, {
      onSuccess: () => toast.success("Regra excluída."),
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : "erro"),
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Regras de substituição"
        subtitle={`${rules.length} regra(s) — substituições aplicadas durante importações ETL (de-para por modelo e campo)`}
        actions={
          <>
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
              title="Atualizar"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Atualizar
            </button>
            <button
              onClick={onNew}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> Nova regra
            </button>
          </>
        }
      />

      {/* Filters */}
      <div className="card-elevated flex flex-wrap items-center gap-2 p-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar valor ou campo…"
            className="h-8 w-full rounded-md border border-border bg-background pl-7 pr-2 text-[12px] outline-none focus:border-ring"
          />
        </div>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          <option value="">Todos modelos</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select
          value={matchFilter}
          onChange={(e) => setMatchFilter(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          <option value="">Todos tipos</option>
          {MATCH_TYPES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      {/* Grouped list */}
      <div className="space-y-2">
        {isLoading ? (
          <div className="card-elevated px-3 py-6 text-center text-[12px] text-muted-foreground">
            Carregando…
          </div>
        ) : grouped.length === 0 ? (
          <div className="card-elevated px-3 py-6 text-center text-[12px] text-muted-foreground">
            Nenhuma regra.
          </div>
        ) : (
          grouped.map(([model, rulesForModel]) => {
            const isOpen = expanded[model] !== false
            return (
              <div key={model} className="card-elevated overflow-hidden">
                <button
                  onClick={() =>
                    setExpanded((e) => ({ ...e, [model]: !(e[model] !== false) }))
                  }
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-accent/30"
                >
                  <span className="flex items-center gap-2 text-[13px] font-semibold">
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                    {model}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {rulesForModel.length} regra(s)
                  </span>
                </button>
                {isOpen && (
                  <table className="w-full text-[12px]">
                    <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="h-8 px-3">Campo</th>
                        <th className="h-8 px-3">Tipo</th>
                        <th className="h-8 px-3">Regra</th>
                        <th className="h-8 w-px px-3"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {rulesForModel.map((r) => (
                        <tr
                          key={r.id}
                          onClick={() => onEdit(r)}
                          className={cn(
                            "cursor-pointer border-t border-border hover:bg-accent/50",
                          )}
                        >
                          <td className="h-9 px-3 font-mono text-muted-foreground">
                            {r.field_name}
                          </td>
                          <td className="h-9 px-3">
                            <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                              {r.match_type}
                            </span>
                          </td>
                          <td className="h-9 px-3">
                            <span className="inline-flex items-center gap-1.5 font-mono text-[11px]">
                              <span className="rounded bg-muted/40 px-1 py-0.5">
                                {r.match_value}
                              </span>
                              <ArrowRight className="h-3 w-3 text-muted-foreground" />
                              <span className="rounded bg-primary/10 px-1 py-0.5 text-primary">
                                {r.substitution_value || "∅"}
                              </span>
                            </span>
                          </td>
                          <td className="h-9 px-3">
                            <button
                              onClick={(e) => onDelete(r, e)}
                              className="inline-flex h-6 items-center rounded px-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Editor drawer (inline card, not a modal — the list is the primary context) */}
      {editing !== null && (
        <div className="card-elevated space-y-3 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[13px] font-semibold">
              {editing.id ? `Editar regra #${editing.id}` : "Nova regra"}
            </h3>
            <button
              onClick={() => setEditing(null)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Modelo">
              <input
                value={editing.model_name ?? ""}
                onChange={(e) => setEditing({ ...editing, model_name: e.target.value })}
                placeholder="Entity, Account, Transaction, …"
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Campo">
              <input
                value={editing.field_name ?? ""}
                onChange={(e) => setEditing({ ...editing, field_name: e.target.value })}
                placeholder="id, name, account_code, …"
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Tipo de match">
              <select
                value={editing.match_type ?? "exact"}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    match_type: e.target.value as SubstitutionMatchType,
                  })
                }
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
              >
                {MATCH_TYPES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Valor original">
              <input
                value={editing.match_value ?? ""}
                onChange={(e) => setEditing({ ...editing, match_value: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Substituir por">
              <input
                value={editing.substitution_value ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, substitution_value: e.target.value })
                }
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
          </div>

          <div className="rounded-md border border-dashed border-border p-2 text-[11px] text-muted-foreground">
            Durante importações, valores iguais a <code>{editing.match_value || "∅"}</code>{" "}
            em <code>{editing.model_name || "?"}</code>.<code>{editing.field_name || "?"}</code>{" "}
            ({editing.match_type ?? "?"}) serão substituídos por{" "}
            <code>{editing.substitution_value || "∅"}</code>.
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditing(null)}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              onClick={onSave}
              disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" /> Salvar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  )
}
