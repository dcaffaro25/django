import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useTenant } from "@/providers/TenantProvider"
import { extractApiErrorMessage } from "@/lib/api-client"
import { billingApi } from "./api"
import type {
  BillingTenantConfig, BusinessPartner, BusinessPartnerCategory,
  Invoice, InvoiceLineWithContext, NFTransactionLink, NotaFiscal,
  NotaFiscalItem, ProductService, ProductServiceCategory,
} from "./types"

const qk = {
  invoices: (sub: string, params?: unknown) => ["billing", sub, "invoices", params] as const,
  invoice: (sub: string, id: number) => ["billing", sub, "invoice", id] as const,
  nfList: (sub: string, params?: unknown) => ["billing", sub, "nfe", params] as const,
  nf: (sub: string, id: number) => ["billing", sub, "nfe", id] as const,
  nfTxLinks: (sub: string, params?: unknown) => ["billing", sub, "nf-tx-links", params] as const,
  invoiceNfLinks: (sub: string, params?: unknown) =>
    ["billing", sub, "invoice-nf-links", params] as const,
  config: (sub: string) => ["billing", sub, "config"] as const,
  partners: (sub: string, params?: unknown) => ["billing", sub, "partners", params] as const,
}

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

function showError(prefix: string, error: unknown) {
  const detail = extractApiErrorMessage(error) || "Erro inesperado."
  toast.error(`${prefix}: ${detail}`)
}

// ============================================================
// Invoices
// ============================================================
export function useInvoices(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: qk.invoices(sub, params),
    queryFn: () => billingApi.listInvoices(params),
    enabled: !!sub,
  })
}

export function useInvoice(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? qk.invoice(sub, id) : ["billing", sub, "invoice", "none"],
    queryFn: () => billingApi.getInvoice(id as number),
    enabled: !!sub && id != null,
  })
}

export function useSaveInvoice() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<Invoice> }) =>
      billingApi.saveInvoice(id, body),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      qc.invalidateQueries({ queryKey: qk.invoice(sub, saved.id) })
      toast.success("Fatura salva.")
    },
    onError: (e) => showError("Falha ao salvar fatura", e),
  })
}

export function useDeleteInvoice() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteInvoice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Fatura removida.")
    },
    onError: (e) => showError("Falha ao remover fatura", e),
  })
}

export function useAttachNfToInvoice() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({
      invoiceId,
      ...body
    }: { invoiceId: number; nota_fiscal: number; relation_type?: string; allocated_amount?: number; notes?: string }) =>
      billingApi.attachNfToInvoice(invoiceId, body),
    onSuccess: (link) => {
      qc.invalidateQueries({ queryKey: qk.invoice(sub, link.invoice) })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoice-nf-links"] })
      toast.success("NF vinculada à fatura.")
    },
    onError: (e) => showError("Falha ao vincular NF", e),
  })
}

export function useInvoiceCritics(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? ["billing", sub, "invoice-critics", id] : ["billing", sub, "invoice-critics", "none"],
    queryFn: () => billingApi.getInvoiceCritics(id as number),
    enabled: !!sub && id != null,
  })
}

export function useAcknowledgeCritic() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ invoiceId, ...body }: {
      invoiceId: number; kind: string; subject_type: string;
      subject_id: number; note?: string;
    }) => billingApi.acknowledgeCritic(invoiceId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoice-critics", vars.invoiceId] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Crítica aceita.")
    },
    onError: (e) => showError("Falha ao aceitar crítica", e),
  })
}

export function useUnacknowledgeCritic() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ invoiceId, ...body }: {
      invoiceId: number; kind: string; subject_type: string; subject_id: number;
    }) => billingApi.unacknowledgeCritic(invoiceId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoice-critics", vars.invoiceId] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Aceite removido.")
    },
    onError: (e) => showError("Falha ao remover aceite", e),
  })
}

export function useAuditCritics() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (body?: Parameters<typeof billingApi.auditCritics>[0]) =>
      billingApi.auditCritics(body),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoice-critics"] })
      toast.success(
        `Auditoria: ${res.swept} faturas analisadas, ${res.invoices_with_critics_count} com críticas.`,
      )
    },
    onError: (e) => showError("Falha na auditoria", e),
  })
}

export function useRefreshFiscalStatus() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (invoiceId: number) => billingApi.refreshFiscalStatus(invoiceId),
    onSuccess: (inv) => {
      qc.invalidateQueries({ queryKey: qk.invoice(sub, inv.id) })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Status fiscal recalculado.")
    },
    onError: (e) => showError("Falha ao recalcular status fiscal", e),
  })
}

// ============================================================
// NotaFiscal
// ============================================================
export function useNotasFiscais(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: qk.nfList(sub, params),
    queryFn: () => billingApi.listNotasFiscais(params),
    enabled: !!sub,
  })
}

export function useNotaFiscal(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? qk.nf(sub, id) : ["billing", sub, "nfe", "none"],
    queryFn: () => billingApi.getNotaFiscal(id as number),
    enabled: !!sub && id != null,
  })
}

// ============================================================
// NFTransactionLink (review)
// ============================================================
export function useNfTxLinks(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: qk.nfTxLinks(sub, params),
    queryFn: () => billingApi.listNfTxLinks(params),
    enabled: !!sub,
  })
}

export function useAcceptLink() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes?: string }) =>
      billingApi.acceptLink(id, notes),
    onMutate: async ({ id }) => {
      // Optimistic update on suggested→accepted
      await qc.cancelQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      const previous = qc.getQueriesData<NFTransactionLink[]>({ queryKey: ["billing", sub, "nf-tx-links"] })
      previous.forEach(([key, data]) => {
        if (!data) return
        qc.setQueryData(
          key,
          data.map((l) => (l.id === id ? { ...l, review_status: "accepted" } : l)),
        )
      })
      return { previous }
    },
    onError: (e, _vars, ctx) => {
      ctx?.previous?.forEach(([key, data]) => qc.setQueryData(key, data))
      showError("Falha ao aceitar vínculo", e)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
    },
  })
}

export function useRejectLink() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes?: string }) =>
      billingApi.rejectLink(id, notes),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      const previous = qc.getQueriesData<NFTransactionLink[]>({ queryKey: ["billing", sub, "nf-tx-links"] })
      previous.forEach(([key, data]) => {
        if (!data) return
        qc.setQueryData(
          key,
          data.map((l) => (l.id === id ? { ...l, review_status: "rejected" } : l)),
        )
      })
      return { previous }
    },
    onError: (e, _vars, ctx) => {
      ctx?.previous?.forEach(([key, data]) => qc.setQueryData(key, data))
      showError("Falha ao rejeitar vínculo", e)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
    },
  })
}

export function useScanLinks() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (body: Parameters<typeof billingApi.scanLinks>[0]) =>
      billingApi.scanLinks(body),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      const c = res.persisted
      const note = res.dry_run ? " (simulação)" : ""
      toast.success(
        `Scan: ${res.candidates} candidatos · criados ${c.created} · atualizados ${c.updated} · auto-aceitos ${c.auto_accepted}${note}`,
      )
    },
    onError: (e) => showError("Falha ao rodar scan", e),
  })
}

export function useAcceptAllAbove() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (confidence: number | string) => billingApi.acceptAllAbove(confidence),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success(`${res.accepted} vínculos aceitos.`)
    },
    onError: (e) => showError("Falha em aceite em massa", e),
  })
}

export function useBulkAcceptLinks() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (ids: number[]) => billingApi.bulkAcceptLinks(ids),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-group-memberships"] })
      toast.success(`${res.count} vínculos aceitos.`)
    },
    onError: (e) => showError("Falha em aceite em massa", e),
  })
}

export function useBulkRejectLinks() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (ids: number[]) => billingApi.bulkRejectLinks(ids),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      toast.success(`${res.count} vínculos rejeitados.`)
    },
    onError: (e) => showError("Falha ao rejeitar em massa", e),
  })
}

export function useCreateManualLink() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (body: Parameters<typeof billingApi.createManualLink>[0]) =>
      billingApi.createManualLink(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "nf-tx-links"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Vínculo manual criado.")
    },
    onError: (e) => showError("Falha ao criar vínculo manual", e),
  })
}

// ============================================================
// InvoiceNFLink
// ============================================================
export function useInvoiceNfLinks(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: qk.invoiceNfLinks(sub, params),
    queryFn: () => billingApi.listInvoiceNfLinks(params),
    enabled: !!sub,
  })
}

export function useDeleteInvoiceNfLink() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteInvoiceNfLink(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoice-nf-links"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "invoices"] })
      toast.success("Vínculo Invoice↔NF removido.")
    },
    onError: (e) => showError("Falha ao remover vínculo", e),
  })
}

// ============================================================
// BillingTenantConfig
// ============================================================
export function useBillingConfig() {
  const sub = useSub()
  return useQuery({
    queryKey: qk.config(sub),
    queryFn: () => billingApi.getConfig(),
    enabled: !!sub,
  })
}

export function useSaveBillingConfig() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (body: Partial<BillingTenantConfig>) => billingApi.saveConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.config(sub) })
      toast.success("Configuração salva.")
    },
    onError: (e) => showError("Falha ao salvar configuração", e),
  })
}

// ============================================================
// BusinessPartner
// ============================================================
export function useBusinessPartners(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: qk.partners(sub, params),
    queryFn: () => billingApi.listBusinessPartners(params),
    enabled: !!sub,
  })
}

export function useBusinessPartner(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? ["billing", sub, "partner", id] : ["billing", sub, "partner", "none"],
    queryFn: () => billingApi.getBusinessPartner(id as number),
    enabled: !!sub && id != null,
  })
}

export function useSaveBusinessPartner() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<BusinessPartner> }) =>
      billingApi.saveBusinessPartner(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "partner"] })
      toast.success("Parceiro salvo.")
    },
    onError: (e) => showError("Falha ao salvar parceiro", e),
  })
}

export function useDeleteBusinessPartner() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteBusinessPartner(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      toast.success("Parceiro removido.")
    },
    onError: (e) => showError("Falha ao remover parceiro", e),
  })
}

// BP categories
export function useBusinessPartnerCategories() {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-categories"],
    queryFn: () => billingApi.listBusinessPartnerCategories(),
    enabled: !!sub,
  })
}

export function useSaveBusinessPartnerCategory() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<BusinessPartnerCategory> }) =>
      billingApi.saveBusinessPartnerCategory(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-categories"] })
      toast.success("Categoria salva.")
    },
    onError: (e) => showError("Falha ao salvar categoria", e),
  })
}

export function useDeleteBusinessPartnerCategory() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteBusinessPartnerCategory(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-categories"] })
      toast.success("Categoria removida.")
    },
    onError: (e) => showError("Falha ao remover categoria", e),
  })
}

// ============================================================
// Cross-link queries (BP→Invoices/NFs, PS→Lines/Items)
// ============================================================
export function useInvoicesByPartner(partnerId: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "invoices-by-partner", partnerId],
    queryFn: () => billingApi.listInvoices({ partner: partnerId as number }),
    enabled: !!sub && partnerId != null,
  })
}

export function useNFsByEmitente(partnerId: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "nfs-by-emitente", partnerId],
    queryFn: () => billingApi.listNotasFiscais({ emitente: partnerId as number }) as Promise<NotaFiscal[]>,
    enabled: !!sub && partnerId != null,
  })
}

export function useNFsByDestinatario(partnerId: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "nfs-by-destinatario", partnerId],
    queryFn: () => billingApi.listNotasFiscais({ destinatario: partnerId as number }) as Promise<NotaFiscal[]>,
    enabled: !!sub && partnerId != null,
  })
}

export function useInvoiceLinesByProduct(productId: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "invoice-lines-by-product", productId],
    queryFn: () => billingApi.listInvoiceLines({ product_service: productId as number }) as Promise<InvoiceLineWithContext[]>,
    enabled: !!sub && productId != null,
  })
}

export function useNFItemsByProduct(productId: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "nf-items-by-product", productId],
    queryFn: () => billingApi.listNotaFiscalItems({ produto: productId as number }) as Promise<NotaFiscalItem[]>,
    enabled: !!sub && productId != null,
  })
}

// ============================================================
// ProductService
// ============================================================
export function useProductServices(params?: Record<string, string | number | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "product-services", params],
    queryFn: () => billingApi.listProductServices(params),
    enabled: !!sub,
  })
}

export function useProductService(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? ["billing", sub, "product-service", id] : ["billing", sub, "product-service", "none"],
    queryFn: () => billingApi.getProductService(id as number),
    enabled: !!sub && id != null,
  })
}

export function useSaveProductService() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<ProductService> }) =>
      billingApi.saveProductService(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "product-services"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "product-service"] })
      toast.success("Produto/Serviço salvo.")
    },
    onError: (e) => showError("Falha ao salvar produto/serviço", e),
  })
}

export function useDeleteProductService() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteProductService(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "product-services"] })
      toast.success("Produto/Serviço removido.")
    },
    onError: (e) => showError("Falha ao remover produto/serviço", e),
  })
}

// PS categories
export function useProductServiceCategories() {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "ps-categories"],
    queryFn: () => billingApi.listProductServiceCategories(),
    enabled: !!sub,
  })
}

export function useSaveProductServiceCategory() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<ProductServiceCategory> }) =>
      billingApi.saveProductServiceCategory(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "ps-categories"] })
      toast.success("Categoria salva.")
    },
    onError: (e) => showError("Falha ao salvar categoria", e),
  })
}

export function useDeleteProductServiceCategory() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.deleteProductServiceCategory(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "ps-categories"] })
      toast.success("Categoria removida.")
    },
    onError: (e) => showError("Falha ao remover categoria", e),
  })
}

// ============================================================
// BusinessPartnerGroup / Membership / Alias
// ============================================================

export function useBusinessPartnerGroups(params?: Record<string, string | number | boolean | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-groups", params],
    queryFn: () => billingApi.listBusinessPartnerGroups(params),
    enabled: !!sub,
  })
}

export function useBusinessPartnerGroup(id: number | null | undefined) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? ["billing", sub, "bp-group", id] : ["billing", sub, "bp-group", "none"],
    queryFn: () => billingApi.getBusinessPartnerGroup(id as number),
    enabled: !!sub && id != null,
  })
}

export function usePromoteGroupPrimary() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ groupId, membershipId }: { groupId: number; membershipId: number }) =>
      billingApi.promoteGroupPrimary(groupId, membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-groups"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-group"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      toast.success("Primary do grupo atualizado.")
    },
    onError: (e) => showError("Falha ao promover primary", e),
  })
}

export function useMergeGroup() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ targetId, sourceGroupId }: { targetId: number; sourceGroupId: number }) =>
      billingApi.mergeGroup(targetId, sourceGroupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-groups"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-group-memberships"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      toast.success("Grupos mesclados.")
    },
    onError: (e) => showError("Falha ao mesclar grupos", e),
  })
}

export function useGroupMemberships(params?: Record<string, string | number | boolean | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-group-memberships", params],
    queryFn: () => billingApi.listGroupMemberships(params),
    enabled: !!sub,
  })
}

export function useAcceptMembership() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.acceptMembership(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-group-memberships"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-groups"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      toast.success("Membership aceito.")
    },
    onError: (e) => showError("Falha ao aceitar membership", e),
  })
}

export function useRejectMembership() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.rejectMembership(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-group-memberships"] })
      toast.success("Membership rejeitado.")
    },
    onError: (e) => showError("Falha ao rejeitar membership", e),
  })
}

export function useBusinessPartnerAliases(params?: Record<string, string | number | boolean | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-aliases", params],
    queryFn: () => billingApi.listBusinessPartnerAliases(params),
    enabled: !!sub,
  })
}

export function useAcceptAlias() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.acceptAlias(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-aliases"] })
      toast.success("Apelido aceito.")
    },
    onError: (e) => showError("Falha ao aceitar apelido", e),
  })
}

export function useRejectAlias() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => billingApi.rejectAlias(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-aliases"] })
      toast.success("Apelido rejeitado.")
    },
    onError: (e) => showError("Falha ao rejeitar apelido", e),
  })
}

export function useConsolidatedBPs(params?: Record<string, string | number | boolean | undefined>) {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-consolidated", params],
    queryFn: () => billingApi.listConsolidatedBPs(params),
    enabled: !!sub,
  })
}

export function useCnpjRootClusters() {
  const sub = useSub()
  return useQuery({
    queryKey: ["billing", sub, "bp-cnpj-root-clusters"],
    queryFn: () => billingApi.listCnpjRootClusters(),
    enabled: !!sub,
  })
}

export function useMaterializeCnpjRoot() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (cnpjRoot: string) => billingApi.materializeCnpjRoot(cnpjRoot),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-cnpj-root-clusters"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "bp-groups"] })
      qc.invalidateQueries({ queryKey: ["billing", sub, "partners"] })
      toast.success("Grupo materializado a partir da raiz CNPJ.")
    },
    onError: (e) => showError("Falha ao materializar grupo", e),
  })
}
