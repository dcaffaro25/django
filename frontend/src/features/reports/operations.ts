// Whitelisted "operations" emitted by the AI chat endpoint. Applied
// client-side so the backend doesn't have to track per-turn state.
//
// Matches ``ALLOWED_OPS`` in accounting/reports/services/ai_assistant.py.

import type { Block, SectionBlock, TemplateDocument } from "./types"
import type { PeriodPreset } from "./periods"

export type ChatOperation =
  | { op: "add_block"; parent_id: string | null; after_id: string | null; block: Block }
  | { op: "update_block"; id: string; patch: Partial<Block> }
  | { op: "remove_block"; id: string }
  | { op: "set_period_preset"; preset: PeriodPreset }

export interface ApplyResult {
  doc: TemplateDocument
  applied: boolean
  reason?: string
}

/** Apply a single operation to a template document; returns the new doc.
 *  Pure — the input is not mutated. If the op can't be applied cleanly
 *  (missing ids, etc.), returns { applied: false, reason }. */
export function applyOperation(doc: TemplateDocument, op: ChatOperation): ApplyResult {
  if (op.op === "set_period_preset") {
    // Periods live on the BuilderPage state, not the doc — the caller is
    // expected to route this op to its period handler separately.
    return { doc, applied: false, reason: "handled by period state, not doc" }
  }

  if (op.op === "add_block") {
    if (doc.blocks.some((b) => containsId(b, op.block.id))) {
      return { doc, applied: false, reason: `id '${op.block.id}' already in use` }
    }
    if (op.parent_id && !findBlock(doc.blocks, op.parent_id)) {
      return { doc, applied: false, reason: `parent_id '${op.parent_id}' not found` }
    }
    if (op.after_id && !findBlock(doc.blocks, op.after_id)) {
      return { doc, applied: false, reason: `after_id '${op.after_id}' not found` }
    }
    return { doc: { ...doc, blocks: insertBlock(doc.blocks, op) }, applied: true }
  }

  if (op.op === "update_block") {
    const found = findBlock(doc.blocks, op.id)
    if (!found) return { doc, applied: false, reason: `id '${op.id}' not found` }
    return {
      doc: { ...doc, blocks: mapBlocks(doc.blocks, op.id, (b) => ({ ...b, ...op.patch } as Block)) },
      applied: true,
    }
  }

  if (op.op === "remove_block") {
    if (!findBlock(doc.blocks, op.id)) {
      return { doc, applied: false, reason: `id '${op.id}' not found` }
    }
    return { doc: { ...doc, blocks: removeBlock(doc.blocks, op.id) }, applied: true }
  }

  return { doc, applied: false, reason: "unknown op" }
}

/** Apply a batch of operations, short-circuiting on the first failure.
 *  The caller decides whether to keep or discard partial progress — we
 *  return both the resulting doc and a per-op report. */
export function applyOperations(
  doc: TemplateDocument,
  ops: ChatOperation[],
): { doc: TemplateDocument; results: Array<{ op: ChatOperation; applied: boolean; reason?: string }> } {
  let cur = doc
  const results: Array<{ op: ChatOperation; applied: boolean; reason?: string }> = []
  for (const op of ops) {
    const { doc: next, applied, reason } = applyOperation(cur, op)
    results.push({ op, applied, reason })
    if (applied) cur = next
  }
  return { doc: cur, results }
}

/** Human-readable preview of an operation, for chat's operation cards. */
export function describeOperation(op: ChatOperation): string {
  switch (op.op) {
    case "add_block": {
      const where = op.parent_id ? `em "${op.parent_id}"` : "no topo"
      const after = op.after_id ? ` após "${op.after_id}"` : ""
      return `Adicionar ${op.block.type} "${op.block.id}"${after} ${where}`
    }
    case "update_block":
      return `Atualizar "${op.id}": ${Object.keys(op.patch).join(", ")}`
    case "remove_block":
      return `Remover "${op.id}"`
    case "set_period_preset":
      return `Aplicar predefinição de períodos: ${op.preset}`
  }
}

// ---- internals ---------------------------------------------------------

function containsId(block: Block, id: string): boolean {
  if (block.id === id) return true
  if (block.type === "section") {
    return (block.children ?? []).some((c) => containsId(c, id))
  }
  return false
}

function findBlock(blocks: Block[], id: string): Block | null {
  for (const b of blocks) {
    if (b.id === id) return b
    if (b.type === "section") {
      const hit = findBlock(b.children ?? [], id)
      if (hit) return hit
    }
  }
  return null
}

function mapBlocks(blocks: Block[], id: string, f: (b: Block) => Block): Block[] {
  return blocks.map((b) => {
    if (b.id === id) return f(b)
    if (b.type === "section") {
      return { ...b, children: mapBlocks(b.children ?? [], id, f) } as SectionBlock
    }
    return b
  })
}

function removeBlock(blocks: Block[], id: string): Block[] {
  const out: Block[] = []
  for (const b of blocks) {
    if (b.id === id) continue
    if (b.type === "section") {
      out.push({ ...b, children: removeBlock(b.children ?? [], id) } as SectionBlock)
    } else {
      out.push(b)
    }
  }
  return out
}

function insertBlock(
  blocks: Block[],
  op: Extract<ChatOperation, { op: "add_block" }>,
): Block[] {
  // Root-level insert
  if (op.parent_id == null) {
    const idx = op.after_id ? blocks.findIndex((b) => b.id === op.after_id) : -1
    if (idx < 0) {
      // Append when after_id missing / not at root
      return [...blocks, op.block]
    }
    return [...blocks.slice(0, idx + 1), op.block, ...blocks.slice(idx + 1)]
  }
  // Nested insert into a section
  return blocks.map((b) => {
    if (b.type === "section" && b.id === op.parent_id) {
      const kids = b.children ?? []
      const idx = op.after_id ? kids.findIndex((c) => c.id === op.after_id) : -1
      const inserted =
        idx < 0
          ? [...kids, op.block]
          : [...kids.slice(0, idx + 1), op.block, ...kids.slice(idx + 1)]
      return { ...b, children: inserted } as SectionBlock
    }
    if (b.type === "section") {
      return { ...b, children: insertBlock(b.children ?? [], op) } as SectionBlock
    }
    return b
  })
}
