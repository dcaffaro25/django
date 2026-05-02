import { api, unwrapList } from "@/lib/api-client"
import type {
  BillingTenantConfig,
  BusinessPartner,
  BusinessPartnerAlias,
  BusinessPartnerCategory,
  BusinessPartnerGroup,
  BusinessPartnerGroupMembership,
  CnpjRootClustersResponse,
  ConsolidatedBPResponse,
  CriticAuditResponse,
  CriticsResponse,
  DsoReportResponse,
  Invoice,
  InvoiceDetail,
  InvoiceNFLink,
  NFTransactionLink,
  NotaFiscal,
  PaginatedListResponse,
  ProductService,
  ProductServiceAlias,
  ProductServiceCategory,
  ProductServiceGroup,
  ProductServiceGroupMembership,
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
  getInvoiceCritics: (invoiceId: number): Promise<CriticsResponse> =>
    api.tenant.get<CriticsResponse>(`/api/invoices/${invoiceId}/critics/`),
  acknowledgeCritic: (invoiceId: number, body: {
    kind: string; subject_type: string; subject_id: number; note?: string;
  }): Promise<{ acknowledged: boolean; ack_id: number }> =>
    api.tenant.post(`/api/invoices/${invoiceId}/acknowledge-critic/`, body),
  unacknowledgeCritic: (invoiceId: number, body: {
    kind: string; subject_type: string; subject_id: number;
  }): Promise<{ unacknowledged: boolean }> =>
    api.tenant.delete(`/api/invoices/${invoiceId}/unacknowledge-critic/`, { data: body }),
  auditCritics: (body?: {
    invoice_ids?: number[];
    severity_in?: ("error" | "warning" | "info")[];
    only_unacknowledged?: boolean;
    persist?: boolean;
  }): Promise<CriticAuditResponse> =>
    api.tenant.post<CriticAuditResponse>(`/api/invoices/audit-critics/`, body ?? {}),

  // DSO + aging + per-partner + payment-evidence report.
  dsoReport: (params?: {
    date_from?: string
    date_to?: string
    partner?: number
    top_n_partners?: number
  }): Promise<DsoReportResponse> =>
    api.tenant.get<DsoReportResponse>(
      `/api/invoices/dso-report/${toQueryString(params)}`,
    ),

  // Backfill ``Invoice.status`` from NF↔Tx reconciliation evidence.
  // The backend returns the same counter shape for dry-run and real
  // run; the UI shows a confirm modal between the two.
  backfillInvoiceStatusFromRecon: (body?: {
    dry_run?: boolean;
    include_non_open?: boolean;
  }): Promise<{
    scanned: number;
    would_promote: number;
    promoted: number;
    by_evidence: Record<string, number>;
    promoted_amount: string;
    samples: Array<{
      invoice_id: number;
      invoice_number: string;
      amount: string;
      old_status: string;
      tx_ids: number[];
    }>;
  }> =>
    api.tenant.post(`/api/invoices/backfill-status-from-recon/`, body ?? { dry_run: true }),

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
  bulkAcceptLinks: (ids: number[]): Promise<{ count: number; requested: number }> =>
    api.tenant.post(`/api/nf-transaction-links/bulk-accept/`, { ids }),
  bulkRejectLinks: (ids: number[]): Promise<{ count: number; requested: number }> =>
    api.tenant.post(`/api/nf-transaction-links/bulk-reject/`, { ids }),
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
  // BusinessPartner CRUD
  // ============================================================
  listBusinessPartners: async (params?: AnyParams): Promise<BusinessPartner[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartner[] | PaginatedListResponse<BusinessPartner>>(
      `/api/business_partners/${qs}`,
    )
    return unwrapList(data as never)
  },
  getBusinessPartner: (id: number): Promise<BusinessPartner> =>
    api.tenant.get<BusinessPartner>(`/api/business_partners/${id}/`),
  saveBusinessPartner: (id: number | null, body: Partial<BusinessPartner>): Promise<BusinessPartner> => {
    if (id == null) return api.tenant.post<BusinessPartner>("/api/business_partners/", body)
    return api.tenant.patch<BusinessPartner>(`/api/business_partners/${id}/`, body)
  },
  deleteBusinessPartner: (id: number) =>
    api.tenant.delete(`/api/business_partners/${id}/`),

  // BP categories
  listBusinessPartnerCategories: async (params?: AnyParams): Promise<BusinessPartnerCategory[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartnerCategory[] | PaginatedListResponse<BusinessPartnerCategory>>(
      `/api/business_partner_categories/${qs}`,
    )
    return unwrapList(data as never)
  },
  saveBusinessPartnerCategory: (id: number | null, body: Partial<BusinessPartnerCategory>): Promise<BusinessPartnerCategory> => {
    if (id == null) return api.tenant.post<BusinessPartnerCategory>("/api/business_partner_categories/", body)
    return api.tenant.patch<BusinessPartnerCategory>(`/api/business_partner_categories/${id}/`, body)
  },
  deleteBusinessPartnerCategory: (id: number) =>
    api.tenant.delete(`/api/business_partner_categories/${id}/`),

  // ============================================================
  // ProductService CRUD
  // ============================================================
  listProductServices: async (params?: AnyParams): Promise<ProductService[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<ProductService[] | PaginatedListResponse<ProductService>>(
      `/api/product_services/${qs}`,
    )
    return unwrapList(data as never)
  },
  getProductService: (id: number): Promise<ProductService> =>
    api.tenant.get<ProductService>(`/api/product_services/${id}/`),
  saveProductService: (id: number | null, body: Partial<ProductService>): Promise<ProductService> => {
    if (id == null) return api.tenant.post<ProductService>("/api/product_services/", body)
    return api.tenant.patch<ProductService>(`/api/product_services/${id}/`, body)
  },
  deleteProductService: (id: number) =>
    api.tenant.delete(`/api/product_services/${id}/`),

  // Invoice lines (cross-link from product)
  listInvoiceLines: async (params?: AnyParams): Promise<unknown[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<unknown[] | PaginatedListResponse<unknown>>(
      `/api/invoice_lines/${qs}`,
    )
    return unwrapList(data as never)
  },

  // NotaFiscalItem (cross-link from product)
  listNotaFiscalItems: async (params?: AnyParams): Promise<unknown[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<unknown[] | PaginatedListResponse<unknown>>(
      `/api/nfe-itens/${qs}`,
    )
    return unwrapList(data as never)
  },

  // PS categories
  listProductServiceCategories: async (params?: AnyParams): Promise<ProductServiceCategory[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<ProductServiceCategory[] | PaginatedListResponse<ProductServiceCategory>>(
      `/api/product_service_categories/${qs}`,
    )
    return unwrapList(data as never)
  },
  saveProductServiceCategory: (id: number | null, body: Partial<ProductServiceCategory>): Promise<ProductServiceCategory> => {
    if (id == null) return api.tenant.post<ProductServiceCategory>("/api/product_service_categories/", body)
    return api.tenant.patch<ProductServiceCategory>(`/api/product_service_categories/${id}/`, body)
  },
  deleteProductServiceCategory: (id: number) =>
    api.tenant.delete(`/api/product_service_categories/${id}/`),

  // ============================================================
  // BusinessPartnerGroup
  // ============================================================
  listBusinessPartnerGroups: async (params?: AnyParams): Promise<BusinessPartnerGroup[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartnerGroup[] | PaginatedListResponse<BusinessPartnerGroup>>(
      `/api/business-partner-groups/${qs}`,
    )
    return unwrapList(data as never)
  },
  getBusinessPartnerGroup: (id: number): Promise<BusinessPartnerGroup> =>
    api.tenant.get<BusinessPartnerGroup>(`/api/business-partner-groups/${id}/`),
  saveBusinessPartnerGroup: (id: number | null, body: Partial<BusinessPartnerGroup>): Promise<BusinessPartnerGroup> => {
    if (id == null) return api.tenant.post<BusinessPartnerGroup>("/api/business-partner-groups/", body)
    return api.tenant.patch<BusinessPartnerGroup>(`/api/business-partner-groups/${id}/`, body)
  },
  deleteBusinessPartnerGroup: (id: number) =>
    api.tenant.delete(`/api/business-partner-groups/${id}/`),
  promoteGroupPrimary: (groupId: number, membershipId: number): Promise<BusinessPartnerGroup> =>
    api.tenant.post<BusinessPartnerGroup>(
      `/api/business-partner-groups/${groupId}/promote-primary/`,
      { membership_id: membershipId },
    ),
  mergeGroup: (targetId: number, sourceGroupId: number): Promise<BusinessPartnerGroup> =>
    api.tenant.post<BusinessPartnerGroup>(
      `/api/business-partner-groups/${targetId}/merge/`,
      { source_group_id: sourceGroupId },
    ),
  listCnpjRootClusters: (): Promise<CnpjRootClustersResponse> =>
    api.tenant.get<CnpjRootClustersResponse>(
      `/api/business-partner-groups/cnpj-root-clusters/`,
    ),
  materializeCnpjRoot: (cnpjRoot: string): Promise<BusinessPartnerGroup> =>
    api.tenant.post<BusinessPartnerGroup>(
      `/api/business-partner-groups/materialize-cnpj-root/`,
      { cnpj_root: cnpjRoot },
    ),

  // ============================================================
  // BusinessPartnerGroupMembership
  // ============================================================
  listGroupMemberships: async (params?: AnyParams): Promise<BusinessPartnerGroupMembership[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartnerGroupMembership[] | PaginatedListResponse<BusinessPartnerGroupMembership>>(
      `/api/business-partner-group-memberships/${qs}`,
    )
    return unwrapList(data as never)
  },
  acceptMembership: (id: number): Promise<BusinessPartnerGroupMembership> =>
    api.tenant.post<BusinessPartnerGroupMembership>(
      `/api/business-partner-group-memberships/${id}/accept/`, {},
    ),
  rejectMembership: (id: number): Promise<BusinessPartnerGroupMembership> =>
    api.tenant.post<BusinessPartnerGroupMembership>(
      `/api/business-partner-group-memberships/${id}/reject/`, {},
    ),
  deleteMembership: (id: number) =>
    api.tenant.delete(`/api/business-partner-group-memberships/${id}/`),

  // ============================================================
  // BusinessPartnerAlias
  // ============================================================
  listBusinessPartnerAliases: async (params?: AnyParams): Promise<BusinessPartnerAlias[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<BusinessPartnerAlias[] | PaginatedListResponse<BusinessPartnerAlias>>(
      `/api/business-partner-aliases/${qs}`,
    )
    return unwrapList(data as never)
  },
  acceptAlias: (id: number): Promise<BusinessPartnerAlias> =>
    api.tenant.post<BusinessPartnerAlias>(`/api/business-partner-aliases/${id}/accept/`, {}),
  rejectAlias: (id: number): Promise<BusinessPartnerAlias> =>
    api.tenant.post<BusinessPartnerAlias>(`/api/business-partner-aliases/${id}/reject/`, {}),

  // ============================================================
  // BP consolidated view (Leroy-Merlin pattern)
  // ============================================================
  listConsolidatedBPs: (params?: AnyParams): Promise<ConsolidatedBPResponse> => {
    const qs = toQueryString(params)
    return api.tenant.get<ConsolidatedBPResponse>(
      `/api/business_partners/consolidated/${qs}`,
    )
  },

  // ============================================================
  // ProductServiceGroup -- mirror of BP groups for the product side.
  // Auto-discovered by ``manage.py suggest_product_groups``; the UI
  // here is just for review (accept / reject suggested members).
  // ============================================================
  listProductServiceGroups: async (params?: AnyParams): Promise<ProductServiceGroup[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<ProductServiceGroup[] | PaginatedListResponse<ProductServiceGroup>>(
      `/api/product-service-groups/${qs}`,
    )
    return unwrapList(data as never)
  },
  promoteProductGroupPrimary: (groupId: number, membershipId: number): Promise<ProductServiceGroup> =>
    api.tenant.post<ProductServiceGroup>(
      `/api/product-service-groups/${groupId}/promote-primary/`,
      { membership_id: membershipId },
    ),

  listProductGroupMemberships: async (params?: AnyParams): Promise<ProductServiceGroupMembership[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<ProductServiceGroupMembership[] | PaginatedListResponse<ProductServiceGroupMembership>>(
      `/api/product-service-group-memberships/${qs}`,
    )
    return unwrapList(data as never)
  },
  acceptProductMembership: (id: number): Promise<ProductServiceGroupMembership> =>
    api.tenant.post<ProductServiceGroupMembership>(
      `/api/product-service-group-memberships/${id}/accept/`, {},
    ),
  rejectProductMembership: (id: number): Promise<ProductServiceGroupMembership> =>
    api.tenant.post<ProductServiceGroupMembership>(
      `/api/product-service-group-memberships/${id}/reject/`, {},
    ),
  deleteProductMembership: (id: number) =>
    api.tenant.delete(`/api/product-service-group-memberships/${id}/`),

  listProductServiceAliases: async (params?: AnyParams): Promise<ProductServiceAlias[]> => {
    const qs = toQueryString(params)
    const data = await api.tenant.get<ProductServiceAlias[] | PaginatedListResponse<ProductServiceAlias>>(
      `/api/product-service-aliases/${qs}`,
    )
    return unwrapList(data as never)
  },
  acceptProductAlias: (id: number): Promise<ProductServiceAlias> =>
    api.tenant.post<ProductServiceAlias>(`/api/product-service-aliases/${id}/accept/`, {}),
  rejectProductAlias: (id: number): Promise<ProductServiceAlias> =>
    api.tenant.post<ProductServiceAlias>(`/api/product-service-aliases/${id}/reject/`, {}),
}
