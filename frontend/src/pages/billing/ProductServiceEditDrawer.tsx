import { useEffect, useState } from "react"
import { Save, X, FileText, Receipt } from "lucide-react"
import { Drawer } from "@/components/ui/drawer"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import {
  useProductService, useProductServiceCategories, useSaveProductService,
  useInvoiceLinesByProduct, useNFItemsByProduct,
} from "@/features/billing"
import type { ProductService } from "@/features/billing"
import { useUserRole } from "@/features/auth/useUserRole"
import { formatCurrency, formatDate } from "@/lib/utils"
import { CollapsibleRelatedList } from "./components/CollapsibleRelatedList"

const EMPTY: Partial<ProductService> = {
  name: "",
  code: "",
  category: null,
  description: "",
  item_type: "product",
  price: "0",
  cost: null,
  tax_code: "",
  track_inventory: false,
  stock_quantity: "0",
  is_active: true,
  inventory_account: null,
  cogs_account: null,
  adjustment_account: null,
  revenue_account: null,
  purchase_account: null,
  discount_given_account: null,
  erp_id: "",
}

const ACCOUNT_FIELDS: Array<{ key: keyof ProductService; label: string; help?: string }> = [
  { key: "revenue_account", label: "Conta de Receita", help: "Para vendas." },
  { key: "purchase_account", label: "Conta de Compra", help: "Para entradas / recebimento." },
  { key: "cogs_account", label: "COGS", help: "Custo do produto vendido." },
  { key: "inventory_account", label: "Estoque", help: "Conta de estoque (balanço)." },
  { key: "adjustment_account", label: "Ajuste / Reavaliação", help: "Inventory revaluation." },
  { key: "discount_given_account", label: "Desconto concedido" },
]

export function ProductServiceEditDrawer({
  productId,
  onClose,
}: {
  productId: number | "new" | null
  onClose: () => void
}) {
  const isNew = productId === "new"
  const open = productId != null
  const id = typeof productId === "number" ? productId : null
  const { data: existing } = useProductService(id)
  const cats = useProductServiceCategories()
  const save = useSaveProductService()
  const { canWrite } = useUserRole()

  const [draft, setDraft] = useState<Partial<ProductService>>(EMPTY)
  useEffect(() => {
    if (isNew) setDraft({ ...EMPTY })
    else if (existing) setDraft(existing)
  }, [isNew, existing?.id])

  const update = <K extends keyof ProductService>(key: K, value: ProductService[K]) => {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  const submit = async () => {
    await save.mutateAsync({ id, body: draft })
    onClose()
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={isNew ? "Novo Item" : `Item #${id ?? ""}`}
      width="640px"
    >
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="ps-code">Código</Label>
            <Input
              id="ps-code"
              value={draft.code ?? ""}
              onChange={(e) => update("code", e.target.value)}
              disabled={!canWrite}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ps-erp">ERP id</Label>
            <Input
              id="ps-erp"
              value={draft.erp_id ?? ""}
              onChange={(e) => update("erp_id", e.target.value)}
              disabled={!canWrite}
            />
          </div>
          <div className="col-span-2 grid gap-1.5">
            <Label htmlFor="ps-name">Nome</Label>
            <Input
              id="ps-name"
              value={draft.name ?? ""}
              onChange={(e) => update("name", e.target.value)}
              disabled={!canWrite}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Tipo</Label>
            <Select
              value={draft.item_type ?? "product"}
              onValueChange={(v) => update("item_type", v as ProductService["item_type"])}
              disabled={!canWrite}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="product">Produto</SelectItem>
                <SelectItem value="service">Serviço</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>Categoria</Label>
            <Select
              value={draft.category != null ? String(draft.category) : "none"}
              onValueChange={(v) => update("category", v === "none" ? null : Number(v))}
              disabled={!canWrite}
            >
              <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— sem categoria —</SelectItem>
                {(cats.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ps-price">Preço</Label>
            <Input
              id="ps-price"
              type="number" step="0.01"
              value={draft.price ?? ""}
              onChange={(e) => update("price", e.target.value)}
              disabled={!canWrite}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ps-cost">Custo</Label>
            <Input
              id="ps-cost"
              type="number" step="0.01"
              value={draft.cost ?? ""}
              onChange={(e) => update("cost", e.target.value || null)}
              disabled={!canWrite}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ps-tax">Código fiscal</Label>
            <Input
              id="ps-tax"
              value={draft.tax_code ?? ""}
              onChange={(e) => update("tax_code", e.target.value)}
              disabled={!canWrite}
              placeholder="Ex.: NCM, CFOP"
            />
          </div>
          <label className="flex items-center gap-2 text-[13px]">
            <Checkbox
              checked={!!draft.track_inventory}
              onCheckedChange={(v) => update("track_inventory", !!v)}
              disabled={!canWrite}
            />
            Controlar estoque
          </label>
          {draft.track_inventory ? (
            <div className="grid gap-1.5">
              <Label htmlFor="ps-stock">Quantidade em estoque</Label>
              <Input
                id="ps-stock"
                type="number" step="0.01"
                value={draft.stock_quantity ?? ""}
                onChange={(e) => update("stock_quantity", e.target.value)}
                disabled={!canWrite}
              />
            </div>
          ) : null}
          <div className="col-span-2 grid gap-1.5">
            <Label htmlFor="ps-desc">Descrição</Label>
            <Textarea
              id="ps-desc"
              rows={2}
              value={draft.description ?? ""}
              onChange={(e) => update("description", e.target.value)}
              disabled={!canWrite}
            />
          </div>
        </div>

        <fieldset className="rounded-md border border-border p-3">
          <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Mapeamento contábil (postagem GL)
          </legend>
          <div className="grid grid-cols-2 gap-3">
            {ACCOUNT_FIELDS.map(({ key, label, help }) => (
              <div key={String(key)} className="grid gap-1.5">
                <Label htmlFor={`ps-${String(key)}`}>{label}</Label>
                <Input
                  id={`ps-${String(key)}`}
                  type="number"
                  value={(draft[key] as number | null) ?? ""}
                  onChange={(e) =>
                    update(
                      key,
                      (e.target.value ? Number(e.target.value) : null) as ProductService[typeof key],
                    )
                  }
                  disabled={!canWrite}
                  placeholder="ID da conta"
                />
                {help ? (
                  <p className="text-[11px] text-muted-foreground">{help}</p>
                ) : null}
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Vazias caem no default do TenantCostingConfig.
          </p>
        </fieldset>

        <label className="flex items-center gap-2 text-[13px]">
          <Checkbox
            checked={!!draft.is_active}
            onCheckedChange={(v) => update("is_active", !!v)}
            disabled={!canWrite}
          />
          Ativo
        </label>

        {!isNew && id != null ? <PSRelatedSections productId={id} /> : null}
      </div>

      {canWrite ? (
        <div className="flex items-center justify-end gap-2 border-t border-border p-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
            Cancelar
          </Button>
          <Button size="sm" onClick={submit} disabled={save.isPending || !draft.name || !draft.code}>
            <Save className="h-4 w-4" />
            {save.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      ) : null}
    </Drawer>
  )
}


/**
 * Cross-links section shown at the bottom of the PS drawer.
 * Two collapsible groups: Faturas (linhas) where this product was billed,
 * and NFs (itens) where this product appeared in the fiscal doc.
 */
function PSRelatedSections({ productId }: { productId: number }) {
  const lines = useInvoiceLinesByProduct(productId)
  const items = useNFItemsByProduct(productId)

  return (
    <div className="space-y-3 border-t border-border pt-3">
      <CollapsibleRelatedList
        title="Faturas (linhas)"
        subtitle="Linhas de Faturas onde este item foi cobrado"
        icon={FileText}
        count={lines.data?.length ?? 0}
        loading={lines.isLoading}
        empty="Este produto/serviço não aparece em nenhuma fatura ainda."
      >
        {(lines.data ?? []).slice(0, 50).map((l) => (
          <li key={l.id} className="flex items-center justify-between border-b border-border/40 px-2 py-1.5 last:border-b-0 text-[12px]">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono">{l.invoice_number}</span>
              <span className="text-muted-foreground">{formatDate(l.invoice_date)}</span>
              <span className="truncate text-muted-foreground" title={l.invoice_partner}>
                {l.invoice_partner}
              </span>
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
                {Number(l.quantity).toLocaleString("pt-BR")} × {formatCurrency(l.unit_price)}
              </span>
            </div>
            <span className="font-medium tabular-nums">{formatCurrency(l.total_price)}</span>
          </li>
        ))}
      </CollapsibleRelatedList>

      <CollapsibleRelatedList
        title="NFs (itens)"
        subtitle="Itens de Notas Fiscais que referenciam este produto"
        icon={Receipt}
        count={items.data?.length ?? 0}
        loading={items.isLoading}
        empty="Este produto/serviço não aparece em nenhuma NF ainda."
      >
        {(items.data ?? []).slice(0, 50).map((it) => (
          <li key={it.id} className="flex items-center justify-between border-b border-border/40 px-2 py-1.5 last:border-b-0 text-[12px]">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono">NF #{it.nota_fiscal}</span>
              <span className="text-muted-foreground">item {it.numero_item}</span>
              <span className="truncate text-muted-foreground" title={it.descricao}>
                {it.descricao}
              </span>
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
                {Number(it.quantidade).toLocaleString("pt-BR")} {it.unidade}
              </span>
            </div>
            <span className="font-medium tabular-nums">{formatCurrency(it.valor_total)}</span>
          </li>
        ))}
      </CollapsibleRelatedList>
    </div>
  )
}
