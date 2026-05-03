import { useNavigate } from "react-router-dom"
import {
  RefreshCw, AlertTriangle, AlertCircle, CheckCircle2,
  ArrowRight, ChevronRight, Activity,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { useHealthChecks } from "@/features/billing"
import type { HealthCheck, HealthCheckSeverity } from "@/features/billing"
import { cn, formatCurrency, formatDateTime } from "@/lib/utils"

/**
 * Operations / data-health dashboard. Surfaces the pipeline-gap
 * checks ``billing.services.health_check_service`` registers --
 * each card is one check (count, oldest example, sample, CTA).
 *
 * Intended as the "what's broken in our plumbing" hub: every report
 * we build can spawn a check here when it surfaces a "should-auto-
 * update but isn't" signal. The reports answer "what's the state?";
 * this answers "what's broken in the pipelines that produce it?"
 *
 * V1 ships three checks:
 *  1. unposted_transactions    -- Tx.is_posted=False
 *  2. stale_invoice_status     -- Invoice.status not derived from recon
 *  3. unmatched_nfs            -- NFs with no accepted Tx link >30d
 *
 * Adding more is a backend-only change: register a new check function
 * in ``ALL_CHECKS`` and it shows up here without UI changes.
 */
const SEVERITY_TONE: Record<HealthCheckSeverity, string> = {
  info: "border-success/30 bg-success/5",
  warning: "border-warning/40 bg-warning/5",
  danger: "border-destructive/40 bg-destructive/5",
}

const SEVERITY_ICON: Record<HealthCheckSeverity, typeof AlertTriangle> = {
  info: CheckCircle2,
  warning: AlertCircle,
  danger: AlertTriangle,
}

const SEVERITY_ICON_TONE: Record<HealthCheckSeverity, string> = {
  info: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
}

const SEVERITY_LABEL: Record<HealthCheckSeverity, string> = {
  info: "OK",
  warning: "Atenção",
  danger: "Urgente",
}

function ageInDays(iso: string | null): number | null {
  if (!iso) return null
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return null
  const days = Math.floor((Date.now() - d) / 86_400_000)
  return Math.max(0, days)
}

function HealthCard({ check, onCta }: { check: HealthCheck; onCta: (c: HealthCheck) => void }) {
  const Icon = SEVERITY_ICON[check.severity]
  const oldestDays = ageInDays(check.oldest_at)
  return (
    <div
      className={cn(
        "card-elevated flex h-full flex-col rounded-lg border p-4",
        SEVERITY_TONE[check.severity],
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", SEVERITY_ICON_TONE[check.severity])} />
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold leading-tight">{check.title}</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">{check.hint}</div>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider",
            check.severity === "danger" && "bg-destructive/15 text-destructive",
            check.severity === "warning" && "bg-warning/15 text-warning",
            check.severity === "info" && "bg-success/15 text-success",
          )}
        >
          {SEVERITY_LABEL[check.severity]}
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className={cn(
          "text-3xl font-bold tabular-nums",
          check.count > 0 ? "text-foreground" : "text-muted-foreground",
        )}>
          {check.count.toLocaleString("pt-BR")}
        </span>
        {check.amount ? (
          <span className="text-[12px] text-muted-foreground tabular-nums">
            {formatCurrency(Number(check.amount))}
          </span>
        ) : null}
      </div>

      {oldestDays != null && check.count > 0 ? (
        <div className="mt-1 text-[11px] text-muted-foreground">
          Mais antigo:{" "}
          <span className={cn(
            "font-medium",
            oldestDays >= 60 && "text-destructive",
            oldestDays >= 30 && oldestDays < 60 && "text-warning",
          )}>
            {oldestDays} dias atrás
          </span>{" "}
          ({check.oldest_at?.slice(0, 10)})
        </div>
      ) : null}

      {check.sample.length > 0 ? (
        <div className="mt-3 max-h-28 overflow-y-auto rounded-md border border-border/40 bg-background/40 p-2 text-[11px]">
          {check.sample.slice(0, 3).map((s, i) => {
            // Each check returns a different sample shape; render a
            // small key/value summary skipping null fields.
            const entries = Object.entries(s)
              .filter(([k, v]) => v != null && k !== "id")
              .slice(0, 4)
            return (
              <div key={i} className="flex items-center gap-1.5 truncate text-muted-foreground">
                <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                {entries.map(([k, v]) => (
                  <span key={k} className="truncate">
                    <span className="text-muted-foreground/60">{k}:</span>{" "}
                    <span className="text-foreground">
                      {typeof v === "number" ? v.toLocaleString("pt-BR") : String(v).slice(0, 40)}
                    </span>
                  </span>
                ))}
              </div>
            )
          })}
        </div>
      ) : null}

      {check.notes ? (
        <div className="mt-2 text-[10px] italic text-muted-foreground/80">
          {check.notes}
        </div>
      ) : null}

      {check.cta_label && (check.cta_url || check.cta_action) ? (
        <div className="mt-3 flex justify-end">
          <Button size="sm" variant="outline" onClick={() => onCta(check)}>
            {check.cta_label}
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>
      ) : (
        <div className="mt-3 flex-1" />
      )}
    </div>
  )
}

export function DataHealthPage() {
  const navigate = useNavigate()
  const { data, isLoading, isFetching, refetch } = useHealthChecks()

  const onCta = (check: HealthCheck) => {
    if (check.cta_url) {
      navigate(check.cta_url)
    }
    // Future: dispatch by ``cta_action`` for inline modals (e.g.
    // open the backfill modal instead of navigating).
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Saúde dos Dados"
        subtitle="Pipelines que deveriam atualizar automaticamente. Cada card é um check independente; severidade danger merece atenção, info significa que o pipeline está acompanhando."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            Atualizar
          </Button>
        }
      />

      {isLoading ? (
        <div className="rounded-md border border-border bg-card p-12 text-center text-muted-foreground">
          Carregando checks…
        </div>
      ) : !data ? (
        <div className="rounded-md border border-border bg-card p-8 text-center text-muted-foreground">
          Não foi possível carregar os checks.
        </div>
      ) : (
        <>
          {/* Headline strip */}
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card px-4 py-3">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <span className="text-[13px] font-medium">
              {data.n_checks} {data.n_checks === 1 ? "check" : "checks"}
            </span>
            <span className="text-muted-foreground">·</span>
            <div className="flex items-center gap-2 text-[12px]">
              {data.by_severity.danger > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 font-medium text-destructive">
                  <AlertTriangle className="h-3 w-3" />
                  {data.by_severity.danger} urgente{data.by_severity.danger !== 1 ? "s" : ""}
                </span>
              ) : null}
              {data.by_severity.warning > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 font-medium text-warning">
                  <AlertCircle className="h-3 w-3" />
                  {data.by_severity.warning} atenção
                </span>
              ) : null}
              {data.by_severity.info > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 font-medium text-success">
                  <CheckCircle2 className="h-3 w-3" />
                  {data.by_severity.info} ok
                </span>
              ) : null}
            </div>
            <span className="ml-auto text-[11px] text-muted-foreground">
              Atualizado: {formatDateTime(data.as_of)}
            </span>
          </div>

          {/* Cards grid -- danger first, then warning, then info */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {[...data.checks]
              .sort((a, b) => {
                const order: Record<HealthCheckSeverity, number> = {
                  danger: 0, warning: 1, info: 2,
                }
                return order[a.severity] - order[b.severity]
              })
              .map((c) => (
                <HealthCard key={c.key} check={c} onCta={onCta} />
              ))}
          </div>

          <p className="text-[10px] text-muted-foreground">
            Para adicionar um novo check, registre uma função em
            <code className="ml-1 rounded bg-muted px-1">
              billing/services/health_check_service.py:ALL_CHECKS
            </code>
            . O dashboard se atualiza automaticamente.
          </p>
        </>
      )}
    </div>
  )
}
