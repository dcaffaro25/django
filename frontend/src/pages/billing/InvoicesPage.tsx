import { useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  RefreshCw, Search, ArrowDownToLine, ArrowUpFromLine, Eye,
  Receipt as ReceiptIcon, AlertTriangle, Sparkles,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { useInvoices } from "@/features/billing"
import type { Invoice, InvoiceFiscalStatus, InvoiceStatus } from "@/features/billing"
import { FiscalStatusBadge } from "./components/FiscalStatusBadge"
import { CriticsAuditModal } from "./components/CriticsAuditModal"
import { InvoiceDetailDrawer } from "./InvoiceDetailDrawer"
import { useDebounced } from "@/lib/useDebounced"
import { cn, formatCurrency, formatDate } from "@/lib/utils"
import { useUserRole } from "@/features/auth/useUserRole"

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

function CriticsBadgeInline({
  count, bySeverity,
}: {
  count: number
  bySeverity?: { error?: number; warning?: number; info?: number }
}) {
  const err = bySeverity?.error ?? 0
  const warn = bySeverity?.warning ?? 0
  const info = bySeverity?.info ?? 0
  const tone = err > 0
    ? "bg-danger/15 text-danger"
    : warn > 0
      ? "bg-warning/15 text-warning"
      : "bg-info/15 text-info"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums",
        tone,
      )}
      title={`${err} erro(s), ${warn} alerta(s), ${info} info`}
    >
      <AlertTriangle className="h-3 w-3" />
      {count}
    </span>
  )
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
  // Local input + debounced copy: keeps typing snappy by deferring the
  // URL write (and the filter useMemo over a potentially long invoice
  // list) until 200 ms after the user stops typing.
  const initialSearch = useMemo(() => params.get("q") || "", []) // eslint-disable-line react-hooks/exhaustive-deps
  const [searchInput, setSearchInput] = useState(initialSearch)
  const search = useDebounced(searchInput, 200)
  const fiscalFilter = (params.get("fiscal_status") || "all") as "all" | InvoiceFiscalStatus
  const statusFilter = (params.get("status") || "all") as "all" | InvoiceStatus
  const hasCritics = params.get("has_critics") === "1"
  const dateFrom = params.get("date_from") || ""
  const dateTo = params.get("date_to") || ""
  const { canWrite } = useUserRole()

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "" || value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const skipFirstSync = useRef(true)
  useEffect(() => {
    if (skipFirstSync.current) { skipFirstSync.current = false; return }
    setFilter("q", search)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const apiParams = useMemo(() => {
    const p: Record<string, string> = {}
    if (fiscalFilter !== "all") p.fiscal_status = fiscalFilter
    if (statusFilter !== "all") p.status = statusFilter
    if (hasCritics) p.has_critics = "1"
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    return p
  }, [fiscalFilter, statusFilter, hasCritics, dateFrom, dateTo])

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
  const [auditOpen, setAuditOpen] = useState(false)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Faturas"
        subtitle="Cobranças emitidas e recebidas. Eixo comercial (status de pagamento) + eixo fiscal (NFs vinculadas)."
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Atualizar
            </Button>
            {canWrite ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAuditOpen(true)}
              >
                <Sparkles className="h-4 w-4" />
                Auditar críticas
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap items-end gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
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
        <label
          className={cn(
            "flex h-9 cursor-pointer items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium",
            hasCritics && "border-warning/50 bg-warning/10 text-warning",
          )}
          title="Mostrar apenas faturas com críticas não-aceitas"
        >
          <Checkbox
            checked={hasCritics}
            onCheckedChange={(v) => setFilter("has_critics", v ? "1" : null)}
          />
          <AlertTriangle className="h-3.5 w-3.5" />
          Com críticas
        </label>
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
              <th className="px-3 py-2">Críticas</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-muted-foreground">
                  Carregando faturas…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center">
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
                  <td className="px-3 py-2">
                    {(inv.critics_count ?? 0) === 0 ? (
                      <span className="text-[11px] text-muted-foreground/60">—</span>
                    ) : (
                      <CriticsBadgeInline
                        count={inv.critics_count ?? 0}
                        bySeverity={inv.critics_count_by_severity}
                      />
                    )}
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
      <CriticsAuditModal
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        onJumpToInvoice={(id) => setSelectedId(id)}
      />
    </div>
  )
}
