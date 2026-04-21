import { useMemo } from "react"
import {
  DndContext, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import {
  FileText, Receipt, Equal, Sigma, Minus, Heading, GripVertical, Trash2, Plus, ChevronRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type {
  Block, BlockType, LineBlock, SubtotalBlock, TotalBlock, TemplateDocument,
} from "@/features/reports"
import {
  flattenForEdit, reorderFlat, uniqueBlockId, type FlatBlock,
} from "./block-tree"

/**
 * Minimal flat-list block editor for PR 4. Supports:
 * - drag-reorder (within the flattened list; cross-section moves land in PR 9)
 * - inline label + type edit
 * - a collapsible detail row for calc method, sign, formula, account pattern
 * - add/remove root-level blocks
 *
 * PR 9 will replace this with a proper per-block drawer + block-type styling.
 */
export function BlockEditor({
  document,
  onChange,
}: {
  document: TemplateDocument
  onChange: (next: TemplateDocument) => void
}) {
  const flat = useMemo(() => flattenForEdit(document), [document])

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
    // Removing a section removes its descendants too.
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

      {flat.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-[12px] text-muted-foreground">
          Sem blocos. Adicione um bloco ou gere um modelo com IA (em breve).
        </div>
      ) : (
        <div className="rounded-md border border-border">
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={flat.map((fb) => fb._key)} strategy={verticalListSortingStrategy}>
              {flat.map((fb) => (
                <BlockRow
                  key={fb._key}
                  item={fb}
                  onChange={(patch) => updateBlock(fb._key, patch)}
                  onRemove={() => removeBlock(fb._key)}
                />
              ))}
            </SortableContext>
          </DndContext>
        </div>
      )}
    </div>
  )
}

function BlockRow({
  item, onChange, onRemove,
}: {
  item: FlatBlock
  onChange: (patch: Partial<Block>) => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item._key })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }
  const { block, depth } = item

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border/50 px-2 py-1.5 last:border-b-0 hover:bg-accent/30",
        block.type === "section" && "bg-surface-2/50",
        block.type === "header" && "bg-surface-3/50",
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

      <TypeIcon type={block.type} />

      <div style={{ width: `${depth * 12}px` }} />

      <input
        value={block.type === "spacer" ? "" : ((block as { label?: string | null }).label ?? "")}
        onChange={(e) => onChange({ label: e.target.value } as Partial<Block>)}
        disabled={block.type === "spacer"}
        placeholder={block.type === "spacer" ? "— espaçador —" : "Rótulo"}
        className={cn(
          "h-7 flex-1 min-w-[120px] rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring disabled:bg-muted/50 disabled:text-muted-foreground",
          ((block as { bold?: boolean | null }).bold
            || block.type === "subtotal" || block.type === "total"
            || block.type === "header" || block.type === "section") && "font-semibold",
        )}
      />

      <code className="text-[10px] text-muted-foreground">{block.id}</code>

      {(block.type === "line" || block.type === "subtotal" || block.type === "total") && (
        <InlineDetail block={block as LineBlock | SubtotalBlock | TotalBlock} onChange={onChange} />
      )}

      <button
        onClick={onRemove}
        className="grid h-6 w-6 place-items-center rounded-md text-red-600/70 hover:bg-red-500/10 hover:text-red-600"
        aria-label="Remover"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

function InlineDetail({
  block,
  onChange,
}: {
  block: LineBlock | SubtotalBlock | TotalBlock
  onChange: (patch: Partial<Block>) => void
}) {
  const showFormula = block.type === "subtotal" || block.type === "total"
  const showAccounts = block.type === "line" || block.type === "subtotal"
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {showAccounts && (
        <input
          value={(block as LineBlock).accounts?.code_prefix ?? ""}
          onChange={(e) =>
            onChange({
              accounts: {
                ...(block as LineBlock).accounts,
                code_prefix: e.target.value || null,
                include_descendants: (block as LineBlock).accounts?.include_descendants ?? true,
              },
            } as Partial<Block>)
          }
          placeholder="prefixo (4.01)"
          className="h-6 w-[100px] rounded-md border border-border bg-background px-1.5 font-mono text-[11px] outline-none focus:border-ring"
        />
      )}

      {showFormula && (
        <input
          value={(block as SubtotalBlock | TotalBlock).formula ?? ""}
          onChange={(e) => onChange({ formula: e.target.value || null } as Partial<Block>)}
          placeholder="fórmula (ex. sum(children))"
          className="h-6 w-[160px] rounded-md border border-border bg-background px-1.5 font-mono text-[11px] outline-none focus:border-ring"
        />
      )}
    </div>
  )
}

function TypeIcon({ type }: { type: BlockType }) {
  const cls = "h-3.5 w-3.5 text-muted-foreground"
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
  // Same logic as unflattenForSave but returns only the blocks array.
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
      return { ...fb.block, children }
    }
    return fb.block
  }
  return roots.map(build)
}
