import { useState } from "react"
import { toast } from "sonner"
import { Plus, Trash2, Save, X } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useDeleteSubstitutionRule,
  useSaveSubstitutionRule,
  useSubstitutionRules,
  type SubstitutionRule,
} from "@/features/imports"
import { useTenant } from "@/providers/TenantProvider"
import { cn } from "@/lib/utils"

type Draft = Partial<SubstitutionRule> & { company?: number }

export function SubstitutionRulesPage() {
  const { data: rules = [], isLoading } = useSubstitutionRules()
  const save = useSaveSubstitutionRule()
  const del = useDeleteSubstitutionRule()
  const [editing, setEditing] = useState<Draft | null>(null)
  const { tenant } = useTenant()

  const onNew = () => setEditing({ name: "", source_value: "", target_value: "", rule_type: "exact", is_active: true, company: tenant?.id })
  const onEdit = (r: SubstitutionRule) => setEditing({ ...r })
  const onCancel = () => setEditing(null)

  const onSave = () => {
    if (!editing?.name) {
      toast.error("Nome obrigatório.")
      return
    }
    const { id, ...body } = editing
    save.mutate(
      { id, body: { ...body, company: body.company ?? tenant?.id } },
      {
        onSuccess: () => {
          toast.success(id ? "Regra atualizada." : "Regra criada.")
          setEditing(null)
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "erro"),
      },
    )
  }

  const onDelete = (r: SubstitutionRule) => {
    if (!window.confirm(`Excluir "${r.name}"?`)) return
    del.mutate(r.id, {
      onSuccess: () => toast.success("Regra excluída."),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "erro"),
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Regras de substituição"
        subtitle="Substitui valores em colunas durante importações (ex.: normalização de nomes)."
        actions={
          <button
            onClick={onNew}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" /> Nova regra
          </button>
        }
      />

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-9 px-3">Nome</th>
              <th className="h-9 px-3">De</th>
              <th className="h-9 px-3">Para</th>
              <th className="h-9 px-3">Tipo</th>
              <th className="h-9 px-3">Ativa</th>
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="h-12 px-3 text-center text-muted-foreground">Carregando…</td></tr>
            ) : rules.length === 0 ? (
              <tr><td colSpan={6} className="h-12 px-3 text-center text-muted-foreground">Nenhuma regra.</td></tr>
            ) : (
              rules.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => onEdit(r)}
                  className={cn("cursor-pointer border-t border-border hover:bg-accent/50")}
                >
                  <td className="h-10 px-3 font-medium">{r.name}</td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">{r.source_value ?? "—"}</td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">{r.target_value ?? "—"}</td>
                  <td className="h-10 px-3 text-muted-foreground">{r.rule_type ?? "—"}</td>
                  <td className="h-10 px-3">{r.is_active ? "sim" : "não"}</td>
                  <td className="h-10 px-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); onDelete(r) }}
                      className="inline-flex h-6 items-center rounded px-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {editing !== null && (
        <div className="card-elevated space-y-3 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[13px] font-semibold">
              {editing.id ? `Editar regra #${editing.id}` : "Nova regra"}
            </h3>
            <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Nome">
              <input
                value={editing.name ?? ""}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Tipo">
              <select
                value={editing.rule_type ?? "exact"}
                onChange={(e) => setEditing({ ...editing, rule_type: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              >
                <option value="exact">exact</option>
                <option value="regex">regex</option>
                <option value="contains">contains</option>
              </select>
            </Field>
            <Field label="Valor original">
              <input
                value={editing.source_value ?? ""}
                onChange={(e) => setEditing({ ...editing, source_value: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Valor destino">
              <input
                value={editing.target_value ?? ""}
                onChange={(e) => setEditing({ ...editing, target_value: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Descrição">
              <input
                value={editing.description ?? ""}
                onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              />
            </Field>
            <label className="flex items-end gap-2 text-[12px]">
              <input
                type="checkbox"
                checked={!!editing.is_active}
                onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })}
                className="accent-primary"
              />
              Ativa
            </label>
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              onClick={onSave}
              disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" /> Salvar
            </button>
          </div>
        </div>
      )}
    </div>
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
