import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  CheckCircle2, XCircle, Search, Wand2, RefreshCw,
  AlertTriangle, FileText, Receipt, ArrowRight,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import {
  useAcceptAllAbove, useAcceptLink, useNfTxLinks, useRejectLink, useScanLinks,
} from "@/features/billing"
import type { LinkReviewStatus, NFTransactionLink } from "@/features/billing"
import { ConfidenceBadge } from "./components/ConfidenceBadge"
import { useUserRole } from "@/features/auth/useUserRole"
import { cn, formatCurrency } from "@/lib/utils"

const TAB_TO_STATUS: Record<string, LinkReviewStatus> = {
  suggested: "suggested",
  accepted: "accepted",
  rejected: "rejected",
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

function MatchedFieldChips({ fields }: { fields: string[] }) {
  if (!fields?.length) return null
  return (
    <div className="flex flex-wrap gap-1">
      {fields.map((f) => (
        <span
          key={f}
          className="rounded-full bg-info/10 px-1.5 py-0.5 text-[10px] font-medium text-info"
        >
          {f}
        </span>
      ))}
    </div>
  )
}

function LinkRow({
  link,
  onAccept,
  onReject,
  busy,
}: {
  link: NFTransactionLink
  onAccept: () => void
  onReject: () => void
  busy?: boolean
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-3 transition-shadow hover:shadow-sm",
        link.is_stale && "border-warning/40",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1 min-w-0">
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
          </div>
          <MatchedFieldChips fields={link.matched_fields} />
        </div>
        {link.review_status === "suggested" ? (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="default"
              onClick={onAccept}
              disabled={busy}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Aceitar
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onReject}
              disabled={busy}
            >
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

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr]">
        {/* Transaction side */}
        <div className="rounded-md border border-border/60 bg-muted/20 p-2">
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
              <div className="line-clamp-2 text-muted-foreground/80">
                {link.transaction_description}
              </div>
            ) : null}
          </div>
        </div>

        <div className="hidden items-center justify-center md:flex">
          <ArrowRight className="h-4 w-4 text-muted-foreground" />
        </div>

        {/* NF side */}
        <div className="rounded-md border border-border/60 bg-muted/20 p-2">
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
            {link.nf_emit_nome} <span className="font-mono">({fmtCnpj(link.nf_emit_cnpj)})</span>
            {" → "}
            {link.nf_dest_nome}
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
  )
}

function ScanModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
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
            <Input
              id="date-window"
              type="number"
              value={dateWindow}
              onChange={(e) => setDateWindow(e.target.value)}
              min={0}
            />
            <p className="text-[11px] text-muted-foreground">
              Tolerância entre Tx.date e NF.data_emissao.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="tolerance">Tolerância de valor (proporção)</Label>
            <Input
              id="tolerance"
              type="number"
              step="0.001"
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              min={0}
            />
            <p className="text-[11px] text-muted-foreground">
              0.01 = 1%. Tx pode divergir de NF.valor_nota até esta proporção.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="min-conf">Confiança mínima</Label>
            <Input
              id="min-conf"
              type="number"
              step="0.05"
              value={minConfidence}
              onChange={(e) => setMinConfidence(e.target.value)}
              min={0}
              max={1}
            />
          </div>
          <label className="flex items-center gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
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

function AcceptAllModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [threshold, setThreshold] = useState("0.95")
  const acceptAll = useAcceptAllAbove()
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Aceitar em massa</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <p className="text-[13px] text-muted-foreground">
            Aceita todos os vínculos sugeridos com confiança igual ou superior ao limiar.
            Use com cuidado — é reversível somente individualmente.
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="thresh">Confiança mínima</Label>
            <Input
              id="thresh"
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
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

export function NfLinkReviewPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get("tab") || "suggested"
  const search = params.get("q") || ""
  const status = TAB_TO_STATUS[tab] ?? "suggested"
  const { canWrite } = useUserRole()

  const { data, isLoading, refetch, isFetching } = useNfTxLinks({
    review_status: status,
  })
  const accept = useAcceptLink()
  const reject = useRejectLink()

  const filtered = useMemo(() => {
    if (!data) return []
    if (!search) return data
    const q = search.toLowerCase()
    return data.filter((l) =>
      [
        String(l.nf_numero),
        l.nf_chave,
        l.nf_emit_nome,
        l.nf_dest_nome,
        l.transaction_nf_number ?? "",
        l.transaction_description ?? "",
        l.transaction_cnpj ?? "",
      ]
        .filter(Boolean)
        .some((s) => s.toLowerCase().includes(q)),
    )
  }, [data, search])

  const setTab = (t: string) => {
    const next = new URLSearchParams(params)
    next.set("tab", t)
    setParams(next, { replace: true })
  }
  const setSearch = (q: string) => {
    const next = new URLSearchParams(params)
    if (q) next.set("q", q); else next.delete("q")
    setParams(next, { replace: true })
  }

  const [scanOpen, setScanOpen] = useState(false)
  const [acceptAllOpen, setAcceptAllOpen] = useState(false)

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Vínculos NF ↔ Lançamento"
        subtitle="Revise sugestões automáticas para conectar Notas Fiscais a transações já lançadas."
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Atualizar
            </Button>
            {canWrite ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setScanOpen(true)}>
                  <Wand2 className="h-4 w-4" />
                  Rodar scan
                </Button>
                <Button size="sm" onClick={() => setAcceptAllOpen(true)}>
                  <CheckCircle2 className="h-4 w-4" />
                  Aceitar em massa
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
        </div>

        <TabsContent value={tab} className="mt-4 space-y-2">
          {isLoading ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
              Carregando vínculos…
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center">
              <p className="text-sm text-muted-foreground">
                {tab === "suggested"
                  ? "Nenhuma sugestão pendente. Rode um scan ou importe novas NFs."
                  : tab === "accepted"
                    ? "Nenhum vínculo aceito ainda."
                    : "Nenhum vínculo rejeitado."}
              </p>
            </div>
          ) : (
            filtered.map((link) => (
              <LinkRow
                key={link.id}
                link={link}
                busy={accept.isPending || reject.isPending}
                onAccept={() => accept.mutate({ id: link.id })}
                onReject={() => reject.mutate({ id: link.id })}
              />
            ))
          )}
        </TabsContent>
      </Tabs>

      <ScanModal open={scanOpen} onClose={() => setScanOpen(false)} />
      <AcceptAllModal open={acceptAllOpen} onClose={() => setAcceptAllOpen(false)} />
    </div>
  )
}
