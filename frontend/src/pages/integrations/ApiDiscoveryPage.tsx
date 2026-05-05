import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import {
  Sparkles, Globe, FileJson, Code2, Brain, ChevronRight, ChevronDown,
  CheckCircle2, AlertTriangle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  useDiscoverApis, useErpConnections, useImportDiscovered,
} from "@/features/integrations"
import type {
  DiscoveryCandidate, DiscoveryResult, DiscoveryStrategy,
} from "@/features/integrations"
import { cn } from "@/lib/utils"

const STRATEGY_LABEL: Record<DiscoveryStrategy, string> = {
  openapi: "OpenAPI / Swagger",
  postman: "Postman Collection",
  html: "HTML (heurística)",
  llm: "LLM (opt-in)",
}

const STRATEGY_ICON: Record<DiscoveryStrategy, typeof Globe> = {
  openapi: FileJson,
  postman: FileJson,
  html: Code2,
  llm: Brain,
}

/**
 * Phase-2 da Sandbox API: tela onde o operador cola uma URL de docs
 * e o sistema tenta identificar as APIs.
 *
 * Fluxo:
 *   1. URL + provider → POST /api-definitions/discover/
 *   2. Mostra candidatas com checkbox; operator filtra/revisa
 *   3. POST /api-definitions/import-discovered/ → cria as ERPAPIDefinitions
 *      (status=inactive, source=discovered) para revisão na lista
 */
export function ApiDiscoveryPage() {
  const navigate = useNavigate()
  const { data: connections = [] } = useErpConnections()
  const providers = useMemo(() => {
    const seen = new Map<number, string>()
    for (const c of connections) if (!seen.has(c.provider)) seen.set(c.provider, c.provider_display)
    return Array.from(seen, ([id, name]) => ({ id, name }))
  }, [connections])

  const [url, setUrl] = useState("")
  const [providerId, setProviderId] = useState<string>("")
  const [allowLlm, setAllowLlm] = useState(false)
  const [result, setResult] = useState<DiscoveryResult | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [filterStrategy, setFilterStrategy] = useState<string>("all")
  const [search, setSearch] = useState("")
  const [importMode, setImportMode] = useState<"create_only" | "enrich_existing" | "upsert">("upsert")

  const discover = useDiscoverApis()
  const imp = useImportDiscovered()

  const onDiscover = async () => {
    if (!url.trim()) { toast.warning("Informe a URL."); return }
    setSelected(new Set())
    discover.mutate(
      { url: url.trim(), allow_llm: allowLlm },
      {
        onSuccess: (res) => {
          setResult(res)
          if (!res.candidates || res.candidates.length === 0) {
            toast.warning("Nenhuma API identificada — tente outra URL ou ajuste os filtros.")
          } else {
            toast.success(`${res.candidates.length} candidata(s) encontrada(s) via ${res.strategy_used}`)
          }
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha na descoberta"),
      },
    )
  }

  const filtered = useMemo(() => {
    const cs = result?.candidates ?? []
    const q = search.trim().toLowerCase()
    return cs.filter((c) => {
      if (filterStrategy !== "all" && c.source_strategy !== filterStrategy) return false
      if (q && ![c.call, c.url, c.description].filter(Boolean).some((s) => s!.toLowerCase().includes(q))) return false
      return true
    })
  }, [result, filterStrategy, search])

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set())
    else setSelected(new Set(filtered.map((_, i) => i)))
  }

  const onImport = async () => {
    if (!result) return
    if (!providerId) { toast.warning("Escolha o provedor antes de importar."); return }
    if (selected.size === 0) { toast.warning("Selecione ao menos uma candidata."); return }
    const cands = filtered.filter((_, i) => selected.has(i))
    imp.mutate(
      { provider: Number(providerId), candidates: cands, mode: importMode },
      {
        onSuccess: (res) => {
          if (res.created_count > 0) {
            toast.success(`${res.created_count} definição(ões) importada(s) como inativas — revise antes de ativar.`)
          }
          if ((res.enriched_count ?? 0) > 0) {
            toast.success(`${res.enriched_count} definicao(oes) enriquecida(s) com filtros/metadados.`)
          }
          if (res.failed_count > 0) {
            toast.warning(`${res.failed_count} falharam (${res.failed.map(f => f.call ?? `#${f.index}`).slice(0, 3).join(", ")})`)
          }
          if (res.created_count > 0 || (res.enriched_count ?? 0) > 0) {
            navigate("/integrations/api-definitions")
          }
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha na importação"),
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Descobrir e enriquecer APIs"
        subtitle="Cole uma referencia de API para criar novas definicoes ou completar filtros, paginacao e records path das APIs cadastradas."
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/integrations/api-definitions")}>
            Ver definições
          </Button>
        }
      />

      {/* Form */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="grid gap-2 text-[12px] text-muted-foreground md:grid-cols-3">
          <div className="rounded-md border border-border bg-muted/20 p-2">
            <span className="font-medium text-foreground">1. Cole a referencia</span>
            <div>OpenAPI, Postman ou pagina HTML de documentacao.</div>
          </div>
          <div className="rounded-md border border-border bg-muted/20 p-2">
            <span className="font-medium text-foreground">2. Revise candidatas</span>
            <div>Confira calls, filtros, paginacao e caminho dos registros.</div>
          </div>
          <div className="rounded-md border border-border bg-muted/20 p-2">
            <span className="font-medium text-foreground">3. Aplique no catalogo</span>
            <div>Crie novas APIs ou complete as existentes sem apagar ajustes manuais.</div>
          </div>
        </div>
        <div className="grid grid-cols-12 gap-2">
          <div className="col-span-12 sm:col-span-7">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground">URL</label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://exemplo.com/swagger.json ou /api/docs"
              onKeyDown={(e) => { if (e.key === "Enter") onDiscover() }}
            />
          </div>
          <div className="col-span-6 sm:col-span-3">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground">Provedor</label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger className="h-9"><SelectValue placeholder="Escolher…" /></SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-6 sm:col-span-2 flex items-end">
            <Button onClick={onDiscover} disabled={discover.isPending} className="w-full">
              <Sparkles className="h-4 w-4" />
              {discover.isPending ? "Buscando..." : "Analisar"}
            </Button>
          </div>
        </div>
        <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <input
            type="checkbox"
            checked={allowLlm}
            onChange={(e) => setAllowLlm(e.target.checked)}
          />
          <span>
            Permitir tentativa por LLM (requer flag <code>allow_llm_doc_parse</code> ativa
            no tenant; sem isso, esta opção é ignorada com segurança).
          </span>
        </label>
      </div>

      {/* Result */}
      {discover.isPending ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center text-muted-foreground">
          Buscando — pode levar alguns segundos para parsear specs grandes…
        </div>
      ) : null}

      {result ? (
        <DiscoveryResultView
          result={result}
          filtered={filtered}
          selected={selected}
          setSelected={setSelected}
          toggleAll={toggleAll}
          search={search}
          setSearch={setSearch}
          filterStrategy={filterStrategy}
          setFilterStrategy={setFilterStrategy}
          onImport={onImport}
          importing={imp.isPending}
          providerId={providerId}
          importMode={importMode}
          setImportMode={setImportMode}
        />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------
// Result view
// ---------------------------------------------------------------------
function DiscoveryResultView({
  result, filtered, selected, setSelected, toggleAll, search, setSearch,
  filterStrategy, setFilterStrategy, onImport, importing, providerId,
  importMode, setImportMode,
}: {
  result: DiscoveryResult
  filtered: DiscoveryCandidate[]
  selected: Set<number>
  setSelected: (s: Set<number>) => void
  toggleAll: () => void
  search: string
  setSearch: (s: string) => void
  filterStrategy: string
  setFilterStrategy: (s: string) => void
  onImport: () => void
  importing: boolean
  providerId: string
  importMode: "create_only" | "enrich_existing" | "upsert"
  setImportMode: (mode: "create_only" | "enrich_existing" | "upsert") => void
}) {
  const strategyCounts = useMemo(() => {
    const m = new Map<DiscoveryStrategy, number>()
    for (const c of result.candidates) {
      m.set(c.source_strategy, (m.get(c.source_strategy) ?? 0) + 1)
    }
    return m
  }, [result.candidates])

  return (
    <div className="space-y-3">
      {/* Strategy banner */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 text-[12px]">
        <div className="flex items-center gap-2">
          {result.strategy_used ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-success" />
              <span className="font-medium">
                Estratégia usada: {STRATEGY_LABEL[result.strategy_used]}
              </span>
            </>
          ) : (
            <>
              <AlertTriangle className="h-4 w-4 text-warning" />
              <span>Nenhuma estratégia teve sucesso.</span>
            </>
          )}
          <span className="text-muted-foreground">
            · Tentadas: {result.strategies_tried.map((s) => STRATEGY_LABEL[s]).join(", ")}
          </span>
        </div>
        {result.errors.length > 0 ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-[11px] text-muted-foreground">
              {result.errors.length} erro(s) silenciados
            </summary>
            <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
              {result.errors.map((e, i) => (
                <li key={i}><span className="font-mono">{e.strategy}</span>: {e.message}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[240px] flex-1">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar call, URL, descrição…" />
        </div>
        <Select value={filterStrategy} onValueChange={setFilterStrategy}>
          <SelectTrigger className="h-9 w-[200px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as estratégias</SelectItem>
            {Array.from(strategyCounts.entries()).map(([s, n]) => (
              <SelectItem key={s} value={s}>
                {STRATEGY_LABEL[s]} ({n})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={importMode} onValueChange={(v) => setImportMode(v as typeof importMode)}>
          <SelectTrigger className="h-9 w-[220px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="upsert">Criar e enriquecer</SelectItem>
            <SelectItem value="create_only">Criar somente novas</SelectItem>
            <SelectItem value="enrich_existing">Enriquecer existentes</SelectItem>
          </SelectContent>
        </Select>
        <div className="basis-full text-[11px] text-muted-foreground">
          {importMode === "upsert"
            ? "Cria APIs novas e enriquece as ja cadastradas quando a call coincide."
            : importMode === "create_only"
              ? "Importa apenas chamadas ainda nao cadastradas."
              : "Completa apenas chamadas que ja existem no catalogo."}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground">
            {selected.size} de {filtered.length} selecionadas
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={toggleAll}
            disabled={filtered.length === 0}
          >
            {selected.size === filtered.length && filtered.length > 0 ? "Limpar" : "Selecionar todas"}
          </Button>
          <Button
            onClick={onImport}
            disabled={importing || selected.size === 0 || !providerId}
          >
            {importMode === "enrich_existing" ? "Enriquecer selecionadas" : "Importar selecionadas"} ({selected.size})
          </Button>
        </div>
      </div>

      {/* Candidates list */}
      <div className="rounded-lg border border-border bg-card divide-y divide-border/40">
        {filtered.length === 0 ? (
          <p className="p-6 text-center text-muted-foreground text-[12px]">
            Nenhuma candidata para os filtros atuais.
          </p>
        ) : filtered.map((c, i) => (
          <CandidateRow
            key={`${c.method}-${c.url}-${i}`}
            candidate={c}
            checked={selected.has(i)}
            onToggle={() => {
              const next = new Set(selected)
              if (next.has(i)) next.delete(i); else next.add(i)
              setSelected(next)
            }}
          />
        ))}
      </div>
    </div>
  )
}

function CandidateRow({
  candidate, checked, onToggle,
}: {
  candidate: DiscoveryCandidate
  checked: boolean
  onToggle: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const Icon = STRATEGY_ICON[candidate.source_strategy]
  return (
    <div className={cn("flex items-start gap-2 px-3 py-2", checked && "bg-primary/5")}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-1"
      />
      <button
        onClick={() => setExpanded((x) => !x)}
        className="grid h-5 w-5 place-items-center text-muted-foreground hover:text-foreground"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase">{candidate.method}</span>
          <span className="font-mono">{candidate.call}</span>
          <span className="text-muted-foreground truncate" title={candidate.url}>
            {candidate.url}
          </span>
        </div>
        {candidate.description ? (
          <div className="text-[11px] text-muted-foreground truncate" title={candidate.description}>
            {candidate.description}
          </div>
        ) : null}
      </div>
      <div className="flex flex-col items-end gap-1 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Icon className="h-3 w-3" />
          {STRATEGY_LABEL[candidate.source_strategy]}
        </span>
        <span className="font-mono">conf: {(candidate.confidence * 100).toFixed(0)}%</span>
      </div>
      {expanded ? (
        <div className="basis-full">
          <CandidateDetail candidate={candidate} />
        </div>
      ) : null}
    </div>
  )
}

function CandidateDetail({ candidate }: { candidate: DiscoveryCandidate }) {
  const params = candidate.param_schema ?? []
  return (
    <div className="ml-7 mt-2 rounded-md border border-border/60 bg-muted/20 p-2 text-[11px]">
      {params.length === 0 ? (
        <p className="text-muted-foreground">Sem parâmetros declarados.</p>
      ) : (
        <table className="w-full">
          <thead className="text-left text-[10px] uppercase text-muted-foreground">
            <tr>
              <th className="pr-3">name</th>
              <th className="pr-3">type</th>
              <th className="pr-3">in</th>
              <th className="pr-3">req</th>
              <th>description</th>
            </tr>
          </thead>
          <tbody>
            {params.map((p, i) => (
              <tr key={i} className="border-t border-border/40">
                <td className="pr-3 py-0.5 font-mono">{p.name}</td>
                <td className="pr-3 py-0.5 text-muted-foreground">{p.type}</td>
                <td className="pr-3 py-0.5 text-muted-foreground">{p.location}</td>
                <td className="pr-3 py-0.5 text-muted-foreground">{p.required ? "✓" : "—"}</td>
                <td className="py-0.5 text-muted-foreground">{p.description ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {candidate.notes ? (
        <p className="mt-2 text-muted-foreground italic">{candidate.notes}</p>
      ) : null}
    </div>
  )
}
