import { useMemo, useState } from "react"
import {
  DndContext, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import {
  FileText, Receipt, Equal, Sigma, Minus, Heading, GripVertical, Trash2, Plus,
  ChevronRight, AlertTriangle, MoreHorizontal, Sparkles,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type {
  Block, BlockType, LineBlock, SectionBlock, SubtotalBlock, TemplateDocument, TotalBlock,
} from "@/features/reports"
import { collectBlockIds, detectFormulaCycle } from "@/features/reports"
import {
  flattenForEdit, reorderFlat, uniqueBlockId, type FlatBlock,
} from "./block-tree"
import { BlockDetailDrawer } from "./BlockDetailDrawer"

/**
 * PR9 refresh: the row is now compact — drag / type-icon / label / id /
 * overflow (⋯) / delete — and every other setting lives in a right-side
 * drawer (BlockDetailDrawer). Block types render with distinct styling
 * (sections = colored strip, totals = top border, spacers = hairline).
 */
export function BlockEditor({
  document,
  onChange,
}: {
  document: TemplateDocument
  onChange: (next: TemplateDocument) => void
}) {
  const flat = useMemo(() => flattenForEdit(document), [document])
  const validIds = useMemo(() => collectBlockIds(document), [document])
  const cycle = useMemo(() => detectFormulaCycle(document), [document])
  const cyclicIds = useMemo(() => new Set(cycle ?? []), [cycle])

  const [drawerKey, setDrawerKey] = useState<string | null>(null)
  const drawerBlock: Block | null = useMemo(() => {
    if (!drawerKey) return null
    const match = flat.find((fb) => fb._key === drawerKey)
    return match?.block ?? null
  }, [drawerKey, flat])

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))

  const writeFlat = (nextFlat: FlatBlock[]) => {
    const blocks = buildBlocksFromFlat(nextFlat)
    onChange({ ...document, blocks })
  }

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const from = flat.findIndex((fb) => fb._key === active.id)
    const to = flat.findIndex((fb) => fb._key === over.id)
    if (from < 0 || to < 0) return
    writeFlat(reorderFlat(flat, from, to))
  }

  const addBlock = (type: BlockType) => {
    const newId = uniqueBlockId(flat, type)
    const base = { id: newId, label: labelForType(type) }
    let newBlock: Block
    switch (type) {
      case "section":
        newBlock = { type, ...base, children: [] }
        break
      case "header":
        newBlock = { type, ...base }
        break
      case "line":
        newBlock = { type, ...base, accounts: { code_prefix: "", include_descendants: true } }
        break
      case "subtotal":
      case "total":
        newBlock = { type, ...base, formula: "" } as SubtotalBlock | TotalBlock
        break
      case "spacer":
      default:
        newBlock = { type: "spacer", id: newId }
        break
    }
    onChange({ ...document, blocks: [...document.blocks, newBlock] })
  }

  const updateBlock = (key: string, patch: Partial<Block>) => {
    const nextFlat = flat.map((fb) =>
      fb._key === key ? { ...fb, block: { ...fb.block, ...patch } as Block } : fb,
    )
    writeFlat(nextFlat)
  }

  const removeBlock = (key: string) => {
    const target = flat.find((fb) => fb._key === key)
    if (!target) return
    const toRemove = new Set<string>([key])
    if (target.block.type === "section") {
      for (const fb of flat) {
        if (fb.parent_id === target.block.id) toRemove.add(fb._key)
      }
    }
    writeFlat(flat.filter((fb) => !toRemove.has(fb._key)))
  }

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <span className="mr-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Adicionar
        </span>
        <AddBlockButton onClick={() => addBlock("section")} icon={<ChevronRight className="h-3 w-3" />} label="Seção" />
        <AddBlockButton onClick={() => addBlock("header")} icon={<Heading className="h-3 w-3" />} label="Cabeçalho" />
        <AddBlockButton onClick={() => addBlock("line")} icon={<Receipt className="h-3 w-3" />} label="Linha" />
        <AddBlockButton onClick={() => addBlock("subtotal")} icon={<Sigma className="h-3 w-3" />} label="Subtotal" />
        <AddBlockButton onClick={() => addBlock("total")} icon={<Equal className="h-3 w-3" />} label="Total" />
        <AddBlockButton onClick={() => addBlock("spacer")} icon={<Minus className="h-3 w-3" />} label="Espaçador" />
      </div>

      {cycle && (
        <div className="mb-2 flex items-start gap-2 rounded-md border border-red-500/50 bg-red-500/10 p-2 text-[11px] text-red-700 dark:text-red-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <div>
            <div className="font-medium">Referência circular detectada</div>
            <div className="text-[10px] opacity-80">{cycle.join(" → ")}</div>
          </div>
        </div>
      )}

      {flat.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-[12px] text-muted-foreground">
          Sem blocos. Adicione um bloco, gere com IA, ou abra o chat.
        </div>
      ) : (
        <div className="rounded-md border border-border">
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={flat.map((fb) => fb._key)} strategy={verticalListSortingStrategy}>
              {flat.map((fb) => (
                <BlockRow
                  key={fb._key}
                  item={fb}
                  isInCycle={cyclicIds.has(fb.block.id)}
                  onChange={(patch) => updateBlock(fb._key, patch)}
                  onRemove={() => removeBlock(fb._key)}
                  onOpenDetail={() => setDrawerKey(fb._key)}
                />
              ))}
            </SortableContext>
          </DndContext>
        </div>
      )}

      <BlockDetailDrawer
        open={drawerKey !== null}
        block={drawerBlock}
        validIds={validIds}
        onChange={(patch) => {
          if (drawerKey) updateBlock(drawerKey, patch)
        }}
        onClose={() => setDrawerKey(null)}
      />
    </div>
  )
}

// ---- BlockRow -------------------------------------------------------------

function BlockRow({
  item, isInCycle, onChange, onRemove, onOpenDetail,
}: {
  item: FlatBlock
  isInCycle: boolean
  onChange: (patch: Partial<Block>) => void
  onRemove: () => void
  onOpenDetail: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item._key })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }
  const { block, depth } = item
  const styling = rowStyleFor(block.type)
  const label = (block as { label?: string | null }).label ?? ""
  const isBold =
    ((block as { bold?: boolean | null }).bold ?? false)
    || block.type === "subtotal" || block.type === "total"
    || block.type === "header" || block.type === "section"

  // Spacer is a special minimal row — thin hairline with just a drag handle.
  if (block.type === "spacer") {
    return (
      <div
        ref={setNodeRef}
        style={style}
        className={cn(
          "group flex items-center gap-2 border-b border-border/30 px-2 py-0.5 last:border-b-0",
          isInCycle && "border-l-2 border-l-red-500",
        )}
      >
        <button {...attributes} {...listeners}
          className="grid h-5 w-5 cursor-grab place-items-center text-muted-foreground/50 hover:text-foreground">
          <GripVertical className="h-3 w-3" />
        </button>
        <div className="flex-1 border-t border-dashed border-border/60" />
        <code className="text-[10px] text-muted-foreground/60">{block.id}</code>
        <button onClick={onRemove}
          className="grid h-5 w-5 place-items-center rounded-md text-red-600/60 opacity-0 hover:bg-red-500/10 group-hover:opacity-100">
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    )
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "group flex flex-wrap items-center gap-2 border-b border-border/50 px-2 py-1.5 last:border-b-0 hover:bg-accent/30",
        styling.row,
        isInCycle && "border-l-2 border-l-red-500 bg-red-500/5",
      )}
    >
      <button
        {...attributes}
        {...listeners}
        className="grid h-6 w-5 cursor-grab place-items-center text-muted-foreground hover:text-foreground"
        aria-label="Mover"
      >
        <GripVertical className="h-3 w-3" />
      </button>

      <div className={cn("grid h-5 w-5 place-items-center rounded", styling.iconBg)}>
        <TypeIcon type={block.type} />
      </div>

      <div style={{ width: `${depth * 12}px` }} />

      <input
        value={label}
        onChange={(e) => onChange({ label: e.target.value } as Partial<Block>)}
        placeholder="Rótulo"
        className={cn(
          "h-7 flex-1 min-w-[140px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring",
          isBold && "font-semibold",
        )}
      />

      <code className="text-[10px] text-muted-foreground">{block.id}</code>

      {(block as { ai_explanation?: string | null }).ai_explanation && (
        <Sparkles
          className="h-3 w-3 text-amber-500"
          aria-label="Sugerido pela IA"
        />
      )}

      <button
        onClick={onOpenDetail}
        title="Configurações do bloco"
        className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <MoreHorizontal className="h-3 w-3" />
      </button>

      <button
        onClick={onRemove}
        title="Remover"
        className="grid h-6 w-6 place-items-center rounded-md text-red-600/70 hover:bg-red-500/10 hover:text-red-600"
        aria-label="Remover"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

// ---- Style helpers --------------------------------------------------------

interface RowStyle {
  row: string
  iconBg: string
}

function rowStyleFor(type: BlockType): RowStyle {
  switch (type) {
    case "section":
      return {
        row: "bg-gradient-to-r from-blue-500/10 to-transparent border-l-2 border-l-blue-500/60",
        iconBg: "bg-blue-500/20 text-blue-700 dark:text-blue-300",
      }
    case "header":
      return {
        row: "bg-surface-3/50",
        iconBg: "bg-surface-3",
      }
    case "subtotal":
      return {
        row: "border-t border-t-foreground/30",
        iconBg: "bg-muted",
      }
    case "total":
      return {
        row: "border-t-2 border-t-foreground/70 bg-surface-2/40",
        iconBg: "bg-primary/20 text-primary",
      }
    case "line":
    default:
      return { row: "", iconBg: "bg-muted/60" }
  }
}

function TypeIcon({ type }: { type: BlockType }) {
  const cls = "h-3 w-3"
  if (type === "section") return <ChevronRight className={cls} />
  if (type === "header") return <Heading className={cls} />
  if (type === "line") return <Receipt className={cls} />
  if (type === "subtotal") return <Sigma className={cls} />
  if (type === "total") return <Equal className={cls} />
  return <FileText className={cls} />
}

function AddBlockButton({
  onClick, icon, label,
}: {
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent"
    >
      {icon}
      <span>{label}</span>
      <Plus className="h-2.5 w-2.5 text-muted-foreground" />
    </button>
  )
}

function labelForType(type: BlockType): string {
  return {
    section: "Nova Seção",
    header: "Novo Cabeçalho",
    line: "Nova Linha",
    subtotal: "Novo Subtotal",
    total: "Novo Total",
    spacer: "",
  }[type]
}

function buildBlocksFromFlat(flat: FlatBlock[]): Block[] {
  const childrenByParent = new Map<string, FlatBlock[]>()
  const roots: FlatBlock[] = []
  for (const fb of flat) {
    if (fb.parent_id == null) {
      roots.push(fb)
    } else {
      const arr = childrenByParent.get(fb.parent_id) ?? []
      arr.push(fb)
      childrenByParent.set(fb.parent_id, arr)
    }
  }
  function build(fb: FlatBlock): Block {
    if (fb.block.type === "section") {
      const children = (childrenByParent.get(fb.block.id) ?? []).map(build)
      return { ...fb.block, children } as SectionBlock
    }
    return fb.block
  }
  return roots.map(build)
}

// Suppress unused-import warnings for the types we import purely for narrowing
// above (TS compile is satisfied by their use in types, but ESLint sometimes
// flags them). They are intentional.
export type { LineBlock }
