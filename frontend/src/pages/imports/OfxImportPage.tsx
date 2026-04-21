import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  Play,
  Upload,
  XCircle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useOfxImport, useOfxScan } from "@/features/imports"
import type {
  OfxImportResponse,
  OfxImportResult,
  OfxLookupInfo,
} from "@/features/imports/types"
import { cn } from "@/lib/utils"

type Policy = "records" | "files"

function asLookup(v: OfxImportResult["bank"]): OfxLookupInfo | null {
  if (v == null) return null
  if (typeof v === "string") return { result: "Success", value: v }
  return v as OfxLookupInfo
}

function lookupLabel(info: OfxLookupInfo | null): string {
  if (!info) return "—"
  const val = info.value
  if (val == null) return info.message ?? "—"
  if (typeof val === "string") return val
  if (typeof val === "number") return String(val)
  if (typeof val === "object") {
    const v = val as Record<string, unknown>
    return (v.name as string) ?? (v.bank_code as string) ?? (v.account_number as string) ?? "—"
  }
  return "—"
}

/** Per-file actionable hints driven by the scan output. */
function fileHints(r: OfxImportResult): React.ReactNode[] {
  const hints: React.ReactNode[] = []
  const bank = asLookup(r.bank)
  const account = asLookup(r.account)
  if (bank?.result === "Error") {
    hints.push(
      <span key="bank">
        Banco <code>{String(bank.value ?? "?")}</code> não está cadastrado. Crie-o antes de
        importar para que as transações tenham vínculo bancário correto.
      </span>,
    )
  }
  if (account?.result === "Error") {
    hints.push(
      <span key="acct">
        Conta <code>{String(account.value ?? "?")}</code> não encontrada. Cadastre-a em{" "}
        <Link to="/accounting/bank-accounts" className="underline">
          contas bancárias
        </Link>{" "}
        ou confirme o número/agência do extrato.
      </span>,
    )
  }
  if ((r.duplicate_ratio ?? 0) > 0.8) {
    hints.push(
      <span key="dup">
        Mais de 80% das transações já existem no banco — provavelmente este arquivo já
        foi importado. Confira antes de prosseguir.
      </span>,
    )
  }
  if (r.warning) {
    hints.push(<span key="warn">{r.warning}</span>)
  }
  return hints
}

function FileRow({ row, open, onToggle }: { row: OfxImportResult; open: boolean; onToggle: () => void }) {
  const bank = asLookup(row.bank)
  const account = asLookup(row.account)
  const bankOk = bank?.result !== "Error"
  const acctOk = account?.result !== "Error"
  const dupPct = row.duplicate_ratio != null ? Math.round(row.duplicate_ratio * 100) : null
  const hints = fileHints(row)
  const total = (row.transactions?.length ?? 0)
  const pending = (row.transactions ?? []).filter((t) => t.status === "pending").length
  return (
    <div className="card-elevated overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-accent/30"
      >
        {open ? (
          <ChevronDown className="mt-0.5 h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 text-muted-foreground" />
        )}
        <div className="flex flex-1 flex-wrap items-baseline gap-3">
          <span className="flex items-center gap-1.5 text-[13px] font-semibold">
            <FileText className="h-3.5 w-3.5 text-muted-foreground" /> {row.filename ?? "—"}
          </span>
          <span
            className={cn(
              "text-[11px]",
              bankOk ? "text-muted-foreground" : "text-destructive",
            )}
          >
            Banco: {lookupLabel(bank)}
          </span>
          <span
            className={cn(
              "text-[11px]",
              acctOk ? "text-muted-foreground" : "text-destructive",
            )}
          >
            Conta: {lookupLabel(account)}
          </span>
          <span className="ml-auto flex items-center gap-2 text-[11px] tabular-nums">
            <span>{total} tx</span>
            <span className="text-emerald-600">{pending} novas</span>
            <span className="text-amber-500">
              {row.duplicates} dup{dupPct != null ? ` (${dupPct}%)` : ""}
            </span>
          </span>
        </div>
      </button>
      {hints.length > 0 && (
        <ul className="space-y-1 border-t border-border bg-amber-500/5 p-2 text-[11px] text-amber-700 dark:text-amber-300">
          {hints.map((h, i) => (
            <li key={i} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {h}
            </li>
          ))}
        </ul>
      )}
      {open && row.transactions && row.transactions.length > 0 && (
        <div className="max-h-80 overflow-auto border-t border-border">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-7 px-2">Data</th>
                <th className="h-7 px-2 text-right">Valor</th>
                <th className="h-7 px-2">Tipo</th>
                <th className="h-7 px-2">Descrição</th>
                <th className="h-7 px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {row.transactions.map((t, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="h-6 px-2 font-mono">{t.date}</td>
                  <td className="h-6 px-2 text-right font-mono tabular-nums">
                    {typeof t.amount === "number" ? t.amount.toFixed(2) : String(t.amount)}
                  </td>
                  <td className="h-6 px-2 text-muted-foreground">
                    {String((t as { transaction_type?: string }).transaction_type ?? "—")}
                  </td>
                  <td className="h-6 px-2 text-muted-foreground">
                    {String((t as { description?: string }).description ?? "—")}
                  </td>
                  <td className="h-6 px-2">
                    {t.status === "duplicate" ? (
                      <span className="text-amber-500">duplicate</span>
                    ) : t.status === "pending" ? (
                      <span className="text-emerald-600">pending</span>
                    ) : (
                      <span className="text-muted-foreground">{t.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function OfxImportPage() {
  const [files, setFiles] = useState<File[]>([])
  const [policy, setPolicy] = useState<Policy>("records")
  const [openIdx, setOpenIdx] = useState<Set<number>>(new Set())
  const scan = useOfxScan()
  const importMut = useOfxImport()
  const res: OfxImportResponse | undefined = importMut.data ?? scan.data
  const isImportResult = !!importMut.data
  const isPending = scan.isPending || importMut.isPending

  const totals = useMemo(() => {
    if (!res) return { inserted: 0, duplicates: 0, pending: 0, warnings: 0, errors: 0 }
    let inserted = 0
    let duplicates = 0
    let pending = 0
    let warnings = 0
    let errors = 0
    for (const r of res.import_results) {
      inserted += r.inserted || 0
      duplicates += r.duplicates || 0
      pending += (r.transactions ?? []).filter((t) => t.status === "pending").length
      if (r.warning) warnings += 1
      const bank = asLookup(r.bank)
      const account = asLookup(r.account)
      if (bank?.result === "Error" || account?.result === "Error") errors += 1
    }
    return { inserted, duplicates, pending, warnings, errors }
  }, [res])

  const canImport = !!scan.data && !importMut.data && totals.errors === 0 && totals.pending > 0

  const toggleOpen = (i: number) =>
    setOpenIdx((s) => {
      const next = new Set(s)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

  const onScan = () => {
    if (!files.length) {
      toast.error("Selecione um ou mais arquivos .ofx.")
      return
    }
    importMut.reset()
    setOpenIdx(new Set())
    scan.mutate(files, {
      onError: (err: unknown) => {
        const msg =
          (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
          (err instanceof Error ? err.message : "erro desconhecido")
        toast.error(`Scan falhou: ${msg}`)
      },
    })
  }

  const onImport = () => {
    if (!files.length) return
    scan.reset()
    importMut.mutate(
      { files, policy },
      {
        onSuccess: () => toast.success("OFX importado."),
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`OFX falhou: ${msg}`)
        },
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação OFX"
        subtitle="Pré-visualize duplicatas e avisos antes de importar. Hash de transação evita duplicação."
      />

      <div className="card-elevated space-y-3 p-4">
        <input
          type="file"
          accept=".ofx"
          multiple
          onChange={(e) => {
            setFiles(Array.from(e.target.files ?? []))
            scan.reset()
            importMut.reset()
            setOpenIdx(new Set())
          }}
          className="block w-full text-[12px] file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium hover:file:bg-accent"
        />

        {files.length > 0 && (
          <ul className="space-y-1 text-[12px] text-muted-foreground">
            {files.map((f, i) => (
              <li key={i} className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5" />
                <span>{f.name}</span>
                <span>· {(f.size / 1024).toFixed(1)} KB</span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Política de import
            </span>
            <select
              value={policy}
              onChange={(e) => setPolicy(e.target.value as Policy)}
              className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
            >
              <option value="records">records — importar pendentes, pular duplicatas</option>
              <option value="files">files — pular arquivo se &gt;80% duplicatas</option>
            </select>
          </label>

          <button
            onClick={onScan}
            disabled={!files.length || isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
            title="Scan: classifica duplicatas sem gravar no banco."
          >
            {scan.isPending ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            {scan.isPending ? "Analisando…" : "Pré-visualizar"}
          </button>

          <button
            onClick={onImport}
            disabled={!files.length || isPending || !canImport}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            title={
              canImport
                ? "Importar transações pendentes (não duplicadas)."
                : "Rode uma pré-visualização sem erros antes de importar."
            }
          >
            {importMut.isPending ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {importMut.isPending ? "Importando…" : "Importar para valer"}
          </button>
        </div>
      </div>

      {res && (
        <div className="space-y-3">
          <div
            className={cn(
              "flex flex-wrap items-center gap-3 rounded-lg border p-3 text-[13px]",
              totals.errors > 0
                ? "border-destructive/40 bg-destructive/5 text-destructive"
                : totals.warnings > 0
                  ? "border-amber-500/40 bg-amber-500/5 text-amber-600"
                  : "border-emerald-500/40 bg-emerald-500/5 text-emerald-600",
            )}
          >
            {totals.errors > 0 ? (
              <XCircle className="h-4 w-4" />
            ) : totals.warnings > 0 ? (
              <AlertTriangle className="h-4 w-4" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            <span className="font-semibold">
              {isImportResult
                ? `${totals.inserted} transação(ões) inserida(s) em ${res.import_results.length} arquivo(s).`
                : totals.errors > 0
                  ? `${totals.errors} arquivo(s) com problemas graves. Resolva antes de importar.`
                  : totals.warnings > 0
                    ? `${totals.warnings} aviso(s) — revise antes de importar.`
                    : `Pronto para importar ${totals.pending} transação(ões) nova(s).`}
            </span>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {totals.pending} pendentes · {totals.duplicates} duplicatas ·{" "}
              {res.import_results.length} arquivo(s)
            </span>
          </div>

          {res.import_results.map((r, i) => (
            <FileRow key={i} row={r} open={openIdx.has(i)} onToggle={() => toggleOpen(i)} />
          ))}
        </div>
      )}
    </div>
  )
}
