import { useState } from "react"
import { toast } from "sonner"
import { Upload, Play, FileText } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useOfxImport } from "@/features/imports"

export function OfxImportPage() {
  const [files, setFiles] = useState<File[]>([])
  const mut = useOfxImport()
  const res = mut.data

  const onRun = () => {
    if (!files.length) {
      toast.error("Selecione um ou mais arquivos .ofx.")
      return
    }
    mut.mutate(files, {
      onError: (err: unknown) => {
        const msg =
          (err as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ??
          (err instanceof Error ? err.message : "erro desconhecido")
        toast.error(`OFX falhou: ${msg}`)
      },
    })
  }

  const totals = res?.import_results.reduce(
    (acc, r) => ({
      inserted: acc.inserted + (r.inserted || 0),
      duplicates: acc.duplicates + (r.duplicates || 0),
    }),
    { inserted: 0, duplicates: 0 },
  )

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importação OFX"
        subtitle="Envia extratos bancários em OFX. Duplicatas são detectadas pelo hash."
      />

      <div className="card-elevated space-y-3 p-4">
        <input
          type="file"
          accept=".ofx"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
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

        <button
          onClick={onRun}
          disabled={!files.length || mut.isPending}
          className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {mut.isPending ? <Upload className="h-3.5 w-3.5 animate-pulse" /> : <Play className="h-3.5 w-3.5" />}
          {mut.isPending ? "Importando…" : `Importar ${files.length || ""}`}
        </button>
      </div>

      {res && (
        <div className="card-elevated p-4">
          <div className="mb-3 flex items-baseline gap-4 text-[12px]">
            <span className="text-emerald-500 font-semibold">{totals?.inserted ?? 0} inseridos</span>
            <span className="text-amber-500 font-semibold">{totals?.duplicates ?? 0} duplicatas</span>
            <span className="text-muted-foreground">· {res.import_results.length} arquivo(s)</span>
          </div>
          <div className="overflow-auto rounded-md border border-border" style={{ maxHeight: 420 }}>
            <table className="w-full text-[11px]">
              <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="h-7 px-2">Arquivo</th>
                  <th className="h-7 px-2">Banco</th>
                  <th className="h-7 px-2">Conta</th>
                  <th className="h-7 px-2 text-right">Inseridos</th>
                  <th className="h-7 px-2 text-right">Duplicatas</th>
                  <th className="h-7 px-2 text-right">Ratio</th>
                </tr>
              </thead>
              <tbody>
                {res.import_results.map((r, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="h-7 px-2 font-medium">{r.filename}</td>
                    <td className="h-7 px-2 text-muted-foreground">{r.bank ?? "—"}</td>
                    <td className="h-7 px-2 text-muted-foreground">{r.account ?? "—"}</td>
                    <td className="h-7 px-2 text-right tabular-nums">{r.inserted}</td>
                    <td className="h-7 px-2 text-right tabular-nums">{r.duplicates}</td>
                    <td className="h-7 px-2 text-right tabular-nums">
                      {r.duplicate_ratio != null ? (r.duplicate_ratio * 100).toFixed(0) + "%" : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
