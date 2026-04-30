import { api, unwrapList } from "@/lib/api-client"
import type {
  BillingTenantConfig,
  BusinessPartner,
  Invoice,
  InvoiceDetail,
  InvoiceNFLink,
  NFTransactionLink,
  NotaFiscal,
  PaginatedListResponse,
  ScanResponse,
} from "./types"

type AnyParams = Record<string, string | number | boolean | undefined | null>

function toQueryString(params?: AnyParams): string {
  if (!params) return ""
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ""
}

export const billingApi = {
  // ============================================================
  // Invoices
  // ============================================================
  listInvoices: async (params?: AnyParams): Promise<Invoice[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<Invoice[] | PaginatedListResponse<Invoice>>(
      `/api/invoices/${qs}`,
    )
    return unwrapList(data as never)
  },
  getInvoice: (id: number): Promise<InvoiceDetail> =>
    api.tenant.get<InvoiceDetail>(`/api/invoices/${id}/`),
  saveInvoice: (id: number | null, body: Partial<Invoice>): Promise<Invoice> => {
    if (id == null) return api.tenant.post<Invoice>("/api/invoices/", body)
    return api.tenant.patch<Invoice>(`/api/invoices/${id}/`, body)
  },
  deleteInvoice: (id: number) =>
    api.tenant.delete(`/api/invoices/${id}/`),
  attachNfToInvoice: (
    invoiceId: number,
    body: { nota_fiscal: number; relation_type?: string; allocated_amount?: number; notes?: string },
  ): Promise<InvoiceNFLink> =>
    api.tenant.post<InvoiceNFLink>(`/api/invoices/${invoiceId}/attach-nf/`, body),
  refreshFiscalStatus: (invoiceId: number): Promise<InvoiceDetail> =>
    api.tenant.post<InvoiceDetail>(`/api/invoices/${invoiceId}/refresh-fiscal-status/`, {}),

  // ============================================================
  // NotaFiscal (read-only listing for picking)
  // ============================================================
  listNotasFiscais: async (params?: AnyParams): Promise<NotaFiscal[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<NotaFiscal[] | PaginatedListResponse<NotaFiscal>>(
      `/api/nfe/${qs}`,
    )
    return unwrapList(data as never)
  },
  getNotaFiscal: (id: number): Promise<NotaFiscal> =>
    api.tenant.get<NotaFiscal>(`/api/nfe/${id}/`),

  // ============================================================
  // NFTransactionLink (review surface)
  // ============================================================
  listNfTxLinks: async (params?: AnyParams): Promise<NFTransactionLink[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<NFTransactionLink[] | PaginatedListResponse<NFTransactionLink>>(
      `/api/nf-transaction-links/${qs}`,
    )
    return unwrapList(data as never)
  },
  acceptLink: (id: number, notes?: string): Promise<NFTransactionLink> =>
    api.tenant.post<NFTransactionLink>(`/api/nf-transaction-links/${id}/accept/`, { notes: notes ?? "" }),
  rejectLink: (id: number, notes?: string): Promise<NFTransactionLink> =>
    api.tenant.post<NFTransactionLink>(`/api/nf-transaction-links/${id}/reject/`, { notes: notes ?? "" }),
  scanLinks: (body: {
    transaction_ids?: number[]
    nota_fiscal_ids?: number[]
    date_window_days?: number
    amount_tolerance?: number | string
    min_confidence?: number | string
    limit?: number
    dry_run?: boolean
  }): Promise<ScanResponse> =>
    api.tenant.post<ScanResponse>(`/api/nf-transaction-links/scan/`, body),
  acceptAllAbove: (confidence: number | string): Promise<{ accepted: number }> =>
    api.tenant.post(`/api/nf-transaction-links/accept-all-above/`, { confidence }),
  createManualLink: (body: {
    transaction: number
    nota_fiscal: number
    method?: string
    confidence?: string
    matched_fields?: string[]
    notes?: string
    review_status?: string
  }): Promise<NFTransactionLink> =>
    api.tenant.post<NFTransactionLink>(`/api/nf-transaction-links/`, {
      method: "manual",
      review_status: "accepted",
      confidence: "1.000",
      matched_fields: ["manual"],
      ...body,
    }),

  // ============================================================
  // InvoiceNFLink
  // ============================================================
  listInvoiceNfLinks: async (params?: AnyParams): Promise<InvoiceNFLink[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<InvoiceNFLink[] | PaginatedListResponse<InvoiceNFLink>>(
      `/api/invoice-nf-links/${qs}`,
    )
    return unwrapList(data as never)
  },
  deleteInvoiceNfLink: (id: number) =>
    api.tenant.delete(`/api/invoice-nf-links/${id}/`),

  // ============================================================
  // BillingTenantConfig
  // ============================================================
  getConfig: (): Promise<BillingTenantConfig> =>
    api.tenant.get<BillingTenantConfig>(`/api/billing-config/current/`),
  saveConfig: (body: Partial<BillingTenantConfig>): Promise<BillingTenantConfig> =>
    api.tenant.patch<BillingTenantConfig>(`/api/billing-config/current/`, body),

  // ============================================================
  // BusinessPartner (light list for pickers)
  // ============================================================
  listBusinessPartners: async (params?: AnyParams): Promise<BusinessPartner[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartner[] | PaginatedListResponse<BusinessPartner>>(
      `/api/business_partners/${qs}`,
    )
    return unwrapList(data as never)
  },
}
