import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  FileSpreadsheet,
  Play,
  Upload,
  XCircle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useEtlExecute, useEtlPreview } from "@/features/imports"
import type { EtlError, EtlExecuteResponse, EtlWarning } from "@/features/imports/types"
import { cn } from "@/lib/utils"

type Bucket = "python" | "database" | "substitution" | "warnings"

interface ErrorSectionProps {
  id: Bucket
  title: string
  tone: "danger" | "warning" | "info"
  items: Array<EtlError | EtlWarning>
  open: boolean
  onToggle: () => void
  renderHint?: (item: EtlError) => React.ReactNode
}

/**
 * Actionable fix hints keyed off the error `type`. Keep terse; the user
 * already sees stage/message/value, so hints should answer "what do I do?".
 */
function hintForError(err: EtlError): React.ReactNode {
  const t = err.type
  if (t === "substitution_not_found" || t === "fk_substitution_failed") {
    return (
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span>
          Cadastre uma regra de substituição para <code>{err.field ?? "?"}</code> ={" "}
          <code>{String(err.value ?? "?")}</code> e rode o preview de novo.
        </span>
        <Link
          to="/imports?tab=substitutions"
          className="inline-flex h-6 items-center rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent"
        >
          Abrir substituições
        </Link>
      </div>
    )
  }
  if (t === "account_not_found") {
    return (
      <div className="text-[11px]">
        Conta <code>{err.account_path ?? err.value}</code> não existe no plano de contas.
        Crie a conta ou ajuste o caminho na planilha.{" "}
        <Link to="/accounting/chart" className="underline">
          Ir ao plano de contas
        </Link>
      </div>
    )
  }
  if (t === "integrity_error" || t === "constraint_error") {
    return (
      <div className="text-[11px]">
        Violação de restrição no banco de dados (FK, unique, not-null). Verifique se o
        registro referenciado existe e se valores obrigatórios estão preenchidos.
      </div>
    )
  }
  if (t === "database_error") {
    return (
      <div className="text-[11px]">
        Erro inesperado no banco. Copie o stage/message e reporte se persistir.
      </div>
    )
  }
  if (t === "type_error" || t === "value_error") {
    return (
      <div className="text-[11px]">
        Valor inválido para o campo. Confira se formato/tipo na planilha bate com o campo
        alvo (data, número, ID, etc.).
      </div>
    )
  }
  if (t === "exception" || t === "python_error") {
    return (
      <div className="text-[11px]">
        Exceção não tratada. Se a stacktrace abaixo não for clara, copie-a para o suporte.
      </div>
    )
  }
  return null
}

function ErrorRow({
  item,
  index,
  renderHint,
}: {
  item: EtlError | EtlWarning
  index: number
  renderHint?: (item: EtlError) => React.ReactNode
}) {
  const [tbOpen, setTbOpen] = useState(false)
  const e = item as EtlError
  const traceback = typeof e.traceback === "string" ? e.traceback : ""
  return (
    <div className="space-y-1 rounded-md border border-border bg-surface-1 p-2">
      <div className="flex items-baseline gap-2 text-[12px]">
        <span className="font-mono text-[10px] text-muted-foreground">[{index + 1}]</span>
        <span className="font-mono text-[11px] font-semibold">{e.type}</span>
        {e.stage && (
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {e.stage}
          </span>
        )}
        {e.model && (
          <span className="font-mono text-[10px] text-muted-foreground">{String(e.model)}</span>
        )}
        {e.record_id != null && (
          <span className="font-mono text-[10px] text-muted-foreground">
            id={String(e.record_id)}
          </span>
        )}
        {e.sheet && (
          <span className="font-mono text-[10px] text-muted-foreground">
            sheet={String(e.sheet)}
          </span>
        )}
        {e.row != null && (
          <span className="font-mono text-[10px] text-muted-foreground">
            row={String(e.row)}
          </span>
        )}
      </div>
      <div className="text-[12px]">{e.message}</div>
      {renderHint && renderHint(e)}
      {traceback && (
        <div>
          <button
            onClick={() => setTbOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            {tbOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Stacktrace
          </button>
          {tbOpen && (
            <pre className="mt-1 max-h-64 overflow-auto rounded border border-border bg-muted/40 p-2 font-mono text-[10px] leading-tight">
              {traceback}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function ErrorSection({ id: _id, title, tone, items, open, onToggle, renderHint }: ErrorSectionProps) {
  if (!items.length) return null
  const color =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-amber-500"
        : "text-muted-foreground"
  return (
    <div className="card-elevated overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-accent/30"
      >
        <span className="flex items-center gap-2 text-[13px] font-semibold">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          <span className={color}>{title}</span>
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
            {items.length}
          </span>
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border bg-surface-2/50 p-2">
          {items.map((it, i) => (
            <ErrorRow key={i} item={it} index={i} renderHint={renderHint} />
          ))}
        </div>
      )}
    </div>
  )
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function EtlImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [rowLimit, setRowLimit] = useState(10)
  const preview = useEtlPreview()
  const execute = useEtlExecute()
  const res = (execute.data ?? preview.data) as EtlExecuteResponse | undefined
  const isPreviewResult = !!preview.data && !execute.data
  const isPending = preview.isPending || execute.isPending

  const [open, setOpen] = useState<Record<Bucket, boolean>>({
    python: true,
    database: true,
    substitution: true,
    warnings: false,
  })
  const toggle = (b: Bucket) => setOpen((o) => ({ ...o, [b]: !o[b] }))

  const buckets = useMemo(() => {
    const org = res?.errors_organized ?? {}
    return {
      python: (org.python_errors ?? []) as EtlError[],
      database: (org.database_errors ?? []) as EtlError[],
      substitution: (org.substitution_errors ?? []) as EtlError[],
      warnings: (org.warnings ?? res?.warnings ?? []) as EtlWarning[],
    }
  }, [res])

  const errorTotal = buckets.python.length + buckets.database.length + buckets.substitution.length
  const canExecute = isPreviewResult && res?.success && errorTotal === 0

  const onPreview = () => {
    if (!file) {
      toast.error("Selecione um arquivo .xlsx.")
      return
    }
    execute.reset()
    preview.mutate(
      { file, rowLimit },
      {
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`Preview falhou: ${msg}`)
        },
      },
    )
  }

  const onExecute = () => {
    if (!file) return
    preview.reset()
    execute.mutate(
      { file, rowLimit },
      {
        onSuccess: (r) =>
          r.success
            ? toast.success("Importação aplicada.")
            : toast.error("Importação falhou — veja os erros abaixo."),
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`Execução falhou: ${msg}`)
        },
      },
    )
  }

  const onDownloadReport = () => {
    const text = (res?.errors_organized?.error_report_text as string | null | undefined) ?? ""
    if (!text) {
      toast.error("Sem relatório de erros para baixar.")
      return
    }
    downloadText(`etl_error_report_${Date.now()}.txt`, text)
  }

  const sheetsProcessed = res?.summary?.sheets_processed ?? []
  const sheetsSkipped = res?.summary?.sheets_skipped ?? []
  const sheetsFailed = res?.summary?.sheets_failed ?? []

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação ETL"
        subtitle="Pré-visualize o efeito do arquivo antes de commitar. Usa __row_id para criar/editar/deletar."
      />

      <div className="card-elevated space-y-3 p-4">
        <label className="flex items-center gap-3">
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              preview.reset()
              execute.reset()
            }}
            className="block w-full text-[12px] file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium hover:file:bg-accent"
          />
        </label>

        {file && (
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <FileSpreadsheet className="h-3.5 w-3.5" />
            <span>{file.name}</span>
            <span>· {(file.size / 1024).toFixed(1)} KB</span>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Row limit (0 = todas)
            </span>
            <input
              type="number"
              min={0}
              max={100000}
              value={rowLimit}
              onChange={(e) => setRowLimit(Math.max(0, Number(e.target.value) || 0))}
              className="h-8 w-28 rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
            />
          </label>

          <button
            onClick={onPreview}
            disabled={!file || isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
            title="Dry-run: valida e simula sem gravar no banco."
          >
            {preview.isPending ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            {preview.isPending ? "Simulando…" : "Pré-visualizar"}
          </button>

          <button
            onClick={onExecute}
            disabled={!file || isPending || !canExecute}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            title={
              canExecute
                ? "Roda novamente e commita no banco."
                : "Rode um preview sem erros antes de executar."
            }
          >
            {execute.isPending ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {execute.isPending ? "Executando…" : "Executar para valer"}
          </button>
        </div>
      </div>

      {res && (
        <div className="space-y-3">
          {/* Verdict strip */}
          <div
            className={cn(
              "flex flex-wrap items-center gap-3 rounded-lg border p-3 text-[13px]",
              res.success && errorTotal === 0
                ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-600"
                : errorTotal > 0
                  ? "border-destructive/40 bg-destructive/5 text-destructive"
                  : "border-border bg-surface-2 text-foreground",
            )}
          >
            {res.success && errorTotal === 0 ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : errorTotal > 0 ? (
              <XCircle className="h-4 w-4" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            <span className="font-semibold">
              {isPreviewResult
                ? res.success && errorTotal === 0
                  ? "Pré-visualização OK — pronto para executar."
                  : "Pré-visualização com erros. Corrija antes de executar."
                : res.success
                  ? "Importação aplicada com sucesso."
                  : "Importação falhou. Nada foi commitado."}
            </span>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {errorTotal > 0 && `${errorTotal} erro(s) · `}
              {buckets.warnings.length > 0 && `${buckets.warnings.length} aviso(s)`}
            </span>
          </div>

          {/* Sheets summary */}
          {(sheetsProcessed.length > 0 || sheetsSkipped.length > 0 || sheetsFailed.length > 0) && (
            <div className="card-elevated space-y-1 p-3 text-[12px]">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Sheets
              </div>
              {sheetsProcessed.length > 0 && (
                <div>
                  <span className="text-muted-foreground">Processadas: </span>
                  {sheetsProcessed.map((s, i) => (
                    <span
                      key={i}
                      className="mr-1 inline-flex h-5 items-center rounded-full border border-emerald-500/30 bg-emerald-500/5 px-2 text-[11px] text-emerald-600"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {sheetsSkipped.length > 0 && (
                <div>
                  <span className="text-muted-foreground">Puladas: </span>
                  {sheetsSkipped.map((s, i) => (
                    <span
                      key={i}
                      className="mr-1 inline-flex h-5 items-center rounded-full border border-border bg-muted px-2 text-[11px] text-muted-foreground"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {sheetsFailed.length > 0 && (
                <div>
                  <span className="text-destructive">Falharam: </span>
                  {sheetsFailed.map((s, i) => (
                    <span
                      key={i}
                      className="mr-1 inline-flex h-5 items-center rounded-full border border-destructive/40 bg-destructive/5 px-2 text-[11px] text-destructive"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Error buckets */}
          <ErrorSection
            id="substitution"
            title="Substituições não encontradas"
            tone="danger"
            items={buckets.substitution}
            open={open.substitution}
            onToggle={() => toggle("substitution")}
            renderHint={hintForError}
          />
          <ErrorSection
            id="database"
            title="Erros de banco"
            tone="danger"
            items={buckets.database}
            open={open.database}
            onToggle={() => toggle("database")}
            renderHint={hintForError}
          />
          <ErrorSection
            id="python"
            title="Exceções Python"
            tone="danger"
            items={buckets.python}
            open={open.python}
            onToggle={() => toggle("python")}
            renderHint={hintForError}
          />
          <ErrorSection
            id="warnings"
            title="Avisos"
            tone="warning"
            items={buckets.warnings}
            open={open.warnings}
            onToggle={() => toggle("warnings")}
          />

          {/* Report download + raw JSON escape hatch */}
          {(res.errors_organized?.error_report_text || errorTotal > 0) && (
            <div className="flex items-center justify-end">
              <button
                onClick={onDownloadReport}
                disabled={!res.errors_organized?.error_report_text}
                className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium hover:bg-accent disabled:opacity-50"
              >
                <Download className="h-3 w-3" /> Baixar relatório .txt
              </button>
            </div>
          )}

          <RawJsonPanel data={res} />
        </div>
      )}
    </div>
  )
}

function RawJsonPanel({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card-elevated overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] text-muted-foreground hover:bg-accent/30"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        Resposta bruta (JSON)
      </button>
      {open && (
        <pre className="max-h-[420px] overflow-auto border-t border-border bg-muted/20 p-2 font-mono text-[10px]">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}
