import { useEffect, useState } from "react"
import { Save, X } from "lucide-react"
import { Drawer } from "@/components/ui/drawer"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import {
  useBusinessPartner, useBusinessPartnerCategories, useSaveBusinessPartner,
} from "@/features/billing"
import type { BusinessPartner } from "@/features/billing"
import { useUserRole } from "@/features/auth/useUserRole"

const EMPTY: Partial<BusinessPartner> = {
  name: "",
  identifier: "",
  partner_type: "client",
  category: null,
  receivable_account: null,
  payable_account: null,
  address: "",
  city: "",
  state: "",
  zipcode: "",
  country: "Brazil",
  email: "",
  phone: "",
  payment_terms: "",
  is_active: true,
  erp_id: "",
}

export function BusinessPartnerEditDrawer({
  partnerId,
  onClose,
}: {
  partnerId: number | "new" | null
  onClose: () => void
}) {
  const isNew = partnerId === "new"
  const open = partnerId != null
  const id = typeof partnerId === "number" ? partnerId : null
  const { data: existing } = useBusinessPartner(id)
  const cats = useBusinessPartnerCategories()
  const save = useSaveBusinessPartner()
  const { canWrite } = useUserRole()

  const [draft, setDraft] = useState<Partial<BusinessPartner>>(EMPTY)
  useEffect(() => {
    if (isNew) setDraft({ ...EMPTY })
    else if (existing) setDraft(existing)
  }, [isNew, existing?.id])

  const update = <K extends keyof BusinessPartner>(key: K, value: BusinessPartner[K]) => {
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
      title={isNew ? "Novo Parceiro" : `Parceiro #${id ?? ""}`}
      width="600px"
    >
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 grid gap-1.5">
            <Label htmlFor="bp-name">Nome / Razão Social</Label>
            <Input
              id="bp-name"
              value={draft.name ?? ""}
              onChange={(e) => update("name", e.target.value)}
              disabled={!canWrite}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="bp-identifier">CNPJ / CPF</Label>
            <Input
              id="bp-identifier"
              value={draft.identifier ?? ""}
              onChange={(e) => update("identifier", e.target.value)}
              disabled={!canWrite}
              placeholder="14 dígitos (CNPJ) ou 11 (CPF)"
            />
            {draft.cnpj_root ? (
              <p className="text-[11px] text-muted-foreground">
                Raiz CNPJ: <span className="font-mono">{draft.cnpj_root}</span>
              </p>
            ) : null}
          </div>
          <div className="grid gap-1.5">
            <Label>Tipo</Label>
            <Select
              value={draft.partner_type ?? "client"}
              onValueChange={(v) => update("partner_type", v as BusinessPartner["partner_type"])}
              disabled={!canWrite}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="client">Cliente</SelectItem>
                <SelectItem value="vendor">Fornecedor</SelectItem>
                <SelectItem value="both">Ambos</SelectItem>
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
            <Label htmlFor="bp-erp">ERP id</Label>
            <Input
              id="bp-erp"
              value={draft.erp_id ?? ""}
              onChange={(e) => update("erp_id", e.target.value)}
              disabled={!canWrite}
            />
          </div>
        </div>

        <fieldset className="rounded-md border border-border p-3">
          <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Contas contábeis (postagem GL)
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="bp-recv">Conta A/R (vendas)</Label>
              <Input
                id="bp-recv"
                type="number"
                value={draft.receivable_account ?? ""}
                onChange={(e) => update("receivable_account", e.target.value ? Number(e.target.value) : null)}
                disabled={!canWrite}
                placeholder="ID da conta"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-pay">Conta A/P (compras)</Label>
              <Input
                id="bp-pay"
                type="number"
                value={draft.payable_account ?? ""}
                onChange={(e) => update("payable_account", e.target.value ? Number(e.target.value) : null)}
                disabled={!canWrite}
                placeholder="ID da conta"
              />
            </div>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Vazias caem no default do tenant em Configurações.
          </p>
        </fieldset>

        <fieldset className="rounded-md border border-border p-3">
          <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Contato
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="bp-email">E-mail</Label>
              <Input
                id="bp-email" type="email"
                value={draft.email ?? ""}
                onChange={(e) => update("email", e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-phone">Telefone</Label>
              <Input
                id="bp-phone"
                value={draft.phone ?? ""}
                onChange={(e) => update("phone", e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="col-span-2 grid gap-1.5">
              <Label htmlFor="bp-address">Endereço</Label>
              <Input
                id="bp-address"
                value={draft.address ?? ""}
                onChange={(e) => update("address", e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-city">Cidade</Label>
              <Input
                id="bp-city"
                value={draft.city ?? ""}
                onChange={(e) => update("city", e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-state">Estado</Label>
              <Input
                id="bp-state"
                value={draft.state ?? ""}
                onChange={(e) => update("state", e.target.value)}
                disabled={!canWrite}
                maxLength={2}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-zipcode">CEP</Label>
              <Input
                id="bp-zipcode"
                value={draft.zipcode ?? ""}
                onChange={(e) => update("zipcode", e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bp-country">País</Label>
              <Input
                id="bp-country"
                value={draft.country ?? ""}
                onChange={(e) => update("country", e.target.value)}
                disabled={!canWrite}
              />
            </div>
          </div>
        </fieldset>

        <div className="grid gap-1.5">
          <Label htmlFor="bp-pterms">Condições de pagamento</Label>
          <Input
            id="bp-pterms"
            value={draft.payment_terms ?? ""}
            onChange={(e) => update("payment_terms", e.target.value)}
            disabled={!canWrite}
            placeholder="Ex.: 30/60/90"
          />
        </div>

        <label className="flex items-center gap-2 text-[13px]">
          <Checkbox
            checked={!!draft.is_active}
            onCheckedChange={(v) => update("is_active", !!v)}
            disabled={!canWrite}
          />
          Ativo
        </label>
      </div>

      {canWrite ? (
        <div className="flex items-center justify-end gap-2 border-t border-border p-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
            Cancelar
          </Button>
          <Button size="sm" onClick={submit} disabled={save.isPending || !draft.name || !draft.identifier}>
            <Save className="h-4 w-4" />
            {save.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      ) : null}
    </Drawer>
  )
}
