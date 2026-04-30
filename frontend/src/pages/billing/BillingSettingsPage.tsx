import { useEffect, useState } from "react"
import { Save, Settings as SettingsIcon, Wand2, Receipt, Wallet } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { useBillingConfig, useSaveBillingConfig } from "@/features/billing"
import type { BillingTenantConfig } from "@/features/billing"
import { useUserRole } from "@/features/auth/useUserRole"

const ALL_FINALIDADES = [
  { value: 1, label: "Normal" },
  { value: 2, label: "Complementar" },
  { value: 3, label: "Ajuste" },
  { value: 4, label: "Devolução" },
]

const ALL_TIPOS = [
  { value: 0, label: "Entrada (compra)" },
  { value: 1, label: "Saída (venda)" },
]

export function BillingSettingsPage() {
  const { data, isLoading } = useBillingConfig()
  const save = useSaveBillingConfig()
  const { canWrite } = useUserRole()

  const [draft, setDraft] = useState<Partial<BillingTenantConfig>>({})
  useEffect(() => {
    if (data) setDraft(data)
  }, [data])

  const update = <K extends keyof BillingTenantConfig>(key: K, value: BillingTenantConfig[K]) => {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  const toggleFinalidade = (v: number) => {
    const list = draft.auto_create_invoice_for_finalidades ?? []
    const next = list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
    update("auto_create_invoice_for_finalidades", next)
  }
  const toggleTipo = (v: number) => {
    const list = draft.auto_create_invoice_for_tipos ?? []
    const next = list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
    update("auto_create_invoice_for_tipos", next)
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(data ?? {})

  const submit = async () => {
    await save.mutateAsync(draft)
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Configurações de Faturamento"
        subtitle="Comportamento da importação de NFs e vínculos automáticos com a contabilidade."
        actions={
          canWrite ? (
            <Button onClick={submit} disabled={!dirty || save.isPending}>
              <Save className="h-4 w-4" />
              {save.isPending ? "Salvando…" : "Salvar"}
            </Button>
          ) : null
        }
      />

      {isLoading || !data ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-muted-foreground">
          Carregando configuração…
        </div>
      ) : (
        <>
          <section className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 text-[14px] font-semibold">
              <Wand2 className="h-4 w-4" />
              Vínculos automáticos NF ↔ Lançamento
            </h3>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex items-start gap-2">
                <Checkbox
                  checked={!!draft.auto_link_nf_to_transactions}
                  onCheckedChange={(v) => update("auto_link_nf_to_transactions", !!v)}
                  disabled={!canWrite}
                />
                <div>
                  <div className="text-[13px] font-medium">
                    Sugerir vínculos ao importar NF
                  </div>
                  <div className="text-[12px] text-muted-foreground">
                    Roda o matching toda vez que uma NF é importada e cria sugestões
                    em <em>Vínculos NF↔Tx</em>.
                  </div>
                </div>
              </label>
              <div className="grid gap-1.5">
                <Label htmlFor="auto-accept">Aceitar automaticamente acima de</Label>
                <Input
                  id="auto-accept"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1.001}
                  value={draft.auto_accept_link_above ?? "1.001"}
                  onChange={(e) => update("auto_accept_link_above", e.target.value)}
                  disabled={!canWrite}
                />
                <p className="text-[11px] text-muted-foreground">
                  Confiança 0..1. <strong>1.001</strong> nunca aceita sozinho — o operador revisa.
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="date-window">Janela de datas (dias)</Label>
                <Input
                  id="date-window"
                  type="number"
                  min={0}
                  value={draft.link_date_window_days ?? 7}
                  onChange={(e) => update("link_date_window_days", Number(e.target.value))}
                  disabled={!canWrite}
                />
                <p className="text-[11px] text-muted-foreground">
                  Diferença máxima entre Tx.date e NF.data_emissao para o match valer.
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="amount-tol">Tolerância de valor (proporção)</Label>
                <Input
                  id="amount-tol"
                  type="number"
                  step="0.001"
                  min={0}
                  value={draft.link_amount_tolerance_pct ?? "0.01"}
                  onChange={(e) => update("link_amount_tolerance_pct", e.target.value)}
                  disabled={!canWrite}
                />
                <p className="text-[11px] text-muted-foreground">
                  0.01 = 1%. Tx.amount pode divergir de NF.valor_nota até esta proporção.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 text-[14px] font-semibold">
              <Receipt className="h-4 w-4" />
              Auto-criação de Faturas a partir de NFs
            </h3>
            <label className="mb-3 flex items-start gap-2">
              <Checkbox
                checked={!!draft.auto_create_invoice_from_nf}
                onCheckedChange={(v) => update("auto_create_invoice_from_nf", !!v)}
                disabled={!canWrite}
              />
              <div>
                <div className="text-[13px] font-medium">
                  Ativar auto-criação
                </div>
                <div className="text-[12px] text-muted-foreground">
                  Para NFs que não casarem com Faturas existentes, cria uma Fatura
                  rascunho com os dados da NF e vincula automaticamente.
                </div>
              </div>
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label>Finalidades elegíveis</Label>
                <div className="flex flex-wrap gap-3 rounded-md border border-border bg-background p-2">
                  {ALL_FINALIDADES.map((f) => (
                    <label key={f.value} className="flex items-center gap-1.5 text-[12px]">
                      <Checkbox
                        checked={(draft.auto_create_invoice_for_finalidades ?? []).includes(f.value)}
                        onCheckedChange={() => toggleFinalidade(f.value)}
                        disabled={!canWrite || !draft.auto_create_invoice_from_nf}
                      />
                      {f.label}
                    </label>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Padrão (vazio): apenas <strong>Normal</strong>. Marque para incluir outras.
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label>Tipos de operação elegíveis</Label>
                <div className="flex flex-wrap gap-3 rounded-md border border-border bg-background p-2">
                  {ALL_TIPOS.map((t) => (
                    <label key={t.value} className="flex items-center gap-1.5 text-[12px]">
                      <Checkbox
                        checked={(draft.auto_create_invoice_for_tipos ?? []).includes(t.value)}
                        onCheckedChange={() => toggleTipo(t.value)}
                        disabled={!canWrite || !draft.auto_create_invoice_from_nf}
                      />
                      {t.label}
                    </label>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Padrão (vazio): apenas <strong>Saída</strong>.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 text-[14px] font-semibold">
              <Wallet className="h-4 w-4" />
              Contas padrão para postagem GL
            </h3>
            <p className="mb-3 text-[12px] text-muted-foreground">
              Usadas como fallback quando a Conta A/R ou A/P não está definida no
              parceiro de negócio. Contas específicas em <em>Parceiro</em> têm prioridade.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="def-recv">Conta A/R padrão</Label>
                <Input
                  id="def-recv"
                  type="number"
                  placeholder="ID da conta"
                  value={draft.default_receivable_account ?? ""}
                  onChange={(e) =>
                    update(
                      "default_receivable_account",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                  disabled={!canWrite}
                />
                <p className="text-[11px] text-muted-foreground">
                  Receita / contas a receber para vendas.
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="def-pay">Conta A/P padrão</Label>
                <Input
                  id="def-pay"
                  type="number"
                  placeholder="ID da conta"
                  value={draft.default_payable_account ?? ""}
                  onChange={(e) =>
                    update(
                      "default_payable_account",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                  disabled={!canWrite}
                />
                <p className="text-[11px] text-muted-foreground">
                  Despesa / contas a pagar para compras.
                </p>
              </div>
            </div>
          </section>

          <p className="rounded-md border border-info/20 bg-info/5 p-3 text-[12px] text-info">
            <SettingsIcon className="mr-1 inline h-3.5 w-3.5 align-text-bottom" />
            Postagem automática no Razão (Fase 4) ainda não está implementada — estes
            campos preparam o terreno para quando ativarmos.
          </p>
        </>
      )}
    </div>
  )
}
