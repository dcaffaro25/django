import { useState } from "react"
import { toast } from "sonner"
import { Plus, Trash2, FileCog, Download } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useDeleteImportTemplate,
  useImportTemplates,
  useSaveImportTemplate,
  type ImportTransformationRule,
} from "@/features/imports"
import { useTenant } from "@/providers/TenantProvider"

export function ImportTemplatesPage() {
  const { data: templates = [], isLoading } = useImportTemplates()
  const save = useSaveImportTemplate()
  const del = useDeleteImportTemplate()
  const { tenant } = useTenant()
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<{ name: string; description: string; model_name: string }>({
    name: "",
    description: "",
    model_name: "",
  })

  const onCreate = () => {
    if (!draft.name.trim()) {
      toast.error("Nome obrigatório.")
      return
    }
    save.mutate(
      { body: { ...draft, company: tenant?.id } },
      {
        onSuccess: () => {
          toast.success("Template criado.")
          setCreating(false)
          setDraft({ name: "", description: "", model_name: "" })
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "erro"),
      },
    )
  }

  const onDelete = (t: ImportTransformationRule) => {
    if (!window.confirm(`Excluir template "${t.name}"?`)) return
    del.mutate(t.id, {
      onSuccess: () => toast.success("Template excluído."),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "erro"),
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Templates de importação"
        subtitle="Regras de transformação reutilizáveis — definem como linhas de planilha viram registros."
        actions={
          <>
            <a
              href="/bulk_import_template.xlsx"
              download
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
              title="Baixar modelo de planilha base (com __row_id e abas-exemplo)"
            >
              <Download className="h-3.5 w-3.5" /> Baixar template
            </a>
            <button
              onClick={() => setCreating((v) => !v)}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> {creating ? "Fechar" : "Novo template"}
            </button>
          </>
        }
      />

      {creating && (
        <div className="card-elevated space-y-3 p-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Nome">
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Modelo-alvo">
              <input
                value={draft.model_name}
                onChange={(e) => setDraft({ ...draft, model_name: e.target.value })}
                placeholder="Transaction, JournalEntry, ..."
                className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Descrição">
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
              />
            </Field>
          </div>
          <div className="flex justify-end">
            <button
              onClick={onCreate}
              disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              Criar
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            O <code>mapping_config</code> completo é editado no Django Admin — esta tela cria o esqueleto.
          </p>
        </div>
      )}

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-9 px-3">Nome</th>
              <th className="h-9 px-3">Modelo-alvo</th>
              <th className="h-9 px-3">Descrição</th>
              <th className="h-9 px-3">Ativa</th>
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="h-12 px-3 text-center text-muted-foreground">Carregando…</td></tr>
            ) : templates.length === 0 ? (
              <tr><td colSpan={5} className="h-12 px-3 text-center text-muted-foreground">Nenhum template.</td></tr>
            ) : (
              templates.map((t) => (
                <tr key={t.id} className="border-t border-border hover:bg-accent/30">
                  <td className="h-10 px-3 font-medium">
                    <FileCog className="mr-1 inline h-3 w-3 text-muted-foreground" />
                    {t.name}
                  </td>
                  <td className="h-10 px-3 font-mono text-muted-foreground">{t.model_name ?? "—"}</td>
                  <td className="h-10 px-3 text-muted-foreground">{t.description ?? "—"}</td>
                  <td className="h-10 px-3">{t.is_active !== false ? "sim" : "não"}</td>
                  <td className="h-10 px-3">
                    <button
                      onClick={() => onDelete(t)}
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
