import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  RefreshCw, Search, ArrowDownToLine, ArrowUpFromLine, Eye,
  Receipt as ReceiptIcon,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useInvoices } from "@/features/billing"
import type { Invoice, InvoiceFiscalStatus, InvoiceStatus } from "@/features/billing"
import { FiscalStatusBadge } from "./components/FiscalStatusBadge"
import { InvoiceDetailDrawer } from "./InvoiceDetailDrawer"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: "Rascunho",
  issued: "Emitida",
  partially_paid: "Parc. paga",
  paid: "Paga",
  canceled: "Cancelada",
}

const STATUS_TONE: Record<InvoiceStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  issued: "bg-info/10 text-info",
  partially_paid: "bg-warning/10 text-warning",
  paid: "bg-success/10 text-success",
  canceled: "bg-muted text-muted-foreground line-through",
}

function PaymentStatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium",
        STATUS_TONE[status],
      )}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

const FISCAL_FILTER_OPTIONS: Array<{ value: "all" | InvoiceFiscalStatus; label: string }> = [
  { value: "all", label: "Todas" },
  { value: "pending_nf", label: "Pendente de NF" },
  { value: "invoiced", label: "Faturada" },
  { value: "partially_returned", label: "Devolvida (parcial)" },
  { value: "fully_returned", label: "Devolvida" },
  { value: "fiscally_cancelled", label: "NF cancelada" },
  { value: "mixed", label: "Misto" },
]

const STATUS_FILTER_OPTIONS: Array<{ value: "all" | InvoiceStatus; label: string }> = [
  { value: "all", label: "Todos" },
  { value: "draft", label: "Rascunho" },
  { value: "issued", label: "Emitida" },
  { value: "partially_paid", label: "Parc. paga" },
  { value: "paid", label: "Paga" },
  { value: "canceled", label: "Cancelada" },
]

export function InvoicesPage() {
  const [params, setParams] = useSearchParams()
  const search = params.get("q") || ""
  const fiscalFilter = (params.get("fiscal_status") || "all") as "all" | InvoiceFiscalStatus
  const statusFilter = (params.get("status") || "all") as "all" | InvoiceStatus
  const dateFrom = params.get("date_from") || ""
  const dateTo = params.get("date_to") || ""

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "" || value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const apiParams = useMemo(() => {
    const p: Record<string, string> = {}
    if (fiscalFilter !== "all") p.fiscal_status = fiscalFilter
    if (statusFilter !== "all") p.status = statusFilter
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    return p
  }, [fiscalFilter, statusFilter, dateFrom, dateTo])

  const { data, isLoading, isFetching, refetch } = useInvoices(apiParams)

  const filtered = useMemo(() => {
    if (!data) return []
    if (!search) return data
    const q = search.toLowerCase()
    return data.filter((i) =>
      [i.invoice_number, i.description, i.erp_id ?? ""]
        .filter(Boolean)
        .some((s) => s.toLowerCase().includes(q)),
    )
  }, [data, search])

  const [selectedId, setSelectedId] = useState<number | null>(null)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Faturas"
        subtitle="Cobranças emitidas e recebidas. Eixo comercial (status de pagamento) + eixo fiscal (NFs vinculadas)."
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

      <div className="flex flex-wrap items-end gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setFilter("q", e.target.value)}
            placeholder="Buscar número, descrição, ERP id…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Status pgto
          </span>
          <Select
            value={statusFilter}
            onValueChange={(v) => setFilter("status", v)}
          >
            <SelectTrigger className="h-9 w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_FILTER_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Status fiscal
          </span>
          <Select
            value={fiscalFilter}
            onValueChange={(v) => setFilter("fiscal_status", v)}
          >
            <SelectTrigger className="h-9 w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FISCAL_FILTER_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Emissão de
          </span>
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => setFilter("date_from", e.target.value)}
            className="h-9 w-[150px]"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            até
          </span>
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => setFilter("date_to", e.target.value)}
            className="h-9 w-[150px]"
          />
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <table className="w-full text-[12px]">
          <thead className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Número</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Emissão</th>
              <th className="px-3 py-2">Vencimento</th>
              <th className="px-3 py-2 text-right">Valor</th>
              <th className="px-3 py-2">Status pgto</th>
              <th className="px-3 py-2">Status fiscal</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">
                  Carregando faturas…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center">
                  <ReceiptIcon className="mx-auto mb-2 h-6 w-6 text-muted-foreground/60" />
                  <p className="text-muted-foreground">
                    Nenhuma fatura encontrada com os filtros atuais.
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((inv: Invoice) => (
                <tr
                  key={inv.id}
                  className="border-b border-border/40 last:border-b-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-2">
                    <span className="font-mono">{inv.invoice_number}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      {inv.invoice_type === "sale" ? (
                        <>
                          <ArrowUpFromLine className="h-3 w-3" /> Venda
                        </>
                      ) : (
                        <>
                          <ArrowDownToLine className="h-3 w-3" /> Compra
                        </>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {formatDate(inv.invoice_date)}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {formatDate(inv.due_date)}
                  </td>
                  <td className="px-3 py-2 text-right font-medium tabular-nums">
                    {formatCurrency(inv.total_amount)}
                  </td>
                  <td className="px-3 py-2">
                    <PaymentStatusBadge status={inv.status} />
                  </td>
                  <td className="px-3 py-2">
                    <FiscalStatusBadge
                      status={inv.fiscal_status}
                      pendingCorrections={inv.has_pending_corrections}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedId(inv.id)}
                    >
                      <Eye className="h-3.5 w-3.5" /> Ver
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <InvoiceDetailDrawer
        invoiceId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  )
}
