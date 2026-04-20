import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Play, Plus, Save, Trash2, ChevronRight, ArrowDown, Zap } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useErpApiDefinitions,
  useErpConnections,
  useRunSandbox,
  useSavePipeline,
  type SandboxBinding,
  type SandboxBindingMode,
  type SandboxResult,
  type SandboxStep,
} from "@/features/integrations"
import { cn } from "@/lib/utils"

type UIStep = {
  localId: number
  order: number
  api_definition_id: number | null
  extra_params_text: string
  param_bindings: SandboxBinding[]
  select_fields: string
}

function makeStep(order: number, localId: number): UIStep {
  return {
    localId,
    order,
    api_definition_id: null,
    extra_params_text: "{}",
    param_bindings: [],
    select_fields: "",
  }
}

export function ApiSandboxPage() {
  const { data: connections = [], isLoading: connLoading } = useErpConnections()
  const [connectionId, setConnectionId] = useState<number | null>(null)
  const selectedConnection = connections.find((c) => c.id === connectionId) ?? null
  const { data: apiDefs = [], isLoading: apiDefsLoading } = useErpApiDefinitions(
    selectedConnection?.provider ?? undefined,
  )

  const [nextLocalId, setNextLocalId] = useState(2)
  const [steps, setSteps] = useState<UIStep[]>([makeStep(1, 1)])

  // Sandbox caps (also enforced server-side)
  const [maxFanout, setMaxFanout] = useState(50)
  const [maxPages, setMaxPages] = useState(1)
  const [maxSteps, setMaxSteps] = useState(2)

  const runMut = useRunSandbox()
  const saveMut = useSavePipeline()
  const [saveName, setSaveName] = useState("")
  const result: SandboxResult | undefined = runMut.data

  // Auto-select first connection once loaded.
  if (!connLoading && connections.length > 0 && connectionId == null) {
    setConnectionId(connections[0].id)
  }

  const addStep = () => {
    if (steps.length >= maxSteps) {
      toast.warning(`Limite de passos (${maxSteps}) atingido`)
      return
    }
    setSteps((s) => [...s, makeStep(s.length + 1, nextLocalId)])
    setNextLocalId((n) => n + 1)
  }

  const removeStep = (localId: number) => {
    setSteps((s) =>
      s
        .filter((st) => st.localId !== localId)
        .map((st, i) => ({ ...st, order: i + 1 })),
    )
  }

  const updateStep = (localId: number, patch: Partial<UIStep>) => {
    setSteps((s) => s.map((st) => (st.localId === localId ? { ...st, ...patch } : st)))
  }

  const parsedSteps: { ok: true; steps: SandboxStep[] } | { ok: false; error: string } = useMemo(() => {
    if (connectionId == null) return { ok: false, error: "Selecione uma conexão." }
    const out: SandboxStep[] = []
    for (const st of steps) {
      if (st.api_definition_id == null) {
        return { ok: false, error: `Passo ${st.order}: selecione uma API.` }
      }
      let extra: Record<string, unknown> = {}
      try {
        extra = st.extra_params_text.trim() ? JSON.parse(st.extra_params_text) : {}
        if (typeof extra !== "object" || Array.isArray(extra) || extra == null) {
          return { ok: false, error: `Passo ${st.order}: extra_params deve ser um objeto JSON.` }
        }
      } catch (err: unknown) {
        return {
          ok: false,
          error: `Passo ${st.order}: extra_params JSON inválido (${err instanceof Error ? err.message : "erro"}).`,
        }
      }
      out.push({
        order: st.order,
        api_definition_id: st.api_definition_id,
        extra_params: extra,
        param_bindings: st.param_bindings,
        select_fields: st.select_fields.trim() || null,
      })
    }
    return { ok: true, steps: out }
  }, [steps, connectionId])

  const runDisabled = !parsedSteps.ok || runMut.isPending

  const onRun = () => {
    if (connectionId == null || !parsedSteps.ok) {
      if (!parsedSteps.ok) toast.error(parsedSteps.error)
      return
    }
    runMut.mutate(
      {
        connection_id: connectionId,
        steps: parsedSteps.steps,
        max_steps: maxSteps,
        max_pages_per_step: maxPages,
        max_fanout: maxFanout,
      },
      {
        onError: (err: unknown) => {
          const msg = extractError(err)
          toast.error(`Falha: ${msg}`)
        },
      },
    )
  }

  const onSavePipeline = () => {
    if (connectionId == null || !parsedSteps.ok) return
    if (!saveName.trim()) {
      toast.error("Nome do pipeline é obrigatório.")
      return
    }
    saveMut.mutate(
      {
        connection: connectionId,
        name: saveName.trim(),
        steps: parsedSteps.steps.map((s) => ({
          order: s.order,
          api_definition: s.api_definition_id,
          extra_params: s.extra_params,
          param_bindings: s.param_bindings,
          select_fields: s.select_fields,
        })),
      },
      {
        onSuccess: (p) => {
          toast.success(`Pipeline #${p.id} salvo`)
          setSaveName("")
        },
        onError: (err: unknown) => toast.error(extractError(err)),
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Sandbox de integração"
        subtitle="Teste composições de chamadas de API antes de salvar um pipeline"
        actions={
          <>
            <button
              disabled={runDisabled}
              onClick={onRun}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {runMut.isPending ? "Executando…" : "Rodar"}
            </button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* Left: connection + step builder */}
        <div className="space-y-3">
          <div className="card-elevated p-4">
            <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
              Conexão
            </h3>
            <select
              value={connectionId ?? ""}
              onChange={(e) => setConnectionId(e.target.value ? Number(e.target.value) : null)}
              className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              disabled={connLoading}
            >
              {connections.length === 0 ? (
                <option value="">Nenhuma conexão cadastrada</option>
              ) : (
                connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name ?? c.provider_display} · {c.provider_display}
                  </option>
                ))
              )}
            </select>

            <div className="mt-3 grid grid-cols-3 gap-2">
              <NumField label="Max passos" value={maxSteps} onChange={setMaxSteps} min={1} max={10} />
              <NumField label="Pág./passo" value={maxPages} onChange={setMaxPages} min={1} max={5} />
              <NumField label="Max fanout" value={maxFanout} onChange={setMaxFanout} min={1} max={200} />
            </div>
          </div>

          {steps.map((st, idx) => (
            <StepCard
              key={st.localId}
              step={st}
              isFirst={idx === 0}
              apiDefs={apiDefs}
              apiDefsLoading={apiDefsLoading}
              priorSteps={steps.filter((s) => s.order < st.order).map((s) => s.order)}
              onChange={(patch) => updateStep(st.localId, patch)}
              onRemove={() => removeStep(st.localId)}
            />
          ))}

          <button
            onClick={addStep}
            disabled={steps.length >= maxSteps}
            className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md border border-dashed border-border text-[12px] font-medium text-muted-foreground hover:bg-accent/40 hover:text-foreground disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" /> Adicionar passo
          </button>

          {parsedSteps.ok ? null : (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
              {parsedSteps.error}
            </div>
          )}

          <div className="card-elevated p-4">
            <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
              Salvar como pipeline
            </h3>
            <div className="flex gap-2">
              <input
                placeholder="Nome (ex: 'Clientes + detalhes')"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                className="h-8 flex-1 rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              />
              <button
                onClick={onSavePipeline}
                disabled={!parsedSteps.ok || saveMut.isPending || !saveName.trim()}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" /> Salvar
              </button>
            </div>
          </div>
        </div>

        {/* Right: preview */}
        <div className="space-y-3">
          {result ? (
            <ResultPane result={result} />
          ) : (
            <div className="card-elevated flex h-[400px] flex-col items-center justify-center p-8 text-center text-[13px] text-muted-foreground">
              <Zap className="mb-3 h-6 w-6" />
              <div className="font-medium text-foreground">Nenhuma execução ainda</div>
              <div className="mt-1">
                Configure passos à esquerda e clique em "Rodar" para ver o preview.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StepCard({
  step,
  isFirst,
  apiDefs,
  apiDefsLoading,
  priorSteps,
  onChange,
  onRemove,
}: {
  step: UIStep
  isFirst: boolean
  apiDefs: Array<{ id: number; call: string; description?: string | null }>
  apiDefsLoading: boolean
  priorSteps: number[]
  onChange: (patch: Partial<UIStep>) => void
  onRemove: () => void
}) {
  return (
    <div className="card-elevated p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
          Passo {step.order}
        </div>
        {!isFirst && (
          <button
            onClick={onRemove}
            className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" /> Remover
          </button>
        )}
      </div>

      <div className="space-y-3">
        <Field label="API">
          <select
            value={step.api_definition_id ?? ""}
            onChange={(e) => onChange({ api_definition_id: e.target.value ? Number(e.target.value) : null })}
            disabled={apiDefsLoading || apiDefs.length === 0}
            className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
          >
            <option value="">— escolha uma API —</option>
            {apiDefs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.call}
                {d.description ? ` · ${d.description}` : ""}
              </option>
            ))}
          </select>
        </Field>

        <Field label="extra_params (JSON)">
          <textarea
            value={step.extra_params_text}
            onChange={(e) => onChange({ extra_params_text: e.target.value })}
            rows={2}
            spellCheck={false}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[12px] outline-none focus:border-ring"
          />
        </Field>

        <Field label="Select fields (JMESPath, opcional — só preview)">
          <input
            value={step.select_fields}
            onChange={(e) => onChange({ select_fields: e.target.value })}
            placeholder="ex: [*].{id: codigo, name: nome}"
            spellCheck={false}
            className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
          />
        </Field>

        <BindingsEditor
          bindings={step.param_bindings}
          priorSteps={priorSteps}
          onChange={(param_bindings) => onChange({ param_bindings })}
        />
      </div>
    </div>
  )
}

function BindingsEditor({
  bindings,
  priorSteps,
  onChange,
}: {
  bindings: SandboxBinding[]
  priorSteps: number[]
  onChange: (next: SandboxBinding[]) => void
}) {
  const add = () => {
    const defaultMode: SandboxBindingMode = priorSteps.length > 0 ? "jmespath" : "static"
    onChange([
      ...bindings,
      defaultMode === "static"
        ? { mode: "static", into: "", value: "" }
        : { mode: defaultMode, into: "", source_step: priorSteps[0], expression: "" },
    ])
  }
  const update = (idx: number, patch: Partial<SandboxBinding>) => {
    onChange(bindings.map((b, i) => (i === idx ? ({ ...b, ...patch } as SandboxBinding) : b)))
  }
  const remove = (idx: number) => {
    onChange(bindings.filter((_, i) => i !== idx))
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Bindings</span>
        <button
          onClick={add}
          className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Plus className="h-3 w-3" /> Adicionar
        </button>
      </div>
      {bindings.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-2 py-2 text-[11px] text-muted-foreground">
          Nenhum binding — os parâmetros vêm apenas de <code>extra_params</code>.
        </div>
      ) : (
        <div className="space-y-2">
          {bindings.map((b, i) => (
            <div key={i} className="rounded-md border border-border bg-muted/20 p-2">
              <div className="grid grid-cols-[110px_minmax(0,1fr)_32px] items-start gap-2">
                <select
                  value={b.mode}
                  onChange={(e) => {
                    const mode = e.target.value as SandboxBindingMode
                    if (mode === "static") {
                      update(i, { mode, source_step: undefined, expression: undefined, value: b.value ?? "" })
                    } else {
                      update(i, { mode, value: undefined, source_step: b.source_step ?? priorSteps[0], expression: b.expression ?? "" })
                    }
                  }}
                  className="h-7 rounded border border-border bg-background px-1 text-[11px]"
                >
                  <option value="static">static</option>
                  <option value="jmespath" disabled={priorSteps.length === 0}>jmespath</option>
                  <option value="fanout" disabled={priorSteps.length === 0}>fanout</option>
                </select>

                <div className="space-y-1.5">
                  <input
                    value={b.into}
                    onChange={(e) => update(i, { into: e.target.value })}
                    placeholder="into (nome do parâmetro)"
                    className="h-7 w-full rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                  />
                  {b.mode === "static" ? (
                    <input
                      value={b.value == null ? "" : String(b.value)}
                      onChange={(e) => update(i, { value: e.target.value })}
                      placeholder="valor (string)"
                      className="h-7 w-full rounded border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
                    />
                  ) : (
                    <div className="grid grid-cols-[80px_minmax(0,1fr)] gap-2">
                      <select
                        value={b.source_step ?? ""}
                        onChange={(e) => update(i, { source_step: Number(e.target.value) })}
                        className="h-7 rounded border border-border bg-background px-1 text-[11px]"
                      >
                        {priorSteps.map((o) => (
                          <option key={o} value={o}>passo {o}</option>
                        ))}
                      </select>
                      <input
                        value={b.expression ?? ""}
                        onChange={(e) => update(i, { expression: e.target.value })}
                        placeholder={b.mode === "fanout" ? "items[*].codigo" : "items[0].codigo"}
                        className="h-7 w-full rounded border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
                      />
                    </div>
                  )}
                </div>

                <button
                  onClick={() => remove(i)}
                  className="grid h-7 w-7 place-items-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ResultPane({ result }: { result: SandboxResult }) {
  const hasError = !!result.error || (result.errors && result.errors.length > 0)
  const previews = result.preview_by_step ?? []
  const [activeOrder, setActiveOrder] = useState<number | null>(previews[0]?.order ?? null)
  const active = previews.find((p) => p.order === activeOrder) ?? previews[0] ?? null

  return (
    <>
      <div className="card-elevated p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Resultado</div>
            <div
              className={cn(
                "text-[13px] font-semibold",
                result.status === "completed" && "text-emerald-500",
                result.status === "partial" && "text-amber-500",
                (result.status === "failed" || result.error) && "text-destructive",
              )}
            >
              {result.error ? "Erro de configuração" : result.status ?? (result.success ? "ok" : "—")}
            </div>
          </div>
          <div className="text-right text-[12px] text-muted-foreground">
            <div>{result.records_extracted ?? 0} registros · {result.diagnostics?.pages ?? 0} páginas</div>
            {result.caps && (
              <div className="text-[10px] opacity-70">
                caps: {result.caps.max_steps}s / {result.caps.max_pages_per_step}p / {result.caps.max_fanout}f
              </div>
            )}
          </div>
        </div>

        {hasError && (
          <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-[12px] text-destructive">
            {result.error && <div>{result.error}</div>}
            {(result.errors ?? []).map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        )}
      </div>

      {result.diagnostics?.steps && result.diagnostics.steps.length > 0 && (
        <div className="card-elevated p-4">
          <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Diagnóstico por passo
          </div>
          <div className="space-y-2">
            {result.diagnostics.steps.map((s) => (
              <div key={s.order} className="rounded-md border border-border p-2 text-[12px]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-primary/15 text-[10px] font-semibold text-primary">
                      {s.order}
                    </span>
                    <code className="font-mono">{s.api_call}</code>
                  </div>
                  <div className="text-muted-foreground">
                    {s.extracted} rec · {s.pages} pág · {s.retries} retries
                  </div>
                </div>
                {s.fanout && (
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <ArrowDown className="h-3 w-3" />
                    fanout <code className="font-mono">{s.fanout.expression}</code> → {s.fanout.value_count} chamadas
                  </div>
                )}
                {s.resolved_bindings && s.resolved_bindings.length > 0 && (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {s.resolved_bindings.length} binding(s) resolvido(s)
                  </div>
                )}
                {s.error && <div className="mt-1 text-[11px] text-destructive">{s.error}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {previews.length > 0 && (
        <div className="card-elevated p-4">
          <div className="mb-2 flex items-center gap-1">
            {previews.map((p) => (
              <button
                key={p.order}
                onClick={() => setActiveOrder(p.order)}
                className={cn(
                  "rounded-md px-2 py-1 text-[12px] font-medium",
                  (active?.order ?? previews[0].order) === p.order
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {p.order}. {p.api_call}{" "}
                <span className="text-[10px] opacity-60">({p.row_count})</span>
              </button>
            ))}
          </div>
          {active && <PreviewTable rows={active.rows} projected={active.projected} />}
        </div>
      )}

      {result.first_payload_redacted && (
        <details className="card-elevated p-4">
          <summary className="cursor-pointer text-[12px] font-medium text-muted-foreground">
            Primeiro payload (mascarado)
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-[11px]">
            {JSON.stringify(result.first_payload_redacted, null, 2)}
          </pre>
        </details>
      )}
    </>
  )
}

function PreviewTable({ rows, projected }: { rows: Array<Record<string, unknown>>; projected: unknown }) {
  const [mode, setMode] = useState<"table" | "json" | "projected">(projected == null ? "table" : "projected")
  const keys = useMemo(() => {
    const s = new Set<string>()
    for (const r of rows.slice(0, 50)) {
      if (r && typeof r === "object") Object.keys(r).forEach((k) => s.add(k))
    }
    return Array.from(s)
  }, [rows])

  if (rows.length === 0 && projected == null) {
    return <div className="text-[12px] text-muted-foreground">Sem linhas.</div>
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-1 text-[11px]">
        <ChevronRight className="h-3 w-3" />
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
        {projected != null && (
          <button
            onClick={() => setMode("projected")}
            className={cn(
              "rounded px-1.5 py-0.5",
              mode === "projected" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            Projeção
          </button>
        )}
      </div>

      {mode === "table" && (
        <div className="overflow-auto rounded-md border border-border" style={{ maxHeight: 360 }}>
          <table className="w-full text-[11px]">
            <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {keys.map((k) => (
                  <th key={k} className="h-7 whitespace-nowrap px-2 font-medium">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 100).map((r, i) => (
                <tr key={i} className="border-t border-border">
                  {keys.map((k) => (
                    <td key={k} className="h-7 max-w-[220px] truncate px-2 font-mono">
                      {formatCell((r as Record<string, unknown>)?.[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mode === "json" && (
        <pre className="max-h-[360px] overflow-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-[11px]">
          {JSON.stringify(rows.slice(0, 20), null, 2)}
        </pre>
      )}

      {mode === "projected" && (
        <pre className="max-h-[360px] overflow-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-[11px]">
          {JSON.stringify(projected, null, 2)}
        </pre>
      )}
    </div>
  )
}

function formatCell(v: unknown): string {
  if (v == null) return ""
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function NumField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min: number
  max: number
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value)
          if (Number.isFinite(n)) onChange(Math.max(min, Math.min(max, Math.round(n))))
        }}
        className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
      />
    </label>
  )
}

function extractError(err: unknown): string {
  if (err && typeof err === "object") {
    const anyErr = err as { response?: { data?: unknown }; message?: string }
    const data = anyErr.response?.data
    if (data && typeof data === "object") {
      const d = data as { error?: string; detail?: string; errors?: string[] }
      if (d.error) return d.error
      if (d.detail) return d.detail
      if (Array.isArray(d.errors) && d.errors.length) return d.errors.join("; ")
    }
    if (typeof data === "string") return data
    if (anyErr.message) return anyErr.message
  }
  return "erro desconhecido"
}
