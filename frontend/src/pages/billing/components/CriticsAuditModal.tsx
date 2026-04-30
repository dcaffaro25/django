import { useState } from "react"
import { Sparkles, AlertCircle, AlertTriangle, Info, ExternalLink } from "lucide-react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { useAuditCritics } from "@/features/billing"
import type { CriticAuditResponse } from "@/features/billing"
import { cn, formatCurrency } from "@/lib/utils"

const KIND_LABEL: Record<string, string> = {
  over_returned: "Devolução total excedida",
  quantity_over_returned: "Qtd devolvida > vendida",
  unit_price_drift: "Preço unitário diferente",
  bundle_expansion_suspected: "Bundle expandido",
  ncm_drift: "NCM divergente",
  produto_unresolved: "Produto não cadastrado",
}

/**
 * Bulk audit modal — runs the same critics_service.audit_critics_for_company
 * pass that the management command does, but from the UI. The user can
 * narrow scope (severity filter, only-unacknowledged) before running and
 * then drill through to the affected Invoices.
 *
 * Persists ``Invoice.critics_count`` so the list view filter stays accurate.
 */
export function CriticsAuditModal({
  open,
  onClose,
  onJumpToInvoice,
}: {
  open: boolean
  onClose: () => void
  onJumpToInvoice?: (invoiceId: number) => void
}) {
  const [onlyUnack, setOnlyUnack] = useState(true)
  const [withErrors, setWithErrors] = useState(true)
  const [withWarnings, setWithWarnings] = useState(true)
  const [withInfo, setWithInfo] = useState(false)
  const [persist, setPersist] = useState(true)
  const [result, setResult] = useState<CriticAuditResponse | null>(null)
  const audit = useAuditCritics()

  const run = async () => {
    const severity_in: ("error" | "warning" | "info")[] = []
    if (withErrors) severity_in.push("error")
    if (withWarnings) severity_in.push("warning")
    if (withInfo) severity_in.push("info")
    const res = await audit.mutateAsync({
      severity_in: severity_in.length ? severity_in : undefined,
      only_unacknowledged: onlyUnack,
      persist,
    })
    setResult(res)
  }

  const reset = () => {
    setResult(null)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Auditoria de Críticas
          </DialogTitle>
        </DialogHeader>

        {!result ? (
          <div className="space-y-3 py-2">
            <p className="text-[12px] text-muted-foreground">
              Roda o motor de críticas em todas as faturas do tenant e atualiza
              o contador denormalizado em <code>Invoice.critics_count</code>.
              Mesma lógica do <code>python manage.py audit_invoice_critics</code>.
            </p>
            <div className="grid gap-2 rounded-md border border-border bg-muted/30 p-3">
              <label className="flex items-center gap-2 text-[13px]">
                <Checkbox
                  checked={onlyUnack}
                  onCheckedChange={(v) => setOnlyUnack(!!v)}
                />
                Apenas críticas não aceitas
              </label>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Severidades a incluir nos itens
              </div>
              <div className="flex flex-wrap gap-3">
                <label className="flex items-center gap-1.5 text-[12px]">
                  <Checkbox checked={withErrors} onCheckedChange={(v) => setWithErrors(!!v)} />
                  <AlertCircle className="h-3 w-3 text-danger" /> Erros
                </label>
                <label className="flex items-center gap-1.5 text-[12px]">
                  <Checkbox checked={withWarnings} onCheckedChange={(v) => setWithWarnings(!!v)} />
                  <AlertTriangle className="h-3 w-3 text-warning" /> Alertas
                </label>
                <label className="flex items-center gap-1.5 text-[12px]">
                  <Checkbox checked={withInfo} onCheckedChange={(v) => setWithInfo(!!v)} />
                  <Info className="h-3 w-3 text-info" /> Informativos
                </label>
              </div>
              <label className="flex items-center gap-2 text-[13px]">
                <Checkbox checked={persist} onCheckedChange={(v) => setPersist(!!v)} />
                Persistir contador em <code>Invoice.critics_count</code>
              </label>
            </div>
          </div>
        ) : (
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
              <SummaryStat label="Faturas analisadas" value={result.swept} />
              <SummaryStat label="Com críticas" value={result.invoices_with_critics_count} />
              <SummaryStat label="Erros" value={result.by_severity.error ?? 0} tone="danger" />
              <SummaryStat label="Alertas" value={result.by_severity.warning ?? 0} tone="warning" />
            </div>
            {Object.keys(result.by_kind).length ? (
              <div className="rounded-md border border-border bg-muted/20 p-2 text-[11px]">
                <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">
                  Por tipo
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(result.by_kind).map(([kind, n]) => (
                    <span
                      key={kind}
                      className="inline-flex items-center gap-1 rounded-full bg-background px-2 py-0.5"
                    >
                      <span className="text-muted-foreground">{KIND_LABEL[kind] ?? kind}</span>
                      <span className="font-mono font-semibold tabular-nums">{n}</span>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="max-h-[320px] overflow-auto rounded-md border border-border">
              {result.results.length === 0 ? (
                <p className="p-4 text-center text-[12px] text-muted-foreground">
                  Nenhuma fatura com críticas encontrada com os filtros atuais.
                </p>
              ) : (
                <ul>
                  {result.results.map((row) => (
                    <li
                      key={row.invoice_id}
                      className="flex items-center justify-between gap-2 border-b border-border/40 px-3 py-2 text-[12px] last:border-b-0"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-medium">{row.invoice_number}</span>
                          <span className="font-medium tabular-nums">
                            {formatCurrency(row.total_amount)}
                          </span>
                          <span className="text-muted-foreground">{row.fiscal_status}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        {row.by_severity.error ? (
                          <span className="rounded-full bg-danger/15 px-1.5 py-0.5 text-[10px] font-bold text-danger">
                            {row.by_severity.error} err
                          </span>
                        ) : null}
                        {row.by_severity.warning ? (
                          <span className="rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-bold text-warning">
                            {row.by_severity.warning} alerta
                          </span>
                        ) : null}
                        {row.by_severity.info ? (
                          <span className="rounded-full bg-info/15 px-1.5 py-0.5 text-[10px] font-bold text-info">
                            {row.by_severity.info} info
                          </span>
                        ) : null}
                        {onJumpToInvoice ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              onJumpToInvoice(row.invoice_id)
                              reset()
                            }}
                            title="Abrir fatura"
                            className="h-7 px-2"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </Button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          {!result ? (
            <>
              <Button variant="outline" onClick={reset}>Cancelar</Button>
              <Button onClick={run} disabled={audit.isPending}>
                {audit.isPending ? "Auditando…" : "Rodar auditoria"}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setResult(null)}>
                Nova auditoria
              </Button>
              <Button onClick={reset}>Fechar</Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SummaryStat({
  label, value, tone = "default",
}: {
  label: string; value: number; tone?: "default" | "danger" | "warning"
}) {
  return (
    <div className={cn(
      "rounded-md border border-border bg-card p-2",
      tone === "danger" && value > 0 && "border-danger/30 bg-danger/5",
      tone === "warning" && value > 0 && "border-warning/30 bg-warning/5",
    )}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn(
        "text-lg font-semibold tabular-nums",
        tone === "danger" && value > 0 && "text-danger",
        tone === "warning" && value > 0 && "text-warning",
      )}>{value}</div>
    </div>
  )
}
