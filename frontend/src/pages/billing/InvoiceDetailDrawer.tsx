import { useMemo, useState } from "react"
import {
  Calendar, FileText, Plus, RefreshCw, Trash2, Receipt, Wallet,
  ArrowDownToLine, ArrowUpFromLine,
} from "lucide-react"
import { Drawer } from "@/components/ui/drawer"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  useAttachNfToInvoice, useDeleteInvoiceNfLink, useInvoice,
  useNotasFiscais, useRefreshFiscalStatus,
} from "@/features/billing"
import type { InvoiceNFRelation } from "@/features/billing"
import { FiscalStatusBadge } from "./components/FiscalStatusBadge"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency, formatDate, formatDateTime } from "@/lib/utils"

const RELATION_LABEL: Record<InvoiceNFRelation, string> = {
  normal: "Normal",
  devolucao: "Devolução",
  complementar: "Complementar",
  ajuste: "Ajuste",
}

function fmtCnpj(d?: string | null) {
  if (!d) return ""
  const s = d.replace(/\D/g, "")
  if (s.length !== 14) return d
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`
}

function AttachNfModal({
  open,
  onClose,
  invoiceId,
}: {
  open: boolean
  onClose: () => void
  invoiceId: number
}) {
  const [search, setSearch] = useState("")
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [relation, setRelation] = useState<InvoiceNFRelation>("normal")
  const [allocated, setAllocated] = useState("")
  const [notes, setNotes] = useState("")

  const { data: nfs, isLoading } = useNotasFiscais()
  const filtered = useMemo(() => {
    if (!nfs) return []
    if (!search) return nfs.slice(0, 30)
    const q = search.toLowerCase()
    return nfs
      .filter((n) =>
        [
          String(n.numero),
          n.chave,
          n.emit_nome,
          n.dest_nome,
          n.emit_cnpj,
          n.dest_cnpj,
        ].some((s) => (s ?? "").toLowerCase().includes(q)),
      )
      .slice(0, 30)
  }, [nfs, search])

  const attach = useAttachNfToInvoice()

  const submit = async () => {
    if (!selectedId) return
    await attach.mutateAsync({
      invoiceId,
      nota_fiscal: selectedId,
      relation_type: relation,
      allocated_amount: allocated ? Number(allocated) : undefined,
      notes,
    })
    setSelectedId(null)
    setAllocated("")
    setNotes("")
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Vincular Nota Fiscal</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="nf-search">Buscar NF</Label>
            <Input
              id="nf-search"
              placeholder="Número, chave, CNPJ ou nome do parceiro…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
          </div>
          <div className="max-h-[280px] overflow-auto rounded-md border border-border">
            {isLoading ? (
              <div className="p-4 text-center text-muted-foreground">
                Carregando NFs…
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">
                Nenhuma NF encontrada.
              </div>
            ) : (
              <ul>
                {filtered.map((n) => (
                  <li
                    key={n.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-2 border-b border-border/40 px-3 py-2 text-[12px] hover:bg-muted/40",
                      selectedId === n.id && "bg-info/10",
                    )}
                    onClick={() => setSelectedId(n.id)}
                  >
                    <input
                      type="radio"
                      checked={selectedId === n.id}
                      onChange={() => setSelectedId(n.id)}
                      className="mt-1"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="font-mono font-medium">NF {n.numero}</span>
                        <span className="font-medium tabular-nums">
                          {formatCurrency(n.valor_nota)}
                        </span>
                        <span className="text-muted-foreground">
                          {formatDate(n.data_emissao)}
                        </span>
                        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {n.tipo_operacao === 1 ? "Saída" : "Entrada"}
                          {" · "}
                          {["", "Normal", "Complementar", "Ajuste", "Devolução"][n.finalidade]}
                        </span>
                      </div>
                      <div className="mt-0.5 truncate text-muted-foreground">
                        {n.emit_nome} → {n.dest_nome}
                      </div>
                      <div className="truncate font-mono text-[10px] text-muted-foreground/70">
                        {n.chave}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Tipo de relação</Label>
              <Select
                value={relation}
                onValueChange={(v) => setRelation(v as InvoiceNFRelation)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(RELATION_LABEL) as InvoiceNFRelation[]).map((r) => (
                    <SelectItem key={r} value={r}>{RELATION_LABEL[r]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="alloc">Valor alocado (opcional)</Label>
              <Input
                id="alloc"
                type="number"
                step="0.01"
                value={allocated}
                onChange={(e) => setAllocated(e.target.value)}
                placeholder="Cobertura parcial"
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="notes">Observação</Label>
            <Input
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Opcional"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={submit}
            disabled={!selectedId || attach.isPending}
          >
            {attach.isPending ? "Vinculando…" : "Vincular"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function InvoiceDetailDrawer({
  invoiceId,
  onClose,
}: {
  invoiceId: number | null
  onClose: () => void
}) {
  const open = invoiceId != null
  const { data: invoice, isLoading } = useInvoice(invoiceId)
  const refresh = useRefreshFiscalStatus()
  const removeLink = useDeleteInvoiceNfLink()
  const [attachOpen, setAttachOpen] = useState(false)
  const { canWrite } = useUserRole()

  return (
    <Drawer open={open} onClose={onClose} title="Detalhe da Fatura" width="720px">
      <div className="space-y-4 p-4">
        {isLoading || !invoice ? (
          <div className="rounded-md border border-dashed border-border p-6 text-center text-muted-foreground">
            Carregando fatura…
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold">
                      Fatura {invoice.invoice_number}
                    </h3>
                    {invoice.invoice_type === "sale" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                        <ArrowUpFromLine className="h-3 w-3" /> Venda
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                        <ArrowDownToLine className="h-3 w-3" /> Compra
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[12px] text-muted-foreground">
                    {invoice.partner_name}
                    {invoice.partner_identifier ? (
                      <span className="ml-1 font-mono">({fmtCnpj(invoice.partner_identifier)})</span>
                    ) : null}
                  </div>
                  {invoice.contract_number ? (
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      Contrato: <span className="font-mono">{invoice.contract_number}</span>
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <div className="text-lg font-semibold tabular-nums">
                    {formatCurrency(invoice.total_amount)}
                  </div>
                  <FiscalStatusBadge
                    status={invoice.fiscal_status}
                    pendingCorrections={invoice.has_pending_corrections}
                  />
                </div>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-3 text-[12px] sm:grid-cols-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Emissão
                  </div>
                  <div className="flex items-center gap-1">
                    <Calendar className="h-3 w-3 text-muted-foreground" />
                    {formatDate(invoice.invoice_date)}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Vencimento
                  </div>
                  <div className="flex items-center gap-1">
                    <Calendar className="h-3 w-3 text-muted-foreground" />
                    {formatDate(invoice.due_date)}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Status pgto
                  </div>
                  <div className="capitalize">{invoice.status}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Impostos
                  </div>
                  <div className="tabular-nums">{formatCurrency(invoice.tax_amount)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Desconto
                  </div>
                  <div className="tabular-nums">{formatCurrency(invoice.discount_amount)}</div>
                </div>
                {invoice.fiscal_status_computed_at ? (
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      Status fiscal recalc.
                    </div>
                    <div title={invoice.fiscal_status_computed_at}>
                      {formatDateTime(invoice.fiscal_status_computed_at)}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => refresh.mutate(invoice.id)}
                  disabled={refresh.isPending}
                >
                  <RefreshCw
                    className={cn("h-3.5 w-3.5", refresh.isPending && "animate-spin")}
                  />
                  Recalcular status fiscal
                </Button>
                {canWrite ? (
                  <Button size="sm" onClick={() => setAttachOpen(true)}>
                    <Plus className="h-3.5 w-3.5" />
                    Vincular NF
                  </Button>
                ) : null}
              </div>
            </div>

            {/* Lines */}
            <section>
              <h4 className="mb-2 flex items-center gap-1 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
                <FileText className="h-3.5 w-3.5" />
                Itens ({invoice.lines?.length ?? 0})
              </h4>
              {invoice.lines && invoice.lines.length > 0 ? (
                <div className="rounded-md border border-border">
                  <table className="w-full text-[12px]">
                    <thead className="bg-muted/30 text-left text-[11px] text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5">Descrição</th>
                        <th className="px-2 py-1.5 text-right">Qtd.</th>
                        <th className="px-2 py-1.5 text-right">Unit.</th>
                        <th className="px-2 py-1.5 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoice.lines.map((l) => (
                        <tr key={l.id} className="border-t border-border/40">
                          <td className="px-2 py-1.5">
                            {l.description || `Item #${l.id}`}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums">
                            {Number(l.quantity).toLocaleString("pt-BR")}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums">
                            {formatCurrency(l.unit_price)}
                          </td>
                          <td className="px-2 py-1.5 text-right font-medium tabular-nums">
                            {formatCurrency(l.total_price)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-border p-3 text-center text-[12px] text-muted-foreground">
                  Sem itens registrados.
                </div>
              )}
            </section>

            {/* NF attachments */}
            <section>
              <h4 className="mb-2 flex items-center gap-1 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
                <Receipt className="h-3.5 w-3.5" />
                Notas Fiscais vinculadas ({invoice.nf_attachments?.length ?? 0})
              </h4>
              {invoice.nf_attachments && invoice.nf_attachments.length > 0 ? (
                <ul className="space-y-1.5">
                  {invoice.nf_attachments.map((att) => (
                    <li
                      key={att.id}
                      className="rounded-md border border-border bg-card p-2 text-[12px]"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-medium">NF {att.nf_numero}</span>
                            <span className="font-medium tabular-nums">
                              {formatCurrency(att.nf_valor_nota)}
                            </span>
                            <span className="text-muted-foreground">
                              {formatDate(att.nf_data_emissao)}
                            </span>
                            <span className="rounded-full bg-info/10 px-1.5 py-0.5 text-[10px] text-info">
                              {RELATION_LABEL[att.relation_type]}
                            </span>
                            {att.nf_finalidade === 4 ? (
                              <span className="rounded-full bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">
                                devolução
                              </span>
                            ) : null}
                          </div>
                          {att.allocated_amount ? (
                            <div className="text-muted-foreground">
                              Cobertura:{" "}
                              <span className="tabular-nums text-foreground">
                                {formatCurrency(att.allocated_amount)}
                              </span>
                            </div>
                          ) : null}
                          <div
                            className="truncate font-mono text-[10px] text-muted-foreground/70"
                            title={att.nf_chave}
                          >
                            {att.nf_chave}
                          </div>
                        </div>
                        {canWrite ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => removeLink.mutate(att.id)}
                            title="Desvincular NF"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="rounded-md border border-dashed border-border p-3 text-center text-[12px] text-muted-foreground">
                  Esta fatura ainda não tem NF vinculada.
                </div>
              )}
            </section>

            {invoice.description ? (
              <section>
                <h4 className="mb-1 flex items-center gap-1 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <Wallet className="h-3.5 w-3.5" />
                  Observações
                </h4>
                <p className="rounded-md border border-border bg-muted/30 p-2 text-[12px] text-muted-foreground">
                  {invoice.description}
                </p>
              </section>
            ) : null}
          </>
        )}
      </div>

      {invoice ? (
        <AttachNfModal
          open={attachOpen}
          onClose={() => setAttachOpen(false)}
          invoiceId={invoice.id}
        />
      ) : null}
    </Drawer>
  )
}
