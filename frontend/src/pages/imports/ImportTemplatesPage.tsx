import { useCallback, useMemo, useState } from "react"
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
  Sparkles,
  Upload,
  XCircle,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useBulkImport, useImportSessionPolling } from "@/features/imports"
import { downloadBulkImportTemplate, importsV2 } from "@/features/imports/api"
import type {
  BulkImportResponse,
  BulkImportRowResult,
  BulkImportSheetResult,
  ImportResolutionInput,
  ImportSession,
} from "@/features/imports/types"
import { DiagnosticsPanel } from "@/components/imports/DiagnosticsPanel"
import { cn } from "@/lib/utils"

interface SheetStats {
  total: number
  success: number
  errors: number
  byAction: Record<string, number>
}

function statsFor(sheet: BulkImportSheetResult): SheetStats {
  const rows = sheet.result ?? []
  const out: SheetStats = { total: rows.length, success: 0, errors: 0, byAction: {} }
  for (const r of rows) {
    const status = (r.status ?? "").toLowerCase()
    if (status === "success") out.success += 1
    else if (status === "error") out.errors += 1
    const action = (r.action ?? "").toString()
    if (action) out.byAction[action] = (out.byAction[action] ?? 0) + 1
  }
  return out
}

function rowHint(r: BulkImportRowResult): string | null {
  const msg = (r.message ?? "").toLowerCase()
  if (!msg) return null
  if (msg.includes("unknown model")) {
    return "Nome da aba inválido — verifique se o nome da sheet bate com um dos modelos do template."
  }
  if (msg.includes("substitution") || msg.includes("_fk") || msg.includes("not found")) {
    return "Referência não resolvida. Confira se o __row_id, erp_id ou o valor do _fk existe em outra aba do mesmo arquivo."
  }
  if (msg.includes("validation") || msg.includes("required")) {
    return "Falha de validação. Revise os campos obrigatórios e formatos (data, número, FK) nessa linha."
  }
  if (msg.includes("integrity") || msg.includes("unique") || msg.includes("duplicate key")) {
    return "Violação de unicidade. Outro registro já usa essa chave — ajuste o valor ou use um __row_id existente para atualizar."
  }
  if (msg.includes("permission") || msg.includes("forbidden")) {
    return "Permissão insuficiente para criar/atualizar esse modelo — verifique seu usuário."
  }
  return null
}

function SheetBlock({
  sheet,
  open,
  onToggle,
}: {
  sheet: BulkImportSheetResult
  open: boolean
  onToggle: () => void
}) {
  const stats = useMemo(() => statsFor(sheet), [sheet])
  const hasErrors = stats.errors > 0
  return (
    <div className="card-elevated overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-accent/30"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span
          className={cn(
            "text-[13px] font-semibold",
            hasErrors ? "text-destructive" : stats.success > 0 ? "text-emerald-600" : "",
          )}
        >
          {sheet.model}
        </span>
        <span className="flex items-center gap-2 text-[11px] tabular-nums text-muted-foreground">
          <span>{stats.total} linhas</span>
          {stats.success > 0 && <span className="text-emerald-600">{stats.success} ok</span>}
          {stats.errors > 0 && <span className="text-destructive">{stats.errors} erros</span>}
        </span>
        <span className="ml-auto flex flex-wrap gap-1 text-[10px] text-muted-foreground">
          {Object.entries(stats.byAction).map(([action, count]) => (
            <span
              key={action}
              className="inline-flex h-5 items-center rounded-full border border-border bg-surface-1 px-2 font-mono"
            >
              {action} · {count}
            </span>
          ))}
        </span>
      </button>
      {open && sheet.result.length > 0 && (
        <div className="max-h-80 overflow-auto border-t border-border">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="h-7 px-2">__row_id</th>
                <th className="h-7 px-2">Ação</th>
                <th className="h-7 px-2">Status</th>
                <th className="h-7 px-2">Mensagem</th>
              </tr>
            </thead>
            <tbody>
              {sheet.result.map((r, i) => {
                const hint = rowHint(r)
                const isErr = (r.status ?? "").toLowerCase() === "error"
                const isOk = (r.status ?? "").toLowerCase() === "success"
                return (
                  <tr key={i} className="border-t border-border align-top">
                    <td className="h-6 px-2 font-mono text-muted-foreground">
                      {String(r.__row_id ?? "—")}
                    </td>
                    <td className="h-6 px-2 font-mono text-muted-foreground">{r.action ?? "—"}</td>
                    <td className="h-6 px-2">
                      {isErr ? (
                        <span className="text-destructive">error</span>
                      ) : isOk ? (
                        <span className="text-emerald-600">success</span>
                      ) : (
                        <span className="text-muted-foreground">{r.status ?? "—"}</span>
                      )}
                    </td>
                    <td className="h-6 px-2">
                      <div>{r.message ?? "—"}</div>
                      {hint && (
                        <div className="mt-0.5 rounded bg-muted/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {hint}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function ImportTemplatesPage() {
  const [file, setFile] = useState<File | null>(null)
  const [downloading, setDownloading] = useState(false)
  const mut = useBulkImport()
  const res: BulkImportResponse | undefined = mut.data
  const [isPreview, setIsPreview] = useState(false)
  const [openSheets, setOpenSheets] = useState<Set<string>>(new Set())

  // v2 interactive mode — separate state so the legacy flow stays
  // byte-identical. Toggle defaults to OFF; operators who want the
  // diagnostics panel flip it on explicitly.
  const [mode, setMode] = useState<"v1" | "v2">("v1")
  const [v2Session, setV2Session] = useState<ImportSession | null>(null)
  const [v2Pending, setV2Pending] = useState<"analyze" | "resolve" | "commit" | null>(
    null,
  )

  // Phase 6.z-a — analyze/commit are now async on the backend. The
  // initial POST returns 202 with the session still in ``analyzing`` /
  // ``committing``; we poll the detail endpoint until it leaves that
  // state. In eager mode (dev without Redis) the poller is a no-op
  // because the session is already terminal when analyze returns.
  const { pollUntilDone: pollV2 } = useImportSessionPolling("template")

  const runV2Analyze = useCallback(async () => {
    if (!file) {
      toast.error("Selecione um arquivo .xlsx.")
      return
    }
    setV2Pending("analyze")
    try {
      const initial = await importsV2.template.analyze({ file })
      // Render what we got immediately — in prod this paints the
      // "analisando…" state in the diagnostics panel, so the operator
      // sees progress instead of a frozen button.
      setV2Session(initial)
      const session = await pollV2(initial)
      setV2Session(session)
      if (session.status === "ready") {
        toast.success("Pronto para importar — nenhuma pendência encontrada.")
      } else if (session.status === "awaiting_resolve") {
        const n = session.open_issues?.length ?? 0
        toast.message(
          `Sessão criada — ${n} pendência${n === 1 ? "" : "s"} aguardando resolução.`,
        )
      } else if (session.status === "error") {
        toast.error(
          `Falha ao analisar: ${
            (session.result as { error?: string })?.error ?? "erro desconhecido"
          }`,
        )
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string; error?: string } } })
          ?.response?.data?.error ?? (err instanceof Error ? err.message : "erro")
      toast.error(`Análise falhou: ${msg}`)
    } finally {
      setV2Pending(null)
    }
  }, [file, pollV2])

  const runV2Resolve = useCallback(
    async (resolutions: ImportResolutionInput[]) => {
      if (!v2Session) return
      setV2Pending("resolve")
      try {
        const updated = await importsV2.template.resolve(v2Session.id, {
          resolutions,
        })
        setV2Session(updated)
        if (updated.status === "ready") {
          toast.success("Pendências resolvidas — pronto para importar.")
        }
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string; error?: string } } })
            ?.response?.data?.error ?? (err instanceof Error ? err.message : "erro")
        toast.error(`Falha ao resolver: ${msg}`)
      } finally {
        setV2Pending(null)
      }
    },
    [v2Session],
  )

  const runV2Commit = useCallback(async () => {
    if (!v2Session) return
    setV2Pending("commit")
    try {
      const initial = await importsV2.template.commit(v2Session.id)
      setV2Session(initial)
      const finalised = await pollV2(initial)
      setV2Session(finalised)
      if (finalised.status === "committed") {
        toast.success("Importação concluída.")
      } else if (finalised.status === "error") {
        toast.error(
          `Falha no commit: ${
            (finalised.result as { error?: string })?.error ?? "erro"
          }`,
        )
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string; error?: string } } })
          ?.response?.data?.error ?? (err instanceof Error ? err.message : "erro")
      toast.error(`Commit falhou: ${msg}`)
    } finally {
      setV2Pending(null)
    }
  }, [v2Session, pollV2])

  const resetV2 = useCallback(() => {
    setV2Session(null)
    setV2Pending(null)
  }, [])

  const totals = useMemo(() => {
    if (!res) return { total: 0, success: 0, errors: 0 }
    let total = 0
    let success = 0
    let errors = 0
    for (const s of res.imports) {
      const st = statsFor(s)
      total += st.total
      success += st.success
      errors += st.errors
    }
    return { total, success, errors }
  }, [res])

  const canExecute = isPreview && !!res && !res.committed && totals.errors === 0 && totals.total > 0

  const toggleSheet = (model: string) =>
    setOpenSheets((s) => {
      const next = new Set(s)
      if (next.has(model)) next.delete(model)
      else next.add(model)
      return next
    })

  const onDownload = async () => {
    setDownloading(true)
    try {
      await downloadBulkImportTemplate()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : "erro desconhecido")
      toast.error(`Download falhou: ${msg}`)
    } finally {
      setDownloading(false)
    }
  }

  const run = (commit: boolean) => {
    if (!file) {
      toast.error("Selecione um arquivo .xlsx.")
      return
    }
    setIsPreview(!commit)
    setOpenSheets(new Set())
    mut.mutate(
      { file, commit },
      {
        onSuccess: (r) => {
          const errs = r.imports.reduce(
            (acc, s) =>
              acc + s.result.filter((row) => (row.status ?? "").toLowerCase() === "error").length,
            0,
          )
          if (errs > 0) {
            setOpenSheets(
              new Set(
                r.imports
                  .filter((s) =>
                    s.result.some((row) => (row.status ?? "").toLowerCase() === "error"),
                  )
                  .map((s) => s.model),
              ),
            )
            toast.error(
              commit
                ? `Importação falhou em ${errs} linha(s). Rollback aplicado — nada foi persistido.`
                : `Pré-visualização com ${errs} erro(s). Corrija antes de executar.`,
            )
          } else {
            toast.success(
              commit
                ? `Importação aplicada — ${r.imports.length} modelo(s).`
                : "Pré-visualização OK — pronto para executar.",
            )
          }
        },
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`${commit ? "Importação" : "Pré-visualização"} falhou: ${msg}`)
        },
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação via template"
        subtitle="Upload da planilha mestre (multi-modelo). Pré-visualize antes de commitar."
        actions={
          <button
            onClick={onDownload}
            disabled={downloading}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
            title="Baixa o workbook com cabeçalhos para cada modelo suportado."
          >
            {downloading ? (
              <Upload className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            {downloading ? "Gerando…" : "Baixar template"}
          </button>
        }
      />

      {/* Mode toggle: v1 is the legacy preview/execute flow (default);
          v2 swaps in the analyze → resolve → commit session-based flow.
          Switching modes resets both flows' state so there's no
          ambiguity about which payload the result panel is showing. */}
      <div className="card-elevated flex items-center gap-3 p-3 text-[12px]">
        <span className="text-muted-foreground">Modo:</span>
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          <button
            onClick={() => {
              setMode("v1")
              resetV2()
            }}
            className={cn(
              "h-7 px-3 text-[12px] font-medium",
              mode === "v1"
                ? "bg-primary text-primary-foreground"
                : "bg-background hover:bg-accent",
            )}
          >
            Clássico
          </button>
          <button
            onClick={() => {
              setMode("v2")
              mut.reset()
              setOpenSheets(new Set())
            }}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 px-3 text-[12px] font-medium",
              mode === "v2"
                ? "bg-primary text-primary-foreground"
                : "bg-background hover:bg-accent",
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Modo interativo (v2)
          </button>
        </div>
        {mode === "v2" && (
          <span className="text-[11px] text-muted-foreground">
            Analisa o arquivo, mostra pendências em cards e permite resolvê-las antes de importar.
          </span>
        )}
      </div>

      <div className="card-elevated space-y-3 p-4">
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null)
            mut.reset()
            setOpenSheets(new Set())
            resetV2()
          }}
          className="block w-full text-[12px] file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium hover:file:bg-accent"
        />

        {file && (
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <FileSpreadsheet className="h-3.5 w-3.5" />
            <span>{file.name}</span>
            <span>· {(file.size / 1024).toFixed(1)} KB</span>
          </div>
        )}

        {mode === "v1" ? (
          <div className="flex flex-wrap items-end gap-3">
            <button
              onClick={() => run(false)}
              disabled={!file || mut.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
              title="Dry-run: tudo roda, mas nada é commitado."
            >
              {mut.isPending && isPreview ? (
                <Upload className="h-3.5 w-3.5 animate-pulse" />
              ) : (
                <Eye className="h-3.5 w-3.5" />
              )}
              {mut.isPending && isPreview ? "Simulando…" : "Pré-visualizar"}
            </button>

            <button
              onClick={() => run(true)}
              disabled={!file || mut.isPending || !canExecute}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              title={
                canExecute
                  ? "Reenvia o arquivo com commit=true."
                  : "Rode uma pré-visualização sem erros antes de executar."
              }
            >
              {mut.isPending && !isPreview ? (
                <Upload className="h-3.5 w-3.5 animate-pulse" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {mut.isPending && !isPreview ? "Executando…" : "Executar para valer"}
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <button
              onClick={runV2Analyze}
              disabled={!file || v2Pending != null || (v2Session != null && !v2Session.is_terminal)}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              title={
                v2Session != null && !v2Session.is_terminal
                  ? "Sessão já em andamento — descarte-a antes de reanalisar."
                  : "Analisa o arquivo, cria uma sessão e surfaces pendências."
              }
            >
              {v2Pending === "analyze" ? (
                <Upload className="h-3.5 w-3.5 animate-pulse" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {v2Pending === "analyze" ? "Analisando…" : "Analisar"}
            </button>
            {v2Session && !v2Session.is_terminal && (
              <button
                onClick={resetV2}
                disabled={v2Pending != null}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
                title="Descarta a sessão e começa uma nova análise."
              >
                Descartar sessão
              </button>
            )}
          </div>
        )}
      </div>

      {mode === "v2" && v2Session && (
        <DiagnosticsPanel
          session={v2Session}
          onResolve={runV2Resolve}
          isResolving={v2Pending === "resolve"}
          onCommit={runV2Commit}
          isCommitting={v2Pending === "commit"}
        />
      )}

      {mode === "v1" && res && (
        <div className="space-y-3">
          <div
            className={cn(
              "flex flex-wrap items-center gap-3 rounded-lg border p-3 text-[13px]",
              totals.errors > 0
                ? "border-destructive/40 bg-destructive/5 text-destructive"
                : res.committed
                  ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-600"
                  : "border-amber-500/40 bg-amber-500/5 text-amber-600",
            )}
          >
            {totals.errors > 0 ? (
              <XCircle className="h-4 w-4" />
            ) : res.committed ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            <span className="font-semibold">
              {totals.errors > 0
                ? res.committed
                  ? `Importação falhou em ${totals.errors} linha(s). Rollback aplicado.`
                  : `Pré-visualização encontrou ${totals.errors} erro(s). Nada seria importado.`
                : res.committed
                  ? `${totals.success} linha(s) importada(s) com sucesso em ${res.imports.length} modelo(s).`
                  : `Pré-visualização OK — ${totals.success} linha(s) prontas para importar.`}
            </span>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {totals.total} linha(s) · {res.imports.length} modelo(s)
              {res.reason ? ` · ${res.reason}` : ""}
            </span>
          </div>

          {res.imports.length === 0 ? (
            <div className="card-elevated px-3 py-6 text-center text-[12px] text-muted-foreground">
              Nenhuma aba processada.
            </div>
          ) : (
            res.imports.map((s) => (
              <SheetBlock
                key={s.model}
                sheet={s}
                open={openSheets.has(s.model)}
                onToggle={() => toggleSheet(s.model)}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}
