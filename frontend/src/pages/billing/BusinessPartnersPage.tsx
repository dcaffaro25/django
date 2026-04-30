import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  RefreshCw, Search, Plus, Pencil, Trash2, Tag, Users,
  Building2,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  useBusinessPartners, useBusinessPartnerCategories, useDeleteBusinessPartner,
} from "@/features/billing"
import type { BusinessPartner } from "@/features/billing"
import { BusinessPartnerEditDrawer } from "./BusinessPartnerEditDrawer"
import { BusinessPartnerCategoriesModal } from "./BusinessPartnerCategoriesModal"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn } from "@/lib/utils"

const PARTNER_TYPE_LABEL: Record<BusinessPartner["partner_type"], string> = {
  client: "Cliente",
  vendor: "Fornecedor",
  both: "Ambos",
}

const PARTNER_TYPE_TONE: Record<BusinessPartner["partner_type"], string> = {
  client: "bg-info/10 text-info",
  vendor: "bg-warning/10 text-warning",
  both: "bg-success/10 text-success",
}

function fmtCnpj(d?: string | null) {
  if (!d) return ""
  const s = d.replace(/\D/g, "")
  if (s.length === 14) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`
  if (s.length === 11) return `${s.slice(0, 3)}.${s.slice(3, 6)}.${s.slice(6, 9)}-${s.slice(9)}`
  return d
}

/** Branch index — counts BPs sharing the same cnpj_root so we can surface
 *  "matriz + filiais" relationships in the list. */
function buildRootIndex(partners: BusinessPartner[]): Map<string, BusinessPartner[]> {
  const idx = new Map<string, BusinessPartner[]>()
  for (const p of partners) {
    if (!p.cnpj_root) continue
    const arr = idx.get(p.cnpj_root) ?? []
    arr.push(p)
    idx.set(p.cnpj_root, arr)
  }
  return idx
}

export function BusinessPartnersPage() {
  const [params, setParams] = useSearchParams()
  const search = params.get("q") || ""
  const ptype = params.get("partner_type") || "all"
  const active = params.get("is_active") || "all"

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "" || value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const { data, isLoading, isFetching, refetch } = useBusinessPartners()
  const cats = useBusinessPartnerCategories()
  const del = useDeleteBusinessPartner()
  const { canWrite } = useUserRole()

  const filtered = useMemo(() => {
    if (!data) return []
    let items = data
    if (ptype !== "all") items = items.filter((p) => p.partner_type === ptype)
    if (active !== "all") items = items.filter((p) => p.is_active === (active === "true"))
    if (search) {
      const q = search.toLowerCase()
      items = items.filter((p) =>
        [p.name, p.identifier, p.email, p.erp_id ?? ""]
          .filter(Boolean)
          .some((s) => s.toLowerCase().includes(q)),
      )
    }
    return items
  }, [data, search, ptype, active])

  const rootIdx = useMemo(() => buildRootIndex(data ?? []), [data])
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
        title="Parceiros de Negócio"
        subtitle="Clientes e fornecedores. CNPJs com mesma raiz (8 dígitos) são tratados como filiais da mesma pessoa jurídica."
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
                Novo parceiro
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
            placeholder="Buscar nome, CNPJ, e-mail, ERP id…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tipo
          </span>
          <Select value={ptype} onValueChange={(v) => setFilter("partner_type", v)}>
            <SelectTrigger className="h-9 w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="client">Cliente</SelectItem>
              <SelectItem value="vendor">Fornecedor</SelectItem>
              <SelectItem value="both">Ambos</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Ativo
          </span>
          <Select value={active} onValueChange={(v) => setFilter("is_active", v)}>
            <SelectTrigger className="h-9 w-[120px]">
              <SelectValue />
            </SelectTrigger>
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
              <th className="px-3 py-2">Nome</th>
              <th className="px-3 py-2">CNPJ/CPF</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Categoria</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  Carregando parceiros…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center">
                  <Users className="mx-auto mb-2 h-6 w-6 text-muted-foreground/60" />
                  <p className="text-muted-foreground">
                    Nenhum parceiro com os filtros atuais.
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((p) => {
                const branches = p.cnpj_root ? rootIdx.get(p.cnpj_root) ?? [] : []
                const otherBranches = branches.filter((b) => b.id !== p.id)
                return (
                  <tr
                    key={p.id}
                    className="border-b border-border/40 last:border-b-0 hover:bg-muted/30"
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium">{p.name}</span>
                        {otherBranches.length > 0 ? (
                          <span
                            className="inline-flex items-center gap-0.5 rounded-full bg-info/10 px-1.5 py-0.5 text-[10px] font-medium text-info"
                            title={`Esta pessoa jurídica tem ${otherBranches.length} outra(s) filial(is) cadastrada(s): ${otherBranches.map((b) => b.name).join(", ")}`}
                          >
                            <Building2 className="h-2.5 w-2.5" />
                            +{otherBranches.length}
                          </span>
                        ) : null}
                      </div>
                      {p.email ? (
                        <div className="text-[11px] text-muted-foreground">{p.email}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {fmtCnpj(p.identifier)}
                      {p.cnpj_root ? (
                        <div className="text-[10px] text-muted-foreground/70">
                          raiz {p.cnpj_root}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={cn(
                          "inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium",
                          PARTNER_TYPE_TONE[p.partner_type],
                        )}
                      >
                        {PARTNER_TYPE_LABEL[p.partner_type]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {p.category != null ? categoryById.get(p.category) ?? "—" : "—"}
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
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <BusinessPartnerEditDrawer
        partnerId={editingId}
        onClose={() => setEditingId(null)}
      />
      <BusinessPartnerCategoriesModal
        open={catsOpen}
        onClose={() => setCatsOpen(false)}
      />
    </div>
  )
}
