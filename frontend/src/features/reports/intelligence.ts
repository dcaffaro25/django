// Client-side coded intelligence — mirrors the Python
// accounting.reports.services.intelligence helpers so the UI can
// validate formulas, detect bad refs, and surface block-id inventory
// without a round-trip to the backend.
//
// Limited, deliberate subset of JavaScript: identifiers, numeric
// literals, unary +/-, binary +/-/*//, parentheses, and whitelisted
// calls sum/abs/min/max (with the special 'children' identifier).
// Rejects anything else at parse time.

import type { Block, TemplateDocument } from "./types"

// ---------- Tokenizer ----------

type TokKind = "num" | "id" | "op" | "lparen" | "rparen" | "comma"
interface Tok {
  kind: TokKind
  value: string
  start: number
  end: number
}

const ID_START = /[A-Za-z_]/
const ID_CONT = /[A-Za-z0-9_]/
const DIGIT = /[0-9]/

function tokenize(input: string): Tok[] {
  const out: Tok[] = []
  let i = 0
  while (i < input.length) {
    const c = input[i]
    if (c === " " || c === "\t" || c === "\n" || c === "\r") {
      i += 1
      continue
    }
    if (c === "(") {
      out.push({ kind: "lparen", value: "(", start: i, end: i + 1 })
      i += 1
      continue
    }
    if (c === ")") {
      out.push({ kind: "rparen", value: ")", start: i, end: i + 1 })
      i += 1
      continue
    }
    if (c === ",") {
      out.push({ kind: "comma", value: ",", start: i, end: i + 1 })
      i += 1
      continue
    }
    if ("+-*/".includes(c)) {
      out.push({ kind: "op", value: c, start: i, end: i + 1 })
      i += 1
      continue
    }
    if (DIGIT.test(c) || (c === "." && DIGIT.test(input[i + 1] ?? ""))) {
      const start = i
      while (i < input.length && (DIGIT.test(input[i]) || input[i] === ".")) i += 1
      out.push({ kind: "num", value: input.slice(start, i), start, end: i })
      continue
    }
    if (ID_START.test(c)) {
      const start = i
      while (i < input.length && ID_CONT.test(input[i])) i += 1
      out.push({ kind: "id", value: input.slice(start, i), start, end: i })
      continue
    }
    throw new FormulaParseError(`caractere inválido '${c}' na posição ${i}`, i, i + 1)
  }
  return out
}

// ---------- AST ----------

export type FormulaNode =
  | { type: "num"; value: number }
  | { type: "id"; name: string; pos: { start: number; end: number } }
  | { type: "unary"; op: "+" | "-"; arg: FormulaNode }
  | { type: "binary"; op: "+" | "-" | "*" | "/"; left: FormulaNode; right: FormulaNode }
  | { type: "call"; name: "sum" | "abs" | "min" | "max"; args: FormulaNode[] }

export class FormulaParseError extends Error {
  start: number
  end: number
  constructor(message: string, start: number, end: number) {
    super(message)
    this.start = start
    this.end = end
  }
}

const ALLOWED_FUNCS = new Set(["sum", "abs", "min", "max"])

// Recursive-descent parser with standard precedence:
// expr    = term ( ('+' | '-') term )*
// term    = factor ( ('*' | '/') factor )*
// factor  = unary
// unary   = ('+' | '-') unary | atom
// atom    = num | call | id | '(' expr ')'
// call    = id '(' ( expr ( ',' expr )* )? ')'

function parse(input: string): FormulaNode {
  const toks = tokenize(input)
  let pos = 0
  const peek = () => toks[pos]
  const consume = () => toks[pos++]
  const expect = (kind: TokKind, value?: string) => {
    const t = peek()
    if (!t || t.kind !== kind || (value !== undefined && t.value !== value)) {
      const start = t?.start ?? input.length
      const end = t?.end ?? input.length
      throw new FormulaParseError(
        `esperado '${value ?? kind}' mas encontrado '${t?.value ?? "fim"}'`,
        start,
        end,
      )
    }
    return consume()
  }

  function parseExpr(): FormulaNode {
    let left = parseTerm()
    while (peek()?.kind === "op" && (peek()!.value === "+" || peek()!.value === "-")) {
      const op = consume().value as "+" | "-"
      const right = parseTerm()
      left = { type: "binary", op, left, right }
    }
    return left
  }
  function parseTerm(): FormulaNode {
    let left = parseUnary()
    while (peek()?.kind === "op" && (peek()!.value === "*" || peek()!.value === "/")) {
      const op = consume().value as "*" | "/"
      const right = parseUnary()
      left = { type: "binary", op, left, right }
    }
    return left
  }
  function parseUnary(): FormulaNode {
    const t = peek()
    if (t?.kind === "op" && (t.value === "+" || t.value === "-")) {
      consume()
      return { type: "unary", op: t.value as "+" | "-", arg: parseUnary() }
    }
    return parseAtom()
  }
  function parseAtom(): FormulaNode {
    const t = peek()
    if (!t) {
      throw new FormulaParseError("expressão vazia", input.length, input.length)
    }
    if (t.kind === "num") {
      consume()
      return { type: "num", value: Number(t.value) }
    }
    if (t.kind === "lparen") {
      consume()
      const e = parseExpr()
      expect("rparen")
      return e
    }
    if (t.kind === "id") {
      consume()
      const next = peek()
      if (next?.kind === "lparen") {
        if (!ALLOWED_FUNCS.has(t.value)) {
          throw new FormulaParseError(
            `função '${t.value}' não permitida (use sum/abs/min/max)`,
            t.start,
            t.end,
          )
        }
        consume()
        const args: FormulaNode[] = []
        if (peek()?.kind !== "rparen") {
          args.push(parseExpr())
          while (peek()?.kind === "comma") {
            consume()
            args.push(parseExpr())
          }
        }
        expect("rparen")
        return {
          type: "call",
          name: t.value as "sum" | "abs" | "min" | "max",
          args,
        }
      }
      // Bare identifier — a block-id reference (or the special 'children').
      return { type: "id", name: t.value, pos: { start: t.start, end: t.end } }
    }
    throw new FormulaParseError(`token inesperado '${t.value}'`, t.start, t.end)
  }

  const ast = parseExpr()
  if (pos < toks.length) {
    const t = toks[pos]
    throw new FormulaParseError(
      `token extra após expressão: '${t.value}'`,
      t.start,
      t.end,
    )
  }
  return ast
}

// ---------- Public helpers ----------

export interface FormulaCheckResult {
  ok: boolean
  error?: { message: string; start: number; end: number }
  refs: string[]
  unresolvedRefs: string[]
  tokens: Tok[]
}

/** Parse a formula and report everything the UI needs to render it: token
 *  spans (for highlighting), referenced block ids, which refs are unresolved
 *  against the provided valid-id set, and parse errors. */
export function checkFormula(
  expr: string,
  validIds: Set<string>,
): FormulaCheckResult {
  const tokens: Tok[] = (() => {
    try {
      return tokenize(expr)
    } catch {
      return []
    }
  })()

  if (!expr.trim()) {
    return { ok: true, refs: [], unresolvedRefs: [], tokens }
  }

  let ast: FormulaNode
  try {
    ast = parse(expr)
  } catch (e) {
    if (e instanceof FormulaParseError) {
      return {
        ok: false,
        error: { message: e.message, start: e.start, end: e.end },
        refs: [],
        unresolvedRefs: [],
        tokens,
      }
    }
    throw e
  }

  const refs = new Set<string>()
  function walk(n: FormulaNode) {
    if (n.type === "id" && n.name !== "children") refs.add(n.name)
    else if (n.type === "unary") walk(n.arg)
    else if (n.type === "binary") {
      walk(n.left)
      walk(n.right)
    } else if (n.type === "call") n.args.forEach(walk)
  }
  walk(ast)

  const unresolved = [...refs].filter((r) => !validIds.has(r))
  return {
    ok: unresolved.length === 0,
    refs: [...refs],
    unresolvedRefs: unresolved,
    tokens,
    error:
      unresolved.length > 0
        ? {
            message: `referência(s) não encontrada(s): ${unresolved.join(", ")}`,
            start: 0,
            end: expr.length,
          }
        : undefined,
  }
}

/** Walk the document and collect every non-spacer block id. */
export function collectBlockIds(doc: TemplateDocument): Set<string> {
  const ids = new Set<string>()
  function walk(blocks: Block[]) {
    for (const b of blocks) {
      ids.add(b.id)
      if (b.type === "section") walk(b.children)
    }
  }
  walk(doc.blocks)
  return ids
}

/** Detect a circular dependency among block-formula references. Returns the
 *  cycle as a list of ids if any, else null. */
export function detectFormulaCycle(doc: TemplateDocument): string[] | null {
  const deps = new Map<string, Set<string>>()
  const ids = collectBlockIds(doc)

  function record(blocks: Block[]) {
    for (const b of blocks) {
      if (b.type === "section") {
        record(b.children)
        continue
      }
      const formula =
        b.type === "subtotal" || b.type === "total" ? b.formula : null
      if (!formula) continue
      const res = checkFormula(formula, ids)
      if (res.refs.length) {
        deps.set(b.id, new Set(res.refs))
      }
    }
  }
  record(doc.blocks)

  const WHITE = 0
  const GRAY = 1
  const BLACK = 2
  const state = new Map<string, number>()
  const parent = new Map<string, string | null>()

  function dfs(node: string): string[] | null {
    state.set(node, GRAY)
    const children = deps.get(node) ?? new Set()
    for (const child of children) {
      const s = state.get(child) ?? WHITE
      if (s === GRAY) {
        const cycle: string[] = [child]
        let cur: string | null | undefined = node
        while (cur && cur !== child) {
          cycle.push(cur)
          cur = parent.get(cur)
        }
        cycle.push(child)
        return cycle.reverse()
      }
      if (s === WHITE) {
        parent.set(child, node)
        const c = dfs(child)
        if (c) return c
      }
    }
    state.set(node, BLACK)
    return null
  }

  for (const node of deps.keys()) {
    if ((state.get(node) ?? WHITE) === WHITE) {
      parent.set(node, null)
      const c = dfs(node)
      if (c) return c
    }
  }
  return null
}

/** Account-code pattern (e.g. "4.01") → predicate. Used by the account
 *  tree picker to show a live preview of how many accounts would match. */
export function matchesPrefix(code: string | null | undefined, prefix: string): boolean {
  if (!prefix) return false
  if (!code) return false
  return code.startsWith(prefix)
}
