/**
 * Pedidos de Venda — report page.
 *
 * Reads the latest ERPRawRecord snapshot for the active tenant via
 * /api/erp/reports/pedidos/. The pipeline that populates that snapshot
 * is ``evolat_omie_pedidos_full`` (Pedidos + Clientes + Produtos in
 * one pass, joined in memory by codigo_*).
 *
 * Surface decisions:
 *
 * - **KPI strip first**: filtered count, total value, distinct
 *   clientes, distinct produtos, last sync. The eye lands on the
 *   snapshot freshness immediately.
 * - **Filter bar** sits between KPIs and the table, sticky-ish on
 *   scroll (just visually grouped, not position:sticky for v1).
 * - **Table** with sortable headers, an etapa pill, and a clickable
 *   row that opens the drill drawer.
 * - **Drill drawer** shows the cliente block + the items table with
 *   resolved produto names — exactly what the in-memory join gave us.
 * - **Refresh button** explicitly triggers a live pipeline run. Heavy
 *   (4 Omie calls), so it's an explicit click + spinner, not auto.
 */
import { useMemo, useState } from "react"
import { toast } from "sonner"
import {
  AlertTriangle, Calendar, FileText, Layers, Loader2, RefreshCw, Search,
  ShoppingBag, Users, X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { SectionHeader } from "@/components/ui/section-header"
import { extractApiErrorMessage } from "@/lib/api-client"
import { cn } from "@/lib/utils"
import {
  type PedidoReportFilters,
  type PedidoReportRow,
} from "@/features/erpReports/api"
import {
  usePedidoReport,
  useRefreshPedidoReport,
} from "@/features/erpReports/hooks"


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtBRL(value: string | number | null | undefined): string {
  const n = typeof value === "string" ? parseFloat(value) : (value ?? 0)
  if (!Number.isFinite(n)) return "—"
  return new Intl.NumberFormat("pt-BR", {
    style: "currency", currency: "BRL", minimumFractionDigits: 2,
  }).format(n as number)
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("pt-BR")
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "—"
  const t = new Date(iso).getTime()
  const delta = Date.now() - t
  if (delta < 0) return "agora"
  if (delta < 60_000) return "agora"
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m atrás`
  if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h atrás`
  return `${Math.round(delta / 86_400_000)}d atrás`
}

// Omie etapa codes — sourced from observed values in evolat's dataset
// + Omie docs. Add new codes here as they appear.
const ETAPA_LABELS: Record<string, string> = {
  "10": "Digitado",
  "20": "Atendido",
  "30": "Faturando",
  "50": "Faturado",
  "60": "Faturado parcial",
  "70": "Cancelado",
  "80": "Encerrado",
}

function etapaLabel(code: string | null | undefined): string {
  if (!code) return "—"
  return ETAPA_LABELS[code] ?? code
}

function etapaTone(code: string | null | undefined): string {
  switch (code) {
    case "50": return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
    case "60": return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
    case "80": return "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
    case "30": return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
    case "70": return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
    case "20": return "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
    case "10": return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
    default:   return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
  }
}


// ---------------------------------------------------------------------------
// KPI strip
// ---------------------------------------------------------------------------
function KpiCard(props: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  hint?: string
  tone?: "default" | "warn"
}) {
  return (
    <Card className="flex flex-col gap-1 p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
        {props.icon}
        {props.label}
      </div>
      <div className={cn(
        "font-mono text-lg",
        props.tone === "warn" && "text-amber-700 dark:text-amber-300",
      )}>
        {props.value}
      </div>
      {props.hint && <div className="text-[11px] text-zinc-500">{props.hint}</div>}
    </Card>
  )
}


// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------
function FilterBar(props: {
  filters: PedidoReportFilters
  onChange: (next: PedidoReportFilters) => void
  etapas: Record<string, number>
}) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-5">
      <div className="md:col-span-2 flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
        <Search className="h-3.5 w-3.5 text-zinc-400" />
        <input
          value={props.filters.search ?? ""}
          onChange={(e) => props.onChange({ ...props.filters, search: e.target.value })}
          placeholder="número, cliente, CNPJ…"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-zinc-400"
        />
        {props.filters.search && (
          <button
            type="button"
            onClick={() => props.onChange({ ...props.filters, search: "" })}
            className="rounded p-0.5 text-zinc-400 hover:text-zinc-600"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
        <Calendar className="h-3.5 w-3.5 text-zinc-400" />
        <input
          type="date"
          value={props.filters.date_from ?? ""}
          onChange={(e) => props.onChange({ ...props.filters, date_from: e.target.value })}
          className="flex-1 bg-transparent text-sm outline-none"
        />
      </div>

      <div className="flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
        <Calendar className="h-3.5 w-3.5 text-zinc-400" />
        <input
          type="date"
          value={props.filters.date_to ?? ""}
          onChange={(e) => props.onChange({ ...props.filters, date_to: e.target.value })}
          className="flex-1 bg-transparent text-sm outline-none"
        />
      </div>

      <select
        value={props.filters.etapa ?? ""}
        onChange={(e) => props.onChange({ ...props.filters, etapa: e.target.value || undefined })}
        className="rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900"
      >
        <option value="">todas as etapas</option>
        {Object.entries(props.etapas).map(([code, count]) => (
          <option key={code} value={code}>
            {etapaLabel(code)} ({count})
          </option>
        ))}
      </select>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Pedido drawer
// ---------------------------------------------------------------------------
function PedidoDrawer(props: { row: PedidoReportRow; onClose: () => void }) {
  const r = props.row
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={props.onClose} />
      <div className="relative flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white shadow-2xl dark:bg-zinc-950">
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
          <div>
            <div className="text-xs uppercase tracking-wide text-zinc-500">Pedido</div>
            <div className="font-mono text-base">
              #{r.numero_pedido ?? r.codigo_pedido}
            </div>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {/* Cabeçalho */}
          <Card className="p-3">
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <div className="text-[11px] uppercase text-zinc-500">Etapa</div>
                <span className={cn(
                  "mt-0.5 inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium",
                  etapaTone(r.etapa),
                )}>
                  {etapaLabel(r.etapa)}
                </span>
              </div>
              <div>
                <div className="text-[11px] uppercase text-zinc-500">Inclusão</div>
                <div className="font-mono">{fmtDate(r.data_inclusao)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase text-zinc-500">Total</div>
                <div className="font-mono font-semibold">{fmtBRL(r.valor_total_pedido)}</div>
              </div>
            </div>
          </Card>

          {/* Cliente */}
          <Card className="p-3">
            <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              <Users className="h-3.5 w-3.5" /> Cliente
            </div>
            <div className="font-medium">
              {r.cliente.razao_social || r.cliente.nome_fantasia || "—"}
            </div>
            <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-zinc-600 dark:text-zinc-400">
              <div>CNPJ/CPF: <span className="font-mono">{r.cliente.cnpj_cpf ?? "—"}</span></div>
              <div>Cidade: {r.cliente.city ?? "—"}</div>
              <div>UF: {r.cliente.uf ?? "—"}</div>
            </div>
          </Card>

          {/* Itens */}
          <Card className="p-0">
            <div className="flex items-center gap-1.5 border-b border-zinc-200 px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <ShoppingBag className="h-3.5 w-3.5" /> Itens ({r.items.length})
            </div>
            <div className="divide-y divide-zinc-100 dark:divide-zinc-800/60">
              {r.items.map((it, i) => (
                <div key={i} className="px-3 py-2 text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="truncate font-medium" title={it.descricao ?? ""}>
                      {it.descricao || it.produto_resolved_name || `Produto ${it.codigo_produto}`}
                    </div>
                    <div className="font-mono text-xs">{fmtBRL(it.valor_total)}</div>
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                    <span>NCM {it.ncm ?? "—"}</span>
                    <span>CFOP {it.cfop ?? "—"}</span>
                    <span>Qtde {it.quantidade}</span>
                    <span>Unit {fmtBRL(it.valor_unitario)}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export function PedidoVendasReportPage() {
  const [filters, setFilters] = useState<PedidoReportFilters>({})
  const [selected, setSelected] = useState<PedidoReportRow | null>(null)

  // Live filters → query
  const queryFilters = useMemo(() => {
    const out: PedidoReportFilters = { limit: 200 }
    if (filters.search?.trim()) out.search = filters.search.trim()
    if (filters.date_from) out.date_from = filters.date_from
    if (filters.date_to) out.date_to = filters.date_to
    if (filters.etapa) out.etapa = filters.etapa
    return out
  }, [filters])

  const report = usePedidoReport(queryFilters)
  const refreshMut = useRefreshPedidoReport()

  const data = report.data
  const summary = data?.summary
  const meta = data?.meta

  const handleRefresh = async () => {
    try {
      await refreshMut.mutateAsync(queryFilters)
      toast.success("Snapshot atualizado.")
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao atualizar.")
    }
  }

  return (
    <div className="space-y-4 p-4">
      <SectionHeader
        title="Pedidos de Venda (Omie)"
        subtitle={
          meta?.last_run
            ? `Última atualização: ${fmtRelative(meta.last_run.completed_at ?? meta.last_run.started_at)} · ${meta.last_run.records_extracted} registros · pipeline #${meta.pipeline_id}`
            : "Snapshot não disponível — clique em Atualizar para puxar do Omie"
        }
        actions={
          <Button
            type="button" size="sm" variant="default"
            onClick={handleRefresh} disabled={refreshMut.isPending}
          >
            {refreshMut.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            )}
            Atualizar
          </Button>
        }
      />

      {/* Pipeline-failure banner */}
      {meta?.last_run?.status === "failed" && (
        <Card className="flex items-start gap-2 border-amber-300 bg-amber-50 p-3 dark:border-amber-800/50 dark:bg-amber-900/30">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-300" />
          <div className="text-sm">
            <div className="font-medium text-amber-900 dark:text-amber-100">
              A última execução do pipeline falhou
            </div>
            <div className="text-amber-800 dark:text-amber-200">
              O relatório mostra o snapshot anterior. Tente atualizar em alguns minutos
              (Omie pode estar bloqueando temporariamente o consumo da API).
            </div>
          </div>
        </Card>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KpiCard
          icon={<FileText className="h-3.5 w-3.5" />}
          label="Pedidos (filtro)"
          value={summary ? summary.n_pedidos_filtered.toLocaleString("pt-BR") : "—"}
          hint={summary && summary.n_pedidos_total !== summary.n_pedidos_filtered
            ? `${summary.n_pedidos_total} no total` : undefined}
        />
        <KpiCard
          icon={<ShoppingBag className="h-3.5 w-3.5" />}
          label="Valor total"
          value={summary ? fmtBRL(summary.valor_total_filtered) : "—"}
        />
        <KpiCard
          icon={<Users className="h-3.5 w-3.5" />}
          label="Clientes indexados"
          value={summary ? summary.n_clientes_indexed.toLocaleString("pt-BR") : "—"}
        />
        <KpiCard
          icon={<Layers className="h-3.5 w-3.5" />}
          label="Produtos indexados"
          value={summary ? summary.n_produtos_indexed.toLocaleString("pt-BR") : "—"}
        />
        <KpiCard
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="Snapshot"
          value={meta?.last_run
            ? fmtRelative(meta.last_run.completed_at ?? meta.last_run.started_at)
            : "—"}
          hint={meta?.last_run?.duration_seconds
            ? `levou ${meta.last_run.duration_seconds.toFixed(1)}s` : undefined}
          tone={meta?.last_run?.status === "failed" ? "warn" : "default"}
        />
      </div>

      {/* Filters */}
      <FilterBar
        filters={filters}
        onChange={setFilters}
        etapas={summary?.by_etapa ?? {}}
      />

      {/* Table */}
      <Card className="p-0">
        {report.isLoading ? (
          <div className="flex items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
          </div>
        ) : (data?.rows.length ?? 0) === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 p-10 text-center text-sm text-zinc-500">
            <ShoppingBag className="h-6 w-6 text-zinc-400" />
            <div>Nenhum pedido encontrado para os filtros selecionados.</div>
            {!meta?.last_run && (
              <div className="text-[11px]">
                Clique em <strong>Atualizar</strong> para buscar do Omie pela primeira vez.
              </div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">
                  <th>Pedido</th>
                  <th>Etapa</th>
                  <th>Cliente</th>
                  <th>Inclusão</th>
                  <th className="text-right">Itens</th>
                  <th className="text-right">Valor</th>
                </tr>
              </thead>
              <tbody className="[&>tr]:border-b [&>tr]:border-zinc-100 dark:[&>tr]:border-zinc-800/60">
                {data!.rows.map((r) => (
                  <tr
                    key={r.codigo_pedido}
                    className="cursor-pointer transition hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                    onClick={() => setSelected(r)}
                  >
                    <td className="px-3 py-2 font-mono">
                      #{r.numero_pedido ?? r.codigo_pedido}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium",
                        etapaTone(r.etapa),
                      )}>
                        {etapaLabel(r.etapa)}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="truncate" title={r.cliente.razao_social ?? ""}>
                        {r.cliente.razao_social || r.cliente.nome_fantasia || "—"}
                      </div>
                      <div className="text-[11px] text-zinc-500">
                        {r.cliente.cnpj_cpf ?? "—"} · {r.cliente.city ?? "—"}/{r.cliente.uf ?? "—"}
                      </div>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{fmtDate(r.data_inclusao)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{r.qtde_itens ?? "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtBRL(r.valor_total_pedido)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && <PedidoDrawer row={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
