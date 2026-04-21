import { useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { FileSpreadsheet, FileText, Eye, Trash2, Clock } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  reportsApi,
  useDeleteReportInstance,
  useReportInstances,
} from "@/features/reports"
import type { ReportType } from "@/features/reports"

const REPORT_TYPE_LABEL: Record<ReportType, string> = {
  income_statement: "DRE",
  balance_sheet: "Balanço",
  cash_flow: "Fluxo de Caixa",
  trial_balance: "Balancete",
  general_ledger: "Razão",
  custom: "Personalizado",
}

export function HistoryPage() {
  const [statusFilter, setStatusFilter] = useState<string>("")
  const { data: instances = [], isLoading } = useReportInstances({
    status: statusFilter || undefined,
  })
  const del = useDeleteReportInstance()

  const onDelete = async (id: number, name: string) => {
    if (!window.confirm(`Excluir "${name}"?`)) return
    try {
      await del.mutateAsync(id)
      toast.success("Excluído")
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro")
    }
  }

  const onExport = async (id: number, fmt: "xlsx" | "pdf", name: string) => {
    try {
      const blob =
        fmt === "xlsx"
          ? await reportsApi.exportXlsx({ instance_id: id })
          : await reportsApi.exportPdf({ instance_id: id })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${safeName(name)}.${fmt}`
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
        title="Histórico de demonstrativos (beta)"
        subtitle="Relatórios gerados e salvos"
      />

      <div className="card-elevated flex items-center gap-2 p-2 text-[12px]">
        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-muted-foreground">Status:</span>
        {["", "draft", "final", "archived"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatusFilter(s)}
            className={
              "h-6 rounded-md px-2 text-[11px] font-medium " +
              (statusFilter === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-foreground")
            }
          >
            {s === "" ? "Todos" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <div className="card-elevated overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="h-8 px-3">Nome</th>
              <th className="h-8 px-3">Tipo</th>
              <th className="h-8 px-3">Status</th>
              <th className="h-8 px-3">Gerado em</th>
              <th className="h-8 px-3">Por</th>
              <th className="h-8 w-[1%] px-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={6} className="h-10 px-3">
                    <div className="h-4 animate-pulse rounded bg-muted/60" />
                  </td>
                </tr>
              ))
            ) : instances.length === 0 ? (
              <tr>
                <td colSpan={6} className="h-24 px-3 text-center text-muted-foreground">
                  Nenhum relatório salvo ainda
                </td>
              </tr>
            ) : (
              instances.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <td className="h-10 px-3 font-medium">{i.name}</td>
                  <td className="h-10 px-3 text-muted-foreground">
                    {REPORT_TYPE_LABEL[i.report_type] ?? i.report_type}
                  </td>
                  <td className="h-10 px-3">
                    <span
                      className={
                        "rounded-md px-2 py-0.5 text-[10px] font-medium " +
                        (i.status === "final"
                          ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                          : i.status === "archived"
                          ? "bg-muted text-muted-foreground"
                          : "bg-amber-500/15 text-amber-700 dark:text-amber-400")
                      }
                    >
                      {i.status}
                    </span>
                  </td>
                  <td className="h-10 px-3 text-muted-foreground">
                    {formatDateTime(i.generated_at)}
                  </td>
                  <td className="h-10 px-3 text-muted-foreground">
                    {i.generated_by_name ?? "—"}
                  </td>
                  <td className="h-10 whitespace-nowrap px-3">
                    <Link
                      to={`/reports/view/${i.id}`}
                      className="mr-1 inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
                    >
                      <Eye className="h-3 w-3" /> Ver
                    </Link>
                    <button
                      onClick={() => onExport(i.id, "xlsx", i.name)}
                      className="mr-1 inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
                    >
                      <FileSpreadsheet className="h-3 w-3" /> Excel
                    </button>
                    <button
                      onClick={() => onExport(i.id, "pdf", i.name)}
                      className="mr-1 inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
                    >
                      <FileText className="h-3 w-3" /> PDF
                    </button>
                    <button
                      onClick={() => onDelete(i.id, i.name)}
                      className="inline-flex h-7 items-center gap-1 rounded-md text-red-600 hover:bg-red-500/10 px-2 text-[11px]"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    })
  } catch {
    return iso
  }
}

function safeName(s: string): string {
  return (s || "demonstrativo").replace(/[/\\?%*:|"<>]/g, "-").trim()
}
