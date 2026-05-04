import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  RefreshCw, Play, Pause, PlayCircle, Search, ChevronRight,
  CheckCircle2, AlertTriangle, XCircle, Clock, History,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Drawer } from "vaul"
import {
  useErpConnections, useErpPipelines, useErpPipeline, useUpdateErpPipeline,
  usePauseErpPipeline, useResumeErpPipeline, useRunPipelineNow,
  useErpPipelineHistory,
} from "@/features/integrations"
import type {
  ERPSyncPipeline, IncrementalConfig, PipelineLastRunStatus,
  PipelineRunHistoryRow,
} from "@/features/integrations"
import { cn, formatDateTime } from "@/lib/utils"
import { useUserRole } from "@/features/auth/useUserRole"

const RUN_STATUS_TONE: Record<PipelineLastRunStatus, string> = {
  never: "text-muted-foreground",
  completed: "text-success",
  failed: "text-destructive",
  partial: "text-warning",
  running: "text-info",
}

const RUN_STATUS_ICON = {
  never: Clock,
  completed: CheckCircle2,
  failed: XCircle,
  partial: AlertTriangle,
  running: RefreshCw,
} as const

/**
 * Phase-4 da Sandbox API: rotinas agendadas.
 *
 * Lista de pipelines (uma rotina = um ERPSyncPipeline) com:
 *   - estado de saúde (último run, status, contagem de registros)
 *   - botões de Pausar/Retomar e "Rodar agora"
 *   - drawer de detalhes com 3 abas (Agendamento, Incremental, Histórico).
 *
 * Pipelines são criados via Sandbox + Save — esta tela é a operação,
 * não a criação.
 */
export function PipelineRoutinesPage() {
  const { canWrite } = useUserRole()
  const [search, setSearch] = useState("")
  const [connectionFilter, setConnectionFilter] = useState<string>("all")
  const [openId, setOpenId] = useState<number | null>(null)

  const { data: connections = [] } = useErpConnections()
  const { data: pipelines = [], isLoading, isFetching, refetch } = useErpPipelines({
    connection: connectionFilter === "all" ? undefined : Number(connectionFilter),
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return pipelines
    return pipelines.filter((p) =>
      [p.name, p.description, p.connection_name].filter(Boolean).some((s) => s!.toLowerCase().includes(q)),
    )
  }, [pipelines, search])

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Rotinas de importação"
        subtitle="Pipelines que rodam em agenda. Crie/edite no Sandbox; aqui se agenda, pausa e replica."
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Atualizar
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="relative min-w-[260px] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar nome, descrição…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Conexão
          </span>
          <Select value={connectionFilter} onValueChange={setConnectionFilter}>
            <SelectTrigger className="h-9 w-[220px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              {connections.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name ?? `Connection #${c.id}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-border bg-card">
        <table className="w-full text-[12px]">
          <thead className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Pipeline</th>
              <th className="px-3 py-2">Conexão</th>
              <th className="px-3 py-2">Agendamento</th>
              <th className="px-3 py-2">Último run</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">Carregando…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">Nenhuma rotina encontrada.</td></tr>
            ) : (
              filtered.map((p) => (
                <PipelineRow
                  key={p.id}
                  pipeline={p}
                  canWrite={canWrite}
                  onOpen={() => setOpenId(p.id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Detail drawer */}
      <PipelineDrawer
        pipelineId={openId}
        onClose={() => setOpenId(null)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------
function PipelineRow({
  pipeline, canWrite, onOpen,
}: {
  pipeline: ERPSyncPipeline
  canWrite: boolean
  onOpen: () => void
}) {
  const pause = usePauseErpPipeline()
  const resume = useResumeErpPipeline()
  const runNow = useRunPipelineNow()
  const Icon = RUN_STATUS_ICON[pipeline.last_run_status]

  const onTogglePause = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (pipeline.is_paused) {
      resume.mutate(pipeline.id, {
        onSuccess: () => toast.success(`${pipeline.name} retomado`),
      })
    } else {
      pause.mutate(pipeline.id, {
        onSuccess: () => toast.success(`${pipeline.name} pausado`),
      })
    }
  }

  const onRunNow = (e: React.MouseEvent) => {
    e.stopPropagation()
    runNow.mutate(
      { id: pipeline.id, body: {} },
      {
        onSuccess: (out) => {
          if (out.status === "ran") toast.success(`Rodou — ${out.detail}`)
          else if (out.status === "locked") toast.warning("Outra execução em andamento.")
          else if (out.status === "paused") toast.warning("Pipeline pausado.")
          else if (out.status === "disabled") toast.warning("Pipeline inativo.")
          else if (out.status === "error") toast.error(`Erro: ${out.detail}`)
          else toast.warning(`Status: ${out.status}`)
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <tr
      className={cn(
        "cursor-pointer border-b border-border/40 last:border-b-0 hover:bg-muted/30",
        pipeline.is_paused && "opacity-60",
        !pipeline.is_active && "line-through opacity-50",
      )}
      onClick={onOpen}
    >
      <td className="px-3 py-2">
        <div className="font-medium">{pipeline.name}</div>
        {pipeline.description ? (
          <div className="text-[11px] text-muted-foreground truncate" title={pipeline.description}>
            {pipeline.description}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-2 text-muted-foreground">{pipeline.connection_name ?? `#${pipeline.connection}`}</td>
      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
        {pipeline.schedule_rrule ? pipeline.schedule_rrule : <span className="italic">sem agenda</span>}
      </td>
      <td className="px-3 py-2 text-muted-foreground text-[11px]">
        {pipeline.last_run_at ? formatDateTime(pipeline.last_run_at) : "—"}
        {pipeline.last_run_record_count ? (
          <span className="ml-1 text-[10px]">· {pipeline.last_run_record_count} reg</span>
        ) : null}
      </td>
      <td className="px-3 py-2">
        <span className={cn("inline-flex items-center gap-1 text-[11px]", RUN_STATUS_TONE[pipeline.last_run_status])}>
          <Icon className="h-3 w-3" />
          {pipeline.last_run_status}
          {pipeline.is_paused ? <span className="ml-1 rounded bg-warning/15 px-1 py-0.5 text-[9px] text-warning">PAUSADO</span> : null}
        </span>
      </td>
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end gap-1">
          {canWrite ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                title={pipeline.is_paused ? "Retomar" : "Pausar"}
                onClick={onTogglePause}
                disabled={pause.isPending || resume.isPending}
              >
                {pipeline.is_paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="Rodar agora"
                onClick={onRunNow}
                disabled={runNow.isPending}
              >
                <PlayCircle className={cn("h-3.5 w-3.5", runNow.isPending && "animate-pulse")} />
              </Button>
            </>
          ) : null}
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------
// Drawer (detail)
// ---------------------------------------------------------------------
function PipelineDrawer({
  pipelineId, onClose,
}: {
  pipelineId: number | null
  onClose: () => void
}) {
  const open = pipelineId != null
  const { data: pipeline } = useErpPipeline(pipelineId)
  const update = useUpdateErpPipeline()
  const runNow = useRunPipelineNow()
  const [tab, setTab] = useState<"schedule" | "incremental" | "history">("schedule")

  const [schedule, setSchedule] = useState("")
  const [incremental, setIncremental] = useState<IncrementalConfig>({})

  useEffect(() => {
    if (pipeline) {
      setSchedule(pipeline.schedule_rrule ?? "")
      setIncremental(pipeline.incremental_config ?? {})
    }
  }, [pipeline?.id, pipeline?.schedule_rrule, pipeline?.incremental_config])  // eslint-disable-line react-hooks/exhaustive-deps

  const onSave = () => {
    if (!pipelineId) return
    update.mutate(
      {
        id: pipelineId,
        body: {
          schedule_rrule: schedule || null,
          incremental_config: Object.keys(incremental).length ? incremental : null,
        } as Partial<ERPSyncPipeline>,
      },
      {
        onSuccess: () => toast.success("Rotina salva."),
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root
      open={open}
      onOpenChange={(o) => { if (!o) onClose() }}
      direction="right"
    >
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Drawer.Content
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-border bg-background shadow-xl outline-none"
          aria-describedby={undefined}
        >
          <Drawer.Title className="sr-only">Detalhes da rotina</Drawer.Title>
          <header className="flex items-center justify-between border-b border-border px-5 py-3">
            <div>
              <h2 className="text-[14px] font-semibold">{pipeline?.name ?? "—"}</h2>
              <p className="text-[11px] text-muted-foreground">
                {pipeline?.connection_name} · {pipeline?.steps.length ?? 0} passo(s)
              </p>
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">×</button>
          </header>

          <div className="flex items-center gap-1 border-b border-border bg-muted/20 px-3">
            {(["schedule", "incremental", "history"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "border-b-2 py-2 px-3 text-[12px] font-medium transition-colors",
                  tab === t
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t === "schedule" ? "Agendamento" : t === "incremental" ? "Incremental" : "Histórico"}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-5">
            {!pipeline ? (
              <p className="text-muted-foreground text-[12px]">Carregando…</p>
            ) : tab === "schedule" ? (
              <ScheduleTab
                schedule={schedule}
                setSchedule={setSchedule}
                pipeline={pipeline}
                onSave={onSave}
                saving={update.isPending}
                onRunNow={(force) => {
                  runNow.mutate(
                    { id: pipeline.id, body: { force_full_dump: force } },
                    {
                      onSuccess: (out) => toast.success(`${out.status} — ${out.detail}`),
                      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
                    },
                  )
                }}
                runNowPending={runNow.isPending}
              />
            ) : tab === "incremental" ? (
              <IncrementalTab
                config={incremental}
                setConfig={setIncremental}
                pipeline={pipeline}
                onSave={onSave}
                saving={update.isPending}
              />
            ) : (
              <HistoryTab pipelineId={pipeline.id} />
            )}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

// ---------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------
function ScheduleTab({
  schedule, setSchedule, pipeline, onSave, saving, onRunNow, runNowPending,
}: {
  schedule: string
  setSchedule: (s: string) => void
  pipeline: ERPSyncPipeline
  onSave: () => void
  saving: boolean
  onRunNow: (force: boolean) => void
  runNowPending: boolean
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label className="text-[10px] font-bold uppercase text-muted-foreground">RRULE (iCal)</label>
        <Input
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
          placeholder="FREQ=HOURLY;INTERVAL=4"
        />
        <p className="text-[11px] text-muted-foreground">
          Em branco = sem agenda. Exemplos:
          {" "}<code>FREQ=HOURLY;INTERVAL=4</code> · <code>FREQ=DAILY;BYHOUR=2</code> ·
          {" "}<code>FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8</code>.
        </p>
      </div>

      <div className="rounded-md border border-border bg-muted/20 p-3 text-[11px] space-y-1">
        <div><span className="text-muted-foreground">Pausada:</span> {pipeline.is_paused ? "sim" : "não"}</div>
        <div><span className="text-muted-foreground">Ativa:</span> {pipeline.is_active ? "sim" : "não"}</div>
        <div><span className="text-muted-foreground">Último run:</span> {pipeline.last_run_at ? formatDateTime(pipeline.last_run_at) : "—"}</div>
        <div><span className="text-muted-foreground">High-watermark:</span> {pipeline.last_high_watermark ? formatDateTime(pipeline.last_high_watermark) : "—"}</div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onSave} disabled={saving}>
          {saving ? "Salvando…" : "Salvar agendamento"}
        </Button>
        <Button variant="outline" onClick={() => onRunNow(false)} disabled={runNowPending}>
          <PlayCircle className="h-4 w-4" /> Rodar agora
        </Button>
        <Button variant="outline" onClick={() => onRunNow(true)} disabled={runNowPending}>
          Rodar full-dump
        </Button>
      </div>
    </div>
  )
}

function IncrementalTab({
  config, setConfig, pipeline, onSave, saving,
}: {
  config: IncrementalConfig
  setConfig: (c: IncrementalConfig) => void
  pipeline: ERPSyncPipeline
  onSave: () => void
  saving: boolean
}) {
  const set = (patch: Partial<IncrementalConfig>) => setConfig({ ...config, ...patch })

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-muted-foreground">
        Quando configurado, o scheduler injeta um filtro do tipo
        <code className="mx-1 rounded bg-muted px-1 font-mono">{`{param_name} = (last_high_watermark - lookback)`}</code>
        no <strong>primeiro passo</strong> da rotina, evitando trazer todos
        os registros a cada disparo.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase text-muted-foreground">Campo da resposta (informativo)</label>
          <Input value={config.field ?? ""} onChange={(e) => set({ field: e.target.value })} placeholder="data_alteracao" />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase text-muted-foreground">Operador</label>
          <Select value={config.operator ?? ">="} onValueChange={(v) => set({ operator: v as ">=" | ">" })}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value=">=">{">="}</SelectItem>
              <SelectItem value=">">{">"}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase text-muted-foreground">Nome do param (request)</label>
          <Input value={config.param_name ?? ""} onChange={(e) => set({ param_name: e.target.value })} placeholder="filtrar_por_alteracao_de" />
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase text-muted-foreground">Formato</label>
          <Select value={config.format ?? "iso8601"} onValueChange={(v) => set({ format: v as IncrementalConfig["format"] })}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="iso8601">ISO 8601</SelectItem>
              <SelectItem value="br_date">BR date (dd/mm/yyyy)</SelectItem>
              <SelectItem value="br_datetime">BR datetime (dd/mm/yyyy HH:mm:ss)</SelectItem>
              <SelectItem value="epoch_seconds">Epoch seconds</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase text-muted-foreground">Lookback (segundos)</label>
          <Input
            type="number"
            value={config.lookback_seconds ?? 300}
            onChange={(e) => set({ lookback_seconds: Number(e.target.value) || 0 })}
          />
        </div>
      </div>

      <div className="rounded-md border border-info/30 bg-info/5 p-3 text-[11px]">
        <div className="font-semibold mb-1">Próximo run vai usar:</div>
        <code className="font-mono">
          {config.param_name && pipeline.last_high_watermark
            ? `${config.param_name} ${config.operator ?? ">="} ${pipeline.last_high_watermark}`
            : pipeline.last_high_watermark
              ? "(sem param_name configurado)"
              : "(sem high-watermark — rodará full-dump na primeira vez)"}
        </code>
      </div>

      <Button onClick={onSave} disabled={saving}>
        {saving ? "Salvando…" : "Salvar incremental"}
      </Button>
    </div>
  )
}

function HistoryTab({ pipelineId }: { pipelineId: number }) {
  const { data: history = [], isLoading, refetch, isFetching } = useErpPipelineHistory(pipelineId)
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">{history.length} run(s) recentes</span>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Atualizar
        </Button>
      </div>
      {isLoading ? (
        <p className="text-muted-foreground text-[12px]">Carregando…</p>
      ) : history.length === 0 ? (
        <p className="text-muted-foreground text-[12px] text-center py-6">Sem runs registrados.</p>
      ) : (
        <div className="space-y-2">
          {history.map((r) => <RunHistoryRow key={r.id} run={r} />)}
        </div>
      )}
    </div>
  )
}

function RunHistoryRow({ run }: { run: PipelineRunHistoryRow }) {
  const tone =
    run.status === "completed" ? "border-success/40" :
    run.status === "failed" ? "border-destructive/40" :
    run.status === "partial" ? "border-warning/40" :
    "border-border"
  return (
    <div className={cn("rounded-md border p-2 text-[11px]", tone)}>
      <div className="flex items-center gap-2">
        <span className="font-mono">#{run.id}</span>
        <span className="font-semibold uppercase">{run.status}</span>
        <span className="text-muted-foreground">via {run.triggered_by}</span>
        {run.duration_seconds != null ? (
          <span className="text-muted-foreground">· {run.duration_seconds.toFixed(1)}s</span>
        ) : null}
        <span className="ml-auto text-muted-foreground">
          {run.started_at ? formatDateTime(run.started_at) : "—"}
        </span>
      </div>
      <div className="mt-1 text-muted-foreground">
        {run.records_extracted} extraídos · {run.records_stored} armazenados ·
        {" "}{run.records_updated} atualizados · {run.records_skipped} ignorados
      </div>
      {run.incremental_window_start || run.incremental_window_end ? (
        <div className="mt-1 text-muted-foreground">
          <History className="inline h-3 w-3 mr-1" />
          janela: {run.incremental_window_start ?? "∞"} → {run.incremental_window_end ?? "∞"}
        </div>
      ) : null}
      {run.errors && run.errors.length > 0 ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-destructive">{run.errors.length} erro(s)</summary>
          <ul className="mt-1 ml-4 list-disc text-destructive/80">
            {run.errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </details>
      ) : null}
    </div>
  )
}
