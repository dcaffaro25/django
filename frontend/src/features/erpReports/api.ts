import { api } from "@/lib/api-client"


export interface PedidoReportRow {
  codigo_pedido: number
  numero_pedido: string | null
  etapa: string | null
  data_inclusao: string | null
  data_inclusao_raw: string | null
  valor_total_pedido: string
  qtde_itens: number | string | null
  encerrado: string | null
  bloqueado: string | null
  cliente: {
    codigo_cliente_omie: number | null
    razao_social: string | null
    nome_fantasia: string | null
    cnpj_cpf: string | null
    uf: string | null
    city: string | null
  }
  items: Array<{
    codigo_produto: number | null
    codigo_item_integracao: string | null
    ncm: string | null
    cfop: string | null
    descricao: string | null
    valor_unitario: string
    quantidade: string
    valor_total: string
    produto_resolved_name: string | null
    produto_unit: string | null
  }>
  fetched_at: string | null
}

export interface PedidoReport {
  rows: PedidoReportRow[]
  summary: {
    n_pedidos_total: number
    n_pedidos_filtered: number
    n_clientes_indexed: number
    n_produtos_indexed: number
    valor_total_filtered: string
    by_etapa: Record<string, number>
  }
  meta: {
    limit: number
    pipeline_id: number | null
    pipeline_name: string | null
    last_run: null | {
      id: number
      status: string
      started_at: string | null
      completed_at: string | null
      records_extracted: number
      duration_seconds: number | null
      is_sandbox: boolean
    }
  }
  filters_applied: Record<string, string | number | null>
}

export interface PedidoReportFilters {
  date_from?: string
  date_to?: string
  etapa?: string
  codigo_cliente?: number
  search?: string
  limit?: number
}

export const erpReportsApi = {
  pedidos: (filters: PedidoReportFilters = {}) =>
    api.tenant.get<PedidoReport>("/api/erp/reports/pedidos/", { params: filters }),

  /** POST with refresh=true triggers a live pipeline run before
   * returning the snapshot. Heavy — use sparingly. */
  refreshPedidos: (filters: PedidoReportFilters = {}) =>
    api.tenant.post<PedidoReport>(
      "/api/erp/reports/pedidos/",
      { refresh: true, ...filters },
    ),
}
