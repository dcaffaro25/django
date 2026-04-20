import { useState } from "react"
import { toast } from "sonner"
import { Upload, Play, FileCode } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useNfeImport } from "@/features/imports"

export function NfImportPage() {
  const [files, setFiles] = useState<File[]>([])
  const mut = useNfeImport()
  const res = mut.data

  const onRun = () => {
    if (!files.length) {
      toast.error("Selecione um ou mais arquivos XML de NF-e.")
      return
    }
    if (files.length > 20) {
      toast.error("Máximo de 20 arquivos por requisição.")
      return
    }
    mut.mutate(files, {
      onError: (err: unknown) => {
        const msg =
          (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
          (err instanceof Error ? err.message : "erro desconhecido")
        toast.error(`Importação NF-e falhou: ${msg}`)
      },
    })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação de NF-e"
        subtitle="Faz upload de XMLs de NF-e, eventos e inutilizações. Máx 20 arquivos por vez."
      />

      <div className="card-elevated space-y-3 p-4">
        <input
          type="file"
          accept=".xml"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          className="block w-full text-[12px] file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium hover:file:bg-accent"
        />

        {files.length > 0 && (
          <div className="text-[12px] text-muted-foreground">
            {files.length} arquivo(s) selecionado(s) · total{" "}
            {(files.reduce((s, f) => s + f.size, 0) / 1024).toFixed(0)} KB
          </div>
        )}

        <button
          onClick={onRun}
          disabled={!files.length || mut.isPending}
          className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {mut.isPending ? <Upload className="h-3.5 w-3.5 animate-pulse" /> : <Play className="h-3.5 w-3.5" />}
          {mut.isPending ? "Importando…" : "Importar"}
        </button>
      </div>

      {res && (
        <div className="card-elevated p-4">
          <div className="mb-3 flex items-baseline gap-4 text-[12px]">
            <span className="font-semibold">{res.nfe_count ?? 0} NF-e</span>
            <span className="font-semibold">{res.evento_count ?? 0} eventos</span>
            <span className="font-semibold">{res.inutilizacao_count ?? 0} inutilizações</span>
            {res.errors && res.errors.length > 0 && (
              <span className="text-destructive font-semibold">{res.errors.length} erro(s)</span>
            )}
          </div>
          {res.nfe_results && res.nfe_results.length > 0 && (
            <div className="overflow-auto rounded-md border border-border" style={{ maxHeight: 320 }}>
              <table className="w-full text-[11px]">
                <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="h-7 px-2">Arquivo</th>
                    <th className="h-7 px-2">Ação</th>
                    <th className="h-7 px-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {res.nfe_results.map((r, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="h-7 px-2 font-medium">
                        <FileCode className="mr-1 inline h-3 w-3" />
                        {r.filename}
                      </td>
                      <td className="h-7 px-2 text-muted-foreground">{r.action ?? "—"}</td>
                      <td className="h-7 px-2 text-muted-foreground">{r.status ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {res.errors && res.errors.length > 0 && (
            <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-[11px] text-destructive">
              {res.errors.map((e, i) => (
                <div key={i}>
                  <strong>{e.filename}:</strong> {e.error_message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
