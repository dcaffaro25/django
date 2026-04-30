import { useState } from "react"
import {
  AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Info, Undo2,
} from "lucide-react"
import {
  useAcknowledgeCritic, useInvoiceCritics, useUnacknowledgeCritic,
} from "@/features/billing"
import type { Critic, CriticSeverity } from "@/features/billing"
import { Button } from "@/components/ui/button"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn } from "@/lib/utils"

const SEVERITY_TONE: Record<CriticSeverity, { cls: string; icon: typeof Info }> = {
  error: { cls: "bg-danger/10 text-danger border-danger/30", icon: AlertCircle },
  warning: { cls: "bg-warning/10 text-warning border-warning/30", icon: AlertTriangle },
  info: { cls: "bg-info/10 text-info border-info/20", icon: Info },
}

const KIND_LABEL: Record<string, string> = {
  over_returned: "Devolução total excedida",
  quantity_over_returned: "Quantidade devolvida > vendida",
  unit_price_drift: "Preço unitário diferente",
  bundle_expansion_suspected: "Bundle expandido (caixa→unidade)",
  ncm_drift: "NCM divergente",
  produto_unresolved: "Produto não cadastrado",
}

function CriticRow({ critic, invoiceId }: { critic: Critic; invoiceId: number }) {
  const [open, setOpen] = useState(false)
  const tone = SEVERITY_TONE[critic.severity]
  const Icon = tone.icon
  const evidenceKeys = Object.keys(critic.evidence)
  const ack = useAcknowledgeCritic()
  const unack = useUnacknowledgeCritic()
  const { canWrite } = useUserRole()
  const isAck = !!critic.acknowledged
  return (
    <li className={cn(
      "rounded-md border p-2",
      isAck ? "bg-muted text-muted-foreground border-muted-foreground/20 opacity-75" : tone.cls,
    )}>
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => evidenceKeys.length && setOpen((v) => !v)}
          className={cn(
            "flex flex-1 items-start gap-2 text-left min-w-0",
            evidenceKeys.length ? "cursor-pointer" : "cursor-default",
          )}
        >
          <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80">
                {KIND_LABEL[critic.kind] ?? critic.kind}
              </span>
              {isAck ? (
                <span className="inline-flex items-center gap-0.5 rounded-full bg-success/15 px-1.5 py-0.5 text-[10px] font-semibold text-success">
                  <Check className="h-2.5 w-2.5" />
                  aceito
                </span>
              ) : null}
            </div>
            <div className="text-[12px] leading-snug">{critic.message}</div>
            {isAck && critic.acknowledged_by_email ? (
              <div className="mt-0.5 text-[10px]">
                por {critic.acknowledged_by_email}
                {critic.acknowledged_note ? ` — “${critic.acknowledged_note}”` : ""}
              </div>
            ) : null}
          </div>
          {evidenceKeys.length ? (
            open ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          ) : null}
        </button>
        {canWrite ? (
          isAck ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => unack.mutate({
                invoiceId,
                kind: critic.kind,
                subject_type: critic.subject_type,
                subject_id: critic.subject_id,
              })}
              disabled={unack.isPending}
              title="Remover aceite"
              className="h-7 shrink-0 px-2"
            >
              <Undo2 className="h-3 w-3" />
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                const note = prompt("Observação (opcional):") || ""
                ack.mutate({
                  invoiceId,
                  kind: critic.kind,
                  subject_type: critic.subject_type,
                  subject_id: critic.subject_id,
                  note,
                })
              }}
              disabled={ack.isPending}
              title="Aceitar — marcar esta crítica como esperada"
              className="h-7 shrink-0 px-2"
            >
              <Check className="h-3 w-3" />
            </Button>
          )
        ) : null}
      </div>
      {open && evidenceKeys.length ? (
        <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 rounded bg-background/50 p-2 text-[11px] font-mono">
          {evidenceKeys.map((k) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="break-all">{JSON.stringify(critic.evidence[k])}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  )
}

/**
 * "Críticas" panel for the InvoiceDetailDrawer.
 *
 * Shows the live critic list grouped by severity (errors → warnings →
 * info). Each row is collapsible to inspect evidence (e.g. the actual
 * unit prices that diverged).
 *
 * Returns null while loading (keeps the drawer compact); renders an
 * "OK" pill when the count is zero so the operator gets explicit
 * confirmation.
 */
export function CriticsPanel({ invoiceId }: { invoiceId: number }) {
  const { data, isLoading, isError } = useInvoiceCritics(invoiceId)

  if (isLoading) return null
  if (isError) {
    return (
      <div className="rounded-md border border-danger/30 bg-danger/10 p-2 text-[12px] text-danger">
        Falha ao carregar críticas.
      </div>
    )
  }
  if (!data) return null

  if (data.count === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-[12px] text-success">
        <Info className="h-3.5 w-3.5" />
        <span>Nenhuma crítica detectada — venda e devoluções coerentes.</span>
      </div>
    )
  }

  const { error: errCount, warning: warnCount, info: infoCount } = data.by_severity
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
        <AlertTriangle className="h-3.5 w-3.5" />
        Críticas
        <span className="flex items-center gap-1">
          {errCount > 0 ? (
            <span className="rounded-full bg-danger/15 px-1.5 py-0.5 text-[10px] font-bold text-danger">
              {errCount} erro
            </span>
          ) : null}
          {warnCount > 0 ? (
            <span className="rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-bold text-warning">
              {warnCount} alerta
            </span>
          ) : null}
          {infoCount > 0 ? (
            <span className="rounded-full bg-info/15 px-1.5 py-0.5 text-[10px] font-bold text-info">
              {infoCount} info
            </span>
          ) : null}
        </span>
      </h4>
      <ul className="space-y-1.5">
        {data.items.map((c, i) => (
          <CriticRow key={`${c.kind}-${c.subject_id}-${i}`} critic={c} invoiceId={invoiceId} />
        ))}
      </ul>
    </section>
  )
}

/** Small inline indicator for the drawer header — count of error+warning
 *  critics. Renders nothing when zero. */
export function CriticsBadge({ invoiceId }: { invoiceId: number }) {
  const { data } = useInvoiceCritics(invoiceId)
  if (!data) return null
  const high = data.by_severity.error + data.by_severity.warning
  if (high === 0) return null
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        data.by_severity.error > 0
          ? "bg-danger/10 text-danger border-danger/30"
          : "bg-warning/10 text-warning border-warning/30",
      )}
      title={`${data.by_severity.error} erro(s), ${data.by_severity.warning} alerta(s)`}
    >
      <AlertTriangle className="h-3 w-3" />
      {high} crítica{high === 1 ? "" : "s"}
    </span>
  )
}
