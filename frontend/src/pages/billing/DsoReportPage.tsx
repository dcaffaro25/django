import { useMemo } from "react"
import { useSearchParams } from "react-router-dom"
import {
  RefreshCw, Calendar, Wallet, Users as UsersIcon,
  TrendingDown, AlertTriangle, ArrowDownToLine,
  Link2, Link2Off, FileQuestion, Clock,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { KpiCard } from "@/components/ui/kpi-card"
import { Button } from "@/components/ui/button"
import { useDsoReport } from "@/features/billing"
import type { DsoReportResponse } from "@/features/billing"
import { cn, formatCurrency } from "@/lib/utils"

/**
 * DSO report page. Three sections:
 *   - KPI strip with headline + adjusted DSO (the latter subtracts
 *     invoices already showing cash-matched evidence).
 *   - Two parallel breakdowns: Aging buckets and Payment evidence.
 *   - Top partners table with per-partner DSO + likely-paid split.
 *
 * The page reads its date window from URL params so the operator can
 * deep-link a specific period; defaults to last 90 days.
 */
const PERIOD_OPTIONS = [
  { days: 30, label: "30d" },
  { days: 60, label: "60d" },
  { days: 90, label: "90d" },
  { days: 180, label: "180d" },
  { days: 365, label: "365d" },
] as const

function isoDaysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10)
}

const EVIDENCE_LABEL: Record<keyof DsoReportResponse["payment_evidence"], string> = {
  cash_matched_full: "Caixa conciliado",
  cash_matched_partial: "Caixa parcial",
  linked_no_recon: "Vinculado sem conciliar",
  nf_linked_no_tx: "NF vinculada sem Tx",
  unlinked: "Sem vínculo",
}

const EVIDENCE_TONE: Record<keyof DsoReportResponse["payment_evidence"], string> = {
  cash_matched_full: "bg-success/30",
  cash_matched_partial: "bg-success/15",
  linked_no_recon: "bg-warning/30",
  nf_linked_no_tx: "bg-info/20",
  unlinked: "bg-muted-foreground/30",
}

const EVIDENCE_ICON: Record<keyof DsoReportResponse["payment_evidence"], typeof Link2> = {
  cash_matched_full: Link2,
  cash_matched_partial: Link2,
  linked_no_recon: Clock,
  nf_linked_no_tx: FileQuestion,
  unlinked: Link2Off,
}

const AGING_TONE: Record<string, string> = {
  "0-30": "bg-success/40",
  "31-60": "bg-info/40",
  "61-90": "bg-warning/40",
  "91+": "bg-destructive/40",
}

function StackedBar({
  segments,
  total,
}: {
  segments: Array<{ key: string; label: string; amount: number; tone: string }>
  total: number
}) {
  const safeTotal = total > 0 ? total : 1
  return (
    <div className="space-y-1.5">
      <div className="flex h-3 w-full overflow-hidden rounded-full border border-border/40 bg-muted/30">
        {segments.map((s) => {
          const pct = (s.amount / safeTotal) * 100
          if (pct <= 0) return null
          return (
            <div
              key={s.key}
              className={cn("h-full", s.tone)}
              style={{ width: `${pct}%` }}
              title={`${s.label}: ${pct.toFixed(1)}%`}
            />
          )
        })}
      </div>
    </div>
  )
}

export function DsoReportPage() {
  const [params, setParams] = useSearchParams()
  const dateFrom = params.get("date_from") || isoDaysAgo(90)
  const dateTo = params.get("date_to") || isoToday()
  const topN = Number(params.get("top_n_partners") || 10)

  const { data, isLoading, isFetching, refetch } = useDsoReport({
    date_from: dateFrom,
    date_to: dateTo,
    top_n_partners: topN,
  })

  const setPeriod = (days: number) => {
    const next = new URLSearchParams(params)
    next.set("date_from", isoDaysAgo(days))
    next.set("date_to", isoToday())
    setParams(next, { replace: true })
  }

  const arOpen = Number(data?.totals.ar_open ?? 0)
  const arAdjusted = Number(data?.totals.ar_adjusted ?? 0)
  const dso = data?.totals.dso_days
  const dsoAdjusted = data?.totals.dso_days_adjusted
  const sales = Number(data?.totals.sales ?? 0)
  const likelyPaid = Number(data?.totals.ar_likely_paid_amount ?? 0)
  const likelyPaidCount = data?.totals.ar_likely_paid_count ?? 0

  const evidenceSegments = useMemo(() => {
    if (!data) return []
    const order: (keyof DsoReportResponse["payment_evidence"])[] = [
      "cash_matched_full",
      "cash_matched_partial",
      "linked_no_recon",
      "nf_linked_no_tx",
      "unlinked",
    ]
    return order.map((k) => ({
      key: k,
      label: EVIDENCE_LABEL[k],
      amount: Number(data.payment_evidence[k].amount),
      tone: EVIDENCE_TONE[k],
    }))
  }, [data])

  const agingSegments = useMemo(() => {
    if (!data) return []
    return data.aging.map((b) => ({
      key: b.label,
      label: b.label,
      amount: Number(b.amount),
      tone: AGING_TONE[b.label] ?? "bg-muted-foreground/30",
    }))
  }, [data])

  return (
    <div className="space-y-4">
      <SectionHeader
        title="DSO — Days Sales Outstanding"
        subtitle="Quanto tempo (em média) leva para o caixa entrar depois da venda. Inclui aging do AR aberto e a parcela já com evidência de pagamento conciliado."
        actions={
          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-1 md:flex">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              {PERIOD_OPTIONS.map((p) => {
                const active = dateFrom === isoDaysAgo(p.days) && dateTo === isoToday()
                return (
                  <Button
                    key={p.days}
                    size="sm"
                    variant={active ? "default" : "outline"}
                    onClick={() => setPeriod(p.days)}
                  >
                    {p.label}
                  </Button>
                )
              })}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Atualizar
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <div className="rounded-md border border-border bg-card p-12 text-center text-muted-foreground">
          Carregando…
        </div>
      ) : !data ? (
        <div className="rounded-md border border-border bg-card p-8 text-center text-muted-foreground">
          Não foi possível carregar o relatório.
        </div>
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard
              label="Vendas no período"
              value={formatCurrency(sales)}
              icon={<ArrowDownToLine className="h-4 w-4" />}
              hint={
                <span className="text-muted-foreground/80">
                  {data.period.days} dias · {data.totals.open_invoice_count} faturas em aberto
                </span>
              }
            />
            <KpiCard
              label="AR aberto"
              value={formatCurrency(arOpen)}
              icon={<Wallet className="h-4 w-4" />}
              hint={
                <span className="text-muted-foreground/80">
                  ajustado:{" "}
                  <strong className="text-foreground">{formatCurrency(arAdjusted)}</strong>{" "}
                  (após evidência)
                </span>
              }
            />
            <KpiCard
              label="DSO"
              value={
                dso == null ? "—" : (
                  <span>
                    {Number(dso).toFixed(0)}
                    <span className="ml-1 text-sm font-normal text-muted-foreground">dias</span>
                  </span>
                )
              }
              icon={<Clock className="h-4 w-4" />}
              tone={
                dso == null ? "default"
                  : Number(dso) > 60 ? "danger"
                  : Number(dso) > 30 ? "warning"
                  : "success"
              }
              hint={
                dsoAdjusted == null ? undefined : (
                  <span className="text-muted-foreground/80">
                    ajustado: <strong className="text-foreground">{Number(dsoAdjusted).toFixed(0)}d</strong>
                  </span>
                )
              }
            />
            <KpiCard
              label="Faturas com caixa conciliado"
              value={String(likelyPaidCount)}
              icon={<TrendingDown className="h-4 w-4" />}
              tone="success"
              hint={
                <span className="text-muted-foreground/80">
                  R$ {data.totals.ar_likely_paid_amount} a regularizar
                </span>
              }
            />
          </div>

          {/* Aging + payment evidence side by side */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {/* Aging */}
            <div className="card-elevated p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold">Aging do AR aberto</h3>
                <span className="text-[11px] text-muted-foreground">
                  base: data de emissão
                </span>
              </div>
              <StackedBar segments={agingSegments} total={arOpen} />
              <div className="mt-3 space-y-1.5">
                {data.aging.map((b) => {
                  const pct = arOpen > 0 ? (Number(b.amount) / arOpen) * 100 : 0
                  return (
                    <div key={b.label} className="flex items-center gap-2 text-[12px]">
                      <span
                        className={cn("inline-block h-2.5 w-2.5 rounded-full", AGING_TONE[b.label])}
                      />
                      <span className="w-12 font-mono text-muted-foreground">{b.label}</span>
                      <span className="flex-1 text-muted-foreground">
                        {b.count} faturas
                      </span>
                      <span className="tabular-nums text-foreground">{formatCurrency(Number(b.amount))}</span>
                      <span className="w-12 text-right tabular-nums text-muted-foreground">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  )
                })}
              </div>
              {Number(data.aging[3]?.amount ?? 0) / Math.max(1, arOpen) > 0.5 ? (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 p-2 text-[11px] text-warning">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    Mais de 50% do AR está em 91+ dias. Considere rodar
                    <strong> Atualizar status </strong>na aba Faturas — a maior parte
                    pode já estar paga e com status desatualizado.
                  </span>
                </div>
              ) : null}
            </div>

            {/* Payment evidence */}
            <div className="card-elevated p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold">Evidência de pagamento</h3>
                <span className="text-[11px] text-muted-foreground">
                  Invoice → NF → Tx → conciliado?
                </span>
              </div>
              <StackedBar segments={evidenceSegments} total={arOpen} />
              <div className="mt-3 space-y-1.5">
                {evidenceSegments.map((s) => {
                  const k = s.key as keyof DsoReportResponse["payment_evidence"]
                  const bucket = data.payment_evidence[k]
                  const pct = arOpen > 0 ? (Number(bucket.amount) / arOpen) * 100 : 0
                  const Icon = EVIDENCE_ICON[k]
                  return (
                    <div key={k} className="flex items-center gap-2 text-[12px]">
                      <Icon className="h-3 w-3 text-muted-foreground" />
                      <span className="w-32 truncate text-muted-foreground" title={s.label}>
                        {s.label}
                      </span>
                      <span className="flex-1 text-muted-foreground">
                        {bucket.count} faturas
                      </span>
                      <span className="tabular-nums text-foreground">
                        {formatCurrency(Number(bucket.amount))}
                      </span>
                      <span className="w-12 text-right tabular-nums text-muted-foreground">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  )
                })}
              </div>
              {likelyPaid > 0 ? (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-success/30 bg-success/5 p-2 text-[11px] text-success">
                  <Wallet className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    {likelyPaidCount} faturas (R$ {data.totals.ar_likely_paid_amount}) têm
                    Tx vinculado conciliado — provavelmente já pagas. Use o botão{" "}
                    <strong>Atualizar status</strong> em Faturas para regularizar.
                  </span>
                </div>
              ) : null}
            </div>
          </div>

          {/* Per-partner table */}
          <div className="card-elevated overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <div className="flex items-center gap-2">
                <UsersIcon className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-[13px] font-semibold">Top {topN} parceiros por AR aberto</h3>
              </div>
              <span className="text-[11px] text-muted-foreground">
                Ordenado por valor a receber
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="h-8 px-3">Parceiro</th>
                    <th className="h-8 px-3 text-right">Vendas</th>
                    <th className="h-8 px-3 text-right">AR aberto</th>
                    <th className="h-8 px-3 text-right">Provável pago</th>
                    <th className="h-8 px-3 text-right">DSO</th>
                    <th className="h-8 px-3 text-right">Idade média</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_partner.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                        Nenhum parceiro com AR aberto no período.
                      </td>
                    </tr>
                  ) : data.per_partner.map((p) => {
                    const ar = Number(p.ar_open)
                    const paid = Number(p.ar_likely_paid)
                    const paidPct = ar > 0 ? (paid / ar) * 100 : 0
                    const dsoNum = p.dso_days == null ? null : Number(p.dso_days)
                    return (
                      <tr key={p.partner_id} className="border-t border-border hover:bg-accent/40">
                        <td className="px-3 py-1.5">
                          <div className="font-medium">{p.partner_name}</div>
                          <div className="font-mono text-[10px] text-muted-foreground">
                            {p.partner_identifier}
                          </div>
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">
                          {formatCurrency(Number(p.sales))}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">
                          {formatCurrency(ar)}
                          <div className="text-[10px] text-muted-foreground">
                            {p.ar_invoice_count} faturas
                          </div>
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">
                          {paid > 0 ? (
                            <>
                              <span className="text-success">{formatCurrency(paid)}</span>
                              <div className="text-[10px] text-muted-foreground">
                                {paidPct.toFixed(0)}% · {p.ar_likely_paid_count} faturas
                              </div>
                            </>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-1.5 text-right tabular-nums",
                            dsoNum != null && dsoNum > 60 && "text-destructive font-medium",
                            dsoNum != null && dsoNum > 30 && dsoNum <= 60 && "text-warning",
                          )}
                        >
                          {dsoNum != null ? `${dsoNum.toFixed(0)}d` : "—"}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {p.weighted_avg_age_days != null
                            ? `${Number(p.weighted_avg_age_days).toFixed(0)}d`
                            : "—"}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[10px] text-muted-foreground">{data.notes}</p>
        </>
      )}
    </div>
  )
}
