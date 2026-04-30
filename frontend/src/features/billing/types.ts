// Generated types for the billing feature module.
// Mirrors backend serializer shapes — keep in sync with billing/serializers.py.

export type InvoiceStatus =
  | "draft"
  | "issued"
  | "partially_paid"
  | "paid"
  | "canceled"

export type InvoiceFiscalStatus =
  | "pending_nf"
  | "invoiced"
  | "partially_returned"
  | "fully_returned"
  | "fiscally_cancelled"
  | "mixed"

export type LinkReviewStatus = "suggested" | "accepted" | "rejected"

export type LinkMethod =
  | "nf_number"
  | "description_regex"
  | "bank_description"
  | "manual"
  | "backfill"

export type InvoiceNFRelation =
  | "normal"
  | "devolucao"
  | "complementar"
  | "ajuste"

export interface Invoice {
  id: number
  company: number
  partner: number
  partner_name?: string
  partner_identifier?: string
  contract: number | null
  invoice_type: "sale" | "purchase"
  invoice_number: string
  invoice_date: string
  due_date: string
  status: InvoiceStatus
  fiscal_status: InvoiceFiscalStatus
  has_pending_corrections: boolean
  fiscal_status_computed_at: string | null
  total_amount: string
  tax_amount: string
  discount_amount: string
  currency: number | null
  description: string
  erp_id: string | null
  critics_count?: number
  critics_count_by_severity?: { error?: number; warning?: number; info?: number }
}

export interface InvoiceDetail extends Invoice {
  partner_name: string
  partner_identifier: string
  contract_number: string | null
  lines: InvoiceLine[]
  nf_attachments: InvoiceNFLink[]
}

export interface InvoiceLine {
  id: number
  invoice: number
  product_service: number
  description: string
  quantity: string
  unit_price: string
  total_price: string
  tax_amount: string
}

export interface InvoiceLineWithContext {
  id: number
  invoice: number
  invoice_number: string
  invoice_date: string
  invoice_status: string
  invoice_partner: string
  product_service: number | null
  product_service_name: string | null
  product_service_code: string | null
  description: string
  quantity: string
  unit_price: string
  total_price: string
  tax_amount: string
}

export interface NotaFiscalItem {
  id: number
  nota_fiscal: number
  numero_item: number
  codigo_produto: string
  ean: string
  descricao: string
  ncm: string
  cfop: string
  unidade: string
  quantidade: string
  valor_unitario: string
  valor_total: string
  produto: number | null
  produto_nome: string | null
}

export interface NFTransactionLink {
  id: number
  company: number
  transaction: number
  nota_fiscal: number
  allocated_amount: string | null
  confidence: string
  method: LinkMethod
  matched_fields: string[]
  review_status: LinkReviewStatus
  reviewed_by: number | null
  reviewed_at: string | null
  notes: string
  tx_amount_snapshot: string | null
  nf_valor_snapshot: string | null
  // Denormalized fields for the review UI
  transaction_amount: string | null
  transaction_date: string | null
  transaction_description: string | null
  transaction_nf_number: string | null
  transaction_cnpj: string | null
  nf_numero: number
  nf_chave: string
  nf_data_emissao: string
  nf_valor_nota: string
  nf_emit_nome: string
  nf_emit_cnpj: string
  nf_dest_nome: string
  nf_dest_cnpj: string
  is_stale: boolean
  /** Populated when matched_fields contains 'cnpj_group' — the BPs on
   *  each side share an accepted BusinessPartnerGroup. The review row
   *  uses this to wire the "Ver grupo" badge to GroupDetailModal. */
  cnpj_group_id: number | null
  created_at: string
  updated_at: string
}

export interface InvoiceNFLink {
  id: number
  company: number
  invoice: number
  nota_fiscal: number
  relation_type: InvoiceNFRelation
  allocated_amount: string | null
  notes: string
  nf_numero: number
  nf_chave: string
  nf_data_emissao: string
  nf_valor_nota: string
  nf_finalidade: number
  nf_status_sefaz: string
  invoice_number: string
  invoice_date: string
  invoice_total_amount: string
  created_at: string
  updated_at: string
}

export interface NotaFiscal {
  id: number
  company: number
  chave: string
  numero: number
  serie: number
  modelo: number
  tipo_operacao: 0 | 1
  finalidade: 1 | 2 | 3 | 4
  natureza_operacao: string
  data_emissao: string
  data_saida_entrada: string | null
  emit_cnpj: string
  emit_nome: string
  emitente: number | null
  dest_cnpj: string
  dest_nome: string
  destinatario: number | null
  valor_nota: string
  valor_produtos: string
  valor_icms: string
  valor_pis: string
  valor_cofins: string
  valor_ipi: string
  valor_desconto: string
  status_sefaz: string
  motivo_sefaz: string
  data_autorizacao: string | null
  inventory_processing_status: "pending" | "processed" | "all_skipped" | "error"
}

export interface BusinessPartner {
  id: number
  company: number
  erp_id: string | null
  name: string
  identifier: string
  cnpj_root: string
  partner_type: "client" | "vendor" | "both"
  category: number | null
  receivable_account: number | null
  payable_account: number | null
  address: string
  city: string
  state: string
  zipcode: string
  country: string
  email: string
  phone: string
  currency: number | null
  payment_terms: string
  is_active: boolean
  created_at: string
  updated_at: string
  // Group context — populated by the BusinessPartnerSerializer when the BP
  // has an accepted group membership. null otherwise.
  group_id: number | null
  group_primary_partner_id: number | null
  group_role: "primary" | "member" | null
}

export interface BusinessPartnerCategory {
  id: number
  company: number
  name: string
  parent: number | null
  parent_id: number | null
  level: number
  path: string
  erp_id: string | null
}

export interface ProductService {
  id: number
  company: number
  erp_id: string | null
  name: string
  code: string
  category: number | null
  description: string
  item_type: "product" | "service"
  price: string
  cost: string | null
  currency: number | null
  tax_code: string
  track_inventory: boolean
  stock_quantity: string
  is_active: boolean
  inventory_account: number | null
  cogs_account: number | null
  adjustment_account: number | null
  revenue_account: number | null
  purchase_account: number | null
  discount_given_account: number | null
  created_at: string
  updated_at: string
}

export interface ProductServiceCategory {
  id: number
  company: number
  name: string
  parent: number | null
  erp_id: string | null
}

export interface BillingTenantConfig {
  id: number
  company: number
  auto_create_invoice_from_nf: boolean
  auto_create_invoice_for_finalidades: number[]
  auto_create_invoice_for_tipos: number[]
  auto_link_nf_to_transactions: boolean
  auto_accept_link_above: string
  link_date_window_days: number
  link_amount_tolerance_pct: string
  default_receivable_account: number | null
  default_payable_account: number | null
}

export interface ScanCounters {
  created: number
  updated: number
  skipped_existing_protected: number
  auto_accepted: number
}

export interface ScanResponse {
  candidates: number
  persisted: ScanCounters
  dry_run: boolean
}

export interface PaginatedListResponse<T> {
  count?: number
  next?: string | null
  previous?: string | null
  results?: T[]
}

export type CriticSeverity = "info" | "warning" | "error"

export type CriticKind =
  | "over_returned"
  | "quantity_over_returned"
  | "unit_price_drift"
  | "bundle_expansion_suspected"
  | "ncm_drift"
  | "produto_unresolved"
  | string

export interface Critic {
  kind: CriticKind
  severity: CriticSeverity
  message: string
  subject_type: "invoice" | "nota_fiscal" | "nota_fiscal_item"
  subject_id: number
  evidence: Record<string, unknown>
  acknowledged?: boolean
  acknowledged_at?: string | null
  acknowledged_by_email?: string | null
  acknowledged_note?: string
}

export interface CriticsResponse {
  count: number
  total_including_acknowledged?: number
  by_severity: { error: number; warning: number; info: number }
  items: Critic[]
}

export interface CriticAuditInvoiceRow {
  invoice_id: number
  invoice_number: string
  partner_id: number | null
  total_amount: string
  fiscal_status: InvoiceFiscalStatus
  count: number
  by_severity: { error?: number; warning?: number; info?: number }
  items: Critic[]
}

export interface CriticAuditResponse {
  started_at: string
  completed_at: string
  swept: number
  invoices_with_critics_count: number
  by_severity: Record<string, number>
  by_kind: Record<string, number>
  results: CriticAuditInvoiceRow[]
}

// =====================================================
// BusinessPartnerGroup / Membership / Alias
// =====================================================

export type GroupReviewStatus = "suggested" | "accepted" | "rejected"
export type GroupRole = "primary" | "member"

export interface BusinessPartnerGroupMembership {
  id: number
  company: number
  group: number
  business_partner: number
  role: GroupRole
  review_status: GroupReviewStatus
  confidence: string
  hit_count: number
  evidence: Array<{
    method?: string
    source?: string
    source_id?: number | null
    at?: string
    confidence?: string
    kind?: string
  }>
  reviewed_by: number | null
  reviewed_at: string | null
  // Denormalized for the review UI
  business_partner_name: string
  business_partner_identifier: string
  business_partner_partner_type: "client" | "vendor" | "both"
  group_name: string
  group_primary_partner_id: number
  created_at: string
  updated_at: string
}

export interface BusinessPartnerGroup {
  id: number
  company: number
  name: string
  description: string
  is_active: boolean
  primary_partner: number
  primary_partner_name: string
  primary_partner_identifier: string
  memberships: BusinessPartnerGroupMembership[]
  member_count: number
  accepted_member_count: number
  created_at: string
  updated_at: string
}

export type AliasReviewStatus = "suggested" | "accepted" | "rejected"

export interface BusinessPartnerAlias {
  id: number
  company: number
  business_partner: number
  alias_identifier: string
  review_status: AliasReviewStatus
  source: string
  confidence: string
  hit_count: number
  last_used_at: string | null
  evidence: Array<{
    source?: string
    source_id?: number | null
    at?: string
    confidence?: string
  }>
  reviewed_by: number | null
  reviewed_at: string | null
  business_partner_name: string
  business_partner_identifier: string
  created_at: string
  updated_at: string
}

export interface ConsolidatedBPRow {
  kind: "group" | "standalone"
  primary: BusinessPartner
  members: BusinessPartner[]
  group_id: number | null
}

export interface ConsolidatedBPResponse {
  count: number
  results: ConsolidatedBPRow[]
}

/** Auto-derived matriz/filial cluster — same cnpj_root, no explicit Group yet. */
export interface CnpjRootCluster {
  cnpj_root: string
  size: number
  primary: BusinessPartner
  members: BusinessPartner[]
}

export interface CnpjRootClustersResponse {
  count: number
  results: CnpjRootCluster[]
}
