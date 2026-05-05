import { useEffect, useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import { Play, Plus, Save, Trash2, ChevronRight, ArrowDown, Zap, Link2, Code2, RotateCcw, Settings2 } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useErpApiDefinitions,
  useErpConnections,
  useRunSandbox,
  useSavePipeline,
  type ERPAPIDefinition,
  type ParamSpec,
  type SandboxBinding,
  type SandboxBindingMode,
  type SandboxResult,
  type SandboxStep,
} from "@/features/integrations"
import { cn } from "@/lib/utils"
import { StepStructurePanel } from "./components/StepStructurePanel"
import { JoinedResultView } from "./components/JoinedResultView"

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
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
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
  const [lastRunSignature, setLastRunSignature] = useState<string | null>(null)
  const [urlPrefillDone, setUrlPrefillDone] = useState(false)
  const result: SandboxResult | undefined = runMut.data

  // Auto-select first connection once loaded.
  useEffect(() => {
    if (connLoading || connections.length === 0 || connectionId != null) return
    const requestedConnectionId = Number(searchParams.get("connection_id"))
    const requested = connections.find((c) => c.id === requestedConnectionId)
    setConnectionId((requested ?? connections[0]).id)
  }, [connLoading, connections, connectionId, searchParams])

  useEffect(() => {
    if (urlPrefillDone || apiDefs.length === 0) return
    const requestedApiId = Number(searchParams.get("api_definition_id"))
    if (!requestedApiId) {
      setUrlPrefillDone(true)
      return
    }
    const apiDef = apiDefs.find((d) => d.id === requestedApiId)
    if (!apiDef) return
    setSteps((current) =>
      current.map((step, index) =>
        index === 0
          ? {
              ...step,
              api_definition_id: apiDef.id,
              extra_params_text: stringifyParams(defaultParamsFromSchema(apiDef.param_schema)),
            }
          : step,
      ),
    )
    setUrlPrefillDone(true)
    const next = new URLSearchParams(searchParams)
    next.delete("api_definition_id")
    next.delete("connection_id")
    setSearchParams(next, { replace: true })
  }, [apiDefs, searchParams, setSearchParams, urlPrefillDone])

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

  const updateStepApiDefinition = (localId: number, apiDefinitionId: number | null) => {
    const apiDef = apiDefs.find((d) => d.id === apiDefinitionId)
    updateStep(localId, {
      api_definition_id: apiDefinitionId,
      extra_params_text: apiDef ? stringifyParams(defaultParamsFromSchema(apiDef.param_schema)) : "{}",
    })
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

  const currentRunSignature = sandboxRunSignature(
    connectionId,
    parsedSteps,
    maxSteps,
    maxPages,
    maxFanout,
  )
  const runDisabled = !parsedSteps.ok || runMut.isPending
  const resultHasError = !!result?.error || (result?.errors?.length ?? 0) > 0
  const previewIsCurrent = !!result && !!lastRunSignature && lastRunSignature === currentRunSignature
  const canSavePipeline = parsedSteps.ok && previewIsCurrent && !resultHasError && !saveMut.isPending && !!saveName.trim()

  const onRun = () => {
    if (connectionId == null || !parsedSteps.ok) {
      if (!parsedSteps.ok) toast.error(parsedSteps.error)
      return
    }
    if (pipelineHasFanout(parsedSteps.steps)) {
      toast.warning(`Este preview pode fazer ate ${maxFanout} chamadas repetidas no passo vinculado.`)
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
        onSuccess: () => {
          setLastRunSignature(currentRunSignature)
        },
        onError: (err: unknown) => {
          const msg = extractError(err)
          setLastRunSignature(null)
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.9fr)]">
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

            <details className="mt-3 rounded-md border border-border bg-muted/20 px-3 py-2">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-[11px] font-medium text-muted-foreground hover:text-foreground">
                <Settings2 className="h-3.5 w-3.5" />
                Modo preview
              </summary>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <NumField label="Max passos" value={maxSteps} onChange={setMaxSteps} min={1} max={10} />
              <NumField label="Pág./passo" value={maxPages} onChange={setMaxPages} min={1} max={5} />
              <NumField label="Max repeticoes" value={maxFanout} onChange={setMaxFanout} min={1} max={200} />
              </div>
            </details>
          </div>

          {steps.map((st, idx) => {
            const nextStep = steps.find((s) => s.order === st.order + 1)
            const currentApiDef = apiDefs.find((d) => d.id === st.api_definition_id) ?? null
            const nextApiDef = nextStep
              ? apiDefs.find((d) => d.id === nextStep.api_definition_id) ?? null
              : null
            // Phase-3: clicking a column in step N's structure adds a
            // jmespath binding to step N+1 with source_step=N and the
            // column path as expression — operator just fills ``into``.
            const onBindToNext = nextStep
              ? (path: string) => {
                  const inferredInto = inferBindingTarget(path, nextApiDef)
                  const newBinding: SandboxBinding = {
                    mode: "fanout",
                    into: inferredInto,
                    source_step: st.order,
                    expression: bindingExpressionForColumn(currentApiDef, path),
                  }
                  updateStep(nextStep.localId, {
                    param_bindings: [...nextStep.param_bindings, newBinding],
                  })
                  toast.success(`Vinculo adicionado ao Passo ${nextStep.order}. Revise o campo de destino.`)
                }
              : undefined
            return (
              <StepCard
                key={st.localId}
                step={st}
                isFirst={idx === 0}
                apiDefs={apiDefs}
                apiDefsLoading={apiDefsLoading}
                priorSteps={steps.filter((s) => s.order < st.order).map((s) => s.order)}
                maxFanout={maxFanout}
                onChange={(patch) => updateStep(st.localId, patch)}
                onApiDefinitionChange={(apiDefinitionId) => updateStepApiDefinition(st.localId, apiDefinitionId)}
                onEditApiDefinition={(apiDefinitionId) => navigate(`/integrations/api-definitions?edit=${apiDefinitionId}`)}
                onRemove={() => removeStep(st.localId)}
                connectionId={connectionId}
                onBindColumnToNext={onBindToNext}
                hasNextStep={!!nextStep}
              />
            )
          })}

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
                disabled={!canSavePipeline}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" /> Salvar
              </button>
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">
              {previewIsCurrent && !resultHasError
                ? "Preview validado. Informe um nome para salvar o pipeline."
                : "Rode o preview com sucesso antes de salvar. Assim o pipeline fica registrado com uma execucao validada."}
            </div>
          </div>
        </div>

        {/* Right: preview */}
        <div className="space-y-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-auto">
          {result ? (
            <ResultPane result={result} isStale={!previewIsCurrent} />
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
  maxFanout,
  onChange,
  onApiDefinitionChange,
  onEditApiDefinition,
  onRemove,
  connectionId,
  onBindColumnToNext,
  hasNextStep,
}: {
  step: UIStep
  isFirst: boolean
  apiDefs: ERPAPIDefinition[]
  apiDefsLoading: boolean
  priorSteps: number[]
  maxFanout: number
  onChange: (patch: Partial<UIStep>) => void
  onApiDefinitionChange: (apiDefinitionId: number | null) => void
  onEditApiDefinition: (apiDefinitionId: number) => void
  onRemove: () => void
  connectionId: number | null
  onBindColumnToNext?: (path: string) => void
  hasNextStep: boolean
}) {
  // Parse extra_params for the structure probe — silently treat invalid
  // JSON as empty so probing keeps working while the operator types.
  const extraParamsForProbe = useMemo(() => {
    try {
      const parsed = JSON.parse(step.extra_params_text || "{}")
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {}
    } catch {
      return {}
    }
  }, [step.extra_params_text])

  const selectedApiDef = apiDefs.find((d) => d.id === step.api_definition_id) ?? null

  return (
    <div className="card-elevated p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
          Passo {step.order}
        </div>
        {!isFirst && (
          <button
            onClick={onRemove}
            aria-label={`Remover passo ${step.order}`}
            className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" /> Remover
          </button>
        )}
      </div>

      <div className="space-y-3">
        <Field label="API">
          <div className="flex gap-2">
            <select
              value={step.api_definition_id ?? ""}
              onChange={(e) => onApiDefinitionChange(e.target.value ? Number(e.target.value) : null)}
              disabled={apiDefsLoading || apiDefs.length === 0}
              className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
            >
              <option value="">? escolha uma API ?</option>
              {apiDefs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.call}
                  {d.description ? ` ? ${d.description}` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!step.api_definition_id}
              onClick={() => step.api_definition_id && onEditApiDefinition(step.api_definition_id)}
              className="inline-flex h-8 shrink-0 items-center rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
              title="Abrir cadastro desta API"
            >
              Editar API
            </button>
          </div>
        </Field>

        <ParamsEditor
          apiDefinition={selectedApiDef}
          valueText={step.extra_params_text}
          onChangeText={(extra_params_text) => onChange({ extra_params_text })}
        />

        {/* Phase-3: auto-probed structure of the API's response. Clicking
            a column wires a binding into the next step (when one exists). */}
        <StepStructurePanel
          connectionId={connectionId}
          apiDefinitionId={step.api_definition_id}
          stepOrder={step.order}
          extraParams={extraParamsForProbe}
          onBindColumn={onBindColumnToNext}
          hasNextStep={hasNextStep}
        />

        <details className="rounded-md border border-border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer list-none text-[11px] font-medium text-muted-foreground hover:text-foreground">
            Campos do preview
          </summary>
          <div className="mt-2 space-y-2">
            <div className="text-[11px] text-muted-foreground">
              Deixe em branco para ver todas as colunas. Use o modo avancado apenas quando precisar montar uma visao tecnica do resultado.
            </div>
          <input
            value={step.select_fields}
            onChange={(e) => onChange({ select_fields: e.target.value })}
            placeholder="Avancado: [*].{id: codigo, nome: nome_fantasia}"
            spellCheck={false}
            className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
          />
          </div>
        </details>

        <BindingsEditor
          apiDefinition={selectedApiDef}
          bindings={step.param_bindings}
          priorSteps={priorSteps}
          maxFanout={maxFanout}
          onChange={(param_bindings) => onChange({ param_bindings })}
        />
      </div>
    </div>
  )
}

function BindingsEditor({
  apiDefinition,
  bindings,
  priorSteps,
  maxFanout,
  onChange,
}: {
  apiDefinition: ERPAPIDefinition | null
  bindings: SandboxBinding[]
  priorSteps: number[]
  maxFanout: number
  onChange: (next: SandboxBinding[]) => void
}) {
  const params = apiDefinition?.param_schema ?? []
  const add = () => {
    const defaultMode: SandboxBindingMode = priorSteps.length > 0 ? "fanout" : "static"
    onChange([
      ...bindings,
      defaultMode === "static"
        ? { mode: "static", into: params[0]?.name ?? "", value: "" }
        : { mode: defaultMode, into: params[0]?.name ?? "", source_step: priorSteps[0], expression: "" },
    ])
  }
  const update = (idx: number, patch: Partial<SandboxBinding>) => {
    onChange(bindings.map((b, i) => (i === idx ? ({ ...b, ...patch } as SandboxBinding) : b)))
  }
  const remove = (idx: number) => {
    onChange(bindings.filter((_, i) => i !== idx))
  }

  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Vinculos de entrada
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            Use dados de passos anteriores para preencher parametros desta API.
          </div>
        </div>
        <button
          type="button"
          onClick={add}
          aria-label="Adicionar vinculo de entrada"
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Plus className="h-3 w-3" /> Adicionar
        </button>
      </div>
      {priorSteps.length > 0 && <JoinStrategyHint apiDefinition={apiDefinition} />}
      {bindings.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-2 py-2 text-[11px] text-muted-foreground">
          Nenhum vinculo. Os parametros deste passo serao usados exatamente como foram preenchidos acima.
        </div>
      ) : (
        <div className="space-y-2">
          {bindings.map((b, i) => (
            <div key={i} className="rounded-md border border-border bg-background p-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-foreground">
                  {bindingModeLabel(b.mode)}
                </div>
                <button
                  type="button"
                  onClick={() => remove(i)}
                  aria-label={`Remover vinculo ${i + 1}`}
                  className="grid h-7 w-7 place-items-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                  title="Remover vinculo"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>

              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_150px]">
                <label className="space-y-1">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Preencher campo
                  </span>
                  {params.length > 0 ? (
                    <select
                      value={b.into}
                      onChange={(e) => update(i, { into: e.target.value })}
                      className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    >
                      <option value="">Escolha um parametro</option>
                      {params.map((param) => (
                        <option key={param.name} value={param.name}>
                          {humanizeParamName(param.name)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={b.into}
                      onChange={(e) => update(i, { into: e.target.value })}
                      placeholder="Nome do parametro"
                      className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    />
                  )}
                </label>

                <label className="space-y-1">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Como preencher
                  </span>
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
                    className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                  >
                    <option value="static">Valor fixo</option>
                    <option value="jmespath" disabled={priorSteps.length === 0}>Copiar campo</option>
                    <option value="fanout" disabled={priorSteps.length === 0}>Repetir por lista</option>
                  </select>
                </label>
              </div>

              {b.mode === "static" ? (
                <label className="mt-2 block space-y-1">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Valor
                  </span>
                  <input
                    value={b.value == null ? "" : String(b.value)}
                    onChange={(e) => update(i, { value: e.target.value })}
                    placeholder="Valor enviado para esta API"
                    className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                  />
                </label>
              ) : (
                <div className="mt-2 grid gap-2 md:grid-cols-[120px_minmax(0,1fr)]">
                  <label className="space-y-1">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      Origem
                    </span>
                    <select
                      value={b.source_step ?? ""}
                      onChange={(e) => update(i, { source_step: Number(e.target.value) })}
                      className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
                    >
                      {priorSteps.map((o) => (
                        <option key={o} value={o}>Passo {o}</option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      Campo de origem
                    </span>
                    <input
                      value={b.expression ?? ""}
                      onChange={(e) => update(i, { expression: e.target.value })}
                      placeholder={b.mode === "fanout" ? "conta_pagar_cadastro[*].codigo_cliente_fornecedor" : "codigo_cliente_fornecedor"}
                      className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
                    />
                  </label>
                </div>
              )}
              {b.mode === "fanout" && (
                <FanoutNotice apiDefinition={apiDefinition} maxFanout={maxFanout} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FanoutNotice({
  apiDefinition,
  maxFanout,
}: {
  apiDefinition: ERPAPIDefinition | null
  maxFanout: number
}) {
  const isLookup = isLookupApi(apiDefinition)
  return (
    <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-2 text-[11px] leading-snug text-amber-200">
      <div className="font-medium text-amber-100">
        Este modo consulta um item por vez.
      </div>
      <div className="mt-0.5">
        No preview, pode fazer ate {maxFanout} chamadas desta API. Use quando a API precisa receber um codigo especifico.
      </div>
      {isLookup ? (
        <div className="mt-1 text-amber-100/80">
          Para grandes volumes, prefira uma API de lista, como ListarClientes/ListarCategorias, e cruze os dados em lote quando existir esse caminho.
        </div>
      ) : null}
    </div>
  )
}

function JoinStrategyHint({ apiDefinition }: { apiDefinition: ERPAPIDefinition | null }) {
  const lookup = isLookupApi(apiDefinition)
  const list = isListApi(apiDefinition)
  return (
    <div className="mb-2 rounded-md border border-border bg-background/70 px-2 py-2 text-[11px] leading-snug text-muted-foreground">
      {lookup ? (
        <>
          <span className="font-medium text-foreground">Consulta por ID.</span>{" "}
          Esta API costuma buscar um registro por vez. Funciona para validar poucos itens, mas pode ficar lenta em volume.
        </>
      ) : list ? (
        <>
          <span className="font-medium text-foreground">Consulta em lote.</span>{" "}
          Esta API tende a trazer uma lista. Para enriquecer contas a pagar, prefira cruzar listas como clientes e categorias quando possivel.
        </>
      ) : (
        <>
          <span className="font-medium text-foreground">Escolha o tipo de vinculo.</span>{" "}
          Use valor fixo para filtros, copiar campo para um unico valor e repetir por lista apenas quando precisar consultar item por item.
        </>
      )}
    </div>
  )
}

function ParamsEditor({
  apiDefinition,
  valueText,
  onChangeText,
}: {
  apiDefinition: ERPAPIDefinition | null
  valueText: string
  onChangeText: (value: string) => void
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [activeParam, setActiveParam] = useState<string | null>(null)

  const parseResult = useMemo(() => parseParamsText(valueText), [valueText])
  const params = parseResult.ok ? parseResult.value : {}
  const schema = apiDefinition?.param_schema ?? []
  const activeSpec = activeParam ? schema.find((spec) => spec.name === activeParam) ?? null : null

  const setParam = (name: string, rawValue: string, spec: ParamSpec) => {
    const next = { ...params }
    if (rawValue === "" && !spec.required) {
      delete next[name]
    } else {
      next[name] = coerceParamValue(rawValue, spec)
    }
    onChangeText(stringifyParams(next))
  }

  const resetDefaults = () => {
    onChangeText(stringifyParams(defaultParamsFromSchema(schema)))
    setActiveParam(null)
  }

  if (!apiDefinition) {
    return (
      <div className="rounded-md border border-dashed border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
        Selecione uma API para configurar os parametros de consulta.
      </div>
    )
  }

  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Parametros da API
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            Preencha os filtros desta chamada sem editar JSON.
          </div>
        </div>
        <button
          type="button"
          onClick={resetDefaults}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          title="Restaurar valores padrao desta API"
        >
          <RotateCcw className="h-3 w-3" />
          Defaults
        </button>
      </div>

      {schema.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-2 py-2 text-[11px] text-muted-foreground">
          Esta API nao declara parametros. Use o modo avancado se precisar enviar algum valor manual.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {schema.map((spec) => (
              <ParamSummaryRow
                key={spec.name}
                spec={spec}
                value={params[spec.name]}
                active={activeParam === spec.name}
                onClick={() => setActiveParam((current) => (current === spec.name ? null : spec.name))}
              />
            ))}
          </div>
          {activeSpec ? (
            <ParamDetailEditor
              spec={activeSpec}
              value={params[activeSpec.name]}
              onChange={(rawValue) => setParam(activeSpec.name, rawValue, activeSpec)}
              onClose={() => setActiveParam(null)}
            />
          ) : (
            <div className="rounded-md border border-dashed border-border px-2 py-2 text-[11px] text-muted-foreground">
              Clique em um parametro para editar seus detalhes.
            </div>
          )}
        </div>
      )}

      {!parseResult.ok && (
        <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-[11px] text-destructive">
          JSON avancado invalido: {parseResult.error}
        </div>
      )}

      <div className="mt-2">
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Code2 className="h-3 w-3" />
          {advancedOpen ? "Ocultar JSON avancado" : "Mostrar JSON avancado"}
        </button>
        {advancedOpen && (
          <textarea
            value={valueText}
            onChange={(e) => onChangeText(e.target.value)}
            rows={4}
            spellCheck={false}
            className="mt-2 w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[12px] outline-none focus:border-ring"
          />
        )}
      </div>
    </div>
  )
}

function ParamSummaryRow({
  spec,
  value,
  active,
  onClick,
}: {
  spec: ParamSpec
  value: unknown
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-md border px-2 text-left text-[11px] transition-colors sm:w-[190px]",
        active
          ? "border-primary/60 bg-primary/10 text-foreground"
          : "border-border bg-background/70 text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
      title={spec.description || spec.name}
    >
      <span className="min-w-0">
        <span className="block truncate font-semibold">{humanizeParamName(spec.name)}</span>
        <span className="block truncate font-mono text-[10px] opacity-75">{summarizeParamValue(value, spec)}</span>
      </span>
      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground">
        {spec.required ? "obrig." : spec.type ?? "string"}
      </span>
    </button>
  )
}

function ParamDetailEditor({
  spec,
  value,
  onChange,
  onClose,
}: {
  spec: ParamSpec
  value: unknown
  onChange: (rawValue: string) => void
  onClose: () => void
}) {
  const type = spec.type ?? "string"
  const displayValue = formatParamInputValue(value)
  const description = spec.description || defaultDescriptionForParam(spec)
  const isComplex = type === "object" || type === "array"
  const isYesNo = isYesNoParam(spec)

  return (
    <label className="flex min-w-0 flex-col gap-1 rounded-md border border-primary/30 bg-background p-2">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <span className="min-w-0">
          <span className="block truncate text-[12px] font-semibold text-foreground">{humanizeParamName(spec.name)}</span>
          {description && <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">{description}</span>}
        </span>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground">
          {spec.required ? "obrig." : type}
        </span>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="self-start rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        Fechar
      </button>
      {type === "boolean" ? (
        <select
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          <option value="">Nao enviar</option>
          <option value="true">Sim</option>
          <option value="false">Nao</option>
        </select>
      ) : isYesNo ? (
        <select
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          {!spec.required && <option value="">Nao enviar</option>}
          <option value="N">Nao</option>
          <option value="S">Sim</option>
        </select>
      ) : type === "enum" && spec.options?.length ? (
        <select
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          {!spec.required && <option value="">Nao enviar</option>}
          {spec.options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      ) : isComplex ? (
        <textarea
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          rows={2}
          spellCheck={false}
          placeholder={type === "array" ? "[]" : "{}"}
          className="rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[12px] outline-none focus:border-ring"
        />
      ) : (
        <input
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          type={inputTypeForParam(type)}
          placeholder={spec.default == null ? "Nao enviar" : String(spec.default)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        />
      )}
    </label>
  )
}

function ResultPane({ result, isStale }: { result: SandboxResult; isStale: boolean }) {
  const hasError = !!result.error || (result.errors && result.errors.length > 0)
  const friendlyErrors = [result.error, ...(result.errors ?? [])]
    .filter(Boolean)
    .map((e) => explainSandboxError(String(e)))
  const previews = result.preview_by_step ?? []
  const [activeOrder, setActiveOrder] = useState<number | null>(previews[0]?.order ?? null)
  // Phase-3: tab toggles between per-step view and the consolidated
  // joined view. Picking a step (per-step button) flips this back to
  // "step"; the Resultado button flips it to "joined".
  const [activeTab, setActiveTab] = useState<"step" | "joined">("step")
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

        {isStale && (
          <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[12px] text-amber-200">
            Esta configuracao mudou depois do ultimo preview. Rode novamente antes de salvar.
          </div>
        )}

        {hasError && (
          <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-[12px] text-destructive">
            {friendlyErrors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
            <details className="mt-1">
              <summary className="cursor-pointer text-[11px] text-destructive/80">Detalhes tecnicos</summary>
              <div className="mt-1 space-y-1 font-mono text-[11px]">
                {result.error && <div>{result.error}</div>}
                {(result.errors ?? []).map((e, i) => (
                  <div key={i}>{e}</div>
                ))}
              </div>
            </details>
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
                    {s.extracted} registros · {s.pages} pags. · {s.retries} tentativas
                  </div>
                </div>
                {s.fanout && (
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <ArrowDown className="h-3 w-3" />
                    Repetiu a chamada usando <code className="font-mono">{s.fanout.expression}</code> → {s.fanout.value_count} chamadas
                  </div>
                )}
                {s.resolved_bindings && s.resolved_bindings.length > 0 && (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {s.resolved_bindings.length} vinculo(s) resolvido(s)
                  </div>
                )}
                {s.error && <div className="mt-1 text-[11px] text-destructive">{explainSandboxError(s.error)}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {previews.length > 0 && (
        <div className="card-elevated p-4">
          <div className="mb-2 flex flex-wrap items-center gap-1">
            {previews.map((p) => (
              <button
                key={p.order}
                onClick={() => { setActiveOrder(p.order); setActiveTab("step") }}
                className={cn(
                  "rounded-md px-2 py-1 text-[12px] font-medium",
                  activeTab === "step" && (active?.order ?? previews[0].order) === p.order
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {p.order}. {p.api_call}{" "}
                <span className="text-[10px] opacity-60">({p.row_count})</span>
              </button>
            ))}
            {/* Phase-3: consolidated tab — shows the join across steps. */}
            {previews.length > 1 ? (
              <button
                onClick={() => setActiveTab("joined")}
                className={cn(
                  "ml-1 rounded-md px-2 py-1 text-[12px] font-medium",
                  activeTab === "joined"
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
                title="Tabela única juntando colunas de todos os passos"
              >
                <Link2 className="mr-1 inline h-3 w-3" />
                Resultado
              </button>
            ) : null}
          </div>
          {activeTab === "joined" && previews.length > 1 ? (
            <JoinedResultView result={result} />
          ) : (
            active && <PreviewTable rows={active.rows} projected={active.projected} />
          )}
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

function sandboxRunSignature(
  connectionId: number | null,
  parsedSteps: { ok: true; steps: SandboxStep[] } | { ok: false; error: string },
  maxSteps: number,
  maxPages: number,
  maxFanout: number,
): string {
  return JSON.stringify({
    connectionId,
    steps: parsedSteps.ok ? parsedSteps.steps : null,
    maxSteps,
    maxPages,
    maxFanout,
  })
}

function pipelineHasFanout(steps: SandboxStep[]): boolean {
  return steps.some((step) => (step.param_bindings ?? []).some((binding) => binding.mode === "fanout"))
}

function explainSandboxError(message: string): string {
  const lower = message.toLowerCase()
  if (lower.includes("425 client error") || lower.includes("app.omie.com.br")) {
    return "A API externa recusou uma das chamadas. Revise o campo usado no vinculo ou prefira uma API de lista para cruzar os dados em lote."
  }
  if (lower.includes("fanout expression") && lower.includes("must resolve to a list")) {
    return "O campo escolhido para repetir chamadas nao retornou uma lista. Escolha uma coluna com varios valores ou mude o modo do vinculo."
  }
  if (lower.includes("only one fanout")) {
    return "Este passo tem mais de um vinculo do tipo repetir por lista. Por enquanto, use apenas um por passo."
  }
  if (lower.includes("invalid select_fields")) {
    return "Os campos do preview avancado estao invalidos. Limpe esse campo ou revise a expressao tecnica."
  }
  return message
}

function defaultParamsFromSchema(schema: ParamSpec[] | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const spec of schema ?? []) {
    if (spec && "default" in spec) out[spec.name] = spec.default
  }
  return out
}

function stringifyParams(params: Record<string, unknown>): string {
  return JSON.stringify(params, null, 2)
}

function parseParamsText(text: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  try {
    const parsed = text.trim() ? JSON.parse(text) : {}
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "use um objeto, por exemplo {\"pagina\": 1}" }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch (err: unknown) {
    return { ok: false, error: err instanceof Error ? err.message : "erro desconhecido" }
  }
}

function coerceParamValue(rawValue: string, spec: ParamSpec): unknown {
  const type = spec.type ?? "string"
  if (type === "int" || type === "integer" || type === "number" || type === "decimal") {
    const parsed = Number(rawValue)
    return Number.isFinite(parsed) ? parsed : rawValue
  }
  if (type === "boolean") {
    if (rawValue === "true") return true
    if (rawValue === "false") return false
    return rawValue
  }
  if (type === "object" || type === "array") {
    try {
      return rawValue.trim() ? JSON.parse(rawValue) : type === "array" ? [] : {}
    } catch {
      return rawValue
    }
  }
  return rawValue
}

function formatParamInputValue(value: unknown): string {
  if (value === undefined || value === null) return ""
  if (typeof value === "object") return JSON.stringify(value, null, 2)
  return String(value)
}

function summarizeParamValue(value: unknown, spec: ParamSpec): string {
  if (value === undefined || value === null || value === "") {
    return spec.required ? "Obrigatorio" : "Nao enviado"
  }
  if (typeof value === "object") {
    const text = JSON.stringify(value)
    return text.length > 36 ? `${text.slice(0, 33)}...` : text
  }
  const text = String(value)
  if (isYesNoParam(spec)) return text === "S" ? "Sim" : text === "N" ? "Nao" : text
  return text.length > 36 ? `${text.slice(0, 33)}...` : text
}

function bindingModeLabel(mode: SandboxBindingMode): string {
  if (mode === "static") return "Valor fixo"
  if (mode === "fanout") return "Repetir chamada para cada item"
  return "Copiar dado de outro passo"
}

function isLookupApi(apiDefinition: ERPAPIDefinition | null): boolean {
  const call = apiDefinition?.call.toLowerCase() ?? ""
  return call.startsWith("consultar") || call.includes("porcodigo") || call.includes("por código")
}

function isListApi(apiDefinition: ERPAPIDefinition | null): boolean {
  return (apiDefinition?.call.toLowerCase() ?? "").startsWith("listar")
}

function bindingExpressionForColumn(apiDefinition: ERPAPIDefinition | null, path: string): string {
  const recordsPath = getRecordsPath(apiDefinition)
  return recordsPath ? `${recordsPath}[*].${path}` : path
}

function getRecordsPath(apiDefinition: ERPAPIDefinition | null): string {
  const records = apiDefinition?.transform_config?.records
  if (records && typeof records === "object" && !Array.isArray(records)) {
    const path = (records as { path?: unknown }).path
    return typeof path === "string" ? path.trim() : ""
  }
  return ""
}

function inferBindingTarget(sourcePath: string, nextApiDefinition: ERPAPIDefinition | null): string {
  const params = nextApiDefinition?.param_schema ?? []
  const names = params.map((p) => p.name)
  const lowerSource = sourcePath.toLowerCase()

  const preferred =
    lowerSource.includes("cliente") || lowerSource.includes("fornecedor")
      ? ["codigo_cliente_omie", "codigo_cliente_fornecedor", "cnpj_cpf"]
      : lowerSource.includes("categoria")
        ? ["codigo_categoria", "categoria"]
        : lowerSource.includes("conta_corrente")
          ? ["id_conta_corrente", "codigo_conta_corrente", "nCodCC"]
          : lowerSource.includes("produto")
            ? ["codigo_produto", "codigo_produto_integracao"]
            : []

  for (const candidate of preferred) {
    if (names.includes(candidate)) return candidate
  }
  return names.find((name) => !["pagina", "registros_por_pagina", "nPagina", "nRegPorPagina"].includes(name)) ?? names[0] ?? ""
}

function inputTypeForParam(type: ParamSpec["type"] | undefined): string {
  if (type === "int" || type === "integer" || type === "number" || type === "decimal") return "number"
  if (type === "date") return "text"
  if (type === "datetime") return "text"
  return "text"
}

function isYesNoParam(spec: ParamSpec): boolean {
  const defaultValue = typeof spec.default === "string" ? spec.default.toUpperCase() : ""
  const description = (spec.description ?? "").toUpperCase()
  return (defaultValue === "S" || defaultValue === "N") && description.includes("S/N")
}

function humanizeParamName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function defaultDescriptionForParam(spec: ParamSpec): string {
  if (spec.name === "pagina" || spec.name === "nPagina") return "Pagina inicial da consulta."
  if (spec.name === "registros_por_pagina" || spec.name === "nRegPorPagina") return "Quantidade de registros por pagina."
  return ""
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
