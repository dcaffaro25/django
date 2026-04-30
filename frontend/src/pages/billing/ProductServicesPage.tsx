import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  RefreshCw, Search, Plus, Pencil, Trash2, Tag, Package, Wrench,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  useProductServices, useProductServiceCategories, useDeleteProductService,
} from "@/features/billing"
import type { ProductService } from "@/features/billing"
import { ProductServiceEditDrawer } from "./ProductServiceEditDrawer"
import { ProductServiceCategoriesModal } from "./ProductServiceCategoriesModal"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency } from "@/lib/utils"

const ITEM_TYPE_LABEL: Record<ProductService["item_type"], string> = {
  product: "Produto",
  service: "Serviço",
}

export function ProductServicesPage() {
  const [params, setParams] = useSearchParams()
  const search = params.get("q") || ""
  const itype = params.get("item_type") || "all"
  const active = params.get("is_active") || "all"

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "" || value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const { data, isLoading, isFetching, refetch } = useProductServices()
  const cats = useProductServiceCategories()
  const del = useDeleteProductService()
  const { canWrite } = useUserRole()

  const filtered = useMemo(() => {
    if (!data) return []
    let items = data
    if (itype !== "all") items = items.filter((p) => p.item_type === itype)
    if (active !== "all") items = items.filter((p) => p.is_active === (active === "true"))
    if (search) {
      const q = search.toLowerCase()
      items = items.filter((p) =>
        [p.name, p.code, p.description, p.erp_id ?? ""]
          .filter(Boolean)
          .some((s) => s.toLowerCase().includes(q)),
      )
    }
    return items
  }, [data, search, itype, active])

  const categoryById = useMemo(() => {
    const m = new Map<number, string>()
    for (const c of cats.data ?? []) m.set(c.id, c.name)
    return m
  }, [cats.data])

  const [editingId, setEditingId] = useState<number | "new" | null>(null)
  const [catsOpen, setCatsOpen] = useState(false)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Produtos e Serviços"
        subtitle="Itens vendáveis. Conta de receita / COGS / estoque por item — fallback do TenantCostingConfig quando vazio."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Atualizar
            </Button>
            <Button variant="outline" size="sm" onClick={() => setCatsOpen(true)}>
              <Tag className="h-4 w-4" />
              Categorias
            </Button>
            {canWrite ? (
              <Button size="sm" onClick={() => setEditingId("new")}>
                <Plus className="h-4 w-4" />
                Novo item
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap items-end gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setFilter("q", e.target.value)}
            placeholder="Buscar nome, código, descrição, ERP id…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tipo
          </span>
          <Select value={itype} onValueChange={(v) => setFilter("item_type", v)}>
            <SelectTrigger className="h-9 w-[150px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="product">Produto</SelectItem>
              <SelectItem value="service">Serviço</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Ativo
          </span>
          <Select value={active} onValueChange={(v) => setFilter("is_active", v)}>
            <SelectTrigger className="h-9 w-[120px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="true">Ativos</SelectItem>
              <SelectItem value="false">Inativos</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <table className="w-full text-[12px]">
          <thead className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2">Nome</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Categoria</th>
              <th className="px-3 py-2 text-right">Preço</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">
                  Carregando itens…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center">
                  <Package className="mx-auto mb-2 h-6 w-6 text-muted-foreground/60" />
                  <p className="text-muted-foreground">
                    Nenhum item com os filtros atuais.
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-border/40 last:border-b-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-2 font-mono">{p.code}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{p.name}</div>
                    {p.description ? (
                      <div className="line-clamp-1 text-[11px] text-muted-foreground">
                        {p.description}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      {p.item_type === "product" ? (
                        <><Package className="h-3 w-3" /> {ITEM_TYPE_LABEL.product}</>
                      ) : (
                        <><Wrench className="h-3 w-3" /> {ITEM_TYPE_LABEL.service}</>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {p.category != null ? categoryById.get(p.category) ?? "—" : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(p.price)}
                  </td>
                  <td className="px-3 py-2">
                    {p.is_active ? (
                      <span className="text-success">Ativo</span>
                    ) : (
                      <span className="text-muted-foreground">Inativo</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingId(p.id)}
                        title={canWrite ? "Editar" : "Ver"}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      {canWrite ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Remover ${p.name}?`)) del.mutate(p.id)
                          }}
                          title="Remover"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ProductServiceEditDrawer
        productId={editingId}
        onClose={() => setEditingId(null)}
      />
      <ProductServiceCategoriesModal
        open={catsOpen}
        onClose={() => setCatsOpen(false)}
      />
    </div>
  )
}
