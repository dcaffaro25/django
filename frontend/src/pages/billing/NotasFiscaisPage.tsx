import { useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { RefreshCw, Search } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useNotasFiscais } from "@/features/billing"
import { useDebounced } from "@/lib/useDebounced"
import { usePageContext } from "@/stores/page-context-store"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

const FINALIDADE_LABEL: Record<number, string> = {
  1: "Normal",
  2: "Complementar",
  3: "Ajuste",
  4: "Devolução",
}

const SEFAZ_TONE: Record<string, string> = {
  // Common SEFAZ codes — neutral by default, danger on cancellation, success on authorization.
  "100": "bg-success/10 text-success",
  "101": "bg-danger/10 text-danger",
  "150": "bg-success/10 text-success",
  "135": "bg-info/10 text-info",
  "155": "bg-info/10 text-info",
}

function fmtCnpj(d?: string | null) {
  if (!d) return ""
  const s = d.replace(/\D/g, "")
  if (s.length !== 14) return d
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`
}

export function NotasFiscaisPage() {
  const [params, setParams] = useSearchParams()
  // Search input is a LOCAL state for snappy typing; the debounced
  // copy is what flows into URL writes + the filter useMemo so a fast
  // typist doesn't pay re-render cost per keystroke (the URL write
  // alone fires the whole tree). Initial value comes from the URL
  // once at mount so a deep-link with ?q=foo still pre-fills the box.
  const initialSearch = useMemo(() => params.get("q") || "", []) // eslint-disable-line react-hooks/exhaustive-deps
  const [searchInput, setSearchInput] = useState(initialSearch)
  const search = useDebounced(searchInput, 200)
  const finalidade = params.get("finalidade") || "all"
  const tipo = params.get("tipo_operacao") || "all"

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value == null || value === "" || value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  // Sync the debounced search back to the URL. ``skipFirstSync``
  // suppresses the no-op first run (initial value already matches the
  // URL); subsequent debounced changes write through.
  const skipFirstSync = useRef(true)
  useEffect(() => {
    if (skipFirstSync.current) { skipFirstSync.current = false; return }
    setFilter("q", search)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const { data, isLoading, isFetching, refetch } = useNotasFiscais()

  const filtered = useMemo(() => {
    if (!data) return []
    let items = data
    if (finalidade !== "all") {
      const n = Number(finalidade)
      items = items.filter((nf) => nf.finalidade === n)
    }
    if (tipo !== "all") {
      const n = Number(tipo)
      items = items.filter((nf) => nf.tipo_operacao === n)
    }
    if (search) {
      const q = search.toLowerCase()
      items = items.filter((nf) =>
        [String(nf.numero), nf.chave, nf.emit_nome, nf.dest_nome, nf.emit_cnpj, nf.dest_cnpj]
          .some((s) => (s ?? "").toLowerCase().includes(q)),
      )
    }
    return items
  }, [data, search, finalidade, tipo])

  usePageContext({
    route: "/billing/nfe",
    title: "Notas Fiscais",
    summary: (
      `Lista de NFs com ${filtered.length} resultados visíveis ` +
      `(de ${data?.length ?? 0} carregadas).`
    ),
    data: {
      filters: {
        search: search || undefined,
        finalidade: finalidade !== "all" ? finalidade : undefined,
        tipo_operacao: tipo !== "all" ? tipo : undefined,
      },
      visible_count: filtered.length,
    },
  })

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Notas Fiscais"
        subtitle="NF-e e NFC-e importadas. Inclui referências (devoluções) e eventos (cancelamento, CCe)."
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            Atualizar
          </Button>
        }
      />

      <div className="flex flex-wrap items-end gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Buscar número, chave, CNPJ ou parceiro…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tipo
          </span>
          <Select value={tipo} onValueChange={(v) => setFilter("tipo_operacao", v)}>
            <SelectTrigger className="h-9 w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="0">Entrada</SelectItem>
              <SelectItem value="1">Saída</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Finalidade
          </span>
          <Select value={finalidade} onValueChange={(v) => setFilter("finalidade", v)}>
            <SelectTrigger className="h-9 w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              <SelectItem value="1">Normal</SelectItem>
              <SelectItem value="2">Complementar</SelectItem>
              <SelectItem value="3">Ajuste</SelectItem>
              <SelectItem value="4">Devolução</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <table className="w-full text-[12px]">
          <thead className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="px-3 py-2">NF</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Emissão</th>
              <th className="px-3 py-2">Emitente</th>
              <th className="px-3 py-2">Destinatário</th>
              <th className="px-3 py-2 text-right">Valor</th>
              <th className="px-3 py-2">Finalidade</th>
              <th className="px-3 py-2">SEFAZ</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">
                  Carregando NFs…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center">
                  <p className="text-muted-foreground">
                    Nenhuma NF encontrada. Use a página de Importações para enviar XMLs.
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((nf) => (
                <tr
                  key={nf.id}
                  className="border-b border-border/40 last:border-b-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-2">
                    <div className="font-mono">{nf.numero}/{nf.serie}</div>
                    <div
                      className="truncate font-mono text-[10px] text-muted-foreground/70"
                      title={nf.chave}
                    >
                      {nf.chave.slice(-12)}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {nf.tipo_operacao === 1 ? "Saída" : "Entrada"}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {formatDate(nf.data_emissao)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="truncate" title={nf.emit_nome}>{nf.emit_nome}</div>
                    <div className="font-mono text-[10px] text-muted-foreground/70">
                      {fmtCnpj(nf.emit_cnpj)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="truncate" title={nf.dest_nome}>{nf.dest_nome}</div>
                    <div className="font-mono text-[10px] text-muted-foreground/70">
                      {fmtCnpj(nf.dest_cnpj)}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-medium tabular-nums">
                    {formatCurrency(nf.valor_nota)}
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      nf.finalidade === 4
                        ? "bg-warning/10 text-warning"
                        : "bg-muted text-muted-foreground",
                    )}>
                      {FINALIDADE_LABEL[nf.finalidade] ?? nf.finalidade}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {nf.status_sefaz ? (
                      <span className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-medium tabular-nums",
                        SEFAZ_TONE[nf.status_sefaz] ?? "bg-muted text-muted-foreground",
                      )}>
                        {nf.status_sefaz}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-muted-foreground">
        Para vincular uma NF a uma fatura, abra a fatura na aba Faturas e use “Vincular NF”.
        Para revisar candidatos automáticos com lançamentos contábeis, use a aba Vínculos NF↔Tx.
      </p>
    </div>
  )
}
