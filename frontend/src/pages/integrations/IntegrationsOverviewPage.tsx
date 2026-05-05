import { Link } from "react-router-dom"
import {
  AlertTriangle, Bot, CheckCircle2, Database, FlaskConical, PauseCircle,
  PlayCircle, PlugZap, SearchCode,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  useErpApiDefinitions, useErpConnections, useErpPipelines, useErpRawRecords,
} from "@/features/integrations"
import { cn, formatDateTime } from "@/lib/utils"

export function IntegrationsOverviewPage() {
  const { data: connections = [] } = useErpConnections()
  const { data: apiDefinitions = [] } = useErpApiDefinitions({ include_inactive: true })
  const { data: pipelines = [] } = useErpPipelines()
  const { data: records } = useErpRawRecords({ page: 1, page_size: 1 })

  const activeApis = apiDefinitions.filter((api) => api.is_active).length
  const pausedPipelines = pipelines.filter((pipeline) => pipeline.is_paused).length
  const failingPipelines = pipelines.filter((pipeline) => pipeline.last_run_status === "failed").length
  const runDates = pipelines
    .map((pipeline) => pipeline.last_run_at)
    .filter(Boolean)
    .sort()
  const latestRun = runDates.length ? runDates[runDates.length - 1] : null

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard label="Conexões" value={connections.length} hint="ambientes ERP ativos" />
        <MetricCard label="APIs cadastradas" value={apiDefinitions.length} hint={`${activeApis} ativas`} />
        <MetricCard label="Automações" value={pipelines.length} hint={`${pausedPipelines} pausadas`} />
        <MetricCard label="Registros salvos" value={records?.count ?? 0} hint="linhas brutas auditáveis" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold">Fluxo recomendado</h2>
              <p className="mt-1 max-w-2xl text-[12px] text-muted-foreground">
                Comece enriquecendo o catálogo de APIs, teste a combinação no sandbox,
                salve como automação e acompanhe os registros gravados.
              </p>
            </div>
            <Button asChild size="sm">
              <Link to="/integrations/sandbox">
                <FlaskConical className="h-4 w-4" /> Montar pipeline
              </Link>
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <FlowStep
              icon={SearchCode}
              title="Descobrir"
              text="Cole uma referência da API para sugerir endpoints, filtros e paginação."
              to="/integrations/api-definitions/discover"
            />
            <FlowStep
              icon={PlugZap}
              title="Catalogar"
              text="Revise parâmetros, autenticação, paths de registros e testes por endpoint."
              to="/integrations/api-definitions"
            />
            <FlowStep
              icon={FlaskConical}
              title="Testar"
              text="Monte chamadas em sequência, faça joins e valide o preview antes de salvar."
              to="/integrations/sandbox"
            />
            <FlowStep
              icon={Bot}
              title="Automatizar"
              text="Agende pipelines ou rode sob demanda, com histórico e controle de pausa."
              to="/integrations/rotinas"
            />
          </div>
        </section>

        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h2 className="text-[15px] font-semibold">Automações cadastradas</h2>
              <p className="mt-1 text-[12px] text-muted-foreground">
                Cada automação pode ser um pipeline salvo pelo sandbox. Regras individuais
                devem entrar como pipelines de uma etapa para manter teste, agenda e auditoria no mesmo lugar.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/integrations/rotinas">Ver todas</Link>
            </Button>
          </div>

          <div className="space-y-2">
            {pipelines.slice(0, 5).map((pipeline) => (
              <Link
                key={pipeline.id}
                to="/integrations/rotinas"
                className="flex items-center justify-between gap-3 rounded-md border border-border/70 px-3 py-2 text-[12px] hover:bg-muted/30"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium">{pipeline.name}</div>
                  <div className="truncate text-[11px] text-muted-foreground">
                    {pipeline.connection_name ?? `Conexão #${pipeline.connection}`} · {pipeline.steps.length} etapa(s)
                  </div>
                </div>
                <PipelineState status={pipeline.last_run_status} paused={pipeline.is_paused} />
              </Link>
            ))}
            {pipelines.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-[12px] text-muted-foreground">
                Nenhuma automação salva ainda. Teste um pipeline no sandbox e salve quando o preview estiver correto.
              </div>
            ) : null}
          </div>

          <div className="mt-3 grid gap-2 text-[12px] md:grid-cols-3">
            <StatusPill icon={CheckCircle2} label="Último run" value={latestRun ? formatDateTime(latestRun) : "sem execução"} />
            <StatusPill icon={PauseCircle} label="Pausadas" value={String(pausedPipelines)} />
            <StatusPill icon={AlertTriangle} label="Com falha" value={String(failingPipelines)} danger={failingPipelines > 0} />
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold">Registros genéricos salvos</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Use a aba Registros para auditar payloads brutos, filtrar por API, ordenar por data,
              inspecionar JSON e exportar páginas de resultado.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to="/integrations/registros">
              <Database className="h-4 w-4" /> Abrir registros
            </Link>
          </Button>
        </div>
      </section>
    </div>
  )
}

function MetricCard({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="text-[11px] font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value.toLocaleString("pt-BR")}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>
    </div>
  )
}

function FlowStep({
  icon: Icon,
  title,
  text,
  to,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  text: string
  to: string
}) {
  return (
    <Link to={to} className="rounded-lg border border-border/70 p-3 text-[12px] hover:bg-muted/30">
      <Icon className="mb-2 h-4 w-4 text-primary" />
      <div className="font-semibold">{title}</div>
      <p className="mt-1 leading-relaxed text-muted-foreground">{text}</p>
    </Link>
  )
}

function PipelineState({ status, paused }: { status: string; paused: boolean }) {
  const failed = status === "failed"
  return (
    <span className={cn(
      "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[11px]",
      failed ? "border-destructive/30 text-destructive" : "border-border text-muted-foreground",
    )}>
      {paused ? <PauseCircle className="h-3 w-3" /> : <PlayCircle className="h-3 w-3" />}
      {paused ? "pausada" : status}
    </span>
  )
}

function StatusPill({
  icon: Icon,
  label,
  value,
  danger,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  danger?: boolean
}) {
  return (
    <div className={cn("rounded-md border border-border/70 px-3 py-2", danger && "border-destructive/30")}>
      <div className={cn("flex items-center gap-1 text-[11px] text-muted-foreground", danger && "text-destructive")}>
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="mt-1 truncate font-medium">{value}</div>
    </div>
  )
}
