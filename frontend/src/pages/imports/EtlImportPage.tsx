import { useState } from "react"
import { toast } from "sonner"
import { Upload, Play, FileSpreadsheet } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useEtlExecute } from "@/features/imports"

export function EtlImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [rowLimit, setRowLimit] = useState(10)
  const mut = useEtlExecute()
  const res = mut.data

  const onRun = () => {
    if (!file) {
      toast.error("Selecione um arquivo .xlsx.")
      return
    }
    mut.mutate(
      { file, rowLimit },
      {
        onError: (err: unknown) => {
          const msg =
            (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
            (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
            (err instanceof Error ? err.message : "erro desconhecido")
          toast.error(`ETL falhou: ${msg}`)
        },
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação ETL"
        subtitle="Executa um arquivo Excel contra o pipeline — usa __row_id para criar/editar/deletar."
      />

      <div className="card-elevated space-y-3 p-4">
        <label className="flex items-center gap-3">
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
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

        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Row limit
            </span>
            <input
              type="number"
              min={1}
              max={10000}
              value={rowLimit}
              onChange={(e) => setRowLimit(Math.max(1, Number(e.target.value) || 1))}
              className="h-8 w-28 rounded-md border border-border bg-background px-2 text-[13px] outline-none focus:border-ring"
            />
          </label>

          <button
            onClick={onRun}
            disabled={!file || mut.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {mut.isPending ? <Upload className="h-3.5 w-3.5 animate-pulse" /> : <Play className="h-3.5 w-3.5" />}
            {mut.isPending ? "Executando…" : "Executar"}
          </button>
        </div>
      </div>

      {res && (
        <div className="card-elevated p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <span
              className={
                "text-[13px] font-semibold " +
                (res.success ? "text-emerald-500" : "text-destructive")
              }
            >
              {res.success ? "Sucesso" : "Falha"}
            </span>
            <span className="text-[11px] text-muted-foreground">
              sheets: {(res.summary?.sheets_processed ?? []).join(", ") || "—"}
            </span>
          </div>
          <pre className="max-h-[520px] overflow-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-[11px]">
            {JSON.stringify(res, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
