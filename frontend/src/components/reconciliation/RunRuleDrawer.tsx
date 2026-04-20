import { useEffect, useMemo, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import { Play, X, Sparkles, CheckCircle2, Info, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  useFilterColumns,
  usePreviewCounts,
  useReconConfig,
  useReconConfigs,
  useReconPipeline,
  useReconPipelines,
  useStartReconTask,
} from "@/features/reconciliation"
import type {
  FilterColumnDef,
  FilterStack,
} from "@/features/reconciliation/types"
import { FilterStackBuilder } from "./FilterStackBuilder"

export interface RunRuleDrawerProps {
  open: boolean
  onClose: () => void
  /** Pre-filled bank filter stack (e.g. derived from Workbench filters). */
  initialBankFilters?: FilterStack | null
  /** Pre-filled book filter stack. */
  initialBookFilters?: FilterStack | null
  /** Optional pre-select: explicit bank/book ids from the current selection. */
  initialBankIds?: number[]
  initialBookIds?: number[]
  /** Hint copy shown near the filter section (e.g. "Usando filtros atuais da bancada"). */
  filtersHint?: string
}

export function RunRuleDrawer({
  open,
  onClose,
  initialBankFilters = null,
  initialBookFilters = null,
  initialBankIds,
  initialBookIds,
  filtersHint,
}: RunRuleDrawerProps) {
  const start = useStartReconTask()
  const { data: configs = [] } = useReconConfigs()
  const { data: pipelines = [] } = useReconPipelines()
  const { data: columnsData } = useFilterColumns()
  const preview = usePreviewCounts()

  const bankColumns: FilterColumnDef[] = (columnsData as { bank_transaction?: FilterColumnDef[] } | undefined)?.bank_transaction ?? []
  const bookColumns: FilterColumnDef[] = (columnsData as { journal_entry?: FilterColumnDef[] } | undefined)?.journal_entry ?? []

  const [configId, setConfigId] = useState<number | "">("")
  const [pipelineId, setPipelineId] = useState<number | "">("")
  const [autoMatch, setAutoMatch] = useState(false)
  const [overrideMode, setOverrideMode] = useState<"append" | "replace" | "intersect">("replace")
  const [mergeConfigFilters, setMergeConfigFilters] = useState(true)
  const [bankStack, setBankStack] = useState<FilterStack | null>(initialBankFilters)
  const [bookStack, setBookStack] = useState<FilterStack | null>(initialBookFilters)
  const [counts, setCounts] = useState<{ bank: number | null; book: number | null }>({ bank: null, book: null })
  // Ephemeral post-run banner so users see clear confirmation inside the
  // drawer even if the sonner toast is out of view or auto-dismisses.
  const [lastStartedTaskId, setLastStartedTaskId] = useState<number | null>(null)

  // Lazy-fetch the full rule on selection so we can render its description.
  const selectedConfig = useReconConfig(typeof configId === "number" ? configId : null)
  const selectedPipeline = useReconPipeline(typeof pipelineId === "number" ? pipelineId : null)
  const selectedConfigData = selectedConfig.data
  const selectedPipelineData = selectedPipeline.data
  const configLoading = selectedConfig.isFetching && !selectedConfigData
  const pipelineLoading = selectedPipeline.isFetching && !selectedPipelineData

  // Reset when opened
  useEffect(() => {
    if (open) {
      setBankStack(initialBankFilters)
      setBookStack(initialBookFilters)
      setCounts({ bank: null, book: null })
      setLastStartedTaskId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Debounced live preview
  useEffect(() => {
    if (!open) return
    const handle = setTimeout(() => {
      preview.mutate(
        {
          bank_filters: bankStack,
          book_filters: bookStack,
          bank_ids: initialBankIds,
          book_ids: initialBookIds,
          override_mode: overrideMode,
          merge_config_filters: mergeConfigFilters,
          config_id: typeof configId === "number" ? configId : undefined,
        },
        {
          onSuccess: (r) => setCounts({ bank: r.bank.total, book: r.book.total }),
          onError: () => setCounts({ bank: null, book: null }),
        },
      )
    }, 400)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, JSON.stringify(bankStack), JSON.stringify(bookStack), configId, overrideMode, mergeConfigFilters])

  const canRun = useMemo(
    () => Boolean(configId || pipelineId),
    [configId, pipelineId],
  )

  const onRun = () => {
    if (!canRun) {
      toast.error("Selecione uma configuração ou pipeline")
      return
    }
    start.mutate(
      {
        config_id: typeof configId === "number" ? configId : undefined,
        pipeline_id: typeof pipelineId === "number" ? pipelineId : undefined,
        bank_filter_overrides: bankStack && bankStack.filters.length ? bankStack : undefined,
        book_filter_overrides: bookStack && bookStack.filters.length ? bookStack : undefined,
        bank_ids: initialBankIds && initialBankIds.length ? initialBankIds : undefined,
        book_ids: initialBookIds && initialBookIds.length ? initialBookIds : undefined,
        override_mode: overrideMode,
        merge_config_filters: mergeConfigFilters,
        auto_match_100: autoMatch,
      },
      {
        onSuccess: (task) => {
          toast.success(`Execução iniciada #${task.id}`, {
            description: "Acompanhe o progresso em Tarefas.",
            duration: 6000,
          })
          // Show an in-drawer confirmation banner and auto-close after a
          // short delay so the user definitely sees the feedback.
          setLastStartedTaskId(task.id)
          window.setTimeout(() => onClose(), 1800)
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : "Erro ao iniciar", {
            duration: 8000,
          }),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[680px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              Executar regra com filtros
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <div className="grid grid-cols-2 gap-3">
              <LabeledSelect
                label="Configuração"
                value={configId}
                onChange={(v) => { setConfigId(v); setPipelineId("") }}
                options={configs.map((c) => ({ value: c.id, label: c.name + (c.is_default ? " (padrão)" : "") }))}
              />
              <LabeledSelect
                label="Pipeline"
                value={pipelineId}
                onChange={(v) => { setPipelineId(v); setConfigId("") }}
                options={pipelines.map((p) => ({ value: p.id, label: p.name + (p.is_default ? " (padrão)" : "") }))}
              />
            </div>

            {/* Description panel: surfaces the selected rule's description so
                the operator knows exactly what will run. Falls back to a
                neutral placeholder when nothing is selected / it has no
                description. */}
            <RuleDescription
              loading={configLoading || pipelineLoading}
              name={selectedConfigData?.name ?? selectedPipelineData?.name}
              description={selectedConfigData?.description ?? selectedPipelineData?.description}
              kind={configId ? "config" : pipelineId ? "pipeline" : null}
              meta={
                selectedConfigData
                  ? [
                      `Tolerância: ${selectedConfigData.amount_tolerance}`,
                      `Confiança mín.: ${selectedConfigData.min_confidence}`,
                      `Grupo máx. (banco/contáb.): ${selectedConfigData.max_group_size_bank}/${selectedConfigData.max_group_size_book}`,
                    ]
                  : selectedPipelineData
                    ? [
                        `Etapas: ${selectedPipelineData.stages?.length ?? 0}`,
                        `Auto-apply score: ${selectedPipelineData.auto_apply_score}`,
                      ]
                    : []
              }
            />

            {filtersHint && (
              <div className="rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-[11px] text-primary">
                {filtersHint}
              </div>
            )}

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Modo de combinação</div>
                <div className="flex items-center gap-2 text-[11px]">
                  <label className="inline-flex items-center gap-1">
                    <input type="checkbox" checked={mergeConfigFilters} onChange={(e) => setMergeConfigFilters(e.target.checked)} className="accent-primary" />
                    Somar com filtros da config
                  </label>
                </div>
              </div>
              <div className="flex items-center gap-1 rounded-md border border-border bg-surface-1 p-1">
                {(["replace", "append", "intersect"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setOverrideMode(m)}
                    className={cn(
                      "h-6 flex-1 rounded-sm px-2 text-[11px] font-medium",
                      overrideMode === m ? "bg-background text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
                    )}
                    title={
                      m === "replace" ? "Usar somente os registros do filtro"
                        : m === "append" ? "Unir com ids explícitos"
                        : "Somente ids explícitos que passem pelo filtro"
                    }
                  >
                    {m === "replace" ? "Substituir" : m === "append" ? "Acumular" : "Interseção"}
                  </button>
                ))}
              </div>
            </div>

            <FilterStackBuilder
              title="Filtros de banco"
              columns={bankColumns}
              value={bankStack}
              onChange={setBankStack}
              count={counts.bank}
            />
            <FilterStackBuilder
              title="Filtros de contabilidade"
              columns={bookColumns}
              value={bookStack}
              onChange={setBookStack}
              count={counts.book}
            />

            <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
              <input type="checkbox" checked={autoMatch} onChange={(e) => setAutoMatch(e.target.checked)} className="accent-primary" />
              <span>Aplicar automaticamente matches com confiança 1.0</span>
            </label>
          </div>

          <div className="hairline flex shrink-0 flex-col gap-2 border-t p-3">
            {lastStartedTaskId != null && (
              <div className="flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-2 text-[12px] text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span className="font-medium">
                  Execução iniciada #{lastStartedTaskId}.
                </span>
                <span className="text-emerald-700/80 dark:text-emerald-300/80">
                  Acompanhe em &quot;Tarefas&quot;.
                </span>
              </div>
            )}
            {start.isPending && (
              <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-2.5 py-2 text-[12px] text-primary">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                <span>Enfileirando execução…</span>
              </div>
            )}
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] text-muted-foreground">
                {counts.bank != null && counts.book != null
                  ? `Processará ${counts.bank.toLocaleString("pt-BR")} banco × ${counts.book.toLocaleString("pt-BR")} contáb.`
                  : "Calculando preview…"}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
                >
                  Cancelar
                </button>
                <button
                  disabled={start.isPending || !canRun || lastStartedTaskId != null}
                  onClick={onRun}
                  className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {start.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  {start.isPending ? "Executando…" : "Executar"}
                </button>
              </div>
            </div>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function RuleDescription({
  loading,
  name,
  description,
  kind,
  meta,
}: {
  loading: boolean
  name?: string
  description?: string
  kind: "config" | "pipeline" | null
  meta: string[]
}) {
  if (!kind && !loading) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-2 text-[11px] text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>Selecione uma configuração ou pipeline para ver a descrição.</span>
      </div>
    )
  }
  return (
    <div className="rounded-md border border-border bg-muted/20 px-3 py-2.5 text-[12px]">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {kind === "pipeline" ? "Pipeline" : "Configuração"}
        </span>
        {loading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        {name && <span className="text-[12px] font-semibold text-foreground">{name}</span>}
      </div>
      {description ? (
        <p className="whitespace-pre-wrap text-[12px] leading-snug text-muted-foreground">
          {description}
        </p>
      ) : !loading ? (
        <p className="text-[11px] italic text-muted-foreground/70">Sem descrição cadastrada.</p>
      ) : null}
      {meta.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {meta.map((m) => (
            <span
              key={m}
              className="inline-flex items-center rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground"
            >
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function LabeledSelect<T extends number | "">({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: T
  onChange: (v: number | "") => void
  options: Array<{ value: number; label: string }>
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
        className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
      >
        <option value="">—</option>
        {options.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
      </select>
    </label>
  )
}
