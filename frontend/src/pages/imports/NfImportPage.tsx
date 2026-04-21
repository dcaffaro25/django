import { useMemo, useState } from "react"
import { toast } from "sonner"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileCode,
  Play,
  Upload,
  XCircle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useNfeImport } from "@/features/imports"
import type { NfeErrorItem, NfeImportResponse } from "@/features/imports/types"
import { cn } from "@/lib/utils"

const MAX_FILES = 20

function errorHint(err: NfeErrorItem): React.ReactNode {
  const msg = (err.erro ?? err.error_message ?? "").toLowerCase()
  if (msg.includes("tipo de xml não reconhecido")) {
    return "Confirme que o arquivo é NFe, evento ou inutilização — outros XMLs não são aceitos."
  }
  if (msg.includes("chave") && (msg.includes("duplicada") || msg.includes("já existe"))) {
    return "NFe já importada anteriormente. Se precisa re-importar, remova o registro existente primeiro."
  }
  if (msg.includes("assinatura") || msg.includes("signature")) {
    return "Assinatura XML inválida. Re-exporte a NFe no ERP emissor e tente novamente."
  }
  if (msg.includes("schema") || msg.includes("xsd")) {
    return "XML fora do schema esperado. Verifique a versão do layout (4.00) e o tipo de documento."
  }
  if (msg.includes("cnpj") && msg.includes("não")) {
    return "CNPJ do emitente/destinatário não cadastrado. Crie a entidade antes de importar."
  }
  if (msg.includes("excede 1mb") || msg.includes("tamanho")) {
    return "Arquivo acima do limite (1MB). Verifique se o XML não está com conteúdo duplicado/inflado."
  }
  return null
}

export function NfImportPage() {
  const [files, setFiles] = useState<File[]>([])
  const mut = useNfeImport()
  const res: NfeImportResponse | undefined = mut.data
  const [isPreview, setIsPreview] = useState(false)
  const [openErrors, setOpenErrors] = useState(true)

  const totalSizeKB = useMemo(
    () => (files.reduce((s, f) => s + f.size, 0) / 1024).toFixed(0),
    [files],
  )

  const onRun = (dryRun: boolean) => {
    if (!files.length) {
      toast.error("Selecione um ou mais arquivos XML de NF-e.")
      return
    }
    if (files.length > MAX_FILES) {
      toast.error(`Máximo de ${MAX_FILES} arquivos por requisição.`)
      return
    }
    setIsPreview(dryRun)
    mut.mutate(
      { files, dryRun },
      {
        onSuccess: (r) => {
          if (r.erros.length > 0) {
            toast.error(
              dryRun
                ? `Pré-visualização encontrou ${r.erros.length} erro(s). Nada seria importado.`
                : `Importação falhou em ${r.erros.length} arquivo(s). Nada foi commitado.`,
            )
          } else {
            toast.success(
              dryRun
                ? `Pré-visualização OK — ${r.importadas.length} NFe + ${r.importados.length} evento(s) seriam importados.`
                : `${r.importadas.length} NFe + ${r.importados.length} evento(s) importados.`,
            )
          }
        },
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`${dryRun ? "Pré-visualização" : "Importação"} falhou: ${msg}`)
        },
      },
    )
  }

  const verdict = useMemo(() => {
    if (!res) return null
    const hasErr = res.erros.length > 0
    const hasDup = res.duplicadas.length > 0
    const totalImp = res.importadas.length + res.importados.length + res.importados_inut.length
    return { hasErr, hasDup, totalImp }
  }, [res])

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação de NF-e"
        subtitle={`Faz upload de XMLs de NF-e, eventos e inutilizações. Máx ${MAX_FILES} arquivos por vez.`}
      />

      <div className="card-elevated space-y-3 p-4">
        <input
          type="file"
          accept=".xml"
          multiple
          onChange={(e) => {
            setFiles(Array.from(e.target.files ?? []))
            mut.reset()
          }}
          className="block w-full text-[12px] file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium hover:file:bg-accent"
        />

        {files.length > 0 && (
          <div className="text-[12px] text-muted-foreground">
            {files.length} arquivo(s) selecionado(s) · total {totalSizeKB} KB
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <button
            onClick={() => onRun(true)}
            disabled={!files.length || mut.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
            title="Dry-run: valida tudo e simula inserts, mas faz rollback no final."
          >
            {mut.isPending && isPreview ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            {mut.isPending && isPreview ? "Simulando…" : "Pré-visualizar"}
          </button>

          <button
            onClick={() => onRun(false)}
            disabled={!files.length || mut.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {mut.isPending && !isPreview ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {mut.isPending && !isPreview ? "Importando…" : "Importar para valer"}
          </button>
        </div>
      </div>

      {res && verdict && (
        <div className="space-y-3">
          <div
            className={cn(
              "flex flex-wrap items-center gap-3 rounded-lg border p-3 text-[13px]",
              verdict.hasErr
                ? "border-destructive/40 bg-destructive/5 text-destructive"
                : verdict.hasDup
                  ? "border-amber-500/40 bg-amber-500/5 text-amber-600"
                  : "border-emerald-500/40 bg-emerald-500/5 text-emerald-600",
            )}
          >
            {verdict.hasErr ? (
              <XCircle className="h-4 w-4" />
            ) : verdict.hasDup ? (
              <AlertTriangle className="h-4 w-4" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            <span className="font-semibold">
              {res.dry_run
                ? verdict.hasErr
                  ? `Pré-visualização: ${res.erros.length} erro(s) — nada seria importado.`
                  : `Pré-visualização OK — ${verdict.totalImp} registro(s) seriam importado(s).`
                : verdict.hasErr
                  ? `Importação falhou em ${res.erros.length} arquivo(s). Rollback aplicado — nada foi persistido.`
                  : `${verdict.totalImp} registro(s) importado(s) com sucesso.`}
            </span>
            <span className="ml-auto text-[11px] text-muted-foreground">
              NFe {res.importadas.length} · eventos {res.importados.length} · inut.{" "}
              {res.importados_inut.length} · duplicadas {res.duplicadas.length}
            </span>
          </div>

          {/* Errors */}
          {res.erros.length > 0 && (
            <div className="card-elevated overflow-hidden">
              <button
                onClick={() => setOpenErrors((v) => !v)}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-accent/30"
              >
                <span className="flex items-center gap-2 text-[13px] font-semibold text-destructive">
                  {openErrors ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                  Erros
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                    {res.erros.length}
                  </span>
                </span>
              </button>
              {openErrors && (
                <div className="space-y-2 border-t border-border bg-surface-2/50 p-2">
                  {res.erros.map((e, i) => {
                    const file = e.arquivo ?? e.filename ?? "—"
                    const msg = e.erro ?? e.error_message ?? "—"
                    const hint = errorHint(e)
                    return (
                      <div
                        key={i}
                        className="space-y-1 rounded-md border border-border bg-surface-1 p-2"
                      >
                        <div className="flex items-baseline gap-2 text-[12px]">
                          <span className="font-mono text-[10px] text-muted-foreground">
                            [{i + 1}]
                          </span>
                          <FileCode className="h-3 w-3 text-muted-foreground" />
                          <span className="font-mono text-[11px] font-semibold">{file}</span>
                        </div>
                        <div className="text-[12px]">{msg}</div>
                        {hint && (
                          <div className="rounded bg-muted/40 p-1.5 text-[11px] text-muted-foreground">
                            {hint}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Imported tables */}
          {(res.importadas.length > 0 || res.importados.length > 0 || res.importados_inut.length > 0) && (
            <div className="card-elevated overflow-hidden">
              <div className="border-b border-border bg-surface-3 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {res.dry_run ? "Seriam importados" : "Importados"}
              </div>
              <div className="space-y-2 p-2 text-[11px]">
                {res.importadas.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
                      NFe ({res.importadas.length})
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {res.importadas.map((n, i) => (
                        <span
                          key={i}
                          className="inline-flex h-5 items-center rounded-full border border-border bg-surface-1 px-2 font-mono"
                          title={String(n.chave ?? "")}
                        >
                          {n.numero ?? n.id}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {res.importados.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
                      Eventos ({res.importados.length})
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {res.importados.map((n, i) => (
                        <span
                          key={i}
                          className="inline-flex h-5 items-center rounded-full border border-border bg-surface-1 px-2 font-mono"
                        >
                          {n.tipo_evento}#{n.n_seq_evento}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {res.importados_inut.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
                      Inutilizações ({res.importados_inut.length})
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {res.importados_inut.map((n, i) => (
                        <span
                          key={i}
                          className="inline-flex h-5 items-center rounded-full border border-border bg-surface-1 px-2 font-mono"
                        >
                          {n.serie}/{n.n_nf_ini}-{n.n_nf_fin}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
