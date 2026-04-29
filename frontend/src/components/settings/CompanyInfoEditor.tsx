import { useEffect, useState } from "react"
import { Drawer } from "vaul"
import { toast } from "sonner"
import { Building2, Save, X } from "lucide-react"
import { useActiveCompany, useUpdateCompany, type Company } from "@/features/company/useCompany"
import {
  CURRENCY_OPTIONS, REGIME_TRIBUTARIO_OPTIONS, UF_OPTIONS,
  formatCepInput, formatCnpjInput,
} from "@/lib/br-fiscal"

/**
 * Editor drawer for the active tenant's Company row -- the
 * counterpart of EntityEditor. Surfaces every Phase E2 field
 * (CNPJ, IE/IM, CNAE, regime tributário, endereço, contato,
 * default currency/locale/timezone) plus name + subdomain (the
 * latter read-only because changing it would orphan every URL
 * pinning to the old subdomain).
 *
 * Manager+ enforced server-side via the middleware write gate;
 * viewers who somehow open the drawer will see a 403 toast on
 * save.
 */
export function CompanyInfoEditor({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: company, isLoading } = useActiveCompany()
  const update = useUpdateCompany()
  const [form, setForm] = useState<Partial<Company>>({})

  useEffect(() => {
    if (company && open) setForm({ ...company })
  }, [company, open])

  const set = <K extends keyof Company>(key: K, value: Company[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.name) { toast.error("Nome é obrigatório"); return }
    update.mutate(form, {
      onSuccess: () => { toast.success("Empresa atualizada"); onClose() },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro ao salvar"),
    })
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[560px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
              Editar empresa
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[12px]">
            {isLoading ? (
              <div className="text-muted-foreground">Carregando dados da empresa…</div>
            ) : (
              <>
                <FormSection title="Identificação">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Nome">
                      <input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Subdomínio (somente leitura)">
                      <input value={form.subdomain ?? ""} disabled
                        className="h-8 w-full rounded-md border border-border bg-muted px-2 text-muted-foreground outline-none" />
                    </Field>
                  </div>
                  <Field label="CNPJ">
                    <input
                      value={formatCnpjInput(form.cnpj ?? "")}
                      onChange={(e) => set("cnpj", e.target.value.replace(/\D/g, "") || null)}
                      placeholder="00.000.000/0000-00"
                      inputMode="numeric"
                      className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                    />
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Razão social">
                      <input value={form.razao_social ?? ""} onChange={(e) => set("razao_social", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Nome fantasia">
                      <input value={form.nome_fantasia ?? ""} onChange={(e) => set("nome_fantasia", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                </FormSection>

                <FormSection title="Dados fiscais">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Inscrição estadual">
                      <input value={form.inscricao_estadual ?? ""} onChange={(e) => set("inscricao_estadual", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Inscrição municipal">
                      <input value={form.inscricao_municipal ?? ""} onChange={(e) => set("inscricao_municipal", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="CNAE principal">
                      <input value={form.cnae_principal ?? ""} onChange={(e) => set("cnae_principal", e.target.value || null)}
                        placeholder="0000-0/00"
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Regime tributário">
                      <select value={form.regime_tributario ?? ""} onChange={(e) => set("regime_tributario", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                        <option value="">—</option>
                        {REGIME_TRIBUTARIO_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </Field>
                  </div>
                </FormSection>

                <FormSection title="Endereço">
                  <div className="grid grid-cols-[1fr_120px] gap-3">
                    <Field label="Logradouro">
                      <input value={form.endereco_logradouro ?? ""} onChange={(e) => set("endereco_logradouro", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Número">
                      <input value={form.endereco_numero ?? ""} onChange={(e) => set("endereco_numero", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Complemento">
                      <input value={form.endereco_complemento ?? ""} onChange={(e) => set("endereco_complemento", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Bairro">
                      <input value={form.endereco_bairro ?? ""} onChange={(e) => set("endereco_bairro", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                  <div className="grid grid-cols-[1fr_80px_120px] gap-3">
                    <Field label="Cidade">
                      <input value={form.endereco_cidade ?? ""} onChange={(e) => set("endereco_cidade", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="UF">
                      <select value={form.endereco_uf ?? ""} onChange={(e) => set("endereco_uf", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                        <option value="">—</option>
                        {UF_OPTIONS.map((uf) => (
                          <option key={uf} value={uf}>{uf}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="CEP">
                      <input
                        value={formatCepInput(form.endereco_cep ?? "")}
                        onChange={(e) => set("endereco_cep", e.target.value.replace(/\D/g, "") || null)}
                        placeholder="00000-000"
                        inputMode="numeric"
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
                      />
                    </Field>
                  </div>
                </FormSection>

                <FormSection title="Contato">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Email">
                      <input type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value || null)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                    <Field label="Telefone">
                      <input value={form.telefone ?? ""} onChange={(e) => set("telefone", e.target.value || null)}
                        placeholder="(00) 0000-0000"
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                  <Field label="Website">
                    <input type="url" value={form.website ?? ""} onChange={(e) => set("website", e.target.value || null)}
                      placeholder="https://"
                      className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                  </Field>
                </FormSection>

                <FormSection title="Preferências operacionais">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Moeda padrão">
                      <select value={form.default_currency ?? "BRL"} onChange={(e) => set("default_currency", e.target.value)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                        {CURRENCY_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Idioma / locale">
                      <input value={form.default_locale ?? "pt-BR"} onChange={(e) => set("default_locale", e.target.value)}
                        placeholder="pt-BR"
                        className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                    </Field>
                  </div>
                  <Field label="Fuso horário (IANA)">
                    <input value={form.default_timezone ?? "America/Sao_Paulo"} onChange={(e) => set("default_timezone", e.target.value)}
                      placeholder="America/Sao_Paulo"
                      className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
                  </Field>
                </FormSection>
              </>
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
              Cancelar
            </button>
            <button onClick={onSave} disabled={update.isPending || isLoading}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-3.5 w-3.5" /> Salvar empresa
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</h3>
      <div className="space-y-3">{children}</div>
    </section>
  )
}
