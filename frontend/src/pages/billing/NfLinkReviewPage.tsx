import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  CheckCircle2, XCircle, Search, Wand2, RefreshCw,
  AlertTriangle, FileText, Receipt, ArrowRight, ArrowUpDown,
  Filter, Network,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import {
  useAcceptAllAbove, useAcceptLink, useBulkAcceptLinks, useBulkRejectLinks,
  useNfTxLinks, useRejectLink, useScanLinks,
} from "@/features/billing"
import type { LinkReviewStatus, NFTransactionLink } from "@/features/billing"
import { ConfidenceBadge } from "./components/ConfidenceBadge"
import {
  DimensionScores,
  type DimensionKey,
} from "./components/DimensionScores"
import { GroupDetailModal } from "./components/GroupDetailModal"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency } from "@/lib/utils"

const TAB_TO_STATUS: Record<string, LinkReviewStatus> = {
  suggested: "suggested",
  accepted: "accepted",
  rejected: "rejected",
}

type SortKey =
  | "confidence_desc" | "confidence_asc"
  | "nf_date_desc" | "nf_date_asc"
  | "amount_desc" | "amount_asc"

const SORT_LABELS: Record<SortKey, string> = {
  confidence_desc: "Confiança ↓",
  confidence_asc: "Confiança ↑",
  nf_date_desc: "Data NF ↓",
  nf_date_asc: "Data NF ↑",
  amount_desc: "Valor ↓",
  amount_asc: "Valor ↑",
}

function fmtCnpj(d?: string | null) {
  if (!d) return ""
  const s = d.replace(/\D/g, "")
  if (s.length !== 14) return d
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`
}

function fmtDate(s?: string | null) {
  if (!s) return ""
  try {
    return new Date(s).toLocaleDateString("pt-BR")
  } catch {
    return s
  }
}

function MethodTag({ method }: { method: NFTransactionLink["method"] }) {
  const label: Record<NFTransactionLink["method"], string> = {
    nf_number: "nf_number",
    description_regex: "regex",
    bank_description: "banco",
    manual: "manual",
    backfill: "backfill",
  }
  return (
    <span className="rounded-md border border-border bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {label[method] ?? method}
    </span>
  )
}

function LinkRow({
  link,
  selected,
  onToggle,
  onAccept,
  onReject,
  onOpenGroup,
  busy,
  selectable,
}: {
  link: NFTransactionLink
  selected: boolean
  onToggle: () => void
  onAccept: () => void
  onReject: () => void
  onOpenGroup: (groupId: number) => void
  busy?: boolean
  selectable: boolean
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm",
        link.is_stale ? "border-warning/40" : "border-border",
        selected && "ring-2 ring-primary/50",
      )}
    >
      <div className="flex items-start gap-3">
        {selectable ? (
          <div className="pt-1">
            <Checkbox
              checked={selected}
              onCheckedChange={() => onToggle()}
              aria-label="Selecionar vínculo"
            />
          </div>
        ) : null}

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-col gap-1.5 min-w-0">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <ConfidenceBadge value={link.confidence} />
                <MethodTag method={link.method} />
                {link.is_stale ? (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-1.5 py-0.5 text-[10px] font-medium text-warning"
                    title="Os valores de origem mudaram após o vínculo — revise."
                  >
                    <AlertTriangle className="h-3 w-3" />
                    desatualizado
                  </span>
                ) : null}
                {link.cnpj_group_id != null ? (
                  <button
                    type="button"
                    onClick={() => onOpenGroup(link.cnpj_group_id!)}
                    className="inline-flex items-center gap-1 rounded-full border border-info/40 bg-info/10 px-1.5 py-0.5 text-[10px] font-medium text-info hover:bg-info/20"
                    title="CNPJs distintos pertencem ao mesmo grupo de parceiros. Clique para ver/editar."
                  >
                    <Network className="h-3 w-3" />
                    mesmo grupo
                  </button>
                ) : null}
              </div>
              <DimensionScores link={link} />
            </div>
            {link.review_status === "suggested" ? (
              <div className="flex items-center gap-2">
                <Button size="sm" variant="default" onClick={onAccept} disabled={busy}>
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Aceitar
                </Button>
                <Button size="sm" variant="outline" onClick={onReject} disabled={busy}>
                  <XCircle className="h-3.5 w-3.5" />
                  Rejeitar
                </Button>
              </div>
            ) : link.review_status === "accepted" ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">
                <CheckCircle2 className="h-3 w-3" /> Aceito
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                <XCircle className="h-3 w-3" /> Rejeitado
              </span>
            )}
          </div>

          {/* Two cards, strict 50/50 with min-w-0 so children can't push them */}
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            <div className="min-w-0 rounded-md border border-border/60 bg-muted/20 p-2">
              <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <FileText className="h-3 w-3" />
                Lançamento contábil
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
                <span className="font-mono text-foreground">#{link.transaction}</span>
                <span className="font-medium tabular-nums text-foreground">
                  {link.transaction_amount
                    ? formatCurrency(link.transaction_amount, "BRL")
                    : "—"}
                </span>
                <span className="text-muted-foreground">{fmtDate(link.transaction_date)}</span>
              </div>
              <div className="mt-1 text-[12px]">
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">NF#:</span>{" "}
                  {link.transaction_nf_number || "—"}
                  {link.transaction_cnpj ? (
                    <>
                      {" · "}
                      <span className="font-medium text-foreground">CNPJ:</span>{" "}
                      <span className="font-mono">{fmtCnpj(link.transaction_cnpj)}</span>
                    </>
                  ) : null}
                </div>
                {link.transaction_description ? (
                  <div className="line-clamp-2 break-words text-muted-foreground/80">
                    {link.transaction_description}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="hidden items-center justify-center md:flex">
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>

            <div className="min-w-0 rounded-md border border-border/60 bg-muted/20 p-2">
              <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <Receipt className="h-3 w-3" />
                Nota Fiscal
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
                <span className="font-mono text-foreground">NF {link.nf_numero}</span>
                <span className="font-medium tabular-nums text-foreground">
                  {formatCurrency(link.nf_valor_nota, "BRL")}
                </span>
                <span className="text-muted-foreground">{fmtDate(link.nf_data_emissao)}</span>
              </div>
              <div className="mt-1 truncate text-[12px] text-muted-foreground">
                <span className="font-medium text-foreground">Emit:</span>{" "}
                {link.nf_emit_nome}{" "}
                <span className="font-mono">({fmtCnpj(link.nf_emit_cnpj)})</span>
              </div>
              <div className="truncate text-[12px] text-muted-foreground">
                <span className="font-medium text-foreground">Dest:</span>{" "}
                {link.nf_dest_nome}{" "}
                <span className="font-mono">({fmtCnpj(link.nf_dest_cnpj)})</span>
              </div>
              <div
                className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground/70"
                title={link.nf_chave}
              >
                {link.nf_chave}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ScanModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [dateWindow, setDateWindow] = useState("7")
  const [tolerance, setTolerance] = useState("0.01")
  const [minConfidence, setMinConfidence] = useState("0.5")
  const [dryRun, setDryRun] = useState(true)
  const scan = useScanLinks()

  const submit = async () => {
    await scan.mutateAsync({
      date_window_days: Number(dateWindow) || 7,
      amount_tolerance: tolerance,
      min_confidence: minConfidence,
      dry_run: dryRun,
    })
    if (!dryRun) onClose()
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rodar scan de vínculos</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="date-window">Janela de datas (dias)</Label>
            <Input id="date-window" type="number" value={dateWindow}
              onChange={(e) => setDateWindow(e.target.value)} min={0} />
            <p className="text-[11px] text-muted-foreground">
              Tolerância entre Tx.date e NF.data_emissao.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="tolerance">Tolerância de valor (proporção)</Label>
            <Input id="tolerance" type="number" step="0.001" value={tolerance}
              onChange={(e) => setTolerance(e.target.value)} min={0} />
            <p className="text-[11px] text-muted-foreground">
              0.01 = 1%. Tx pode divergir de NF.valor_nota até esta proporção.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="min-conf">Confiança mínima</Label>
            <Input id="min-conf" type="number" step="0.05" value={minConfidence}
              onChange={(e) => setMinConfidence(e.target.value)} min={0} max={1} />
          </div>
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)} />
            Simulação (não persiste — apenas conta candidatos)
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={scan.isPending}>
            {scan.isPending ? "Rodando…" : dryRun ? "Simular" : "Rodar scan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AcceptAllModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [threshold, setThreshold] = useState("0.95")
  const acceptAll = useAcceptAllAbove()
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Aceitar em massa por limiar</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <p className="text-[13px] text-muted-foreground">
            Aceita todos os vínculos sugeridos (incluindo os fora da página atual)
            com confiança ≥ ao limiar. Use com cuidado — é reversível somente individualmente.
            Para aceitar uma lista curada, use a seleção por checkbox e o botão na barra inferior.
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="thresh">Confiança mínima</Label>
            <Input id="thresh" type="number" step="0.01" min={0} max={1}
              value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={async () => {
              await acceptAll.mutateAsync(threshold)
              onClose()
            }}
            disabled={acceptAll.isPending}
          >
            {acceptAll.isPending ? "Processando…" : "Aceitar todos"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ===========================================================
// Filters / sort helpers
// ===========================================================

interface DimFilter {
  nf: "any" | "full"
  cnpj: "any" | "full" | "any-match"
  amount: "any" | "full"
  date: "any" | "full"
}

const DEFAULT_FILTERS: DimFilter = {
  nf: "any",
  cnpj: "any",
  amount: "any",
  date: "any",
}

function applyDimFilter(link: NFTransactionLink, f: DimFilter): boolean {
  const fields = new Set(link.matched_fields ?? [])
  if (f.nf === "full" && !fields.has("nf_number")) return false
  if (f.cnpj === "full" && !fields.has("cnpj")) return false
  if (
    f.cnpj === "any-match"
    && !fields.has("cnpj")
    && !fields.has("cnpj_root")
    && !fields.has("cnpj_alias")
  ) return false
  if (f.amount === "full" && !fields.has("amount")) return false
  if (f.date === "full" && !fields.has("date")) return false
  return true
}

function sortLinks(links: NFTransactionLink[], key: SortKey): NFTransactionLink[] {
  const arr = [...links]
  const cmp = (a: NFTransactionLink, b: NFTransactionLink): number => {
    switch (key) {
      case "confidence_desc": return Number(b.confidence) - Number(a.confidence)
      case "confidence_asc":  return Number(a.confidence) - Number(b.confidence)
      case "nf_date_desc":    return (Date.parse(b.nf_data_emissao) || 0) - (Date.parse(a.nf_data_emissao) || 0)
      case "nf_date_asc":     return (Date.parse(a.nf_data_emissao) || 0) - (Date.parse(b.nf_data_emissao) || 0)
      case "amount_desc":     return parseFloat(b.nf_valor_nota || "0") - parseFloat(a.nf_valor_nota || "0")
      case "amount_asc":      return parseFloat(a.nf_valor_nota || "0") - parseFloat(b.nf_valor_nota || "0")
    }
  }
  arr.sort(cmp)
  return arr
}

function FilterChip({
  active, onClick, children, dim,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  dim: DimensionKey | "stale"
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-full border px-2 text-[11px] transition-colors",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border bg-muted/30 text-muted-foreground hover:bg-muted/50",
      )}
      data-dim={dim}
    >
      {children}
    </button>
  )
}

// ===========================================================
// Page
// ===========================================================

export function NfLinkReviewPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get("tab") || "suggested"
  const search = params.get("q") || ""
  const status = TAB_TO_STATUS[tab] ?? "suggested"
  const { canWrite } = useUserRole()
  const isSuggestedTab = tab === "suggested"

  const { data, isLoading, refetch, isFetching } = useNfTxLinks({
    review_status: status,
  })
  const accept = useAcceptLink()
  const reject = useRejectLink()
  const bulkAccept = useBulkAcceptLinks()
  const bulkReject = useBulkRejectLinks()

  // Filters / sort state
  const [minConfidence, setMinConfidence] = useState<string>("0")
  const [dimFilters, setDimFilters] = useState<DimFilter>(DEFAULT_FILTERS)
  const [hideStale, setHideStale] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>("confidence_desc")
  const [showFilters, setShowFilters] = useState(false)

  // Selection state — keyed by link id, only meaningful on suggested tab.
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const filteredAndSorted = useMemo(() => {
    if (!data) return []
    const minConf = parseFloat(minConfidence) || 0
    const q = search.toLowerCase().trim()
    const list = data.filter((l) => {
      if (Number(l.confidence) < minConf) return false
      if (hideStale && l.is_stale) return false
      if (!applyDimFilter(l, dimFilters)) return false
      if (q) {
        const haystack = [
          String(l.nf_numero),
          l.nf_chave,
          l.nf_emit_nome,
          l.nf_dest_nome,
          l.transaction_nf_number ?? "",
          l.transaction_description ?? "",
          l.transaction_cnpj ?? "",
          l.nf_emit_cnpj ?? "",
          l.nf_dest_cnpj ?? "",
        ]
          .filter(Boolean)
          .map((s) => String(s).toLowerCase())
        if (!haystack.some((s) => s.includes(q))) return false
      }
      return true
    })
    return sortLinks(list, sortKey)
  }, [data, search, minConfidence, dimFilters, hideStale, sortKey])

  const setTab = (t: string) => {
    const next = new URLSearchParams(params)
    next.set("tab", t)
    setParams(next, { replace: true })
    setSelected(new Set())
  }
  const setSearch = (q: string) => {
    const next = new URLSearchParams(params)
    if (q) next.set("q", q); else next.delete("q")
    setParams(next, { replace: true })
  }

  const visibleIds = useMemo(
    () => filteredAndSorted.map((l) => l.id),
    [filteredAndSorted],
  )
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected.has(id))
  const someVisibleSelected =
    !allVisibleSelected && visibleIds.some((id) => selected.has(id))

  const toggleAllVisible = () => {
    if (allVisibleSelected) {
      // Clear visible from selection
      setSelected((prev) => {
        const next = new Set(prev)
        for (const id of visibleIds) next.delete(id)
        return next
      })
    } else {
      // Add all visible
      setSelected((prev) => {
        const next = new Set(prev)
        for (const id of visibleIds) next.add(id)
        return next
      })
    }
  }
  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const [scanOpen, setScanOpen] = useState(false)
  const [acceptAllOpen, setAcceptAllOpen] = useState(false)
  const [openGroupId, setOpenGroupId] = useState<number | null>(null)

  const totalCount = data?.length ?? 0
  const filteredCount = filteredAndSorted.length
  const selectedCount = selected.size

  const anyFilterActive =
    minConfidence !== "0" ||
    hideStale ||
    Object.values(dimFilters).some((v) => v !== "any")

  const resetFilters = () => {
    setMinConfidence("0")
    setHideStale(false)
    setDimFilters(DEFAULT_FILTERS)
  }

  return (
    <div className="space-y-4 pb-24">
      <SectionHeader
        title="Vínculos NF ↔ Lançamento"
        subtitle="Revise sugestões automáticas para conectar Notas Fiscais a transações já lançadas."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Atualizar
            </Button>
            {canWrite ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setScanOpen(true)}>
                  <Wand2 className="h-4 w-4" />
                  Rodar scan
                </Button>
                <Button variant="outline" size="sm" onClick={() => setAcceptAllOpen(true)}>
                  <CheckCircle2 className="h-4 w-4" />
                  Aceitar por limiar
                </Button>
              </>
            ) : null}
          </>
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <div className="flex flex-wrap items-center gap-3">
          <TabsList>
            <TabsTrigger value="suggested">Sugeridos</TabsTrigger>
            <TabsTrigger value="accepted">Aceitos</TabsTrigger>
            <TabsTrigger value="rejected">Rejeitados</TabsTrigger>
          </TabsList>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por número de NF, descrição, CNPJ…"
              className="pl-8"
            />
          </div>
          <Button
            size="sm"
            variant={anyFilterActive ? "default" : "outline"}
            onClick={() => setShowFilters((s) => !s)}
            title="Mostrar/esconder filtros"
          >
            <Filter className="h-4 w-4" />
            Filtros
            {anyFilterActive ? (
              <span className="ml-1 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-primary-foreground/20 px-1 text-[10px] font-bold">
                ●
              </span>
            ) : null}
          </Button>
          <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
            <SelectTrigger className="w-[160px]">
              <ArrowUpDown className="mr-1 h-3.5 w-3.5" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SORT_LABELS).map(([k, label]) => (
                <SelectItem key={k} value={k}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {showFilters ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/20 p-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="min-conf-input" className="text-[12px]">
                Confiança ≥
              </Label>
              <Input
                id="min-conf-input"
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={minConfidence}
                onChange={(e) => setMinConfidence(e.target.value)}
                className="h-8 w-20"
              />
              <span className="text-[11px] text-muted-foreground">
                ({Math.round((parseFloat(minConfidence) || 0) * 100)}%)
              </span>
            </div>

            <div className="h-6 w-px bg-border" />

            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Dimensões
            </span>
            <FilterChip
              dim="nf"
              active={dimFilters.nf === "full"}
              onClick={() =>
                setDimFilters((f) => ({ ...f, nf: f.nf === "full" ? "any" : "full" }))
              }
            >
              NF# exato
            </FilterChip>
            <FilterChip
              dim="cnpj"
              active={dimFilters.cnpj !== "any"}
              onClick={() =>
                setDimFilters((f) => ({
                  ...f,
                  cnpj:
                    f.cnpj === "any" ? "any-match"
                      : f.cnpj === "any-match" ? "full"
                        : "any",
                }))
              }
            >
              CNPJ {dimFilters.cnpj === "full" ? "exato" : dimFilters.cnpj === "any-match" ? "(exato/raiz/apelido)" : ""}
            </FilterChip>
            <FilterChip
              dim="amount"
              active={dimFilters.amount === "full"}
              onClick={() =>
                setDimFilters((f) => ({ ...f, amount: f.amount === "full" ? "any" : "full" }))
              }
            >
              Valor dentro da tolerância
            </FilterChip>
            <FilterChip
              dim="date"
              active={dimFilters.date === "full"}
              onClick={() =>
                setDimFilters((f) => ({ ...f, date: f.date === "full" ? "any" : "full" }))
              }
            >
              Data dentro da janela
            </FilterChip>

            <div className="h-6 w-px bg-border" />

            <FilterChip
              dim="stale"
              active={hideStale}
              onClick={() => setHideStale((s) => !s)}
            >
              Ocultar desatualizados
            </FilterChip>

            {anyFilterActive ? (
              <Button size="sm" variant="ghost" onClick={resetFilters} className="ml-auto">
                Limpar filtros
              </Button>
            ) : null}
          </div>
        ) : null}

        <div className="mt-2 flex items-center justify-between text-[12px] text-muted-foreground">
          <span>
            {isLoading
              ? "Carregando…"
              : `Mostrando ${filteredCount} de ${totalCount}`
            }
            {selectedCount > 0 ? ` · ${selectedCount} selecionados` : ""}
          </span>
          {isSuggestedTab && filteredCount > 0 ? (
            <button
              type="button"
              onClick={toggleAllVisible}
              className="inline-flex items-center gap-1.5 text-primary hover:underline"
            >
              <Checkbox
                checked={
                  allVisibleSelected
                    ? true
                    : someVisibleSelected ? "indeterminate" : false
                }
                onCheckedChange={() => toggleAllVisible()}
              />
              {allVisibleSelected ? "Desmarcar visíveis" : "Selecionar visíveis"}
            </button>
          ) : null}
        </div>

        <TabsContent value={tab} className="mt-3 space-y-2">
          {isLoading ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
              Carregando vínculos…
            </div>
          ) : filteredCount === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center">
              <p className="text-sm text-muted-foreground">
                {totalCount === 0
                  ? tab === "suggested"
                    ? "Nenhuma sugestão pendente. Rode um scan ou importe novas NFs."
                    : tab === "accepted"
                      ? "Nenhum vínculo aceito ainda."
                      : "Nenhum vínculo rejeitado."
                  : "Nenhum vínculo bate com os filtros atuais."}
              </p>
              {anyFilterActive && totalCount > 0 ? (
                <Button size="sm" variant="ghost" onClick={resetFilters} className="mt-2">
                  Limpar filtros
                </Button>
              ) : null}
            </div>
          ) : (
            filteredAndSorted.map((link) => (
              <LinkRow
                key={link.id}
                link={link}
                selected={selected.has(link.id)}
                onToggle={() => toggleOne(link.id)}
                selectable={isSuggestedTab && canWrite}
                busy={accept.isPending || reject.isPending}
                onAccept={() => accept.mutate({ id: link.id })}
                onReject={() => reject.mutate({ id: link.id })}
                onOpenGroup={(gid) => setOpenGroupId(gid)}
              />
            ))
          )}
        </TabsContent>
      </Tabs>

      {/* Sticky bulk-action bar */}
      {isSuggestedTab && canWrite && selectedCount > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              {selectedCount} {selectedCount === 1 ? "vínculo selecionado" : "vínculos selecionados"}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
            >
              Limpar seleção
            </Button>
            <div className="ml-auto flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={bulkReject.isPending}
                onClick={async () => {
                  await bulkReject.mutateAsync(Array.from(selected))
                  setSelected(new Set())
                }}
              >
                <XCircle className="h-4 w-4" />
                Rejeitar selecionados
              </Button>
              <Button
                size="sm"
                disabled={bulkAccept.isPending}
                onClick={async () => {
                  await bulkAccept.mutateAsync(Array.from(selected))
                  setSelected(new Set())
                }}
              >
                <CheckCircle2 className="h-4 w-4" />
                Aceitar selecionados
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <ScanModal open={scanOpen} onClose={() => setScanOpen(false)} />
      <AcceptAllModal open={acceptAllOpen} onClose={() => setAcceptAllOpen(false)} />
      <GroupDetailModal groupId={openGroupId} onClose={() => setOpenGroupId(null)} />
    </div>
  )
}
