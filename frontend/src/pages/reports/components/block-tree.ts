// Flat ↔ tree conversion for the block editor. The canonical document is a
// tree; the UI is easier to build as a flat draggable list with parent refs.
// This module is the only place where the two representations cross.

import type { Block, SectionBlock, TemplateDocument } from "@/features/reports"

export interface FlatBlock {
  _key: string
  parent_id: string | null
  depth: number
  block: Block
}

let _keySeq = 0
function mkKey(): string {
  _keySeq += 1
  return `b-${Date.now().toString(36)}-${_keySeq}`
}

/** Walk a document into a depth-ordered flat list with parent refs. */
export function flattenForEdit(doc: TemplateDocument): FlatBlock[] {
  const out: FlatBlock[] = []

  function walk(blocks: Block[], depth: number, parentId: string | null) {
    for (const b of blocks) {
      out.push({ _key: mkKey(), parent_id: parentId, depth, block: b })
      if (b.type === "section") {
        walk((b as SectionBlock).children ?? [], depth + 1, b.id)
      }
    }
  }
  walk(doc.blocks, 0, null)
  return out
}

/** Rebuild a document's ``blocks`` tree from a flat list. Ordering is preserved. */
export function unflattenForSave(
  flat: FlatBlock[],
  meta: Omit<TemplateDocument, "blocks">,
): TemplateDocument {
  const byId = new Map<string, FlatBlock[]>()
  const rootItems: FlatBlock[] = []
  for (const fb of flat) {
    if (fb.parent_id == null) {
      rootItems.push(fb)
    } else {
      const arr = byId.get(fb.parent_id) ?? []
      arr.push(fb)
      byId.set(fb.parent_id, arr)
    }
  }

  function buildBlock(fb: FlatBlock): Block {
    if (fb.block.type === "section") {
      const children = (byId.get(fb.block.id) ?? []).map(buildBlock)
      return { ...fb.block, children }
    }
    return fb.block
  }

  const blocks = rootItems.map(buildBlock)
  return { ...meta, blocks }
}

/** Generate a unique id within the given list. */
export function uniqueBlockId(list: FlatBlock[], prefix = "block"): string {
  const taken = new Set(list.map((fb) => fb.block.id))
  let i = 1
  while (taken.has(`${prefix}_${i}`)) i += 1
  return `${prefix}_${i}`
}

/** Move a flat block to a new index. Keeps parent_id unchanged (no
 * cross-section moves in PR 4 — that lands with the drawer in PR 9). */
export function reorderFlat(list: FlatBlock[], from: number, to: number): FlatBlock[] {
  const out = list.slice()
  const [item] = out.splice(from, 1)
  out.splice(to, 0, item)
  return out
}
