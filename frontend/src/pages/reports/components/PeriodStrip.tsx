import { useState } from "react"
import { Calendar, Plus, X, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { buildPresetPeriods, PRESET_OPTIONS } from "@/features/reports"
import type { Period, PeriodKind, ReportType, PeriodPreset } from "@/features/reports"

export function PeriodStrip({
  periods,
  reportType,
  onChange,
}: {
  periods: Period[]
  reportType: ReportType
  onChange: (next: Period[]) => void
}) {
  const [presetOpen, setPresetOpen] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)

  const addEmpty = () => {
    const isStock = reportType === "balance_sheet"
    const next: Period = isStock
      ? {
          id: `p${Date.now()}`,
          label: todayISO(),
          type: "as_of",
          date: todayISO(),
        }
      : {
          id: `p${Date.now()}`,
          label: "Período",
          type: "range",
          start: startOfMonthISO(),
          end: todayISO(),
        }
    onChange([...periods, next])
  }

  const remove = (id: string) => onChange(periods.filter((p) => p.id !== id))

  const updateOne = (id: string, patch: Partial<Period>) =>
    onChange(periods.map((p) => (p.id === id ? { ...p, ...patch } : p)))

  const applyPreset = (preset: PeriodPreset) => {
    const next = buildPresetPeriods({ ref: todayISO(), reportType }, preset)
    onChange(next)
    setPresetOpen(false)
  }

  return (
    <div className="card-elevated flex flex-wrap items-center gap-2 p-2">
      <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="mr-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        Períodos
      </span>

      {periods.length === 0 && (
        <span className="text-[12px] text-muted-foreground">Nenhum período — use uma predefinição</span>
      )}

      {periods.map((p) => (
        <PeriodChip
          key={p.id}
          period={p}
          editing={editing === p.id}
          onToggleEdit={() => setEditing((e) => (e === p.id ? null : p.id))}
          onChange={(patch) => updateOne(p.id, patch)}
          onRemove={() => remove(p.id)}
          otherPeriodIds={periods.filter((op) => op.id !== p.id).map((op) => op.id)}
        />
      ))}

      <button
        onClick={addEmpty}
        className="inline-flex h-7 items-center gap-1 rounded-md border border-dashed border-border px-2 text-[11px] text-muted-foreground hover:bg-accent"
      >
        <Plus className="h-3 w-3" /> Adicionar
      </button>

      <div className="relative ml-auto">
        <button
          onClick={() => setPresetOpen((o) => !o)}
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent"
        >
          Predefinições <ChevronDown className="h-3 w-3" />
        </button>
        {presetOpen && (
          <div className="absolute right-0 top-[calc(100%+4px)] z-30 w-[220px] rounded-md border border-border bg-popover p-1 shadow-md">
            {PRESET_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => applyPreset(opt.value)}
                className="block w-full rounded px-2 py-1.5 text-left text-[12px] hover:bg-accent"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PeriodChip({
  period,
  editing,
  onToggleEdit,
  onChange,
  onRemove,
  otherPeriodIds,
}: {
  period: Period
  editing: boolean
  onToggleEdit: () => void
  onChange: (patch: Partial<Period>) => void
  onRemove: () => void
  otherPeriodIds: string[]
}) {
  const isVariance = period.type.startsWith("variance")
  return (
    <div className="relative">
      <button
        onClick={onToggleEdit}
        className={cn(
          "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[11px] font-medium",
          isVariance
            ? "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300"
            : "border-border bg-background",
          editing && "ring-1 ring-primary",
        )}
      >
        <span>{period.label}</span>
        <span className="text-muted-foreground">{typeBadge(period.type)}</span>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onRemove()
        }}
        className="absolute -right-1.5 -top-1.5 grid h-4 w-4 place-items-center rounded-full bg-background text-muted-foreground shadow-sm hover:bg-red-500 hover:text-white"
      >
        <X className="h-2.5 w-2.5" />
      </button>

      {editing && (
        <div className="absolute left-0 top-[calc(100%+6px)] z-30 w-[300px] rounded-md border border-border bg-popover p-3 shadow-md">
          <div className="space-y-2">
            <label className="block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Rótulo
            </label>
            <input
              value={period.label}
              onChange={(e) => onChange({ label: e.target.value })}
              className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
            />

            <label className="block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Tipo
            </label>
            <select
              value={period.type}
              onChange={(e) => onChange({ type: e.target.value as PeriodKind })}
              className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
            >
              <option value="range">Intervalo (fluxo)</option>
              <option value="as_of">Ponto no tempo (saldo)</option>
              <option value="variance_abs">Variação absoluta</option>
              <option value="variance_pct">Variação %</option>
            </select>

            {period.type === "range" && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] text-muted-foreground">Início</label>
                  <input
                    type="date"
                    value={period.start ?? ""}
                    onChange={(e) => onChange({ start: e.target.value })}
                    className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-muted-foreground">Fim</label>
                  <input
                    type="date"
                    value={period.end ?? ""}
                    onChange={(e) => onChange({ end: e.target.value })}
                    className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
                  />
                </div>
              </div>
            )}

            {period.type === "as_of" && (
              <div>
                <label className="block text-[10px] text-muted-foreground">Data</label>
                <input
                  type="date"
                  value={period.date ?? ""}
                  onChange={(e) => onChange({ date: e.target.value })}
                  className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
                />
              </div>
            )}

            {isVariance && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] text-muted-foreground">Base</label>
                  <select
                    value={period.base ?? ""}
                    onChange={(e) => onChange({ base: e.target.value })}
                    className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
                  >
                    <option value="">—</option>
                    {otherPeriodIds.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-muted-foreground">Comparar</label>
                  <select
                    value={period.compare ?? ""}
                    onChange={(e) => onChange({ compare: e.target.value })}
                    className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
                  >
                    <option value="">—</option>
                    {otherPeriodIds.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function typeBadge(t: PeriodKind): string {
  const map: Record<PeriodKind, string> = {
    range: "[ ]",
    as_of: "•",
    variance_abs: "Δ",
    variance_pct: "%",
    variance_pp: "pp",
  }
  return map[t]
}

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function startOfMonthISO() {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}
