import { useMemo, useState } from "react"
import { Drawer } from "vaul"
import {
  ArrowUpDown, ChevronLeft, ChevronRight, Copy, Database, Download, Filter, Plus, RefreshCw,
  SlidersHorizontal, Trash2,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { SectionHeader } from "@/components/ui/section-header"
import { useErpRawRecords } from "@/features/integrations"
import type { ERPRawRecord, ERPRawRecordListParams } from "@/features/integrations"
import { cn, formatDateTime } from "@/lib/utils"

const PAGE_SIZES = [25, 50, 100, 200]

type AdvancedLogic = "and" | "or"
type AdvancedRule = {
  id: string
  field: string
  op: string
  value: string
}

export function RawRecordsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [apiSearch, setApiSearch] = useState("")
  const [externalId, setExternalId] = useState("")
  const [externalIdMode, setExternalIdMode] = useState("any")
  const [pageNumber, setPageNumber] = useState("")
  const [recordIndex, setRecordIndex] = useState("")
  const [duplicate, setDuplicate] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [jsonPath, setJsonPath] = useState("")
  const [jsonOperator, setJsonOperator] = useState("icontains")
  const [jsonValue, setJsonValue] = useState("")
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [advancedLogic, setAdvancedLogic] = useState<AdvancedLogic>("and")
  const [advancedRules, setAdvancedRules] = useState<AdvancedRule[]>([])
  const [ordering, setOrdering] = useState("-fetched_at")
  const [selected, setSelected] = useState<ERPRawRecord | null>(null)

  const params = useMemo<ERPRawRecordListParams>(() => {
    const out: ERPRawRecordListParams = {
      page,
      page_size: pageSize,
      ordering,
      api_call__icontains: apiSearch.trim() || undefined,
      external_id: externalId.trim() || undefined,
      external_id__isnull: externalIdMode === "blank" ? true : externalIdMode === "filled" ? false : undefined,
      is_duplicate: duplicate === "all" ? undefined : duplicate === "true",
      page_number: pageNumber ? Number(pageNumber) : undefined,
      record_index: recordIndex ? Number(recordIndex) : undefined,
      fetched_at__gte: dateFrom ? `${dateFrom}T00:00:00` : undefined,
      fetched_at__lte: dateTo ? `${dateTo}T23:59:59` : undefined,
    }
    const cleanJsonPath = jsonPath.trim().replace(/^data__/, "")
    if (cleanJsonPath && jsonValue.trim()) {
      const normalizedPath = cleanJsonPath.replace(/\./g, "__")
      const suffix = jsonOperator === "exact" ? "" : `__${jsonOperator}`
      out[`data__${normalizedPath}${suffix}`] = jsonValue.trim()
    }
    const rules = advancedRules.filter((rule) => rule.field.trim() && rule.op && rule.value.trim())
    if (rules.length) {
      out.advanced_filter = JSON.stringify({
        logic: advancedLogic,
        rules: rules.map((rule) => ({
          field: normalizeAdvancedField(rule.field),
          op: rule.op,
          value: rule.value,
        })),
      })
    }
    return out
  }, [advancedLogic, advancedRules, apiSearch, dateFrom, dateTo, duplicate, externalId, externalIdMode, jsonOperator, jsonPath, jsonValue, ordering, page, pageNumber, pageSize, recordIndex])

  const { data, isLoading, isFetching, refetch } = useErpRawRecords(params)
  const rows = data?.results ?? []
  const total = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const resetFilters = () => {
    setApiSearch("")
    setExternalId("")
    setExternalIdMode("any")
    setPageNumber("")
    setRecordIndex("")
    setDuplicate("all")
    setDateFrom("")
    setDateTo("")
    setJsonPath("")
    setJsonOperator("icontains")
    setJsonValue("")
    setAdvancedRules([])
    setAdvancedLogic("and")
    setOrdering("-fetched_at")
    setPage(1)
  }

  const exportCsv = () => {
    if (rows.length === 0) {
      toast.warning("Nada para exportar nesta página.")
      return
    }
    downloadText(`registros_erp_${Date.now()}.csv`, rowsToCsv(rows), "text/csv;charset=utf-8")
    toast.success("Exportação da página gerada.")
  }

  const exportJson = () => {
    if (rows.length === 0) {
      toast.warning("Nada para exportar nesta página.")
      return
    }
    downloadText(
      `registros_erp_${Date.now()}.json`,
      JSON.stringify(rows.map((row) => row.data), null, 2),
      "application/json;charset=utf-8",
    )
    toast.success("JSON da página gerado.")
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Registros genéricos salvos"
        subtitle="Audite payloads brutos gravados por pipelines e execuções de teste, com filtros, ordenação e exportação."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Atualizar
            </Button>
            <Button variant="outline" size="sm" onClick={exportJson}>
              <Download className="h-4 w-4" /> JSON
            </Button>
            <Button size="sm" onClick={exportCsv}>
              <Download className="h-4 w-4" /> CSV
            </Button>
          </div>
        }
      />

      <section className="rounded-lg border border-border bg-card p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[12px] font-semibold">
            <Filter className="h-4 w-4 text-primary" /> Filtros avancados
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {total.toLocaleString("pt-BR")} registro(s)
            </span>
            <Button variant="outline" size="sm" onClick={() => setAdvancedOpen(true)}>
              <Filter className="h-4 w-4" /> Regras E/OU
              {advancedRules.length ? (
                <span className="ml-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                  {advancedRules.length}
                </span>
              ) : null}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <Field label="Por pagina">
            <Select value={String(pageSize)} onValueChange={(value) => { setPageSize(Number(value)); setPage(1) }}>
              <SelectTrigger className="h-9 w-[120px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>{size}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Button variant="ghost" size="sm" onClick={resetFilters}>Limpar todos os filtros</Button>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="max-h-[72vh] overflow-auto">
          <table className="w-full min-w-[920px] text-[12px]">
            <thead className="sticky top-0 z-10 border-b border-border bg-card text-left text-[11px] font-medium text-muted-foreground shadow-sm">
              <tr>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="ID"
                    active={ordering.replace("-", "") === "id"}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("id"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-id"); setPage(1) }}
                  />
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="API"
                    active={ordering.replace("-", "") === "api_call" || !!apiSearch.trim()}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("api_call"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-api_call"); setPage(1) }}
                    onClear={() => { setApiSearch(""); setPage(1) }}
                  >
                    <TextMenu label="Contem" value={apiSearch} onChange={(value) => { setApiSearch(value); setPage(1) }} placeholder="ex.: contas" />
                  </ColumnFilterHeader>
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="ID externo"
                    active={ordering.replace("-", "") === "external_id" || !!externalId.trim() || externalIdMode !== "any"}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("external_id"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-external_id"); setPage(1) }}
                    onClear={() => { setExternalId(""); setExternalIdMode("any"); setPage(1) }}
                  >
                    <TextMenu label="Igual a" value={externalId} onChange={(value) => { setExternalId(value); setPage(1) }} placeholder="id no ERP" />
                    <Select value={externalIdMode} onValueChange={(value) => { setExternalIdMode(value); setPage(1) }}>
                      <SelectTrigger className="mt-2 h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="any">Todos</SelectItem>
                        <SelectItem value="filled">Com valor</SelectItem>
                        <SelectItem value="blank">Vazios</SelectItem>
                      </SelectContent>
                    </Select>
                  </ColumnFilterHeader>
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="Posicao"
                    active={ordering.replace("-", "") === "page_number" || !!pageNumber || !!recordIndex}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("page_number"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-page_number"); setPage(1) }}
                    onClear={() => { setPageNumber(""); setRecordIndex(""); setPage(1) }}
                  >
                    <div className="grid grid-cols-2 gap-2">
                      <TextMenu label="Pagina" value={pageNumber} onChange={(value) => { setPageNumber(value); setPage(1) }} placeholder="1" type="number" />
                      <TextMenu label="Item" value={recordIndex} onChange={(value) => { setRecordIndex(value); setPage(1) }} placeholder="0" type="number" />
                    </div>
                  </ColumnFilterHeader>
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="Status"
                    active={ordering.replace("-", "") === "is_duplicate" || duplicate !== "all"}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("is_duplicate"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-is_duplicate"); setPage(1) }}
                    onClear={() => { setDuplicate("all"); setPage(1) }}
                  >
                    <Select value={duplicate} onValueChange={(value) => { setDuplicate(value); setPage(1) }}>
                      <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        <SelectItem value="false">Unicos</SelectItem>
                        <SelectItem value="true">Duplicados</SelectItem>
                      </SelectContent>
                    </Select>
                  </ColumnFilterHeader>
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="Coletado em"
                    active={ordering.replace("-", "") === "fetched_at" || !!dateFrom || !!dateTo}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("fetched_at"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-fetched_at"); setPage(1) }}
                    onClear={() => { setDateFrom(""); setDateTo(""); setPage(1) }}
                  >
                    <div className="grid grid-cols-2 gap-2">
                      <TextMenu label="De" value={dateFrom} onChange={(value) => { setDateFrom(value); setPage(1) }} type="date" />
                      <TextMenu label="Ate" value={dateTo} onChange={(value) => { setDateTo(value); setPage(1) }} type="date" />
                    </div>
                  </ColumnFilterHeader>
                </th>
                <th className="px-3 py-2">
                  <ColumnFilterHeader
                    label="Resumo"
                    active={!!jsonPath.trim() && !!jsonValue.trim()}
                    dir={ordering.startsWith("-") ? "desc" : "asc"}
                    onSortAsc={() => { setOrdering("id"); setPage(1) }}
                    onSortDesc={() => { setOrdering("-id"); setPage(1) }}
                    onClear={() => { setJsonPath(""); setJsonValue(""); setJsonOperator("icontains"); setPage(1) }}
                  >
                    <TextMenu label="Campo JSON" value={jsonPath} onChange={(value) => { setJsonPath(value); setPage(1) }} placeholder="cliente.nome" />
                    <Select value={jsonOperator} onValueChange={(value) => { setJsonOperator(value); setPage(1) }}>
                      <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="icontains">Contem</SelectItem>
                        <SelectItem value="exact">Igual a</SelectItem>
                        <SelectItem value="gt">Maior que</SelectItem>
                        <SelectItem value="gte">Maior ou igual</SelectItem>
                        <SelectItem value="lt">Menor que</SelectItem>
                        <SelectItem value="lte">Menor ou igual</SelectItem>
                        <SelectItem value="isnull">Vazio?</SelectItem>
                      </SelectContent>
                    </Select>
                    <TextMenu label="Valor" value={jsonValue} onChange={(value) => { setJsonValue(value); setPage(1) }} placeholder="valor" />
                  </ColumnFilterHeader>
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">Carregando registros...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">Nenhum registro encontrado.</td></tr>
              ) : rows.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-b border-border/40 last:border-b-0 hover:bg-muted/30"
                  onClick={() => setSelected(row)}
                >
                  <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">#{row.id}</td>
                  <td className="px-3 py-2 font-medium">{row.api_call}</td>
                  <td className="px-3 py-2 font-mono text-[11px]">{row.external_id ?? "-"}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    pág. {row.page_number} · item {row.record_index}
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      "rounded-full border px-2 py-1 text-[11px]",
                      row.is_duplicate ? "border-warning/40 text-warning" : "border-success/30 text-success",
                    )}>
                      {row.is_duplicate ? "duplicado" : "único"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{formatDateTime(row.fetched_at)}</td>
                  <td className="max-w-[320px] px-3 py-2 text-muted-foreground">
                    <SummaryCell data={row.data} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2 text-[12px]">
          <span className="text-muted-foreground">
            Página {page} de {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
              <ChevronLeft className="h-4 w-4" /> Anterior
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
              Próxima <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </section>

      <RawRecordDrawer record={selected} onClose={() => setSelected(null)} />
      <AdvancedFiltersDrawer
        open={advancedOpen}
        logic={advancedLogic}
        rules={advancedRules}
        onClose={() => setAdvancedOpen(false)}
        onLogicChange={setAdvancedLogic}
        onRulesChange={(rules) => {
          setAdvancedRules(rules)
          setPage(1)
        }}
      />
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function RawRecordDrawer({ record, onClose }: { record: ERPRawRecord | null; onClose: () => void }) {
  const json = record ? JSON.stringify(record.data, null, 2) : ""
  const copyJson = async () => {
    if (!json) return
    await navigator.clipboard.writeText(json)
    toast.success("JSON copiado.")
  }

  return (
    <Drawer.Root open={!!record} onOpenChange={(open) => !open && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[720px] flex-col border-l border-border surface-2 outline-none">
          <Drawer.Title className="sr-only">Detalhe do registro ERP</Drawer.Title>
          {record ? (
            <>
              <div className="border-b border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-[13px] font-semibold">
                      <Database className="h-4 w-4 text-primary" /> Registro #{record.id}
                    </div>
                    <div className="mt-1 text-[12px] text-muted-foreground">
                      {record.api_call} · {formatDateTime(record.fetched_at)}
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={copyJson}>
                    <Copy className="h-4 w-4" /> Copiar JSON
                  </Button>
                </div>
              </div>

              <div className="grid gap-2 border-b border-border p-4 text-[12px] sm:grid-cols-3">
                <Info label="ID externo" value={record.external_id ?? "-"} />
                <Info label="Página / item" value={`${record.page_number} / ${record.record_index}`} />
                <Info label="Duplicidade" value={record.is_duplicate ? "duplicado" : "único"} />
                <Info label="Run" value={record.pipeline_run ? `pipeline ${record.pipeline_run}` : record.sync_run ? `sync ${record.sync_run}` : "-"} />
                <Info label="Etapa" value={record.pipeline_step_order != null ? String(record.pipeline_step_order) : "-"} />
                <Info label="Hash" value={record.record_hash || "-"} mono />
              </div>

              <div className="min-h-0 flex-1 overflow-auto p-4">
                <pre className="min-h-full whitespace-pre-wrap rounded-lg border border-border bg-background p-3 text-[11px] leading-relaxed">
                  {json}
                </pre>
              </div>
            </>
          ) : null}
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-md border border-border/70 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("mt-1 truncate", mono && "font-mono text-[11px]")}>{value}</div>
    </div>
  )
}

function AdvancedFiltersDrawer({
  open,
  logic,
  rules,
  onClose,
  onLogicChange,
  onRulesChange,
}: {
  open: boolean
  logic: AdvancedLogic
  rules: AdvancedRule[]
  onClose: () => void
  onLogicChange: (logic: AdvancedLogic) => void
  onRulesChange: (rules: AdvancedRule[]) => void
}) {
  const addRule = () => {
    onRulesChange([
      ...rules,
      { id: String(Date.now()), field: "data.", op: "icontains", value: "" },
    ])
  }
  const updateRule = (id: string, patch: Partial<AdvancedRule>) => {
    onRulesChange(rules.map((rule) => (rule.id === id ? { ...rule, ...patch } : rule)))
  }
  const removeRule = (id: string) => {
    onRulesChange(rules.filter((rule) => rule.id !== id))
  }

  return (
    <Drawer.Root open={open} onOpenChange={(value) => !value && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[680px] flex-col border-l border-border surface-2 outline-none">
          <Drawer.Title className="border-b border-border px-4 py-3 text-[13px] font-semibold">
            Filtro avancado
          </Drawer.Title>
          <div className="space-y-4 overflow-auto p-4 text-[12px]">
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="mb-2 font-medium">Como combinar regras</div>
              <Select value={logic} onValueChange={(value) => onLogicChange(value as AdvancedLogic)}>
                <SelectTrigger className="h-9 w-[180px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="and">E - todas verdadeiras</SelectItem>
                  <SelectItem value="or">OU - qualquer uma</SelectItem>
                </SelectContent>
              </Select>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Use campos como <code>api_call</code>, <code>external_id</code>, <code>fetched_at</code> ou caminhos JSON como <code>data.cliente.nome</code>.
              </p>
            </div>

            <div className="space-y-2">
              {rules.map((rule, index) => (
                <div key={rule.id} className="rounded-lg border border-border bg-card p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Regra {index + 1}
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => removeRule(rule.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="grid gap-2 md:grid-cols-[1fr_150px_1fr]">
                    <Field label="Campo">
                      <Input
                        value={rule.field}
                        onChange={(event) => updateRule(rule.id, { field: event.target.value })}
                        placeholder="data.cliente.nome"
                        className="h-9"
                      />
                    </Field>
                    <Field label="Operador">
                      <Select value={rule.op} onValueChange={(value) => updateRule(rule.id, { op: value })}>
                        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="icontains">Contem</SelectItem>
                          <SelectItem value="exact">Igual</SelectItem>
                          <SelectItem value="neq">Diferente</SelectItem>
                          <SelectItem value="gt">Maior que</SelectItem>
                          <SelectItem value="gte">Maior ou igual</SelectItem>
                          <SelectItem value="lt">Menor que</SelectItem>
                          <SelectItem value="lte">Menor ou igual</SelectItem>
                          <SelectItem value="startswith">Comeca com</SelectItem>
                          <SelectItem value="endswith">Termina com</SelectItem>
                          <SelectItem value="isnull">Vazio?</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Valor">
                      <Input
                        value={rule.value}
                        onChange={(event) => updateRule(rule.id, { value: event.target.value })}
                        placeholder={rule.op === "isnull" ? "true ou false" : "valor"}
                        className="h-9"
                      />
                    </Field>
                  </div>
                </div>
              ))}
              {rules.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-muted-foreground">
                  Nenhuma regra avancada. Adicione uma regra para filtrar por JSON, comparacoes numericas ou combinacoes E/OU.
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex justify-between gap-2 border-t border-border p-4">
            <Button variant="outline" onClick={addRule}>
              <Plus className="h-4 w-4" /> Adicionar regra
            </Button>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => onRulesChange([])}>Limpar</Button>
              <Button onClick={onClose}>Aplicar</Button>
            </div>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function ColumnFilterHeader({
  active,
  dir,
  label,
  onSortAsc,
  onSortDesc,
  onClear,
  children,
}: {
  active: boolean
  dir: "asc" | "desc"
  label: string
  onSortAsc: () => void
  onSortDesc: () => void
  onClear?: () => void
  children?: React.ReactNode
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 rounded px-1 py-0.5 font-medium hover:bg-muted hover:text-foreground",
            active && "bg-primary/10 text-foreground",
          )}
        >
          {label}
          <Filter className={cn("h-3 w-3", active ? "text-primary opacity-100" : "opacity-45")} />
          {active ? <span className="text-[9px] uppercase">{dir}</span> : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72 p-3">
        <div className="mb-2 text-[11px] font-semibold text-foreground">{label}</div>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" onClick={onSortAsc} className="h-8 justify-start text-[12px]">
            <ArrowUpDown className="h-3.5 w-3.5" /> A-Z / menor
          </Button>
          <Button variant="outline" size="sm" onClick={onSortDesc} className="h-8 justify-start text-[12px]">
            <ArrowUpDown className="h-3.5 w-3.5" /> Z-A / maior
          </Button>
        </div>
        {children ? (
          <>
            <DropdownMenuSeparator className="my-3" />
            <div className="space-y-2" onKeyDown={(event) => event.stopPropagation()}>
              {children}
            </div>
          </>
        ) : null}
        {onClear ? (
          <>
            <DropdownMenuSeparator className="my-3" />
            <Button variant="ghost" size="sm" onClick={onClear} className="h-8 w-full justify-start text-[12px]">
              Limpar filtro da coluna
            </Button>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function TextMenu({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      <Input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-8 text-[12px]"
      />
    </label>
  )
}

function SummaryCell({ data }: { data: Record<string, unknown> }) {
  const entries = flattenRecord(data).slice(0, 24)
  const preview = summarizeData(data)
  return (
    <div className="group relative">
      <div className="truncate" title="">
        {preview}
      </div>
      <div className="pointer-events-none absolute right-0 top-7 z-50 hidden w-[min(520px,72vw)] rounded-lg border border-border bg-popover p-3 text-popover-foreground shadow-xl group-hover:block">
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-border pb-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Registro
          </div>
          <div className="text-[10px] text-muted-foreground">
            {entries.length} campo(s)
          </div>
        </div>
        {entries.length === 0 ? (
          <div className="text-[12px] text-muted-foreground">Sem campos para exibir.</div>
        ) : (
          <div className="max-h-[360px] overflow-auto pr-1">
            <dl className="grid grid-cols-[minmax(120px,0.42fr)_minmax(180px,0.58fr)] gap-x-3 gap-y-1.5 text-[12px]">
              {entries.map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="min-w-0 truncate font-mono text-[11px] text-muted-foreground" title={key}>
                    {key}
                  </dt>
                  <dd className="min-w-0 whitespace-pre-wrap break-words text-foreground">
                    {formatHoverValue(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </div>
  )
}

function summarizeData(data: Record<string, unknown>) {
  const entries = flattenRecord(data).slice(0, 5)
  if (entries.length === 0) return "{}"
  return entries.map(([key, value]) => key + ": " + formatSummaryValue(value)).join(" | ")
}

function flattenRecord(
  value: unknown,
  prefix = "",
  out: Array<[string, unknown]> = [],
): Array<[string, unknown]> {
  if (out.length >= 8) return out
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    if (prefix) out.push([prefix, value])
    return out
  }
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? prefix + "." + key : key
    if (child && typeof child === "object" && !Array.isArray(child)) {
      flattenRecord(child, path, out)
    } else {
      out.push([path, child])
    }
    if (out.length >= 8) break
  }
  return out
}

function formatSummaryValue(value: unknown) {
  if (value == null || value === "") return "-"
  if (Array.isArray(value)) return "[" + value.length + " itens]"
  if (typeof value === "object") return "{...}"
  return String(value).slice(0, 48)
}

function formatHoverValue(value: unknown) {
  if (value == null || value === "") return "-"
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]"
    const sample = value.slice(0, 3).map((item) =>
      item && typeof item === "object" ? JSON.stringify(item, null, 2) : String(item),
    )
    return sample.join("\n") + (value.length > 3 ? `\n... +${value.length - 3} item(ns)` : "")
  }
  if (typeof value === "object") return JSON.stringify(value, null, 2)
  if (typeof value === "boolean") return value ? "Sim" : "Nao"
  return String(value)
}

function normalizeAdvancedField(field: string) {
  const trimmed = field.trim()
  if (!trimmed) return trimmed
  if (trimmed.startsWith("data.") || trimmed.startsWith("data__")) return trimmed
  if (trimmed.startsWith("page_response_header.") || trimmed.startsWith("page_response_header__")) return trimmed
  if (["id", "api_call", "external_id", "page_number", "record_index", "global_index", "is_duplicate", "fetched_at"].includes(trimmed)) {
    return trimmed
  }
  return `data.${trimmed}`
}

function rowsToCsv(rows: ERPRawRecord[]) {
  const headers = ["id", "api_call", "external_id", "is_duplicate", "page_number", "record_index", "fetched_at", "data"]
  const lines = rows.map((row) => [
    row.id,
    row.api_call,
    row.external_id ?? "",
    row.is_duplicate ? "true" : "false",
    row.page_number,
    row.record_index,
    row.fetched_at,
    JSON.stringify(row.data),
  ].map(csvCell).join(","))
  return [headers.join(","), ...lines].join("\n")
}

function csvCell(value: unknown) {
  const text = String(value ?? "")
  return `"${text.replace(/"/g, '""')}"`
}

function downloadText(filename: string, text: string, type: string) {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
