import { useMemo } from "react"
import { Plus, X, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FilterColumnDef, FilterStack, FilterStackRow } from "@/features/reconciliation/types"

// ---------------------------------------------------------------------------
// Helpers — keep JSON shape identical to backend expectation.
// ---------------------------------------------------------------------------

function isGroup(node: FilterStackRow | FilterStack): node is FilterStack {
  return (node as FilterStack).filters !== undefined
}

function emptyStack(): FilterStack {
  return { operator: "and", filters: [] }
}

function defaultOperator(col: FilterColumnDef): string {
  return col.operators[0] ?? "eq"
}

function emptyRow(col: FilterColumnDef): FilterStackRow {
  return { column_id: col.id, operator: defaultOperator(col), value: "", disabled: false }
}

// Friendly labels for the operator dropdown.
const OP_LABEL: Record<string, string> = {
  eq: "=",
  neq: "≠",
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  between: "entre",
  in: "em (lista)",
  contains: "contém",
  icontains: "contém (i)",
  startswith: "começa com",
  istartswith: "começa com (i)",
  is_null: "é nulo",
  overlap: "sobrepõe",
  len_eq: "tam =",
  len_gt: "tam >",
  len_gte: "tam ≥",
  len_lt: "tam <",
  len_lte: "tam ≤",
  is_empty: "é vazio",
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface FilterStackBuilderProps {
  value: FilterStack | null | undefined
  onChange: (stack: FilterStack) => void
  columns: FilterColumnDef[]
  /** Optional label shown above the stack. */
  title?: string
  /** Optional count preview shown in the header ("3.421 registros"). */
  count?: number | null
  /** Optional warning string(s) to surface under the header. */
  warnings?: string[]
  className?: string
}

export function FilterStackBuilder({
  value,
  onChange,
  columns,
  title,
  count,
  warnings,
  className,
}: FilterStackBuilderProps) {
  const stack = value ?? emptyStack()
  const colById = useMemo(() => {
    const m = new Map<string, FilterColumnDef>()
    for (const c of columns) m.set(c.id, c)
    return m
  }, [columns])

  return (
    <div className={cn("rounded-md border border-border bg-card/40 p-2 text-[12px]", className)}>
      <header className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {title && <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</span>}
          <GroupOperator value={stack.operator} onChange={(op) => onChange({ ...stack, operator: op })} />
        </div>
        <div className="flex items-center gap-2">
          {count != null && (
            <span className="rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {count.toLocaleString("pt-BR")} registros
            </span>
          )}
          <button
            type="button"
            onClick={() => onChange({ ...stack, filters: [...stack.filters, emptyRow(columns[0] ?? { id: "", label: "", type: "string", operators: ["eq"] })] })}
            className="inline-flex items-center gap-1 rounded-sm border border-border bg-background px-1.5 py-0.5 text-[11px] hover:bg-accent"
            disabled={columns.length === 0}
          >
            <Plus className="h-3 w-3" /> Filtro
          </button>
          <button
            type="button"
            onClick={() => onChange({ ...stack, filters: [...stack.filters, emptyStack()] })}
            className="inline-flex items-center gap-1 rounded-sm border border-border bg-background px-1.5 py-0.5 text-[11px] hover:bg-accent"
          >
            <Plus className="h-3 w-3" /> Grupo
          </button>
        </div>
      </header>

      {warnings && warnings.length > 0 && (
        <div className="mb-2 rounded-sm border border-warning/40 bg-warning/10 px-2 py-1 text-[11px] text-warning">
          {warnings.map((w, i) => (<div key={i}>• {w}</div>))}
        </div>
      )}

      {stack.filters.length === 0 ? (
        <div className="rounded-sm border border-dashed border-border/70 px-2 py-3 text-center text-[11px] text-muted-foreground">
          Sem filtros. Todos os registros do escopo serão usados.
        </div>
      ) : (
        <div className="space-y-1.5">
          {stack.filters.map((child, idx) => (
            <FilterNode
              key={idx}
              node={child}
              columns={columns}
              colById={colById}
              onChange={(next) => {
                const filters = [...stack.filters]
                filters[idx] = next
                onChange({ ...stack, filters })
              }}
              onRemove={() => {
                const filters = [...stack.filters]
                filters.splice(idx, 1)
                onChange({ ...stack, filters })
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// One node (leaf row OR nested group)
// ---------------------------------------------------------------------------

interface FilterNodeProps {
  node: FilterStackRow | FilterStack
  columns: FilterColumnDef[]
  colById: Map<string, FilterColumnDef>
  onChange: (next: FilterStackRow | FilterStack) => void
  onRemove: () => void
}

function FilterNode({ node, columns, colById, onChange, onRemove }: FilterNodeProps) {
  if (isGroup(node)) {
    return (
      <div className="rounded-sm border border-border/70 bg-background/60 p-1.5">
        <div className="mb-1 flex items-center justify-between">
          <GroupOperator value={node.operator} onChange={(op) => onChange({ ...node, operator: op })} />
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onChange({ ...node, filters: [...node.filters, emptyRow(columns[0] ?? { id: "", label: "", type: "string", operators: ["eq"] })] })}
              className="inline-flex items-center gap-1 rounded-sm border border-border bg-background px-1.5 py-0.5 text-[10px] hover:bg-accent"
              disabled={columns.length === 0}
            >
              <Plus className="h-2.5 w-2.5" /> Filtro
            </button>
            <button type="button" onClick={onRemove} className="grid h-5 w-5 place-items-center rounded-sm hover:bg-danger/15 hover:text-danger">
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
        {node.filters.length === 0 ? (
          <div className="rounded-sm border border-dashed border-border/60 px-1.5 py-2 text-center text-[10px] text-muted-foreground">Grupo vazio</div>
        ) : (
          <div className="space-y-1">
            {node.filters.map((child, idx) => (
              <FilterNode
                key={idx}
                node={child}
                columns={columns}
                colById={colById}
                onChange={(next) => {
                  const filters = [...node.filters]
                  filters[idx] = next
                  onChange({ ...node, filters })
                }}
                onRemove={() => {
                  const filters = [...node.filters]
                  filters.splice(idx, 1)
                  onChange({ ...node, filters })
                }}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return <FilterRow row={node} columns={columns} colById={colById} onChange={(n) => onChange(n)} onRemove={onRemove} />
}

// ---------------------------------------------------------------------------
// Leaf row
// ---------------------------------------------------------------------------

interface FilterRowProps {
  row: FilterStackRow
  columns: FilterColumnDef[]
  colById: Map<string, FilterColumnDef>
  onChange: (next: FilterStackRow) => void
  onRemove: () => void
}

function FilterRow({ row, columns, colById, onChange, onRemove }: FilterRowProps) {
  const col = colById.get(row.column_id)
  const operators = col?.operators ?? []

  return (
    <div className={cn("flex items-center gap-1", row.disabled && "opacity-50")}>
      <input
        type="checkbox"
        checked={!row.disabled}
        onChange={(e) => onChange({ ...row, disabled: !e.target.checked })}
        className="h-3 w-3 accent-primary"
        title="Ativar/desativar este filtro"
      />
      <select
        value={row.column_id}
        onChange={(e) => {
          const next = colById.get(e.target.value)
          if (!next) return
          onChange({
            ...row,
            column_id: next.id,
            operator: next.operators.includes(row.operator) ? row.operator : defaultOperator(next),
            value: "",
          })
        }}
        className="h-7 flex-1 rounded-sm border border-border bg-background px-1.5 text-[12px]"
      >
        {columns.map((c) => (<option key={c.id} value={c.id}>{c.label}</option>))}
      </select>
      <select
        value={row.operator}
        onChange={(e) => onChange({ ...row, operator: e.target.value, value: "" })}
        className="h-7 w-24 rounded-sm border border-border bg-background px-1.5 text-[12px]"
      >
        {operators.map((op) => (<option key={op} value={op}>{OP_LABEL[op] ?? op}</option>))}
      </select>
      <div className="min-w-[140px] flex-[2]">
        <ValueInput col={col} operator={row.operator} value={row.value} onChange={(v) => onChange({ ...row, value: v })} />
      </div>
      <button type="button" onClick={onRemove} className="grid h-6 w-6 place-items-center rounded-sm hover:bg-danger/15 hover:text-danger">
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Value input — type-aware
// ---------------------------------------------------------------------------

interface ValueInputProps {
  col: FilterColumnDef | undefined
  operator: string
  value: unknown
  onChange: (next: unknown) => void
}

function ValueInput({ col, operator, value, onChange }: ValueInputProps) {
  if (!col) return null

  // Operators that ignore the value.
  if (operator === "is_null") {
    const bool = value === true || value === "true"
    return (
      <select
        value={bool ? "true" : "false"}
        onChange={(e) => onChange(e.target.value === "true")}
        className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]"
      >
        <option value="true">é nulo</option>
        <option value="false">não é nulo</option>
      </select>
    )
  }
  if (operator === "is_empty") return <span className="text-[11px] text-muted-foreground">—</span>

  // List operator uses comma-separated input.
  if (operator === "in" || operator === "overlap") {
    const asText = Array.isArray(value) ? value.join(", ") : String(value ?? "")
    return (
      <input
        type="text"
        value={asText}
        placeholder="valores separados por vírgula"
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]"
      />
    )
  }

  // Between operator uses two inputs.
  if (operator === "between") {
    const [a, b] = Array.isArray(value) ? value : ["", ""]
    const inputType = col.type === "date" ? "date" : col.type === "datetime" ? "datetime-local" : col.type === "number" ? "number" : "text"
    return (
      <div className="flex items-center gap-1">
        <input type={inputType} value={String(a ?? "")} onChange={(e) => onChange([e.target.value, b])} className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]" />
        <span className="text-muted-foreground">—</span>
        <input type={inputType} value={String(b ?? "")} onChange={(e) => onChange([a, e.target.value])} className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]" />
      </div>
    )
  }

  // Enum / bool: dropdown.
  if (col.type === "enum") {
    return (
      <select
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]"
      >
        <option value="">—</option>
        {(col.enum ?? []).map((v) => (<option key={v} value={v}>{v}</option>))}
      </select>
    )
  }
  if (col.type === "bool") {
    const bool = value === true || value === "true"
    return (
      <select
        value={bool ? "true" : "false"}
        onChange={(e) => onChange(e.target.value === "true")}
        className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]"
      >
        <option value="true">sim</option>
        <option value="false">não</option>
      </select>
    )
  }

  // Numeric / date / datetime / string / fk — flat inputs.
  const inputType =
    col.type === "date" ? "date"
      : col.type === "datetime" ? "datetime-local"
      : col.type === "number" || col.type === "fk" ? "number"
      : "text"

  return (
    <input
      type={inputType}
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      className="h-7 w-full rounded-sm border border-border bg-background px-1.5 text-[12px]"
    />
  )
}

// ---------------------------------------------------------------------------
// Tiny AND/OR toggle
// ---------------------------------------------------------------------------

function GroupOperator({ value, onChange }: { value: "and" | "or"; onChange: (op: "and" | "or") => void }) {
  return (
    <div className="relative inline-flex h-6 items-center rounded-sm border border-border bg-background text-[10px]">
      <button
        type="button"
        onClick={() => onChange("and")}
        className={cn("h-full px-2", value === "and" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
      >
        E
      </button>
      <button
        type="button"
        onClick={() => onChange("or")}
        className={cn("h-full px-2", value === "or" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
      >
        OU
      </button>
      <ChevronDown className="mx-1 h-3 w-3 text-muted-foreground" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Convenience hook exports
// ---------------------------------------------------------------------------

export { emptyStack }
