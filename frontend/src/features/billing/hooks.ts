import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useTenant } from "@/providers/TenantProvider"
import { extractApiErrorMessage } from "@/lib/api-client"
import { billingApi } from "./api"
import type { BillingTenantConfig, Invoice, NFTransactionLink } from "./types"

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
