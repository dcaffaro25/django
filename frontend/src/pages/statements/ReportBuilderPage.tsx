import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import {
  FileBarChart, Plus, Save, Trash2, Copy, Download, FileText, FileSpreadsheet,
  Indent, Outdent, GripVertical, RefreshCw, Bold,
} from "lucide-react"
import {
  DndContext, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext, arrayMove, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { SectionHeader } from "@/components/ui/section-header"
import { cn } from "@/lib/utils"
import { useAccounts } from "@/features/reconciliation"
import {
  useTemplates, useSaveTemplate, useDeleteTemplate, useDuplicateTemplate,
  useGenerateStatement,
  statementsApi,
  type StatementTemplate, type LineTemplate, type ReportType,
  type LineType, type CalculationMethod, type SignPolicy,
  type PreviewStatementResponse, type GeneratedStatement,
} from "@/features/statements"

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: "balance_sheet", label: "Balanço Patrimonial" },
  { value: "income_statement", label: "DRE" },
  { value: "cash_flow", label: "Fluxo de Caixa" },
  { value: "trial_balance", label: "Balancete" },
  { value: "general_ledger", label: "Razão Geral" },
  { value: "custom", label: "Personalizado" },
]

const LINE_TYPES: { value: LineType; label: string }[] = [
  { value: "header", label: "Cabeçalho" },
  { value: "account", label: "Conta" },
  { value: "subtotal", label: "Subtotal" },
  { value: "total", label: "Total" },
  { value: "spacer", label: "Espaçador" },
]

const CALC_METHODS: { value: CalculationMethod; label: string }[] = [
  { value: "ending_balance", label: "Saldo Final" },
  { value: "opening_balance", label: "Saldo Inicial" },
  { value: "net_movement", label: "Movimento Líquido" },
  { value: "debit_total", label: "Total Débito" },
  { value: "credit_total", label: "Total Crédito" },
  { value: "change_in_balance", label: "Variação de Saldo" },
  { value: "rollup_children", label: "Soma de Filhos" },
  { value: "formula", label: "Fórmula" },
  { value: "manual_input", label: "Manual" },
]

const SIGN_POLICIES: { value: SignPolicy; label: string }[] = [
  { value: "natural", label: "Natural" },
  { value: "invert", label: "Inverter" },
  { value: "absolute", label: "Absoluto" },
]

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}
function monthStartISO() {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

type LineDraft = LineTemplate & { _key: string }

function blankTemplate(): StatementTemplate {
  return {
    name: "Novo demonstrativo",
    report_type: "income_statement",
    description: "",
    is_active: true,
    show_zero_balances: false,
    show_account_codes: true,
    show_percentages: false,
    group_by_cost_center: false,
    line_templates: [],
  }
}

function toDrafts(lines: LineTemplate[] | undefined): LineDraft[] {
  return (lines ?? [])
    .slice()
    .sort((a, b) => a.line_number - b.line_number)
    .map((l, i) => ({ ...l, _key: `l-${l.id ?? `new-${i}`}-${i}` }))
}

export function ReportBuilderPage() {
  const { data: templates = [], isLoading: loadingTemplates } = useTemplates()
  const saveTemplate = useSaveTemplate()
  const deleteTemplate = useDeleteTemplate()
  const duplicateTemplate = useDuplicateTemplate()
  const generate = useGenerateStatement()
  const { data: accounts = [] } = useAccounts()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [meta, setMeta] = useState<StatementTemplate>(blankTemplate())
  const [lines, setLines] = useState<LineDraft[]>([])
  const [dirty, setDirty] = useState(false)

  const [startDate, setStartDate] = useState(monthStartISO())
  const [endDate, setEndDate] = useState(todayISO())
  const [includePending, setIncludePending] = useState(false)

  const [preview, setPreview] = useState<PreviewStatementResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const previewRef = useRef<HTMLDivElement>(null)

  // Load template when selected
  useEffect(() => {
    if (!selectedId) {
      setMeta(blankTemplate())
      setLines([])
      setDirty(false)
      return
    }
    const t = templates.find((x) => x.id === selectedId)
    if (t) {
      setMeta({ ...t })
      setLines(toDrafts(t.line_templates))
      setDirty(false)
    }
  }, [selectedId, templates])

  const setMetaField = <K extends keyof StatementTemplate>(k: K, v: StatementTemplate[K]) => {
    setMeta((m) => ({ ...m, [k]: v }))
    setDirty(true)
  }

  const addLine = () => {
    const nextNum = (lines.length ? Math.max(...lines.map((l) => l.line_number)) : 0) + 10
    setLines((ls) => [
      ...ls,
      {
        _key: `l-new-${Date.now()}`,
        line_number: nextNum,
        label: "Nova linha",
        line_type: "account",
        calculation_method: "ending_balance",
        sign_policy: "natural",
        indent_level: 0,
        is_bold: false,
        account_ids: [],
        include_descendants: true,
        scale: "none",
        decimal_places: 2,
      },
    ])
    setDirty(true)
  }

  const updateLine = (key: string, patch: Partial<LineDraft>) => {
    setLines((ls) => ls.map((l) => (l._key === key ? { ...l, ...patch } : l)))
    setDirty(true)
  }

  const removeLine = (key: string) => {
    setLines((ls) => ls.filter((l) => l._key !== key))
    setDirty(true)
  }

  const reorder = (from: number, to: number) => {
    setLines((ls) => {
      const next = arrayMove(ls, from, to)
      // Re-stamp line_number in steps of 10 to keep ordering stable
      return next.map((l, i) => ({ ...l, line_number: (i + 1) * 10 }))
    })
    setDirty(true)
  }

  const onNew = () => {
    setSelectedId(null)
    setMeta(blankTemplate())
    setLines([])
    setDirty(true)
  }

  const onDuplicate = () => {
    if (!selectedId) return
    duplicateTemplate.mutate(selectedId, {
      onSuccess: (t) => {
        toast.success("Modelo duplicado")
        if (t.id) setSelectedId(t.id)
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const onDelete = () => {
    if (!selectedId) return
    if (!window.confirm(`Excluir modelo "${meta.name}"?`)) return
    deleteTemplate.mutate(selectedId, {
      onSuccess: () => {
        toast.success("Modelo excluído")
        setSelectedId(null)
      },
      onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
    })
  }

  const buildPayload = (): StatementTemplate => ({
    ...meta,
    line_templates: lines.map(({ _key, ...l }) => l),
  })

  const onSave = () => {
    if (!meta.name.trim()) { toast.error("Informe um nome"); return }
    saveTemplate.mutate(
      { id: selectedId ?? undefined, body: buildPayload() },
      {
        onSuccess: (t) => {
          toast.success("Modelo salvo")
          setDirty(false)
          if (t.id) setSelectedId(t.id)
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  // Run preview: requires saved template (generate endpoint needs a template_id).
  const runPreview = async () => {
    if (!selectedId) {
      toast.message("Salve o modelo antes de gerar a pré-visualização")
      return
    }
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const res = await generate.mutateAsync({
        template_id: selectedId,
        start_date: startDate,
        end_date: endDate,
        include_pending: includePending,
        persist: false,
      })
      setPreview(res as PreviewStatementResponse)
    } catch (err: unknown) {
      setPreviewError(err instanceof Error ? err.message : "Erro ao gerar pré-visualização")
    } finally {
      setPreviewLoading(false)
    }
  }

  const onExportExcel = async () => {
    if (!selectedId) { toast.error("Salve o modelo antes de exportar"); return }
    try {
      const saved = (await generate.mutateAsync({
        template_id: selectedId,
        start_date: startDate,
        end_date: endDate,
        include_pending: includePending,
        persist: true,
      })) as GeneratedStatement
      if (!saved.id) throw new Error("ID do demonstrativo não retornado")
      const blob = await statementsApi.exportExcel(saved.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${meta.name || "demonstrativo"}-${endDate}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success("Excel exportado")
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro na exportação")
    }
  }

  const onExportPDF = async () => {
    if (!previewRef.current || !preview) {
      toast.error("Gere a pré-visualização antes de exportar PDF")
      return
    }
    try {
      const { default: html2pdf } = await import("html2pdf.js")
      await html2pdf(previewRef.current)
        .set({
          margin: 10,
          filename: `${meta.name || "demonstrativo"}-${endDate}.pdf`,
          image: { type: "jpeg", quality: 0.98 },
          html2canvas: { scale: 2 },
          jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
        })
        .save()
      toast.success("PDF exportado")
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro ao exportar PDF")
    }
  }

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))
  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const from = lines.findIndex((l) => l._key === active.id)
    const to = lines.findIndex((l) => l._key === over.id)
    if (from < 0 || to < 0) return
    reorder(from, to)
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Construtor de demonstrativos"
        subtitle="Edite o modelo e veja a pré-visualização ao vivo"
        actions={
          <>
            <button onClick={onNew} className="btn-ghost">
              <Plus className="h-3.5 w-3.5" /> Novo
            </button>
            <button onClick={onDuplicate} disabled={!selectedId} className="btn-ghost disabled:opacity-40">
              <Copy className="h-3.5 w-3.5" /> Duplicar
            </button>
            <button onClick={onDelete} disabled={!selectedId} className="btn-ghost text-red-600 disabled:opacity-40">
              <Trash2 className="h-3.5 w-3.5" /> Excluir
            </button>
            <button
              onClick={onSave}
              disabled={saveTemplate.isPending || !dirty}
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" /> Salvar modelo
            </button>
          </>
        }
      />

      <style>{`
        .btn-ghost { display:inline-flex; height:2rem; align-items:center; gap:.375rem; border-radius:.375rem; border:1px solid hsl(var(--border)); background:hsl(var(--background)); padding:0 .75rem; font-size:12px; font-weight:500; }
        .btn-ghost:hover { background:hsl(var(--accent)); }
      `}</style>

      {/* Template picker */}
      <div className="card-elevated flex flex-wrap items-center gap-3 p-3">
        <label className="flex items-center gap-2 text-[12px]">
          <FileBarChart className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Modelo:</span>
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
            className="h-8 min-w-[260px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
          >
            <option value="">— novo / não selecionado —</option>
            {loadingTemplates ? (
              <option disabled>Carregando...</option>
            ) : (
              templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({REPORT_TYPES.find((r) => r.value === t.report_type)?.label ?? t.report_type})
                </option>
              ))
            )}
          </select>
        </label>
        {dirty && (
          <span className="rounded-md bg-amber-500/15 px-2 py-1 text-[11px] font-medium text-amber-700 dark:text-amber-400">
            alterações não salvas
          </span>
        )}
      </div>

      {/* Two-pane editor / preview */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* LEFT: Editor */}
        <div className="card-elevated flex flex-col p-4">
          <h2 className="mb-3 text-[13px] font-semibold">Estrutura do modelo</h2>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Nome">
              <input
                value={meta.name}
                onChange={(e) => setMetaField("name", e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
              />
            </Field>
            <Field label="Tipo de relatório">
              <select
                value={meta.report_type}
                onChange={(e) => setMetaField("report_type", e.target.value as ReportType)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
              >
                {REPORT_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>
          </div>

          <Field label="Descrição">
            <input
              value={meta.description ?? ""}
              onChange={(e) => setMetaField("description", e.target.value)}
              className="mt-2 h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
            />
          </Field>

          <div className="mt-3 flex flex-wrap gap-4 text-[12px]">
            <CheckField label="Mostrar saldos zerados" value={!!meta.show_zero_balances}
              onChange={(v) => setMetaField("show_zero_balances", v)} />
            <CheckField label="Mostrar códigos de contas" value={!!meta.show_account_codes}
              onChange={(v) => setMetaField("show_account_codes", v)} />
            <CheckField label="Mostrar percentuais" value={!!meta.show_percentages}
              onChange={(v) => setMetaField("show_percentages", v)} />
          </div>

          <div className="mt-4 mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
              Linhas ({lines.length})
            </h3>
            <button onClick={addLine} className="btn-ghost">
              <Plus className="h-3.5 w-3.5" /> Adicionar linha
            </button>
          </div>

          <div className="max-h-[560px] overflow-y-auto rounded-md border border-border">
            {lines.length === 0 ? (
              <div className="p-6 text-center text-[12px] text-muted-foreground">
                Nenhuma linha. Clique em "Adicionar linha" para começar.
              </div>
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                <SortableContext items={lines.map((l) => l._key)} strategy={verticalListSortingStrategy}>
                  {lines.map((line) => (
                    <LineRow
                      key={line._key}
                      line={line}
                      accounts={accounts}
                      onChange={(patch) => updateLine(line._key, patch)}
                      onRemove={() => removeLine(line._key)}
                    />
                  ))}
                </SortableContext>
              </DndContext>
            )}
          </div>
        </div>

        {/* RIGHT: Preview */}
        <div className="card-elevated flex flex-col p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[13px] font-semibold">Pré-visualização</h2>
            <div className="flex items-center gap-2">
              <button onClick={runPreview} disabled={previewLoading} className="btn-ghost">
                <RefreshCw className={cn("h-3.5 w-3.5", previewLoading && "animate-spin")} /> Gerar
              </button>
              <button onClick={onExportExcel} className="btn-ghost">
                <FileSpreadsheet className="h-3.5 w-3.5" /> Excel
              </button>
              <button onClick={onExportPDF} className="btn-ghost">
                <FileText className="h-3.5 w-3.5" /> PDF
              </button>
            </div>
          </div>

          <div className="mb-3 grid grid-cols-3 gap-3">
            <Field label="Data inicial">
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring" />
            </Field>
            <Field label="Data final">
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring" />
            </Field>
            <Field label="Incluir pendentes">
              <label className="flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2 text-[12px]">
                <input type="checkbox" checked={includePending}
                  onChange={(e) => setIncludePending(e.target.checked)} />
                <span className="text-muted-foreground">Transações não postadas</span>
              </label>
            </Field>
          </div>

          <div
            ref={previewRef}
            className="min-h-[560px] rounded-md border border-border bg-white p-6 text-[12px] text-black"
          >
            {previewLoading ? (
              <div className="flex h-full min-h-[400px] items-center justify-center text-muted-foreground">
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Gerando pré-visualização...
              </div>
            ) : previewError ? (
              <div className="text-red-600">{previewError}</div>
            ) : preview?.formatted?.html ? (
              <div
                className="prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: preview.formatted.html }}
              />
            ) : preview ? (
              <PreviewTable preview={preview} />
            ) : (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-2 text-muted-foreground">
                <Download className="h-8 w-8 opacity-30" />
                <span>Clique em "Gerar" para ver a pré-visualização</span>
                {!selectedId && <span className="text-[11px]">(salve o modelo primeiro)</span>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function CheckField({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  )
}

interface LineRowProps {
  line: LineDraft
  accounts: Array<{ id: number; name: string; path: string; account_code?: string | null }>
  onChange: (patch: Partial<LineDraft>) => void
  onRemove: () => void
}

function LineRow({ line, accounts, onChange, onRemove }: LineRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: line._key })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }

  const showFormula = line.calculation_method === "formula"
  const showManual = line.calculation_method === "manual_input"
  const showAccountPicker = ["account", "subtotal", "total"].includes(line.line_type) &&
    !["formula", "manual_input", "rollup_children"].includes(line.calculation_method ?? "")

  return (
    <div ref={setNodeRef} style={style}
      className="flex flex-wrap items-center gap-2 border-b border-border p-2 last:border-b-0 hover:bg-accent/40">
      <button {...attributes} {...listeners}
        className="grid h-7 w-6 cursor-grab place-items-center text-muted-foreground hover:text-foreground">
        <GripVertical className="h-3.5 w-3.5" />
      </button>

      <div className="w-10 text-center text-[11px] tabular-nums text-muted-foreground">
        {line.line_number}
      </div>

      <select value={line.line_type}
        onChange={(e) => onChange({ line_type: e.target.value as LineType })}
        className="h-7 w-[110px] rounded-md border border-border bg-background px-1 text-[11px]">
        {LINE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>

      <div className="flex items-center gap-0.5">
        <button title="Diminuir indentação" onClick={() => onChange({ indent_level: Math.max(0, (line.indent_level ?? 0) - 1) })}
          className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent">
          <Outdent className="h-3.5 w-3.5" />
        </button>
        <span className="w-4 text-center text-[11px] tabular-nums text-muted-foreground">
          {line.indent_level ?? 0}
        </span>
        <button title="Aumentar indentação" onClick={() => onChange({ indent_level: (line.indent_level ?? 0) + 1 })}
          className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent">
          <Indent className="h-3.5 w-3.5" />
        </button>
      </div>

      <input
        value={line.label}
        onChange={(e) => onChange({ label: e.target.value })}
        placeholder="Rótulo..."
        style={{ paddingLeft: `${0.5 + (line.indent_level ?? 0) * 0.75}rem` }}
        className={cn(
          "h-7 min-w-[180px] flex-1 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring",
          line.is_bold && "font-semibold",
        )}
      />

      {line.line_type !== "header" && line.line_type !== "spacer" && (
        <>
          <select value={line.calculation_method ?? "ending_balance"}
            onChange={(e) => onChange({ calculation_method: e.target.value as CalculationMethod })}
            className="h-7 w-[130px] rounded-md border border-border bg-background px-1 text-[11px]">
            {CALC_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>

          <select value={line.sign_policy ?? "natural"}
            onChange={(e) => onChange({ sign_policy: e.target.value as SignPolicy })}
            className="h-7 w-[90px] rounded-md border border-border bg-background px-1 text-[11px]">
            {SIGN_POLICIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>

          {showFormula && (
            <input
              value={line.formula ?? ""}
              onChange={(e) => onChange({ formula: e.target.value })}
              placeholder="L10 + L20 - L30"
              className="h-7 w-[160px] rounded-md border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-ring"
            />
          )}

          {showManual && (
            <input
              type="number" step="0.01"
              value={line.manual_value ?? ""}
              onChange={(e) => onChange({ manual_value: e.target.value })}
              placeholder="0.00"
              className="h-7 w-[100px] rounded-md border border-border bg-background px-2 tabular-nums text-[11px] outline-none focus:border-ring"
            />
          )}

          {showAccountPicker && (
            <AccountPicker
              accounts={accounts}
              value={line.account_ids ?? []}
              onChange={(ids) => onChange({ account_ids: ids })}
            />
          )}
        </>
      )}

      <button title="Negrito" onClick={() => onChange({ is_bold: !line.is_bold })}
        className={cn(
          "grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent",
          line.is_bold && "bg-accent text-foreground",
        )}>
        <Bold className="h-3.5 w-3.5" />
      </button>

      <button title="Remover linha" onClick={onRemove}
        className="grid h-7 w-7 place-items-center rounded-md text-red-600 hover:bg-red-500/10">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

function AccountPicker({
  accounts, value, onChange,
}: {
  accounts: Array<{ id: number; name: string; path: string; account_code?: string | null }>
  value: number[]
  onChange: (ids: number[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim()
    if (!needle) return accounts.slice(0, 200)
    return accounts
      .filter((a) => a.path.toLowerCase().includes(needle) || (a.account_code ?? "").toLowerCase().includes(needle))
      .slice(0, 200)
  }, [accounts, q])

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent">
        <span className="text-muted-foreground">Contas:</span>
        <span className="font-medium tabular-nums">{value.length}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] z-20 w-[360px] rounded-md border border-border bg-popover p-2 shadow-md">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar conta..."
            className="mb-2 h-7 w-full rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring"
          />
          <div className="max-h-[240px] overflow-y-auto">
            {filtered.map((a) => {
              const checked = value.includes(a.id)
              return (
                <label key={a.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-[11px] hover:bg-accent">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      if (checked) onChange(value.filter((v) => v !== a.id))
                      else onChange([...value, a.id])
                    }}
                  />
                  <span className="font-mono text-muted-foreground">{a.account_code ?? ""}</span>
                  <span className="truncate">{a.path}</span>
                </label>
              )
            })}
            {filtered.length === 0 && (
              <div className="px-2 py-3 text-center text-[11px] text-muted-foreground">Nenhuma conta encontrada</div>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
            <button onClick={() => onChange([])} className="text-[11px] text-muted-foreground hover:text-foreground">
              Limpar
            </button>
            <button onClick={() => setOpen(false)} className="btn-ghost">OK</button>
          </div>
        </div>
      )}
    </div>
  )
}

function PreviewTable({ preview }: { preview: PreviewStatementResponse }) {
  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold">{preview.name}</h1>
      <p className="mb-4 text-[11px] text-muted-foreground">
        {preview.start_date} → {preview.end_date}
      </p>
      <table className="w-full text-[12px]">
        <tbody>
          {preview.lines.map((l) => (
            <tr key={l.line_number} className={cn(l.is_bold && "font-semibold")}>
              <td
                className="py-1"
                style={{ paddingLeft: `${(l.indent_level ?? 0) * 1}rem` }}
              >
                {l.label}
              </td>
              <td className="py-1 text-right tabular-nums">
                {typeof l.balance === "string" ? l.balance : Number(l.balance).toLocaleString("pt-BR", {
                  minimumFractionDigits: 2, maximumFractionDigits: 2,
                })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
