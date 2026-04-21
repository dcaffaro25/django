import { useParams, Link } from "react-router-dom"
import { toast } from "sonner"
import { FileSpreadsheet, FileText, ArrowLeft } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { reportsApi, useReportInstance } from "@/features/reports"
import { ReportRenderer } from "./components/ReportRenderer"

export function ViewPage() {
  const { id } = useParams<{ id: string }>()
  const instanceId = id ? Number(id) : null
  const { data, isLoading, error } = useReportInstance(instanceId)

  const onExport = async (fmt: "xlsx" | "pdf") => {
    if (!instanceId) return
    try {
      const blob =
        fmt === "xlsx"
          ? await reportsApi.exportXlsx({ instance_id: instanceId })
          : await reportsApi.exportPdf({ instance_id: instanceId })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${safeName(data?.name ?? "demonstrativo")}.${fmt}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success(`${fmt.toUpperCase()} exportado`)
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { error?: string } } })?.response
      if (resp?.status === 501) {
        toast.error(resp.data?.error ?? "PDF indisponível no servidor")
      } else {
        toast.error(err instanceof Error ? err.message : "Erro na exportação")
      }
    }
  }

  return (
    <div className="space-y-3">
      <SectionHeader
        title={data?.name ?? "Demonstrativo"}
        subtitle={data ? `Gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}` : ""}
        actions={
          <>
            <Link
              to="/reports/history"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] hover:bg-accent"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Histórico
            </Link>
            <button
              onClick={() => onExport("xlsx")}
              disabled={!data}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] hover:bg-accent disabled:opacity-40"
            >
              <FileSpreadsheet className="h-3.5 w-3.5" /> Excel
            </button>
            <button
              onClick={() => onExport("pdf")}
              disabled={!data}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] hover:bg-accent disabled:opacity-40"
            >
              <FileText className="h-3.5 w-3.5" /> PDF
            </button>
          </>
        }
      />

      <div className="card-elevated p-4">
        {isLoading ? (
          <div className="flex h-60 items-center justify-center text-muted-foreground">
            Carregando...
          </div>
        ) : error || !data ? (
          <div className="flex h-60 items-center justify-center text-red-600">
            Demonstrativo não encontrado
          </div>
        ) : (
          <ReportRenderer result={data.result} />
        )}
      </div>
    </div>
  )
}

function safeName(s: string): string {
  return (s || "demonstrativo").replace(/[/\\?%*:|"<>]/g, "-").trim()
}
