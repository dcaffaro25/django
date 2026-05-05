import { useEffect, useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import {
  Plus, RefreshCw, Search, Pencil, Trash2, Play, CheckCircle2,
  XCircle, AlertTriangle, Lock, Sparkles, ArrowUpDown,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Drawer } from "vaul"
import {
  useErpApiDefinitions, useErpConnections, useDeleteApiDefinition,
  useSaveApiDefinition, useTestCallApiDefinition, useValidateApiDefinition,
} from "@/features/integrations"
import type {
  ApiDefinitionTestCallResult, AuthStrategy, ERPAPIDefinition,
  ERPAPIDefinitionWrite, PaginationMode, PaginationSpec, ParamLocation,
  ParamSpec, ParamType, TestOutcome,
} from "@/features/integrations"
import { cn, formatDateTime } from "@/lib/utils"
import { useUserRole } from "@/features/auth/useUserRole"

// ---------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------
const PARAM_TYPES: ParamType[] = [
  "string", "int", "number", "boolean", "date", "datetime",
  "enum", "object", "array",
]
const PARAM_LOCATIONS: ParamLocation[] = ["body", "query", "path", "header"]
const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const

const AUTH_STRATEGIES: { value: AuthStrategy; label: string }[] = [
  { value: "provider_default", label: "Padrão do provedor (Omie etc.)" },
  { value: "query_params", label: "Query params" },
  { value: "bearer_header", label: "Bearer (Authorization header)" },
  { value: "basic", label: "Basic auth" },
  { value: "custom_template", label: "Template customizado" },
]

const PAGINATION_MODES: { value: PaginationMode; label: string }[] = [
  { value: "none", label: "Sem paginação" },
  { value: "page_number", label: "Por número de página" },
  { value: "cursor", label: "Cursor / token" },
  { value: "offset", label: "Offset + limit" },
]

const OUTCOME_LABEL: Record<TestOutcome, string> = {
  "": "Não testada",
  success: "Sucesso",
  error: "Erro",
  auth_fail: "Falha de auth",
}

const OUTCOME_TONE: Record<TestOutcome, string> = {
  "": "text-muted-foreground",
  success: "text-success",
  error: "text-destructive",
  auth_fail: "text-warning",
}

// ---------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------
export function ApiDefinitionsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { canWrite } = useUserRole()
  const [providerFilter, setProviderFilter] = useState<string>("all")
  const [search, setSearch] = useState("")
  const [outcomeFilter, setOutcomeFilter] = useState<string>("all")
  const [sort, setSort] = useState<{ key: "provider" | "call" | "method" | "url" | "auth" | "health" | "version"; dir: "asc" | "desc" }>({
    key: "call",
    dir: "asc",
  })
  const [showInactive, setShowInactive] = useState(false)
  const [editing, setEditing] = useState<ERPAPIDefinition | "new" | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<ERPAPIDefinition | null>(null)

  const { data: connections = [] } = useErpConnections()
  const providers = useMemo(() => {
    const seen = new Map<number, string>()
    for (const c of connections) {
      if (!seen.has(c.provider)) seen.set(c.provider, c.provider_display)
    }
    return Array.from(seen, ([id, name]) => ({ id, name }))
  }, [connections])

  const { data: defs = [], isLoading, isFetching, refetch } = useErpApiDefinitions({
    provider: providerFilter === "all" ? undefined : Number(providerFilter),
    include_inactive: showInactive,
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return defs.filter((d) => {
      if (outcomeFilter === "__untested" && d.last_test_outcome !== "") return false
      if (outcomeFilter !== "all" && outcomeFilter !== "__untested" && d.last_test_outcome !== outcomeFilter) return false
      if (!q) return true
      return [d.call, d.description, d.url, d.provider_display]
        .filter(Boolean)
        .some((s) => s!.toLowerCase().includes(q))
    })
  }, [defs, search, outcomeFilter])

  const sorted = useMemo(() => {
    const factor = sort.dir === "asc" ? 1 : -1
    return [...filtered].sort((a, b) => factor * compareDefinition(a, b, sort.key))
  }, [filtered, sort])

  const toggleSort = (key: typeof sort.key) => {
    setSort((current) => ({
      key,
      dir: current.key === key && current.dir === "asc" ? "desc" : "asc",
    }))
  }

  const del = useDeleteApiDefinition()

  useEffect(() => {
    const editId = Number(searchParams.get("edit"))
    if (!editId || defs.length === 0) return
    const target = defs.find((d) => d.id === editId)
    if (!target) return
    setEditing(target)
    const next = new URLSearchParams(searchParams)
    next.delete("edit")
    setSearchParams(next, { replace: true })
  }, [defs, searchParams, setSearchParams])

  const openInSandbox = (definition: ERPAPIDefinition) => {
    navigate(sandboxUrlForDefinition(definition, connections))
  }

  const onConfirmDelete = () => {
    if (!confirmDelete) return
    del.mutate(confirmDelete.id, {
      onSuccess: () => {
        toast.success(`Definição #${confirmDelete.id} removida`)
        setConfirmDelete(null)
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Definições de API"
        subtitle="Catálogo das APIs externas que o sistema sabe consumir. Edite estruturadamente; o sandbox e as rotinas usam essas definições."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Atualizar
            </Button>
            {canWrite ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/integrations/api-definitions/discover")}
                title="Descobrir APIs a partir de URL de documentação"
              >
                <Sparkles className="h-4 w-4" /> Descobrir/enriquecer
              </Button>
            ) : null}
            {canWrite ? (
              <Button size="sm" onClick={() => setEditing("new")}>
                <Plus className="h-4 w-4" /> Nova definição
              </Button>
            ) : null}
          </>
        }
      />

      {/* Table */}
      <div className="max-h-[70vh] overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 z-10 border-b border-border bg-card text-left text-[11px] font-medium text-muted-foreground shadow-sm">
            <tr>
              <th className="px-3 py-2"><SortButton active={sort.key === "provider"} dir={sort.dir} onClick={() => toggleSort("provider")}>Provedor</SortButton></th>
              <th className="px-3 py-2"><SortButton active={sort.key === "call"} dir={sort.dir} onClick={() => toggleSort("call")}>Call</SortButton></th>
              <th className="px-3 py-2">Método</th>
              <th className="px-3 py-2"><SortButton active={sort.key === "url"} dir={sort.dir} onClick={() => toggleSort("url")}>URL</SortButton></th>
              <th className="px-3 py-2"><SortButton active={sort.key === "auth"} dir={sort.dir} onClick={() => toggleSort("auth")}>Auth</SortButton></th>
              <th className="px-3 py-2">Saúde</th>
              <th className="px-3 py-2"><SortButton active={sort.key === "version"} dir={sort.dir} onClick={() => toggleSort("version")}>v</SortButton></th>
              <th className="px-3 py-2"></th>
            </tr>
            <tr className="border-t border-border/60 bg-muted/20">
              <th className="px-3 py-2">
                <Select value={providerFilter} onValueChange={setProviderFilter}>
                  <SelectTrigger className="h-8 w-full min-w-[140px] text-[12px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {providers.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </th>
              <th className="px-3 py-2">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Call, URL ou descricao" className="h-8 pl-7 text-[12px]" />
                </div>
              </th>
              <th className="px-3 py-2"></th>
              <th className="px-3 py-2"></th>
              <th className="px-3 py-2"></th>
              <th className="px-3 py-2">
                <Select value={outcomeFilter} onValueChange={setOutcomeFilter}>
                  <SelectTrigger className="h-8 w-full min-w-[130px] text-[12px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="success">Sucesso</SelectItem>
                    <SelectItem value="error">Erro</SelectItem>
                    <SelectItem value="auth_fail">Falha auth</SelectItem>
                    <SelectItem value="__untested">Nao testada</SelectItem>
                  </SelectContent>
                </Select>
              </th>
              <th className="px-3 py-2">
                <label className="flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2 text-[11px]">
                  <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="h-3.5 w-3.5" />
                  Inativas
                </label>
              </th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">Carregando…</td></tr>
            ) : sorted.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">Nenhuma definição encontrada.</td></tr>
            ) : (
              sorted.map((d) => (
                <tr
                  key={d.id}
                  className={cn(
                    "border-b border-border/40 last:border-b-0 hover:bg-muted/30 cursor-pointer",
                    !d.is_active && "opacity-60",
                  )}
                  onClick={() => setEditing(d)}
                >
                  <td className="px-3 py-2 text-muted-foreground">{d.provider_display}</td>
                  <td className="px-3 py-2 font-mono">{d.call}</td>
                  <td className="px-3 py-2 text-muted-foreground">{d.method}</td>
                  <td className="px-3 py-2 truncate text-muted-foreground" title={d.url}>
                    {d.url.length > 60 ? d.url.slice(0, 57) + "…" : d.url}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{d.auth_strategy}</td>
                  <td className="px-3 py-2">
                    <HealthPill outcome={d.last_test_outcome} testedAt={d.last_tested_at ?? null} />
                  </td>
                  <td className="px-3 py-2 font-mono text-muted-foreground">v{d.version}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Abrir no sandbox"
                        onClick={(e) => { e.stopPropagation(); openInSandbox(d) }}
                      >
                        <Play className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Editar"
                        onClick={(e) => { e.stopPropagation(); setEditing(d) }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      {canWrite ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Remover"
                          onClick={(e) => { e.stopPropagation(); setConfirmDelete(d) }}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
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

      {/* Editor drawer */}
      <ApiDefinitionEditor
        open={editing !== null}
        definition={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
        onOpenSandbox={(definition) => openInSandbox(definition)}
      />

      {/* Delete confirm */}
      <Dialog open={confirmDelete !== null} onOpenChange={(o) => { if (!o) setConfirmDelete(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Remover definição</DialogTitle>
            <DialogDescription>
              {confirmDelete ? `Remover "${confirmDelete.call}" do provedor ${confirmDelete.provider_display}?` : ""}
              Pipelines existentes que usam esta definição podem quebrar.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>Cancelar</Button>
            <Button variant="destructive" onClick={onConfirmDelete} disabled={del.isPending}>
              <Trash2 className="h-4 w-4" /> Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------
// Health pill
// ---------------------------------------------------------------------
function compareDefinition(
  a: ERPAPIDefinition,
  b: ERPAPIDefinition,
  key: "provider" | "call" | "method" | "url" | "auth" | "health" | "version",
) {
  if (key === "provider") return a.provider_display.localeCompare(b.provider_display)
  if (key === "call") return a.call.localeCompare(b.call)
  if (key === "method") return a.method.localeCompare(b.method)
  if (key === "url") return a.url.localeCompare(b.url)
  if (key === "auth") return a.auth_strategy.localeCompare(b.auth_strategy)
  if (key === "health") return a.last_test_outcome.localeCompare(b.last_test_outcome)
  return a.version - b.version
}

function SortButton({
  active,
  dir,
  onClick,
  children,
}: {
  active: boolean
  dir: "asc" | "desc"
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("inline-flex items-center gap-1 font-medium hover:text-foreground", active && "text-foreground")}
    >
      {children}
      <ArrowUpDown className={cn("h-3 w-3", active ? "opacity-100" : "opacity-40")} />
      {active ? <span className="text-[9px] uppercase">{dir}</span> : null}
    </button>
  )
}

function HealthPill({ outcome, testedAt }: { outcome: TestOutcome; testedAt: string | null }) {
  const Icon =
    outcome === "success" ? CheckCircle2 :
    outcome === "auth_fail" ? Lock :
    outcome === "error" ? XCircle :
    AlertTriangle
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px]", OUTCOME_TONE[outcome])}>
      <Icon className="h-3 w-3" />
      <span>{OUTCOME_LABEL[outcome]}</span>
      {testedAt ? <span className="text-muted-foreground">· {formatDateTime(testedAt)}</span> : null}
    </span>
  )
}

function sandboxUrlForDefinition(definition: ERPAPIDefinition, connections: Array<{ id: number; provider: number }>): string {
  const connection = connections.find((c) => c.provider === definition.provider)
  const params = new URLSearchParams({ api_definition_id: String(definition.id) })
  if (connection) params.set("connection_id", String(connection.id))
  return `/integrations/sandbox?${params.toString()}`
}

// ---------------------------------------------------------------------
// Editor — drawer with structured form
// ---------------------------------------------------------------------
function emptyDefinition(providerId: number): ERPAPIDefinitionWrite {
  return {
    provider: providerId,
    call: "",
    url: "",
    method: "POST",
    description: "",
    is_active: true,
    param_schema: [],
    auth_strategy: "provider_default",
    pagination_spec: { mode: "none" },
    records_path: "",
    documentation_url: "",
    source: "manual",
  }
}

function ApiDefinitionEditor({
  open, definition, onClose, onOpenSandbox,
}: {
  open: boolean
  definition: ERPAPIDefinition | null
  onClose: () => void
  onOpenSandbox: (definition: ERPAPIDefinition) => void
}) {
  const { data: connections = [] } = useErpConnections()
  const providers = useMemo(() => {
    const seen = new Map<number, string>()
    for (const c of connections) if (!seen.has(c.provider)) seen.set(c.provider, c.provider_display)
    return Array.from(seen, ([id, name]) => ({ id, name }))
  }, [connections])
  const firstProviderId = providers[0]?.id ?? 0

  const [form, setForm] = useState<ERPAPIDefinitionWrite>(
    definition ?? emptyDefinition(firstProviderId),
  )
  const [errors, setErrors] = useState<Record<string, unknown>>({})

  // Reset form when the drawer (re)opens with a new target.
  useEffect(() => {
    if (open) {
      setForm(definition ?? emptyDefinition(firstProviderId))
      setErrors({})
      setTestResult(null)
    }
  }, [open, definition?.id, firstProviderId])  // eslint-disable-line react-hooks/exhaustive-deps

  const save = useSaveApiDefinition()
  const validate = useValidateApiDefinition()
  const testCall = useTestCallApiDefinition()
  const [testResult, setTestResult] = useState<ApiDefinitionTestCallResult | null>(null)
  const [testConnectionId, setTestConnectionId] = useState<number | null>(null)
  const [testParamValues, setTestParamValues] = useState<string>("{}")

  // Default test connection to first one matching the form's provider.
  useEffect(() => {
    if (testConnectionId) return
    const match = connections.find((c) => c.provider === form.provider)
    if (match) setTestConnectionId(match.id)
  }, [connections, form.provider, testConnectionId])

  const onSave = async () => {
    // Validate first; do not save if there are errors.
    const v = await validate.mutateAsync(form).catch(() => null)
    if (v && !v.ok) {
      setErrors(v.errors)
      toast.error("Definição tem erros — verifique os campos.")
      return
    }
    setErrors({})
    save.mutate(
      { id: definition?.id, body: form },
      {
        onSuccess: () => {
          toast.success(definition?.id ? "Definição atualizada" : "Definição criada")
          onClose()
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro ao salvar"),
      },
    )
  }

  const onTest = async () => {
    if (!definition?.id) {
      toast.warning("Salve a definição antes de testar.")
      return
    }
    if (!testConnectionId) {
      toast.warning("Selecione uma conexão.")
      return
    }
    let parsedValues: Record<string, unknown> = {}
    try {
      parsedValues = JSON.parse(testParamValues || "{}")
    } catch {
      toast.error("param_values JSON inválido")
      return
    }
    testCall.mutate(
      { id: definition.id, body: { connection_id: testConnectionId, param_values: parsedValues, max_pages: 1 } },
      {
        onSuccess: (res) => {
          setTestResult(res)
          if (res.ok) toast.success(`Testado: ${res.shape.items_found} item(s)`)
          else toast.error(`Falhou: ${res.outcome}`)
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro no teste"),
      },
    )
  }

  return (
    <Drawer.Root
      open={open}
      onOpenChange={(o) => { if (!o) onClose() }}
      direction="right"
    >
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Drawer.Content
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-3xl flex-col border-l border-border bg-background shadow-xl outline-none"
          aria-describedby={undefined}
        >
          <Drawer.Title className="sr-only">
            {definition?.id ? `Editar definição #${definition.id}` : "Nova definição de API"}
          </Drawer.Title>

          <header className="flex items-center justify-between border-b border-border px-5 py-3">
            <div>
              <h2 className="text-[14px] font-semibold">
                {definition?.id ? `${definition.provider_display} / ${definition.call} (v${definition.version})` : "Nova definição de API"}
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Editor estruturado: cada campo vira parte do payload final.
              </p>
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">×</button>
          </header>

          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {/* Identificação */}
            <Section title="Identificação">
              <Row label="Provedor">
                <Select
                  value={String(form.provider)}
                  onValueChange={(v) => setForm({ ...form, provider: Number(v) })}
                  disabled={!!definition?.id}
                >
                  <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {providers.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Row>
              <Row label="Call">
                <Input
                  value={form.call ?? ""}
                  onChange={(e) => setForm({ ...form, call: e.target.value })}
                  placeholder="ListarContasPagar"
                />
              </Row>
              <Row label="Descrição">
                <Input
                  value={form.description ?? ""}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="O que esta API retorna…"
                />
              </Row>
              <Row label="Documentação">
                <Input
                  value={form.documentation_url ?? ""}
                  onChange={(e) => setForm({ ...form, documentation_url: e.target.value })}
                  placeholder="https://app.omie.com.br/api/v1/…"
                />
              </Row>
              <Row label="Ativa">
                <input
                  type="checkbox"
                  checked={form.is_active ?? true}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                />
              </Row>
            </Section>

            {/* HTTP */}
            <Section title="HTTP">
              <Row label="Método">
                <Select
                  value={form.method ?? "POST"}
                  onValueChange={(v) => setForm({ ...form, method: v })}
                >
                  <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {HTTP_METHODS.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Row>
              <Row label="URL">
                <Input
                  value={form.url ?? ""}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                  placeholder="https://app.omie.com.br/api/v1/financas/contapagar/"
                />
              </Row>
            </Section>

            {/* Auth */}
            <Section title="Autenticação">
              <Row label="Estratégia">
                <Select
                  value={form.auth_strategy ?? "provider_default"}
                  onValueChange={(v) => setForm({ ...form, auth_strategy: v as AuthStrategy })}
                >
                  <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {AUTH_STRATEGIES.map((a) => (
                      <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Row>
              <p className="text-[11px] text-muted-foreground">
                Credenciais sempre vêm da Connection — nunca digite app_key /
                app_secret aqui. A estratégia controla COMO são enviadas.
              </p>
            </Section>

            {/* Param schema */}
            <Section title="Parâmetros">
              <ParamSchemaEditor
                rows={form.param_schema ?? []}
                onChange={(rows) => setForm({ ...form, param_schema: rows })}
                errors={(errors.param_schema as Array<{ row?: number; field?: string; message?: string }>) ?? []}
              />
            </Section>

            {/* Pagination */}
            <Section title="Paginação">
              <PaginationEditor
                spec={form.pagination_spec ?? { mode: "none" }}
                onChange={(s) => setForm({ ...form, pagination_spec: s })}
                errors={(errors.pagination_spec as string[]) ?? []}
              />
            </Section>

            {/* Response */}
            <Section title="Resposta">
              <Row label="records_path">
                <Input
                  value={form.records_path ?? ""}
                  onChange={(e) => setForm({ ...form, records_path: e.target.value })}
                  placeholder="conta_pagar_cadastro"
                />
              </Row>
              <p className="text-[11px] text-muted-foreground">
                JMESPath para o array de itens. Em branco, usa transform_engine.
              </p>
            </Section>

            {/* Test call */}
            {definition?.id ? (
              <Section title="Testar chamada">
                <Row label="Conexão">
                  <Select
                    value={testConnectionId ? String(testConnectionId) : ""}
                    onValueChange={(v) => setTestConnectionId(Number(v))}
                  >
                    <SelectTrigger className="h-8"><SelectValue placeholder="Escolha…" /></SelectTrigger>
                    <SelectContent>
                      {connections.filter((c) => c.provider === form.provider).map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.name ?? `Connection #${c.id}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Row>
                <Row label="param_values JSON">
                  <Input
                    value={testParamValues}
                    onChange={(e) => setTestParamValues(e.target.value)}
                    placeholder='{"pagina": 1}'
                  />
                </Row>
                <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onTest}
                  disabled={testCall.isPending || !testConnectionId}
                >
                  <Play className="h-4 w-4" />
                  {testCall.isPending ? "Chamando…" : "Testar"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenSandbox(definition)}
                >
                  <Play className="h-4 w-4" />
                  Abrir no sandbox
                </Button>
                </div>

                {testResult ? <TestCallResultView result={testResult} /> : null}
              </Section>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Salve a definição para habilitar o teste de chamada.
              </p>
            )}
          </div>

          <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
            <Button variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button onClick={onSave} disabled={save.isPending || validate.isPending}>
              {definition?.id ? "Salvar alterações" : "Criar definição"}
            </Button>
          </footer>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

// ---------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-2 rounded-md border border-border bg-card p-3">
        {children}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <label className="w-32 shrink-0 text-[11px] font-medium text-muted-foreground">{label}</label>
      <div className="flex-1">{children}</div>
    </div>
  )
}

function ParamSchemaEditor({
  rows, onChange, errors,
}: {
  rows: ParamSpec[]
  onChange: (rows: ParamSpec[]) => void
  errors: Array<{ row?: number; field?: string; message?: string }>
}) {
  const errByRow = useMemo(() => {
    const m = new Map<number, string[]>()
    for (const e of errors) {
      const row = typeof e.row === "number" ? e.row : -1
      const list = m.get(row) ?? []
      list.push(`${e.field ?? ""}: ${e.message ?? ""}`)
      m.set(row, list)
    }
    return m
  }, [errors])

  const update = (idx: number, patch: Partial<ParamSpec>) => {
    const next = rows.map((r, i) => i === idx ? { ...r, ...patch } : r)
    onChange(next)
  }
  const remove = (idx: number) => onChange(rows.filter((_, i) => i !== idx))
  const add = () => onChange([...rows, { name: "", type: "string", location: "body" }])

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-12 gap-2 text-[10px] font-medium text-muted-foreground">
        <div className="col-span-3">name</div>
        <div className="col-span-2">type</div>
        <div className="col-span-2">location</div>
        <div className="col-span-2">default</div>
        <div className="col-span-1 text-center">req</div>
        <div className="col-span-2"></div>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-3 text-center text-[11px] text-muted-foreground">
          Sem parâmetros — clique em "Adicionar" para começar.
        </p>
      ) : null}
      {rows.map((row, i) => {
        const rowErrors = errByRow.get(i)
        return (
          <div key={i} className="space-y-1">
            <div className="grid grid-cols-12 items-center gap-2">
              <Input
                value={row.name}
                onChange={(e) => update(i, { name: e.target.value })}
                className="col-span-3 h-8 text-[12px]"
                placeholder="pagina"
              />
              <Select value={row.type ?? "string"} onValueChange={(v) => update(i, { type: v as ParamType })}>
                <SelectTrigger className="col-span-2 h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PARAM_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={row.location ?? "body"} onValueChange={(v) => update(i, { location: v as ParamLocation })}>
                <SelectTrigger className="col-span-2 h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PARAM_LOCATIONS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                </SelectContent>
              </Select>
              <Input
                value={row.default == null ? "" : String(row.default)}
                onChange={(e) => update(i, { default: e.target.value })}
                className="col-span-2 h-8 text-[12px]"
                placeholder="—"
              />
              <div className="col-span-1 flex justify-center">
                <input
                  type="checkbox"
                  checked={row.required ?? false}
                  onChange={(e) => update(i, { required: e.target.checked })}
                />
              </div>
              <div className="col-span-2 flex justify-end">
                <Button variant="ghost" size="icon" onClick={() => remove(i)}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            </div>
            {rowErrors ? (
              <div className="ml-2 text-[10px] text-destructive">
                {rowErrors.join(" · ")}
              </div>
            ) : null}
          </div>
        )
      })}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="h-4 w-4" /> Adicionar
      </Button>
    </div>
  )
}

function PaginationEditor({
  spec, onChange, errors,
}: {
  spec: PaginationSpec
  onChange: (s: PaginationSpec) => void
  errors: string[]
}) {
  const set = (patch: Partial<PaginationSpec>) => onChange({ ...spec, ...patch })
  return (
    <div className="space-y-2">
      <Row label="Modo">
        <Select value={spec.mode} onValueChange={(v) => set({ mode: v as PaginationMode })}>
          <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PAGINATION_MODES.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </Row>
      {spec.mode === "page_number" && (
        <>
          <Row label="page_param"><Input value={spec.page_param ?? ""} onChange={(e) => set({ page_param: e.target.value })} placeholder="pagina" /></Row>
          <Row label="page_size_param"><Input value={spec.page_size_param ?? ""} onChange={(e) => set({ page_size_param: e.target.value })} placeholder="registros_por_pagina" /></Row>
          <Row label="page_size"><Input type="number" value={spec.page_size ?? ""} onChange={(e) => set({ page_size: Number(e.target.value) || undefined })} placeholder="50" /></Row>
        </>
      )}
      {spec.mode === "cursor" && (
        <>
          <Row label="cursor_path"><Input value={spec.cursor_path ?? ""} onChange={(e) => set({ cursor_path: e.target.value })} placeholder="next_page_token" /></Row>
          <Row label="next_cursor_param"><Input value={spec.next_cursor_param ?? ""} onChange={(e) => set({ next_cursor_param: e.target.value })} placeholder="page_token" /></Row>
        </>
      )}
      {spec.mode === "offset" && (
        <>
          <Row label="offset_param"><Input value={spec.offset_param ?? ""} onChange={(e) => set({ offset_param: e.target.value })} placeholder="offset" /></Row>
          <Row label="limit_param"><Input value={spec.limit_param ?? ""} onChange={(e) => set({ limit_param: e.target.value })} placeholder="limit" /></Row>
        </>
      )}
      {spec.mode !== "none" && (
        <Row label="max_pages"><Input type="number" value={spec.max_pages ?? ""} onChange={(e) => set({ max_pages: Number(e.target.value) || undefined })} placeholder="Sem limite" /></Row>
      )}
      {errors.length > 0 && (
        <div className="text-[10px] text-destructive">{errors.join(" · ")}</div>
      )}
    </div>
  )
}

function TestCallResultView({ result }: { result: ApiDefinitionTestCallResult }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2">
        <span className={cn("text-[11px] font-bold uppercase", OUTCOME_TONE[result.outcome])}>
          {OUTCOME_LABEL[result.outcome]}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {result.shape.items_found} item(s) extraído(s)
        </span>
      </div>
      {result.error ? (
        <pre className="whitespace-pre-wrap rounded-md border border-destructive/30 bg-destructive/5 p-2 text-[10px] text-destructive">
          {result.error}
        </pre>
      ) : null}
      {result.shape.columns.length > 0 ? (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">Estrutura</div>
          <div className="max-h-48 overflow-y-auto rounded-md border border-border/60">
            <table className="w-full text-[11px]">
              <thead className="bg-muted/50 text-left text-[10px] uppercase text-muted-foreground">
                <tr>
                  <th className="px-2 py-1">Coluna</th>
                  <th className="px-2 py-1">Tipo</th>
                  <th className="px-2 py-1">Exemplos</th>
                </tr>
              </thead>
              <tbody>
                {result.shape.columns.map((c) => (
                  <tr key={c.path} className="border-t border-border/40">
                    <td className="px-2 py-1 font-mono">{c.path}</td>
                    <td className="px-2 py-1 text-muted-foreground">{c.type}</td>
                    <td className="px-2 py-1 text-muted-foreground">
                      {c.samples.slice(0, 3).map((s) => JSON.stringify(s)).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  )
}
