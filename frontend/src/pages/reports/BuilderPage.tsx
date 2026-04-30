import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { useHotkeys } from "react-hotkeys-hook"
import {
  Save, Play, Download, FileSpreadsheet, FileText, Plus, Copy, Trash2, Layers, Sparkles,
  MessageSquare, Code, LayoutGrid,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  buildPresetPeriods,
  reportsApi,
  useCalculateReport,
  useDeleteReportTemplate,
  useDuplicateReportTemplate,
  useReportTemplates,
  useSaveReport,
  useSaveReportTemplate,
} from "@/features/reports"
import type {
  Period,
  ReportResult,
  ReportTemplate,
  ReportType,
  TemplateDocument,
} from "@/features/reports"
import { useUserRole } from "@/features/auth/useUserRole"
import { BlockEditor } from "./components/BlockEditor"
import { ReportRenderer } from "./components/ReportRenderer"
import { PeriodStrip } from "./components/PeriodStrip"
import { AiGenerateModal } from "./components/AiGenerateModal"
import { AiActionsToolbar } from "./components/AiActionsToolbar"
import { AiChatDrawer } from "./components/AiChatDrawer"
import { JsonTextMode } from "./components/JsonTextMode"

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: "income_statement", label: "DRE" },
  { value: "balance_sheet", label: "Balanço Patrimonial" },
  { value: "cash_flow", label: "Fluxo de Caixa" },
  { value: "trial_balance", label: "Balancete" },
  { value: "general_ledger", label: "Razão" },
  { value: "custom", label: "Personalizado" },
]

function newDocument(): TemplateDocument {
  return {
    version: 1,
    name: "Novo demonstrativo",
    report_type: "income_statement",
    description: "",
    defaults: { calculation_method: "net_movement", sign_policy: "natural" },
    blocks: [],
  }
}

export function BuilderPage() {
  const { data: templates = [] } = useReportTemplates()
  const saveTemplate = useSaveReportTemplate()
  const deleteTemplate = useDeleteReportTemplate()
  const duplicateTemplate = useDuplicateReportTemplate()
  const calculate = useCalculateReport()
  const saveReport = useSaveReport()
  // Hide template-mutation buttons (Novo / Duplicar / Excluir /
  // Salvar modelo) and instance-save (Salvar) from viewers /
  // view-as-viewer preview. Calculate + Export stay available so
  // a viewer can still run + download an existing template.
  const { canWrite } = useUserRole()

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [doc, setDoc] = useState<TemplateDocument>(newDocument())
  const [dirty, setDirty] = useState(false)

  const initialPreset = useMemo(
    () => buildPresetPeriods({ ref: new Date().toISOString().slice(0, 10), reportType: doc.report_type }, "yoy"),
    // only on initial mount; the user can explicitly change via the preset menu
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )
  const [periods, setPeriods] = useState<Period[]>(initialPreset)
  const [preview, setPreview] = useState<ReportResult | null>(null)
  const [aiOpen, setAiOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [editMode, setEditMode] = useState<"visual" | "json">("visual")

  // Load selected template into the editor.
  useEffect(() => {
    if (!selectedTemplateId) {
      return
    }
    const t = templates.find((x) => x.id === selectedTemplateId)
    if (!t) return
    setDoc(t.document)
    setDirty(false)
    setPreview(null)
  }, [selectedTemplateId, templates])

  // If the user switches report_type, ensure the periods panel still makes sense
  useEffect(() => {
    if (!periods.length) return
    const isStock = doc.report_type === "balance_sheet"
    const badMix = periods.some((p) => (isStock ? p.type === "range" : p.type === "as_of"))
    if (badMix) {
      setPeriods(
        buildPresetPeriods(
          { ref: new Date().toISOString().slice(0, 10), reportType: doc.report_type },
          "single",
        ),
      )
    }
  }, [doc.report_type, periods])

  const onDocChange = (next: TemplateDocument) => {
    setDoc(next)
    setDirty(true)
  }

  const onSaveTemplate = () => {
    if (!doc.name.trim()) {
      toast.error("Informe um nome")
      return
    }
    const body: ReportTemplate = {
      id: selectedTemplateId ?? undefined,
      name: doc.name,
      report_type: doc.report_type,
      description: doc.description ?? null,
      document: doc,
    }
    saveTemplate.mutate(
      { id: selectedTemplateId ?? undefined, body },
      {
        onSuccess: (t) => {
          toast.success("Modelo salvo")
          if (t.id) setSelectedTemplateId(t.id)
          setDirty(false)
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  const onCalculate = async () => {
    if (!periods.length) {
      toast.error("Adicione pelo menos um período")
      return
    }
    try {
      const result = await calculate.mutateAsync({
        template: doc,
        periods,
      })
      setPreview(result)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: unknown } })?.response?.data
      toast.error(typeof msg === "string" ? msg : (err instanceof Error ? err.message : "Erro no cálculo"))
    }
  }

  const onSaveInstance = async () => {
    if (!preview) {
      toast.error("Calcule antes de salvar")
      return
    }
    try {
      await saveReport.mutateAsync({
        template: doc,
        template_id: selectedTemplateId ?? undefined,
        periods,
        result: preview,
        name: doc.name,
        status: "draft",
      })
      toast.success("Demonstrativo salvo no histórico")
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar")
    }
  }

  const onExport = async (fmt: "xlsx" | "pdf") => {
    if (!preview) {
      toast.error("Calcule antes de exportar")
      return
    }
    try {
      const blob =
        fmt === "xlsx"
          ? await reportsApi.exportXlsx({ result: preview, name: doc.name })
          : await reportsApi.exportPdf({ result: preview, name: doc.name })
      triggerDownload(blob, `${safeName(doc.name)}.${fmt}`)
      toast.success(`${fmt.toUpperCase()} exportado`)
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { error?: string } } })?.response
      if (resp?.status === 501) {
        toast.error(resp.data?.error ?? "PDF indisponível no servidor — use html2pdf no cliente")
      } else {
        toast.error(err instanceof Error ? err.message : "Erro na exportação")
      }
    }
  }

  const onDuplicate = () => {
    if (!selectedTemplateId) return
    duplicateTemplate.mutate(selectedTemplateId, {
      onSuccess: (t) => {
        toast.success("Modelo duplicado")
        if (t.id) setSelectedTemplateId(t.id)
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const onDelete = () => {
    if (!selectedTemplateId) return
    if (!window.confirm(`Excluir modelo "${doc.name}"?`)) return
    deleteTemplate.mutate(selectedTemplateId, {
      onSuccess: () => {
        toast.success("Modelo excluído")
        setSelectedTemplateId(null)
        setDoc(newDocument())
        setDirty(false)
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const onNew = () => {
    setSelectedTemplateId(null)
    setDoc(newDocument())
    setDirty(true)
    setPreview(null)
  }

  // Keyboard shortcuts — preventDefault so the browser's Save dialog
  // doesn't show on Ctrl/Cmd+S, and the textarea/input don't submit a
  // form on Ctrl/Cmd+Enter.
  useHotkeys(
    "mod+s",
    (e) => {
      e.preventDefault()
      if (dirty && !saveTemplate.isPending) onSaveTemplate()
    },
    { enableOnFormTags: true },
    [dirty, saveTemplate.isPending, doc, selectedTemplateId],
  )
  useHotkeys(
    "mod+enter",
    (e) => {
      e.preventDefault()
      if (!calculate.isPending) onCalculate()
    },
    { enableOnFormTags: true },
    [calculate.isPending, doc, periods],
  )
  useHotkeys(
    "slash",
    (e) => {
      // Only trigger when not typing inside a text control.
      const t = e.target as HTMLElement
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) {
        return
      }
      e.preventDefault()
      setChatOpen(true)
    },
  )

  return (
    <div className="space-y-3">
      <SectionHeader
        title="Construtor de demonstrativos (beta)"
        subtitle="Novo motor — edite o modelo, veja a pré-visualização multi-período, exporte"
        actions={
          <>
            {canWrite && (
              <>
                <button
                  onClick={() => setAiOpen(true)}
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 text-[12px] font-medium text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
                >
                  <Sparkles className="h-3.5 w-3.5" /> Gerar com IA
                </button>
                <button
                  onClick={() => setChatOpen(true)}
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-blue-500/40 bg-blue-500/10 px-3 text-[12px] font-medium text-blue-700 hover:bg-blue-500/20 dark:text-blue-300"
                >
                  <MessageSquare className="h-3.5 w-3.5" /> Chat IA
                </button>
                <BtnGhost onClick={onNew}>
                  <Plus className="h-3 w-3" /> Novo
                </BtnGhost>
                <BtnGhost onClick={onDuplicate} disabled={!selectedTemplateId}>
                  <Copy className="h-3 w-3" /> Duplicar
                </BtnGhost>
                <BtnGhost onClick={onDelete} disabled={!selectedTemplateId} className="text-red-600">
                  <Trash2 className="h-3 w-3" /> Excluir
                </BtnGhost>
                <button
                  onClick={onSaveTemplate}
                  disabled={!dirty || saveTemplate.isPending}
                  className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  <Save className="h-3.5 w-3.5" /> Salvar modelo
                </button>
              </>
            )}
          </>
        }
      />

      <AiGenerateModal
        open={aiOpen}
        onClose={() => setAiOpen(false)}
        onGenerated={(generated) => {
          // AI-generated draft drops into the editor as a new unsaved template.
          // Clear the selected template so the user doesn't accidentally
          // overwrite a saved one.
          setSelectedTemplateId(null)
          setDoc(generated)
          setDirty(true)
          setPreview(null)
          toast.success("Modelo gerado pela IA — revise e salve")
        }}
      />

      <AiChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        doc={doc}
        preview={preview}
        onDocChange={(next) => {
          onDocChange(next)
        }}
        onPeriodPreset={(preset) => {
          const next = buildPresetPeriods(
            { ref: new Date().toISOString().slice(0, 10), reportType: doc.report_type },
            preset,
          )
          setPeriods(next)
        }}
      />

      <div className="card-elevated flex flex-wrap items-center gap-3 p-2 text-[12px]">
        <Layers className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-muted-foreground">Modelo:</span>
        <select
          value={selectedTemplateId ?? ""}
          onChange={(e) =>
            setSelectedTemplateId(e.target.value ? Number(e.target.value) : null)
          }
          className="h-7 min-w-[260px] rounded-md border border-border bg-background px-2 text-[12px]"
        >
          <option value="">— novo / não selecionado —</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({REPORT_TYPES.find((r) => r.value === t.report_type)?.label ?? t.report_type})
            </option>
          ))}
        </select>
        <input
          value={doc.name}
          onChange={(e) => onDocChange({ ...doc, name: e.target.value })}
          placeholder="Nome"
          className="h-7 w-[220px] rounded-md border border-border bg-background px-2 text-[12px]"
        />
        <select
          value={doc.report_type}
          onChange={(e) =>
            onDocChange({ ...doc, report_type: e.target.value as ReportType })
          }
          className="h-7 w-[180px] rounded-md border border-border bg-background px-2 text-[12px]"
        >
          {REPORT_TYPES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        {dirty && (
          <span className="rounded-md bg-amber-500/15 px-2 py-1 text-[10px] font-medium text-amber-700 dark:text-amber-400">
            alterações não salvas
          </span>
        )}
      </div>

      <PeriodStrip periods={periods} reportType={doc.report_type} onChange={setPeriods} />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="card-elevated space-y-2 p-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
              Estrutura do modelo
            </h2>
            <div className="inline-flex overflow-hidden rounded-md border border-border bg-background text-[11px]">
              <button
                onClick={() => setEditMode("visual")}
                className={
                  "inline-flex h-6 items-center gap-1 px-2 transition-colors " +
                  (editMode === "visual"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent")
                }
              >
                <LayoutGrid className="h-3 w-3" /> Visual
              </button>
              <button
                onClick={() => setEditMode("json")}
                className={
                  "inline-flex h-6 items-center gap-1 px-2 transition-colors " +
                  (editMode === "json"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent")
                }
              >
                <Code className="h-3 w-3" /> JSON
              </button>
            </div>
          </div>
          {editMode === "visual" ? (
            <>
              <AiActionsToolbar doc={doc} onApply={onDocChange} />
              <BlockEditor document={doc} onChange={onDocChange} />
            </>
          ) : (
            <JsonTextMode document={doc} onApply={onDocChange} />
          )}
        </div>

        <div className="card-elevated p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
              Pré-visualização
            </h2>
            <div className="flex items-center gap-1">
              <BtnGhost onClick={onCalculate} disabled={calculate.isPending}>
                <Play className="h-3 w-3" /> Calcular
              </BtnGhost>
              {canWrite && (
                <BtnGhost onClick={onSaveInstance} disabled={!preview || saveReport.isPending}>
                  <Download className="h-3 w-3" /> Salvar
                </BtnGhost>
              )}
              <BtnGhost onClick={() => onExport("xlsx")} disabled={!preview}>
                <FileSpreadsheet className="h-3 w-3" /> Excel
              </BtnGhost>
              <BtnGhost onClick={() => onExport("pdf")} disabled={!preview}>
                <FileText className="h-3 w-3" /> PDF
              </BtnGhost>
            </div>
          </div>
          <ReportRenderer result={preview} document={doc} />
        </div>
      </div>
    </div>
  )
}

function BtnGhost({
  children, onClick, disabled, className,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  className?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={
        "inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent disabled:opacity-40 " +
        (className ?? "")
      }
    >
      {children}
    </button>
  )
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function safeName(s: string): string {
  return (s || "demonstrativo").replace(/[/\\?%*:|"<>]/g, "-").trim()
}
