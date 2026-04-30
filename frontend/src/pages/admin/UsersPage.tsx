import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  Check, Globe2, KeyRound, Loader2, Plus, RefreshCw, Search, ShieldCheck,
  Trash2, UserCheck, UserMinus, Wand2, X,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useAdminCompanies,
  useAdminUsers,
  useDeactivateAdminUser,
  useResetAdminUserPassword,
  useSaveAdminUser,
  useSetAdminUserActive,
} from "@/features/admin/hooks"
import type { AdminUser } from "@/features/admin/api"
import { cn } from "@/lib/utils"

const ROLES: Array<{ id: string; label: string }> = [
  { id: "owner", label: "Owner" },
  { id: "manager", label: "Manager" },
  { id: "operator", label: "Operator" },
  { id: "viewer", label: "Viewer" },
]

export function UsersPage() {
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250)
    return () => clearTimeout(t)
  }, [search])

  const { data: users = [], isLoading, isFetching, refetch } = useAdminUsers(debounced)
  const setActive = useSetAdminUserActive()
  const deactivate = useDeactivateAdminUser()
  const resetPw = useResetAdminUserPassword()

  const onToggleActive = (u: AdminUser) => {
    setActive.mutate(
      { id: u.id, isActive: !u.is_active },
      {
        onSuccess: () => toast.success(`${u.username}: ${!u.is_active ? "ativado" : "desativado"}`),
        onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Erro"),
      },
    )
  }

  const onResetPassword = async (u: AdminUser) => {
    if (!window.confirm(`Gerar nova senha temporária para ${u.username}?`)) return
    resetPw.mutate(u.id, {
      onSuccess: (res) => {
        // Copy to clipboard and show in a sticky toast — the operator
        // is expected to hand this off out-of-band.
        try {
          void navigator.clipboard.writeText(res.temporary_password)
        } catch {
          /* clipboard unavailable — operator can still read it from the toast */
        }
        toast.success(
          `Senha temporária: ${res.temporary_password} (copiada)`,
          { duration: 15_000 },
        )
      },
      onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Erro"),
    })
  }

  const onDelete = (u: AdminUser) => {
    if (!window.confirm(`Desativar ${u.username}? (soft delete)`)) return
    deactivate.mutate(u.id, {
      onSuccess: () => toast.success(`${u.username} desativado`),
      onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Erro"),
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Usuários"
        subtitle="Gerenciar contas, empresas e permissões."
        actions={
          <>
            <button
              onClick={() => void refetch()}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent",
                isFetching && "opacity-60",
              )}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              Atualizar
            </button>
            <button
              onClick={() => setEditing("new")}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" /> Novo usuário
            </button>
          </>
        }
      />

      <div className="flex items-center gap-2 rounded-md border border-border bg-surface-1 p-2">
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por usuário ou e-mail…"
          className="h-7 flex-1 bg-transparent text-[12px] outline-none"
        />
        {search && (
          <button onClick={() => setSearch("")} className="text-muted-foreground hover:text-foreground">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <span className="text-[11px] text-muted-foreground">{users.length} usuário{users.length === 1 ? "" : "s"}</span>
      </div>

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="border-b border-border bg-muted/20 text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-2 py-2 text-left">Usuário</th>
              <th className="px-2 py-2 text-left">E-mail</th>
              <th className="px-2 py-2 text-left">Empresas</th>
              <th className="px-2 py-2 text-center">Papéis</th>
              <th className="px-2 py-2 text-center">Status</th>
              <th className="px-2 py-2 text-right">Último login</th>
              <th className="w-28 px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-border/60">
                  <td colSpan={7} className="px-2 py-2">
                    <div className="h-6 animate-pulse rounded bg-muted/40" />
                  </td>
                </tr>
              ))
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-2 py-6 text-center text-muted-foreground">
                  Nenhum usuário encontrado.
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr
                  key={u.id}
                  className={cn(
                    "border-b border-border/60 hover:bg-accent/40",
                    !u.is_active && "opacity-50",
                  )}
                >
                  <td className="px-2 py-1.5">
                    <button
                      onClick={() => setEditing(u)}
                      className="font-medium hover:underline"
                    >
                      {u.username}
                    </button>
                    {u.must_change_password && (
                      <span className="ml-2 rounded-full border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[10px] font-medium text-warning">
                        precisa trocar senha
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-muted-foreground">{u.email || "—"}</td>
                  <td className="px-2 py-1.5">
                    {u.companies.length === 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.companies.slice(0, 3).map((c) => (
                          <span
                            key={c.id}
                            className="rounded-md border border-border bg-surface-3 px-1.5 py-0.5 text-[10px]"
                            title={`${c.company_name} (${c.role})`}
                          >
                            {c.company_name}
                            {c.is_primary && " ★"}
                          </span>
                        ))}
                        {u.companies.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{u.companies.length - 3}</span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    {u.is_superuser && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                        <ShieldCheck className="h-3 w-3" /> super
                      </span>
                    )}
                    {u.is_staff && !u.is_superuser && (
                      <span className="rounded-md border border-border bg-muted/40 px-1.5 py-0.5 text-[10px]">staff</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <span
                      className={cn(
                        "rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                        u.is_active ? "bg-success/10 text-success" : "bg-muted/40 text-muted-foreground",
                      )}
                    >
                      {u.is_active ? "ativo" : "inativo"}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right text-muted-foreground">
                    {u.last_login ? new Date(u.last_login).toLocaleString("pt-BR") : "—"}
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => onResetPassword(u)}
                        title="Gerar senha temporária"
                        className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onToggleActive(u)}
                        title={u.is_active ? "Desativar" : "Ativar"}
                        className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                      >
                        {u.is_active ? <UserMinus className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                      </button>
                      <button
                        onClick={() => onDelete(u)}
                        title="Soft delete"
                        className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-danger"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <UserEditorDrawer
        open={editing != null}
        user={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}

/* ---------------- Editor drawer ---------------- */

interface DraftMembership {
  company: number
  role: string
  is_primary: boolean
}

interface Draft {
  username: string
  email: string
  first_name: string
  last_name: string
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
  password: string
  set_companies: DraftMembership[]
}

function emptyDraft(): Draft {
  return {
    username: "",
    email: "",
    first_name: "",
    last_name: "",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    password: "",
    set_companies: [],
  }
}

function draftFromUser(u: AdminUser): Draft {
  return {
    username: u.username,
    email: u.email ?? "",
    first_name: u.first_name ?? "",
    last_name: u.last_name ?? "",
    is_active: u.is_active,
    is_staff: u.is_staff,
    is_superuser: u.is_superuser,
    password: "",
    set_companies: u.companies.map((c) => ({ company: c.company, role: c.role, is_primary: c.is_primary })),
  }
}

function UserEditorDrawer({
  open, user, onClose,
}: {
  open: boolean
  user: AdminUser | null
  onClose: () => void
}) {
  const { data: companies = [] } = useAdminCompanies()
  const save = useSaveAdminUser()
  const [draft, setDraft] = useState<Draft>(emptyDraft())

  useEffect(() => {
    if (open) setDraft(user ? draftFromUser(user) : emptyDraft())
  }, [open, user])

  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }))

  const availableCompanies = useMemo(
    () => companies.filter((c) => !draft.set_companies.some((m) => m.company === c.id)),
    [companies, draft.set_companies],
  )

  const addMembership = (companyId: number) => {
    setDraft((d) => ({
      ...d,
      set_companies: [
        ...d.set_companies,
        { company: companyId, role: "operator", is_primary: d.set_companies.length === 0 },
      ],
    }))
  }
  /**
   * Apply a role to every tenant in one click. Adds missing memberships
   * with the selected role, overwrites the role on memberships that
   * already exist, and preserves whichever entry is marked primary
   * (defaults to the first row when there's none yet). The "all
   * tenants" shortcut the operator asked for — no more clicking through
   * the dropdown six times for a fresh hire.
   */
  const applyRoleToAllTenants = (role: string) => {
    setDraft((d) => {
      const existing = new Map(d.set_companies.map((m) => [m.company, m]))
      const merged: DraftMembership[] = companies.map((c) => {
        const prior = existing.get(c.id)
        return {
          company: c.id,
          role,
          is_primary: prior?.is_primary ?? false,
        }
      })
      // Guarantee exactly one primary so the backend doesn't have to demote.
      if (!merged.some((m) => m.is_primary) && merged.length > 0) {
        merged[0].is_primary = true
      }
      return { ...d, set_companies: merged }
    })
  }
  const clearAllMemberships = () => {
    setDraft((d) => ({ ...d, set_companies: [] }))
  }
  const updateMembership = (i: number, p: Partial<DraftMembership>) => {
    setDraft((d) => ({
      ...d,
      set_companies: d.set_companies.map((m, j) => {
        if (j !== i) {
          // flipping is_primary on row i means clearing it everywhere else.
          if (p.is_primary) return { ...m, is_primary: false }
          return m
        }
        return { ...m, ...p }
      }),
    }))
  }
  const removeMembership = (i: number) => {
    setDraft((d) => ({ ...d, set_companies: d.set_companies.filter((_, j) => j !== i) }))
  }

  const onSubmit = () => {
    if (!draft.username) {
      toast.error("Usuário obrigatório")
      return
    }
    save.mutate(
      {
        id: user?.id,
        body: {
          username: draft.username,
          email: draft.email || null,
          first_name: draft.first_name,
          last_name: draft.last_name,
          is_active: draft.is_active,
          is_staff: draft.is_staff,
          is_superuser: draft.is_superuser,
          ...(draft.password ? { password: draft.password } : {}),
          set_companies: draft.set_companies,
        },
      },
      {
        onSuccess: () => {
          toast.success(user ? "Atualizado" : "Criado")
          onClose()
        },
        onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="text-[13px] font-semibold">
              {user ? `Editar ${user.username}` : "Novo usuário"}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <section className="grid grid-cols-2 gap-2">
              <Field label="Usuário">
                <input
                  value={draft.username}
                  onChange={(e) => patch({ username: e.target.value })}
                  disabled={!!user}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none disabled:opacity-60"
                />
              </Field>
              <Field label="E-mail">
                <input
                  type="email"
                  value={draft.email}
                  onChange={(e) => patch({ email: e.target.value })}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none"
                />
              </Field>
              <Field label="Nome">
                <input
                  value={draft.first_name}
                  onChange={(e) => patch({ first_name: e.target.value })}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none"
                />
              </Field>
              <Field label="Sobrenome">
                <input
                  value={draft.last_name}
                  onChange={(e) => patch({ last_name: e.target.value })}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none"
                />
              </Field>
              <Field label={user ? "Nova senha (opcional)" : "Senha"}>
                <input
                  type="password"
                  value={draft.password}
                  onChange={(e) => patch({ password: e.target.value })}
                  placeholder={user ? "deixar em branco para manter" : "min. 8 caracteres"}
                  className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none"
                />
              </Field>
            </section>

            <section className="flex flex-wrap gap-3 rounded-md border border-border bg-surface-1 p-2">
              <Toggle label="Ativo" value={draft.is_active} onChange={(v) => patch({ is_active: v })} />
              <Toggle label="Staff" value={draft.is_staff} onChange={(v) => patch({ is_staff: v })} />
              <Toggle label="Superuser" value={draft.is_superuser} onChange={(v) => patch({ is_superuser: v })} />
            </section>

            <section className="rounded-md border border-border bg-surface-1 p-2">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Empresas ({draft.set_companies.length}/{companies.length})
                </span>
                {draft.set_companies.length > 0 && (
                  <button
                    type="button"
                    onClick={clearAllMemberships}
                    className="text-[10px] text-muted-foreground hover:text-danger"
                    title="Remover todos os vínculos"
                  >
                    Limpar todos
                  </button>
                )}
              </div>

              {/* "All tenants" shortcut — pick a role and stamp it
                  across every company in one click. Existing entries
                  get their role overwritten; new ones are added. */}
              <BulkAssignRow
                disabled={companies.length === 0}
                allCovered={
                  companies.length > 0 &&
                  draft.set_companies.length === companies.length
                }
                onApply={applyRoleToAllTenants}
              />

              <div className="space-y-2">
                {draft.set_companies.map((m, i) => {
                  const c = companies.find((cc) => cc.id === m.company)
                  return (
                    <div key={m.company} className="grid grid-cols-[1fr_110px_auto_auto] items-center gap-2">
                      <span className="truncate text-[12px]">{c?.name ?? `#${m.company}`}</span>
                      <select
                        value={m.role}
                        onChange={(e) => updateMembership(i, { role: e.target.value })}
                        className="h-7 rounded-md border border-border bg-background px-2 text-[11px]"
                      >
                        {ROLES.map((r) => (
                          <option key={r.id} value={r.id}>{r.label}</option>
                        ))}
                      </select>
                      <label className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={m.is_primary}
                          onChange={(e) => updateMembership(i, { is_primary: e.target.checked })}
                          className="h-3 w-3 accent-primary"
                        />
                        primária
                      </label>
                      <button
                        onClick={() => removeMembership(i)}
                        className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-danger"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )
                })}
                {availableCompanies.length > 0 && (
                  <select
                    onChange={(e) => {
                      const id = Number(e.target.value)
                      if (id) addMembership(id)
                      e.currentTarget.value = ""
                    }}
                    className="h-7 w-full rounded-md border border-dashed border-border bg-background px-2 text-[11px] text-muted-foreground"
                    defaultValue=""
                  >
                    <option value="">+ Adicionar empresa…</option>
                    {availableCompanies.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                )}
              </div>
            </section>
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              onClick={onSubmit}
              disabled={save.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              {user ? "Salvar" : "Criar"}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

/**
 * Pick-a-role + "Aplicar a todas" shortcut for the user editor's
 * Empresas section. Lives in this file because it touches the same
 * draft state as the surrounding editor and is too thin to deserve
 * its own module.
 */
function BulkAssignRow({
  disabled,
  allCovered,
  onApply,
}: {
  disabled: boolean
  /** True when the draft already covers every tenant — used to switch
   *  the button copy from "Aplicar a todas" to "Sobrescrever todas"
   *  so operators don't think it's a no-op. */
  allCovered: boolean
  onApply: (role: string) => void
}) {
  const [role, setRole] = useState<string>("operator")
  return (
    <div className="mb-2 flex items-center gap-2 rounded-md border border-dashed border-border bg-background/40 px-2 py-1.5">
      <Globe2 className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
        Todas
      </span>
      <select
        value={role}
        onChange={(e) => setRole(e.target.value)}
        disabled={disabled}
        className="h-7 rounded-md border border-border bg-background px-2 text-[11px] disabled:opacity-50"
      >
        {ROLES.map((r) => (
          <option key={r.id} value={r.id}>{r.label}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => onApply(role)}
        disabled={disabled}
        title={
          allCovered
            ? "Sobrescrever o papel em todas as empresas"
            : "Vincular a todas as empresas com este papel"
        }
        className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
      >
        <Wand2 className="h-3 w-3" />
        {allCovered ? "Sobrescrever todas" : "Aplicar a todas"}
      </button>
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

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-2 text-[12px]">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 accent-primary"
      />
      {label}
    </label>
  )
}
