import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Drawer } from "vaul"
import { Plus, Trash2, Save, X, Building2, Copy } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ColumnMenu } from "@/components/ui/column-menu"
import { SortableHeader } from "@/components/ui/sortable-header"
import { RowAction, RowActionsCell } from "@/components/ui/row-actions"
import { BulkAction, BulkActionsBar, RowCheckbox, SelectAllCheckbox } from "@/components/ui/bulk-actions-bar"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { useSortable } from "@/lib/use-sortable"
import { useRowSelection } from "@/lib/use-row-selection"
import { useDeleteEntity, useEntities, useSaveEntity } from "@/features/reconciliation"
import { useUserRole } from "@/features/auth/useUserRole"
import { useTenant } from "@/providers/TenantProvider"
import type { Entity } from "@/features/reconciliation/types"
import { cn } from "@/lib/utils"

export function EntitiesPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const { canWrite } = useUserRole()
  const { data: entities = [], isLoading } = useEntities()
  const [editing, setEditing] = useState<Entity | "new" | null>(null)

  const { sort, sorted, toggle: toggleSort } = useSortable(entities, {
    initialKey: "path",
    initialDirection: "asc",
    accessors: {
      name: (r) => r.name,
      path: (r) => r.path ?? r.name,
      level: (r) => r.level,
    },
  })

  const columns: ColumnDef[] = useMemo(
    () => [
      { key: "name", label: "Nome", alwaysVisible: true },
      { key: "path", label: "Caminho" },
      { key: "level", label: "Nível" },
      { key: "inherit_accounts", label: "Herda contas", defaultVisible: false },
      { key: "inherit_cost_centers", label: "Herda CC", defaultVisible: false },
    ],
    [],
  )
  const col = useColumnVisibility("settings.entities", columns)

  const del = useDeleteEntity()
  const onDelete = (e0: Entity, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Excluir entidade "${e0.name}"?`)) return
    del.mutate(e0.id, {
      onSuccess: () => toast.success("Entidade excluída"),
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }
  const onDuplicate = (e0: Entity, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing({
      ...e0,
      id: undefined as unknown as number,
      name: `${e0.name} (cópia)`,
      path: undefined as unknown as string,
    })
  }

  const selection = useRowSelection<number>()
  const sortedIds = sorted.map((r) => r.id)
  const onBulkDelete = async () => {
    const ids = Array.from(selection.selected)
    if (!ids.length) return
    if (!window.confirm(`Excluir ${ids.length} entidade${ids.length > 1 ? "s" : ""}?`)) return
    const res = await Promise.allSettled(ids.map((id) => del.mutateAsync(id)))
    const failed = res.filter((r) => r.status === "rejected").length
    if (failed) toast.warning(`${ids.length - failed} excluídas · ${failed} falharam`)
    else toast.success(`${ids.length} entidades excluídas`)
    selection.clear()
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Entidades"
        subtitle="Unidades de negócio, filiais ou centros de atividade"
        actions={
          <>
            <ColumnMenu
              columns={columns}
              isVisible={col.isVisible}
              toggle={col.toggle}
              showAll={col.showAll}
              resetDefaults={col.resetDefaults}
              label={t("actions.columns", { ns: "common" })}
            />
            {canWrite && (
              <button
                onClick={() => setEditing("new")}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-3.5 w-3.5" /> Nova entidade
              </button>
            )}
          </>
        }
      />

      <BulkActionsBar count={selection.count} onClear={selection.clear}>
        <BulkAction icon={<Trash2 className="h-3 w-3" />} label={`Excluir ${selection.count}`} variant="danger" onClick={onBulkDelete} />
      </BulkActionsBar>

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-9 w-10 px-3">
                <SelectAllCheckbox
                  allSelected={selection.allSelected(sortedIds)}
                  someSelected={selection.someSelected(sortedIds)}
                  onToggle={() => selection.toggleAll(sortedIds)}
                />
              </th>
              <th className="h-9 px-3"><SortableHeader columnKey="name" label="Nome" sort={sort} onToggle={toggleSort} /></th>
              {col.isVisible("path") && <th className="h-9 px-3"><SortableHeader columnKey="path" label="Caminho" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("level") && <th className="h-9 px-3 text-right"><SortableHeader columnKey="level" align="right" label="Nível" sort={sort} onToggle={toggleSort} /></th>}
              {col.isVisible("inherit_accounts") && <th className="h-9 px-3">Herda contas</th>}
              {col.isVisible("inherit_cost_centers") && <th className="h-9 px-3">Herda CC</th>}
              <th className="h-9 w-px px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={7} className="h-10 px-3"><div className="h-4 animate-pulse rounded bg-muted/60" /></td>
                </tr>
              ))
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={7} className="h-24 px-3 text-center text-muted-foreground">Nenhuma entidade cadastrada</td>
              </tr>
            ) : (
              sorted.map((ent) => (
                <tr key={ent.id} onClick={() => setEditing(ent)}
                  className={cn(
                    "group cursor-pointer border-t border-border hover:bg-accent/50",
                    selection.isSelected(ent.id) && "bg-primary/5",
                  )}>
                  <td className="h-10 px-3">
                    <RowCheckbox checked={selection.isSelected(ent.id)} onToggle={() => selection.toggle(ent.id)} />
                  </td>
                  <td className="h-10 px-3 font-medium" style={{ paddingLeft: 12 + (ent.level ?? 0) * 16 }}>
                    {ent.name}
                  </td>
                  {col.isVisible("path") && <td className="h-10 px-3 text-muted-foreground">{ent.path ?? "—"}</td>}
                  {col.isVisible("level") && <td className="h-10 px-3 text-right tabular-nums text-muted-foreground">{ent.level ?? 0}</td>}
                  {col.isVisible("inherit_accounts") && <td className="h-10 px-3 text-muted-foreground">{ent.inherit_accounts ? "sim" : "não"}</td>}
                  {col.isVisible("inherit_cost_centers") && <td className="h-10 px-3 text-muted-foreground">{ent.inherit_cost_centers ? "sim" : "não"}</td>}
                  {canWrite ? (
                    <RowActionsCell>
                      <RowAction icon={<Copy className="h-3.5 w-3.5" />} label="Duplicar" onClick={(e) => onDuplicate(ent, e)} />
                      <RowAction icon={<Trash2 className="h-3.5 w-3.5" />} label="Excluir" variant="danger" onClick={(e) => onDelete(ent, e)} />
                    </RowActionsCell>
                  ) : (
                    <td className="h-10 px-3" />
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <EntityEditor
        open={editing !== null}
        entity={editing === "new" ? null : editing}
        entities={entities}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

function EntityEditor({
  open, entity, entities, onClose,
}: {
  open: boolean
  entity: Entity | null
  entities: Entity[]
  onClose: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const save = useSaveEntity()
  const { tenant } = useTenant()
  const [form, setForm] = useState<Partial<Entity> & { company?: number }>({
    name: "",
    parent_id: null,
    inherit_accounts: true,
    inherit_cost_centers: true,
  })

  useEffect(() => {
    if (entity) {
      setForm({ ...entity })
    } else {
      setForm({
        name: "",
        parent_id: null,
        inherit_accounts: true,
        inherit_cost_centers: true,
        company: tenant?.id,
      })
    }
  }, [entity, open, tenant?.id])

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const onSave = () => {
    if (!form.name) { toast.error("Nome obrigatório"); return }
    const body = { ...form, company: form.company ?? tenant?.id }
    save.mutate(
      { id: entity?.id, body },
      {
        onSuccess: () => { toast.success("Entidade salva"); onClose() },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[480px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
              {entity ? `Editar entidade #${entity.id}` : "Nova entidade"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <Field label="Nome">
              <input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring" />
            </Field>

            <Field label="Entidade pai (opcional)">
              <select value={form.parent_id ?? ""} onChange={(e) => set("parent_id", e.target.value ? Number(e.target.value) : null)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring">
                <option value="">— raiz —</option>
                {entities
                  .filter((e) => e.id !== entity?.id)
                  .map((e) => (
                    <option key={e.id} value={e.id}>{e.path ?? e.name}</option>
                  ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
                <input type="checkbox" checked={!!form.inherit_accounts} onChange={(e) => set("inherit_accounts", e.target.checked)} className="accent-primary" />
                Herdar contas
              </label>
              <label className="flex items-center gap-2 rounded-md border border-border p-2.5">
                <input type="checkbox" checked={!!form.inherit_cost_centers} onChange={(e) => set("inherit_cost_centers", e.target.checked)} className="accent-primary" />
                Herdar centros de custo
              </label>
            </div>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent">
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button onClick={onSave} disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-3.5 w-3.5" />
              {t("actions.save", { ns: "common" })}
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
