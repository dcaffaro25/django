import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import {
  Sparkles,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  PlayCircle,
  TrendingUp,
  Hash,
  Search,
  ArrowDownUp,
  Filter as FilterIcon,
  Banknote,
  BookOpen,
  CalendarDays,
  Calculator,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import {
  useBankTransactions,
  useCreateSuggestions,
  useFinalizeMatches,
  useHydratedTaskSuggestions,
  useSuggestMatches,
} from "@/features/reconciliation"
import type {
  BankTransaction,
  JournalEntry,
  SuggestMatchResponse,
  SuggestionItem,
  TaskSuggestionBankDetail,
  TaskSuggestionBookDetail,
  TaskSuggestionPayload,
} from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

function isoDaysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

/**
 * Map a fetched BankTransaction row to the detail shape the renderer uses.
 * Used when the persisted suggestion only kept `bank_ids` (most engines do).
 */
function bankRowToDetail(bt: BankTransaction): TaskSuggestionBankDetail {
  return {
    id: bt.id,
    date: bt.date ?? null,
    amount: bt.amount != null ? Number(bt.amount) : null,
    description: bt.description ?? null,
    bank_account: null, // name not in list serializer — fine, optional
    entity: bt.entity ?? null,
    currency: bt.currency ?? null,
  }
}

/** Pick the first non-zero value across the candidate columns. Falls back
 *  to the first non-null value if all are zero, and finally to null. Journal
 *  entries sometimes have `transaction_value` set but `balance` zero, or vice
 *  versa (the "other leg" of a double-entry row), so we look at both. */
function pickAmount(...vals: Array<number | string | null | undefined>): number | null {
  let firstDefined: number | null = null
  for (const v of vals) {
    if (v == null || v === "") continue
    const n = Number(v)
    if (!Number.isFinite(n)) continue
    if (firstDefined == null) firstDefined = n
    if (n !== 0) return n
  }
  return firstDefined
}

/** Map a fetched JournalEntry row to the detail shape the renderer uses. */
function journalRowToDetail(je: JournalEntry): TaskSuggestionBookDetail {
  // Journal `description` is often the short accounting label (or blank);
  // `transaction_description` is the parent narrative that actually matches
  // bank descriptions, so prefer it for the detail title and summary text.
  const primaryDesc = je.transaction_description || je.description || null
  return {
    id: je.id,
    date: je.bank_date ?? je.transaction_date ?? null,
    amount: pickAmount(je.transaction_value, je.balance),
    description: primaryDesc,
    account: null, // list serializer doesn't inline account_code/name
    transaction: {
      id: je.transaction_id,
      description: je.transaction_description ?? je.description ?? "",
      date: je.transaction_date ?? null,
    },
  }
}

// Matches the "BANK#<id>" / "BOOK#<id>" prefix emitted by the newer engine
// in the first pipe-separated column. Whitespace-tolerant.
const LINE_ID_RE = /^(?:BANK|BOOK)#\s*(\d+)$/i

/** Parse one `bank_lines` / `book_lines` row. The shape is pipe-delimited
 *  with at least `PREFIX#<id> | <date> | <amount>` up front; everything
 *  after those three columns is treated as a free-form description that we
 *  join with " · " for display. Returns `null` if the prefix can't be
 *  understood. */
function parseSummaryLine(
  line: string,
): { id: number; date: string | null; amount: number | null; description: string } | null {
  const parts = line.split("|").map((s) => s.trim())
  if (parts.length < 3) return null
  const idMatch = LINE_ID_RE.exec(parts[0] ?? "")
  if (!idMatch) return null
  const id = Number(idMatch[1])
  const date = parts[1] && /^\d{4}-\d{2}-\d{2}/.test(parts[1]) ? parts[1] : null
  const rawAmt = parts[2]?.replace(/\s/g, "")
  const amount = rawAmt != null && rawAmt !== "" && !Number.isNaN(Number(rawAmt))
    ? Number(rawAmt)
    : null
  const description = parts
    .slice(3)
    .filter(Boolean)
    .join(" · ")
    .trim()
  return { id, date, amount, description }
}

/** Parse a whole `bank_lines` / `book_lines` blob into a { id → fields } map.
 *  Each blob may carry one line per matched row (M:N). Gracefully ignores
 *  unparseable lines. */
function parseSummaryBlob(
  blob: string | null | undefined,
): Map<number, { date: string | null; amount: number | null; description: string }> {
  const out = new Map<number, { date: string | null; amount: number | null; description: string }>()
  if (!blob) return out
  for (const raw of blob.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const parsed = parseSummaryLine(line)
    if (parsed) out.set(parsed.id, parsed)
  }
  return out
}

/**
 * Normalize + hydrate a raw payload. Guarantees array fields, then fills in
 * `bank_transaction_details` / `journal_entry_details` from every source the
 * backend might use:
 *   1. Already-inlined detail objects (service1 legacy path).
 *   2. Fresh rows fetched via `?id__in=...` (any engine).
 *   3. Pipe-delimited `bank_lines` / `book_lines` (newer fuzzy engine) —
 *      critical when the referenced row has since been deleted so hydration
 *      returns nothing.
 * Also backfills aggregates (`sum_bank/sum_book/difference/N bank/N book/
 * avg_date_diff`) from `bank_stats/book_stats/abs_amount_diff/extra.*` when
 * the legacy keys aren't present.
 */
function normalizePayload(
  p: TaskSuggestionPayload,
  bankById: Map<number, BankTransaction>,
  journalById: Map<number, JournalEntry>,
): TaskSuggestionPayload {
  const bankIds = Array.isArray(p.bank_ids) ? p.bank_ids : []
  const journalIds = Array.isArray(p.journal_entries_ids) ? p.journal_entries_ids : []

  // Start from whatever the engine already emitted; index so we don't
  // duplicate ids we later hydrate.
  const existingBank = Array.isArray(p.bank_transaction_details)
    ? p.bank_transaction_details
    : []
  const existingBook = Array.isArray(p.journal_entry_details)
    ? p.journal_entry_details
    : []
  const bankSeen = new Set(existingBank.map((d) => d.id))
  const bookSeen = new Set(existingBook.map((d) => d.id))

  // Pre-parse the pipe-delimited summary blobs from the newer engine. We
  // keep the raw map around so we can also merge descriptions into rows we
  // hydrate from the API (e.g. to get the chart-of-accounts label that the
  // /journal_entries/ list serializer doesn't return).
  const bankLineMap = parseSummaryBlob(p.bank_lines)
  const bookLineMap = parseSummaryBlob(p.book_lines)

  const bankDetails: TaskSuggestionBankDetail[] = [...existingBank]
  for (const id of bankIds) {
    if (bankSeen.has(id)) continue
    const row = bankById.get(id)
    if (row) {
      const detail = bankRowToDetail(row)
      // Line blob often has richer, pre-concatenated text — keep it as a
      // fallback if the fetched row has no description.
      if (!detail.description && bankLineMap.get(id)?.description) {
        detail.description = bankLineMap.get(id)!.description
      }
      bankDetails.push(detail)
      bankSeen.add(id)
      continue
    }
    // No fetched row — fall back to the parsed summary line.
    const parsed = bankLineMap.get(id)
    if (parsed) {
      bankDetails.push({
        id,
        date: parsed.date,
        amount: parsed.amount,
        description: parsed.description || null,
      })
      bankSeen.add(id)
    }
  }

  const bookDetails: TaskSuggestionBookDetail[] = [...existingBook]
  for (const id of journalIds) {
    if (bookSeen.has(id)) continue
    const row = journalById.get(id)
    if (row) {
      const detail = journalRowToDetail(row)
      // The book_lines string from the fuzzy engine typically carries extra
      // columns (chart-of-accounts name, branch, bank, CNPJ) that the list
      // serializer omits. Append them into the description so highlighting
      // / search / display pick them up.
      const parsed = bookLineMap.get(id)
      if (parsed?.description) {
        const existing = (detail.description ?? "").trim()
        if (!existing) {
          detail.description = parsed.description
        } else if (
          !parsed.description.toLowerCase().includes(existing.toLowerCase())
        ) {
          detail.description = `${existing} · ${parsed.description}`
        }
      }
      bookDetails.push(detail)
      bookSeen.add(id)
      continue
    }
    // No fetched row (common when a JE has been deleted post-run) — fall
    // back to the parsed line so the card still renders something useful.
    const parsed = bookLineMap.get(id)
    if (parsed) {
      bookDetails.push({
        id,
        date: parsed.date,
        amount: parsed.amount,
        description: parsed.description || null,
        transaction: { id: 0, description: parsed.description || "", date: parsed.date },
      })
      bookSeen.add(id)
    }
  }

  // --- Aggregate backfill ----------------------------------------------------
  // Read from legacy keys first, then new-shape stats blocks, then derive
  // from the hydrated detail lists as a last resort.
  const bankStatsSum = p.bank_stats?.sum_amount
  const bookStatsSum = p.book_stats?.sum_amount
  const sumBank =
    p.sum_bank != null
      ? Number(p.sum_bank)
      : bankStatsSum != null
        ? Number(bankStatsSum)
        : bankDetails.reduce((acc, d) => acc + Number(d.amount ?? 0), 0)
  const sumBook =
    p.sum_book != null
      ? Number(p.sum_book)
      : bookStatsSum != null
        ? Number(bookStatsSum)
        : bookDetails.reduce((acc, d) => acc + Number(d.amount ?? 0), 0)
  const difference =
    p.difference != null
      ? Number(p.difference)
      : p.abs_amount_diff != null
        ? Number(p.abs_amount_diff)
        : Math.abs(sumBank - sumBook)
  const nBank =
    p["N bank"] ?? p.bank_stats?.count ?? bankDetails.length ?? bankIds.length
  const nBook =
    p["N book"] ?? p.book_stats?.count ?? bookDetails.length ?? journalIds.length
  const avgDateDiff =
    p.avg_date_diff != null
      ? Number(p.avg_date_diff)
      : p.extra?.avg_date_delta_days_measured != null
        ? Number(p.extra.avg_date_delta_days_measured)
        : undefined

  // Keep the pre-concatenated summary strings so the "raw summary" <details>
  // block still has something to show on minimal payloads.
  const bankSummary = p.bank_transaction_summary ?? p.bank_lines ?? undefined
  const bookSummary = p.journal_entries_summary ?? p.book_lines ?? undefined

  return {
    ...p,
    bank_ids: bankIds,
    journal_entries_ids: journalIds,
    bank_transaction_details: bankDetails,
    journal_entry_details: bookDetails,
    bank_transaction_summary: bankSummary,
    journal_entries_summary: bookSummary,
    sum_bank: sumBank,
    sum_book: sumBook,
    difference,
    "N bank": nBank,
    "N book": nBook,
    ...(avgDateDiff != null ? { avg_date_diff: avgDateDiff } : {}),
  }
}

// ---------------------------------------------------------------------------
// Shared-word highlighting: tokens that appear on BOTH bank and book sides
// get marked so the user can eyeball why the engine matched them.
// ---------------------------------------------------------------------------

const HIGHLIGHT_STOPWORDS = new Set([
  "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "para", "com", "por",
  "em", "no", "na", "nos", "nas", "um", "uma", "uns", "umas", "ao", "aos", "que",
  "ref", "nf", "nfe", "ltda", "sa", "me", "eireli", "boleto", "pgto", "pagto",
  "pagamento", "recebimento", "transferencia", "transf", "tef", "ted", "doc",
  "pix", "via", "cod", "codigo", "ident", "cli", "cnpj", "cpf",
  "the", "and", "or", "of", "to", "for", "from",
])

/** Normalize a string to its alnum/diacritic-free lowercase form. */
function foldText(s: string): string {
  return s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
}

/** Tokenize a description for shared-word matching. Drops short / stop tokens. */
function tokenize(s: string | null | undefined): Set<string> {
  if (!s) return new Set()
  const out = new Set<string>()
  for (const raw of foldText(s).split(/[^a-z0-9]+/)) {
    if (raw.length < 3) continue
    if (HIGHLIGHT_STOPWORDS.has(raw)) continue
    // Drop pure numbers unless they look like identifiers (>=4 digits)
    if (/^\d+$/.test(raw) && raw.length < 4) continue
    out.add(raw)
  }
  // Also extract "digit runs ignoring punctuation" so that formatted
  // CPF/CNPJ/boleto/NFe numbers match their unformatted counterpart.
  //   "12.345.678/0001-90"   → 12345678000190
  //   "123.456.789-00"       → 12345678900
  // We split on whitespace first so we don't merge two separate numbers
  // from the same string, then strip non-digits from each chunk.
  for (const chunk of foldText(s).split(/\s+/)) {
    const digits = chunk.replace(/\D+/g, "")
    if (digits.length >= 4) out.add(digits)
  }
  return out
}

/** Intersect tokens of two text-sets, returning the shared vocabulary. */
function sharedVocab(bankTexts: string[], bookTexts: string[]): Set<string> {
  const bank = new Set<string>()
  for (const s of bankTexts) for (const t of tokenize(s)) bank.add(t)
  const shared = new Set<string>()
  for (const s of bookTexts) {
    for (const t of tokenize(s)) {
      if (bank.has(t)) shared.add(t)
    }
  }
  return shared
}

/** Render a string, wrapping tokens whose folded form is in `shared` with <mark>. */
function Highlighted({
  text,
  shared,
  className,
}: {
  text?: string | null
  shared: Set<string>
  className?: string
}) {
  const content: ReactNode = useMemo(() => {
    if (!text) return "—"
    if (shared.size === 0) return text
    // Split on word boundaries while keeping delimiters, but treat runs of
    // digits separated by `.`, `-`, `/` as a single token so that formatted
    // CPF/CNPJ/NFe/boleto numbers match their unformatted counterpart on the
    // other side. Order matters: the numeric-id alternative is tried first
    // so it wins over the plain-word alternative for bare digit groups.
    const parts = text.split(
      /(\d[\d./-]*\d|[A-Za-z\u00C0-\u024F\u1E00-\u1EFF0-9]+)/,
    )

    type Kind = "delim" | "word" | "match"
    const segs: Array<{ part: string; kind: Kind }> = []
    for (const part of parts) {
      if (!part) continue
      const isWord = /[A-Za-z\u00C0-\u024F0-9]/.test(part)
      if (!isWord) {
        segs.push({ part, kind: "delim" })
        continue
      }
      const folded = foldText(part)
      const digits = folded.replace(/\D+/g, "")
      const isMatch =
        shared.has(folded) ||
        (digits.length >= 4 && shared.has(digits))
      segs.push({ part, kind: isMatch ? "match" : "word" })
    }

    // A word is "bridgeable" — i.e. can be absorbed into a highlighted phrase
    // without being in the shared vocab — if it's either too short to tokenize
    // (e.g. "SB") or a known connector/suffix ("e", "de", "ltda").
    const isBridgeable = (s: string) => {
      const f = foldText(s)
      return f.length < 3 || HIGHLIGHT_STOPWORDS.has(f)
    }
    const isWhitespaceDelim = (s: string) => /^\s*$/.test(s)

    // --- Internal bridging ---------------------------------------------------
    // If two matches are separated only by whitespace + bridgeable words,
    // promote the gap words to `match` so the phrase renders as one span.
    //   "LOGISTICA E COMERCIO DE EMBALAGENS" → E, DE absorbed
    let prevMatch = -1
    for (let i = 0; i < segs.length; i++) {
      if (segs[i].kind !== "match") continue
      if (prevMatch !== -1) {
        let gapOK = true
        for (let k = prevMatch + 1; k < i; k++) {
          const s = segs[k]
          if (s.kind === "delim" && !isWhitespaceDelim(s.part)) { gapOK = false; break }
          if (s.kind === "word" && !isBridgeable(s.part)) { gapOK = false; break }
        }
        if (gapOK) {
          for (let k = prevMatch + 1; k < i; k++) {
            if (segs[k].kind === "word") segs[k].kind = "match"
          }
        }
      }
      prevMatch = i
    }

    // --- Edge expansion ------------------------------------------------------
    // At each run boundary, absorb at most one bridgeable word outward (through
    // whitespace only). Lets "SB LOGISTICA ... LTDA" render as a single span
    // without running away into unrelated surrounding prose.
    const runs: Array<[number, number]> = []
    for (let i = 0; i < segs.length; ) {
      if (segs[i].kind !== "match") { i++; continue }
      const start = i
      let end = i
      let j = i + 1
      while (j < segs.length) {
        const s = segs[j]
        if (s.kind === "match") { end = j; j++; continue }
        if (s.kind === "delim" && isWhitespaceDelim(s.part)) { j++; continue }
        break
      }
      runs.push([start, end])
      i = end + 1
    }
    for (const [start, end] of runs) {
      // backward: skip whitespace, try to promote one bridgeable word
      for (let j = start - 1; j >= 0; j--) {
        const s = segs[j]
        if (s.kind === "delim") {
          if (!isWhitespaceDelim(s.part)) break
          continue
        }
        if (s.kind === "word" && isBridgeable(s.part)) segs[j].kind = "match"
        break
      }
      // forward: mirror
      for (let k = end + 1; k < segs.length; k++) {
        const s = segs[k]
        if (s.kind === "delim") {
          if (!isWhitespaceDelim(s.part)) break
          continue
        }
        if (s.kind === "word" && isBridgeable(s.part)) segs[k].kind = "match"
        break
      }
    }

    // --- Render: coalesce consecutive matches (through whitespace) into one
    // <mark> so the underline is continuous across the whole phrase.
    const nodes: ReactNode[] = []
    for (let p = 0; p < segs.length; ) {
      if (segs[p].kind !== "match") {
        nodes.push(<Fragment key={p}>{segs[p].part}</Fragment>)
        p++
        continue
      }
      let runEnd = p
      let q = p + 1
      while (q < segs.length) {
        const s = segs[q]
        if (s.kind === "match") { runEnd = q; q++; continue }
        if (s.kind === "delim" && isWhitespaceDelim(s.part)) { q++; continue }
        break
      }
      const merged = segs.slice(p, runEnd + 1).map((s) => s.part).join("")
      nodes.push(
        <mark key={p} className="shared-token">
          {merged}
        </mark>,
      )
      p = runEnd + 1
    }
    return nodes
  }, [text, shared])
  return <span className={className}>{content}</span>
}

// ---------------------------------------------------------------------------

/** Parse an ISO-ish date string to a Date, or null. */
function parseDate(s?: string | null): Date | null {
  if (!s) return null
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Day difference (absolute) between two dates, or null if either missing. */
function dayDiff(a?: string | null, b?: string | null): number | null {
  const da = parseDate(a)
  const db = parseDate(b)
  if (!da || !db) return null
  return Math.round(Math.abs(da.getTime() - db.getTime()) / 86_400_000)
}

/** Min/max ISO date from a list, in "yyyy-mm-dd" order. */
function dateRange(dates: Array<string | null | undefined>): { min: string | null; max: string | null } {
  let min: string | null = null
  let max: string | null = null
  for (const d of dates) {
    if (!d) continue
    if (min == null || d < min) min = d
    if (max == null || d > max) max = d
  }
  return { min, max }
}

/** Stable key for a task-mode suggestion across renders / accept maps. */
function payloadKey(p: TaskSuggestionPayload, index: number): string {
  if (p.suggestion_id != null) return `sid:${p.suggestion_id}`
  const b = Array.isArray(p.bank_ids) ? p.bank_ids : []
  const j = Array.isArray(p.journal_entries_ids) ? p.journal_entries_ids : []
  return `k:${[...b].sort().join(",")}|${[...j].sort().join(",")}|${index}`
}

export function SuggestionsPage() {
  const [searchParams] = useSearchParams()
  const taskIdParam = searchParams.get("task_id")
  const taskId = taskIdParam && /^\d+$/.test(taskIdParam) ? Number(taskIdParam) : null

  // Two fundamentally different data shapes / workflows. Keep them in
  // separate components so state doesn't leak and both stay readable.
  if (taskId != null) return <TaskSuggestionsView taskId={taskId} />
  return <ManualSuggestionsView />
}

// ---------------------------------------------------------------------------
// TASK MODE — renders the raw M:M payloads persisted for a past execution.
// ---------------------------------------------------------------------------

type SortKey =
  | "confidence_desc"
  | "confidence_asc"
  | "difference_asc"
  | "date_asc"
  | "size_desc"
  | "bank_desc"
  | "bank_asc"
  | "book_desc"
  | "book_asc"

/** Sum the absolute bank-side amount of a suggestion. Falls back to the
 *  pre-computed ``bank_sum_value`` when the engine ships it; otherwise
 *  walks ``bank_transaction_details``. Same shape on the book side via
 *  ``bookSumAbs``. */
function bankSumAbs(p: TaskSuggestionPayload): number {
  const pre = (p as any).bank_sum_value
  if (pre != null && Number.isFinite(Number(pre))) return Math.abs(Number(pre))
  let s = 0
  for (const d of p.bank_transaction_details ?? []) {
    const v = Number(d?.amount ?? 0)
    if (Number.isFinite(v)) s += v
  }
  return Math.abs(s)
}
function bookSumAbs(p: TaskSuggestionPayload): number {
  const pre = (p as any).book_sum_value
  if (pre != null && Number.isFinite(Number(pre))) return Math.abs(Number(pre))
  let s = 0
  for (const d of p.journal_entry_details ?? []) {
    const v = Number(d?.amount ?? 0)
    if (Number.isFinite(v)) s += v
  }
  return Math.abs(s)
}

export function TaskSuggestionsView({
  taskId,
  embedded,
  onExit,
}: {
  taskId: number
  /** Hide the SectionHeader + redirect the "Sair" button to ``onExit`` so
   *  the view can be hosted inside the Execuções split layout instead of
   *  rendering as a standalone page. */
  embedded?: boolean
  /** Invoked when the user clicks "Sair da execução". Required when
   *  ``embedded`` so the host page can drop the selected execution. */
  onExit?: () => void
}) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Backend filters (server-applied).
  const [limit] = useState(2000)

  const { suggestions: taskSuggestions, bankRows, journalRows } =
    useHydratedTaskSuggestions(taskId, { min_confidence: 0, limit })
  const finalize = useFinalizeMatches()

  // Lookup maps built from the hydration fetches. Rebuilt only when the
  // fetched rows change, so normalize/memoize stays cheap.
  const bankById = useMemo(() => {
    const m = new Map<number, BankTransaction>()
    for (const r of bankRows.data ?? []) m.set(r.id, r)
    return m
  }, [bankRows.data])
  const journalById = useMemo(() => {
    const m = new Map<number, JournalEntry>()
    for (const r of journalRows.data ?? []) m.set(r.id, r)
    return m
  }, [journalRows.data])

  // Client filters. Score thresholds are expressed in PERCENT (0–100) and
  // act as a `>=` floor; a value of 0 means "no filter".
  const [search, setSearch] = useState("")
  const [minConfPct, setMinConfPct] = useState(0)
  // Upper-bound Δ filters default to null ("no limit"); the user can type a
  // number (including 0 for strict) to apply, and the × button on the field
  // clears it back to null.
  const [maxDiff, setMaxDiff] = useState<number | null>(null)
  const [matchTypes, setMatchTypes] = useState<Set<string>>(new Set())
  const [sort, setSort] = useState<SortKey>("confidence_desc")
  const [autoAcceptThreshold, setAutoAcceptThreshold] = useState(0.9)
  // Component-score minimums (percent). Payloads that don't carry a given
  // component at all are NOT filtered out so legacy engines still render.
  const [minDateScorePct, setMinDateScorePct] = useState(0)
  const [minDescScorePct, setMinDescScorePct] = useState(0)
  const [minAmountScorePct, setMinAmountScorePct] = useState(0)
  // Absolute avg date delta, in days.
  const [maxDateDiffDays, setMaxDateDiffDays] = useState<number | null>(null)

  const [accepted, setAccepted] = useState<Set<string>>(new Set())

  // Collapsing the execution panel (banner + filters + stats + bulk-accept
  // bar) lets the operator focus on the suggestion cards. Persisted via
  // ``localStorage`` so the choice survives a page reload — the panel is
  // mostly informational once the operator has dialed in their filters and
  // is just clicking through accepts. Default = expanded.
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem("recon.suggestions.panelCollapsed") === "1"
    } catch {
      return false
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(
        "recon.suggestions.panelCollapsed",
        panelCollapsed ? "1" : "0",
      )
    } catch {
      // Storage may be disabled (private mode); silently ignore.
    }
  }, [panelCollapsed])

  const payloads = useMemo<TaskSuggestionPayload[]>(
    () =>
      (taskSuggestions.data?.suggestions ?? []).map((p) =>
        normalizePayload(p, bankById, journalById),
      ),
    [taskSuggestions.data, bankById, journalById],
  )

  // Distinct match_type values for the filter toolbar.
  const availableMatchTypes = useMemo(() => {
    const s = new Set<string>()
    for (const p of payloads) if (p.match_type) s.add(p.match_type)
    return Array.from(s).sort()
  }, [payloads])

  // Which optional telemetry fields show up at least once across the loaded
  // payloads — used to hide filters that would be uniformly inert for this
  // engine/run. Computing once per `payloads` change keeps it O(N).
  const available = useMemo(() => {
    let dateScore = false
    let descScore = false
    let amountScore = false
    let embedSim = false
    let dateDiff = false
    for (const p of payloads) {
      const cs = p.component_scores ?? {}
      if (cs.date_score != null) dateScore = true
      if (cs.description_score != null) descScore = true
      if (cs.amount_score != null) amountScore = true
      if (p.extra?.embed_similarity != null) embedSim = true
      if (p.avg_date_diff != null) dateDiff = true
      if (dateScore && descScore && amountScore && embedSim && dateDiff) break
    }
    return { dateScore, descScore, amountScore, embedSim, dateDiff }
  }, [payloads])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    // Percent floor helper: the payload value is in 0..1 and the threshold
    // is in percent (0..100). Missing values pass through so legacy engines
    // that don't emit the field still render. A threshold of 0 is a no-op.
    const passFloorPct = (v: number | undefined, thresholdPct: number) => {
      if (thresholdPct <= 0) return true
      if (v == null) return true
      return v * 100 >= thresholdPct
    }
    const rows = payloads.filter((p) => {
      if (!passFloorPct(p.confidence_score, minConfPct)) return false
      const diff = Math.abs(Number(p.difference ?? p.abs_amount_diff ?? 0))
      if (maxDiff != null && diff > maxDiff) return false
      if (matchTypes.size > 0 && !matchTypes.has(p.match_type ?? "")) return false
      // Component scores (payload stores them 0–1, UI takes percent floors).
      // `description_score` already equals `embed_similarity` clamped to
      // [0,1] in the engine, so a separate embed filter is redundant.
      const cs = p.component_scores ?? {}
      if (!passFloorPct(cs.date_score, minDateScorePct)) return false
      if (!passFloorPct(cs.description_score ?? p.extra?.embed_similarity, minDescScorePct)) return false
      if (!passFloorPct(cs.amount_score, minAmountScorePct)) return false
      // Avg date delta (absolute, in days). Missing → pass-through.
      if (maxDateDiffDays != null) {
        const dd = p.avg_date_diff
        if (dd != null && Math.abs(Number(dd)) > maxDateDiffDays) return false
      }
      if (q) {
        const haystack = [
          p.bank_transaction_summary,
          p.journal_entries_summary,
          ...(p.bank_transaction_details ?? []).map((d) => d.description ?? ""),
          ...(p.journal_entry_details ?? []).map(
            (d) => `${d.description ?? ""} ${d.transaction?.description ?? ""}`,
          ),
        ]
          .join(" ")
          .toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
    // Sort
    rows.sort((a, b) => {
      switch (sort) {
        case "confidence_asc":
          return (a.confidence_score ?? 0) - (b.confidence_score ?? 0)
        case "difference_asc":
          return (
            Math.abs(Number(a.difference ?? 0)) - Math.abs(Number(b.difference ?? 0))
          )
        case "date_asc":
          return (a.avg_date_diff ?? 0) - (b.avg_date_diff ?? 0)
        case "size_desc": {
          const sA = (a["N bank"] ?? a.bank_ids.length) + (a["N book"] ?? a.journal_entries_ids.length)
          const sB = (b["N bank"] ?? b.bank_ids.length) + (b["N book"] ?? b.journal_entries_ids.length)
          return sB - sA
        }
        case "bank_desc": return bankSumAbs(b) - bankSumAbs(a)
        case "bank_asc": return bankSumAbs(a) - bankSumAbs(b)
        case "book_desc": return bookSumAbs(b) - bookSumAbs(a)
        case "book_asc": return bookSumAbs(a) - bookSumAbs(b)
        case "confidence_desc":
        default:
          return (b.confidence_score ?? 0) - (a.confidence_score ?? 0)
      }
    })
    return rows
  }, [
    payloads, search, minConfPct, maxDiff, matchTypes, sort,
    minDateScorePct, minDescScorePct, minAmountScorePct,
    maxDateDiffDays,
  ])

  const keyed = useMemo(
    () => filtered.map((p, i) => ({ key: payloadKey(p, i), payload: p })),
    [filtered],
  )

  // Summary stats (for the filtered view).
  const stats = useMemo(() => {
    if (filtered.length === 0) {
      return { count: 0, avgConf: 0, sumBank: 0, sumBook: 0, sumDiff: 0, balanced: 0 }
    }
    let avgConf = 0
    let sumBank = 0
    let sumBook = 0
    let sumDiff = 0
    let balanced = 0
    for (const p of filtered) {
      avgConf += p.confidence_score ?? 0
      sumBank += Number(p.sum_bank ?? 0)
      sumBook += Number(p.sum_book ?? 0)
      const d = Math.abs(Number(p.difference ?? 0))
      sumDiff += d
      if (d <= 0.005) balanced++
    }
    return {
      count: filtered.length,
      avgConf: avgConf / filtered.length,
      sumBank,
      sumBook,
      sumDiff,
      balanced,
    }
  }, [filtered])

  const acceptEligible = useMemo(
    () => keyed.filter(({ payload }) => (payload.confidence_score ?? 0) >= autoAcceptThreshold),
    [keyed, autoAcceptThreshold],
  )

  const clearTaskId = () => {
    if (embedded) {
      onExit?.()
      return
    }
    const next = new URLSearchParams(searchParams)
    next.delete("task_id")
    setSearchParams(next)
  }

  const resetFilters = () => {
    setSearch("")
    setMinConfPct(0)
    setMaxDiff(null)
    setMatchTypes(new Set())
    setMinDateScorePct(0)
    setMinDescScorePct(0)
    setMinAmountScorePct(0)
    setMaxDateDiffDays(null)
    // Reset sort to its default too — operators expect "clear filters"
    // to restore the page to a fully neutral state, including sort
    // (otherwise a stale sort key sits in the URL after a reset).
    setSort("confidence_desc")
  }

  // True when any filter deviates from its "all rows pass" default.
  const hasActiveFilters =
    search.trim() !== "" ||
    minConfPct > 0 ||
    maxDiff != null ||
    matchTypes.size > 0 ||
    minDateScorePct > 0 ||
    minDescScorePct > 0 ||
    minAmountScorePct > 0 ||
    maxDateDiffDays != null ||
    sort !== "confidence_desc"

  // --- URL <-> filter state sync ---------------------------------------
  // Persists every filter into the page URL so an operator can copy/paste
  // a filtered view, refresh without losing context, or share a "Δ valor
  // máx. 5,00 + ordenado por diferença" link with a colleague. One-shot
  // hydrate-from-URL on mount, then write-back on every state change
  // (replace: true so each keystroke doesn't pollute the back/forward
  // stack).
  const hydratedFromUrl = useRef(false)

  useEffect(() => {
    if (hydratedFromUrl.current) return
    hydratedFromUrl.current = true

    const sp = searchParams
    const q = sp.get("q")
    if (q) setSearch(q)
    const cmin = sp.get("cmin")
    if (cmin) setMinConfPct(Math.max(0, Math.min(100, Number(cmin) || 0)))
    const dmax = sp.get("dmax")
    if (dmax !== null) {
      const n = Number(dmax)
      if (Number.isFinite(n) && n >= 0) setMaxDiff(n)
    }
    const mt = sp.get("mt")
    if (mt) setMatchTypes(new Set(mt.split(",").filter(Boolean)))
    // ``sort`` is a 5-value union — accept only known values from the
    // URL so a malformed ``?sort=garbage`` doesn't sneak past the
    // <select> and leave the page in an unselectable state.
    const sortParam = sp.get("sort")
    const validSorts: SortKey[] = [
      "confidence_desc",
      "confidence_asc",
      "difference_asc",
      "bank_desc",
      "bank_asc",
      "book_desc",
      "book_asc",
      "date_asc",
      "size_desc",
    ]
    if (sortParam && (validSorts as string[]).includes(sortParam)) {
      setSort(sortParam as SortKey)
    }
    const dscmin = sp.get("dscmin")
    if (dscmin) setMinDateScorePct(Math.max(0, Math.min(100, Number(dscmin) || 0)))
    const descmin = sp.get("descmin")
    if (descmin) setMinDescScorePct(Math.max(0, Math.min(100, Number(descmin) || 0)))
    const amin = sp.get("amin")
    if (amin) setMinAmountScorePct(Math.max(0, Math.min(100, Number(amin) || 0)))
    const ddmax = sp.get("ddmax")
    if (ddmax !== null) {
      const n = Number(ddmax)
      if (Number.isFinite(n) && n >= 0) setMaxDateDiffDays(n)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!hydratedFromUrl.current) return

    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        // Each filter writes its own param when it deviates from the
        // default; deletes when it returns to default. Keeps the URL
        // tidy and prevents `?cmin=0&dmax=` noise.
        if (search.trim()) next.set("q", search)
        else next.delete("q")
        if (minConfPct > 0) next.set("cmin", String(minConfPct))
        else next.delete("cmin")
        if (maxDiff != null) next.set("dmax", String(maxDiff))
        else next.delete("dmax")
        if (matchTypes.size > 0) next.set("mt", Array.from(matchTypes).join(","))
        else next.delete("mt")
        if (sort !== "confidence_desc") next.set("sort", sort)
        else next.delete("sort")
        if (minDateScorePct > 0) next.set("dscmin", String(minDateScorePct))
        else next.delete("dscmin")
        if (minDescScorePct > 0) next.set("descmin", String(minDescScorePct))
        else next.delete("descmin")
        if (minAmountScorePct > 0) next.set("amin", String(minAmountScorePct))
        else next.delete("amin")
        if (maxDateDiffDays != null) next.set("ddmax", String(maxDateDiffDays))
        else next.delete("ddmax")
        return next
      },
      { replace: true },
    )
  }, [
    search,
    minConfPct,
    maxDiff,
    matchTypes,
    sort,
    minDateScorePct,
    minDescScorePct,
    minAmountScorePct,
    maxDateDiffDays,
    setSearchParams,
  ])

  const toggleAccept = (key: string) => {
    setAccepted((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const bulkAccept = () => {
    setAccepted((prev) => {
      const next = new Set(prev)
      for (const { key } of acceptEligible) next.add(key)
      return next
    })
  }

  const clearAccepted = () => setAccepted(new Set())

  const submit = () => {
    if (accepted.size === 0) return
    const byKey = new Map(keyed.map(({ key, payload }) => [key, payload]))
    const matches = Array.from(accepted)
      .map((k) => byKey.get(k))
      .filter((p): p is TaskSuggestionPayload => !!p)
      .map((p) => ({
        bank_transaction_ids: p.bank_ids,
        journal_entry_ids: p.journal_entries_ids,
      }))
    if (matches.length === 0) return
    finalize.mutate(
      { matches, reference: `Task #${taskId}`, notes: "Aceito via Sugestões" },
      {
        onSuccess: (res) => {
          const created = (res.created as unknown[])?.length ?? 0
          const problems = (res.problems as unknown[])?.length ?? 0
          toast.success(`${created} reconciliação(ões) criada(s)${problems ? ` · ${problems} problema(s)` : ""}`)
          setAccepted(new Set())
          taskSuggestions.refetch()
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <div className="space-y-4">
      {!embedded && (
        <SectionHeader
          title="Sugestões"
          subtitle={`Execução #${taskId}`}
          actions={
            <button
              type="button"
              onClick={clearTaskId}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium text-muted-foreground hover:bg-accent"
            >
              <X className="h-3.5 w-3.5" /> Sair da execução
            </button>
          }
        />
      )}

      {/* Task banner — always visible, even when the rest of the panel is
          collapsed, so the operator can still see *which* execution is loaded
          and toggle the panel back on. */}
      <div className="card-elevated flex flex-wrap items-center gap-3 px-3 py-2 text-[12px]">
        <Hash className="h-3.5 w-3.5 text-primary" />
        <span>
          Sugestões persistidas da execução{" "}
          {embedded ? (
            <span className="font-mono font-semibold text-primary">#{taskId}</span>
          ) : (
            <button
              type="button"
              onClick={() => navigate(`/recon/tasks?id=${taskId}`)}
              className="font-mono font-semibold text-primary hover:underline"
            >
              #{taskId}
            </button>
          )}
          .
        </span>
        <span className="text-muted-foreground">
          {taskSuggestions.isLoading
            ? "Carregando…"
            : `${taskSuggestions.data?.count ?? 0} total · ${stats.count} visíveis · ${stats.balanced} balanceadas`}
        </span>
        {(bankRows.isFetching || journalRows.isFetching) && !taskSuggestions.isLoading && (
          <span className="text-muted-foreground">Hidratando descrições…</span>
        )}
        {taskSuggestions.isError && (
          <span className="text-danger">Falha ao carregar. Tente novamente.</span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setPanelCollapsed((v) => !v)}
            className="inline-flex h-6 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent"
            title={panelCollapsed ? "Mostrar filtros e controles" : "Ocultar painel para revisar sugestões com mais espaço"}
            aria-expanded={!panelCollapsed}
          >
            {panelCollapsed ? (
              <>
                <ChevronDown className="h-3 w-3" /> Mostrar painel
              </>
            ) : (
              <>
                <ChevronUp className="h-3 w-3" /> Ocultar painel
              </>
            )}
          </button>
          {embedded && (
            <button
              type="button"
              onClick={clearTaskId}
              className="inline-flex h-6 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-muted-foreground hover:bg-accent"
              title="Fechar execução"
            >
              <X className="h-3 w-3" /> Fechar
            </button>
          )}
        </div>
      </div>

      {/* Filters / stats / accept controls — collapsible. The whole
          subsection hides on the operator's request (see ``panelCollapsed``)
          so the suggestion cards get the full vertical real estate. The
          task banner above keeps showing the toggle so the panel can be
          recalled at any time. */}
      {!panelCollapsed && (
        <>
      {/* Filters — sticky so the operator can scroll a long list of
          suggestions without losing the filter / sort / reset
          controls. ``z-20`` keeps it above the suggestion cards
          which sit at the default z-index. ``card-elevated`` already
          paints an opaque background; if that ever changes, add
          ``bg-background`` here to prevent bleed-through.

          Single-row layout: ``flex flex-nowrap overflow-x-auto`` keeps every
          control in one line; on a narrow viewport the row scrolls
          horizontally rather than wrapping, which preserved a stable
          information density for operators used to a fixed layout. The
          "Tipo" pills sit at the end of the same row when there's space. */}
      <div className="card-elevated sticky top-0 z-20 p-3">
        <div className="flex flex-nowrap items-end gap-3 overflow-x-auto pb-1">
          <div className="flex shrink-0 flex-col gap-0.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Buscar
            </span>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="descrição, conta, entidade…"
                className="h-8 w-48 rounded-md border border-border bg-background pl-7 pr-2 text-[12px] outline-none focus:border-ring"
              />
            </div>
          </div>

          {/* Confidence / per-component score minimums — grouped in a boxed
              cluster so the user can tell they're all "pass above X%"
              thresholds and can be reasoned about together. */}
          <div className="flex shrink-0 items-end gap-2 rounded-md border border-border/70 bg-muted/20 px-2 pb-1.5 pt-1">
            <PctFloorField label="Confiança" value={minConfPct} onChange={setMinConfPct} />
            {available.dateScore && (
              <PctFloorField label="Data" value={minDateScorePct} onChange={setMinDateScorePct} />
            )}
            {(available.descScore || available.embedSim) && (
              <PctFloorField label="Descrição" value={minDescScorePct} onChange={setMinDescScorePct} />
            )}
            {available.amountScore && (
              <PctFloorField label="Valor" value={minAmountScorePct} onChange={setMinAmountScorePct} />
            )}
          </div>

          <div className="shrink-0">
            <NumField
              label="Δ valor máx."
              value={maxDiff}
              step={1}
              min={0}
              onChange={setMaxDiff}
              allowNull
            />
          </div>

          {available.dateDiff && (
            <div className="shrink-0">
              <NumField
                label="Δ dias máx."
                value={maxDateDiffDays}
                step={1}
                min={0}
                onChange={setMaxDateDiffDays}
                allowNull
              />
            </div>
          )}

          <div className="flex shrink-0 flex-col gap-0.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <ArrowDownUp className="inline h-3 w-3" /> Ordenar
            </span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
            >
              <option value="confidence_desc">Confiança ↓</option>
              <option value="confidence_asc">Confiança ↑</option>
              <option value="difference_asc">Diferença ↑</option>
              <option value="date_asc">Δ data médio ↑</option>
              <option value="size_desc">Tamanho ↓</option>
              <option value="bank_desc">Valor banco ↓</option>
              <option value="bank_asc">Valor banco ↑</option>
              <option value="book_desc">Valor livro ↓</option>
              <option value="book_asc">Valor livro ↑</option>
            </select>
          </div>

          {availableMatchTypes.length > 0 && (
            <div className="flex shrink-0 flex-col gap-0.5">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Tipo
              </span>
              <div className="flex h-8 items-center gap-1">
                {availableMatchTypes.map((mt) => {
                  const active = matchTypes.has(mt)
                  return (
                    <button
                      key={mt}
                      type="button"
                      onClick={() =>
                        setMatchTypes((prev) => {
                          const next = new Set(prev)
                          if (next.has(mt)) next.delete(mt)
                          else next.add(mt)
                          return next
                        })
                      }
                      className={cn(
                        "inline-flex h-6 items-center rounded-full border px-2 text-[11px] transition-colors",
                        active
                          ? "border-primary/40 bg-primary/15 text-primary"
                          : "border-border bg-background text-muted-foreground hover:bg-accent",
                      )}
                    >
                      {mt}
                    </button>
                  )
                })}
                {matchTypes.size > 0 && (
                  <button
                    type="button"
                    onClick={() => setMatchTypes(new Set())}
                    className="ml-0.5 text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    limpar
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
            <FilterIcon className="h-3 w-3" />
            <span className="tabular-nums">{stats.count} / {payloads.length}</span>
            <button
              type="button"
              onClick={resetFilters}
              disabled={!hasActiveFilters}
              className="ml-1 inline-flex h-6 items-center gap-1 rounded-md border border-border bg-background px-2 text-[10px] font-medium text-muted-foreground hover:bg-accent disabled:opacity-40"
              title="Restaurar filtros padrão"
            >
              <X className="h-3 w-3" /> Reset
            </button>
          </div>
        </div>
      </div>

      {/* Stats strip */}
      <div className="card-elevated grid grid-cols-2 gap-2 p-3 text-[11px] md:grid-cols-5">
        <Stat label="Sugestões" value={stats.count.toString()} />
        <Stat label="Conf. média" value={`${(stats.avgConf * 100).toFixed(0)}%`} />
        <Stat label="Σ banco" value={formatCurrency(stats.sumBank)} tabular />
        <Stat label="Σ razão" value={formatCurrency(stats.sumBook)} tabular />
        <Stat label="Σ |Δ|" value={formatCurrency(stats.sumDiff)} tabular tone={stats.sumDiff > 0.005 ? "danger" : "success"} />
      </div>

      {/* Accept controls */}
      <div className="card-elevated flex flex-wrap items-center gap-3 p-3 text-[12px]">
        <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-muted-foreground">Aceitar automaticamente acima de</span>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={autoAcceptThreshold}
          onChange={(e) => setAutoAcceptThreshold(Number(e.target.value))}
          className="h-7 w-16 rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
        />
        <span className="text-muted-foreground">({acceptEligible.length} elegíveis)</span>
        <button
          type="button"
          onClick={bulkAccept}
          disabled={acceptEligible.length === 0}
          className="inline-flex h-7 items-center gap-1.5 rounded-md bg-foreground px-2.5 text-[11px] font-semibold text-background shadow-sm hover:bg-foreground/90 disabled:opacity-40"
        >
          <Check className="h-3 w-3" /> Marcar elegíveis
        </button>
        <button
          type="button"
          onClick={clearAccepted}
          disabled={accepted.size === 0}
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground hover:bg-accent disabled:opacity-40"
        >
          <X className="h-3 w-3" /> Limpar
        </button>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-muted-foreground">{accepted.size} selecionadas</span>
          <button
            type="button"
            onClick={submit}
            disabled={accepted.size === 0 || finalize.isPending}
            className="inline-flex h-7 items-center gap-1.5 rounded-md bg-foreground px-3 text-[11px] font-semibold text-background shadow-sm hover:bg-foreground/90 disabled:opacity-40"
          >
            <PlayCircle className="h-3 w-3" />
            {finalize.isPending ? "Aplicando…" : "Finalizar reconciliações"}
          </button>
        </div>
      </div>
        </>
      )}

      {/* When the panel is collapsed we still surface the most-needed
          actions inline so the operator can finalize selections without
          having to expand. The bar collapses into a compact row that
          shows the running selected count + the "Finalizar" CTA. */}
      {panelCollapsed && (accepted.size > 0 || stats.count > 0) && (
        <div className="card-elevated flex flex-wrap items-center gap-2 p-2 text-[11px]">
          <span className="text-muted-foreground">{stats.count} sugestões visíveis</span>
          {accepted.size > 0 && (
            <>
              <span className="text-muted-foreground">·</span>
              <span className="font-medium text-foreground">
                {accepted.size} selecionada(s)
              </span>
              <button
                type="button"
                onClick={clearAccepted}
                className="inline-flex h-6 items-center gap-1 rounded-md border border-border bg-background px-2 font-medium text-muted-foreground hover:bg-accent"
              >
                <X className="h-3 w-3" /> Limpar
              </button>
            </>
          )}
          <div className="ml-auto">
            <button
              type="button"
              onClick={submit}
              disabled={accepted.size === 0 || finalize.isPending}
              className="inline-flex h-6 items-center gap-1.5 rounded-md bg-foreground px-3 font-semibold text-background shadow-sm hover:bg-foreground/90 disabled:opacity-40"
            >
              <PlayCircle className="h-3 w-3" />
              {finalize.isPending ? "Aplicando…" : "Finalizar reconciliações"}
            </button>
          </div>
        </div>
      )}

      {/* Cards */}
      {taskSuggestions.isLoading ? (
        <div className="card-elevated flex h-[320px] items-center justify-center text-[13px] text-muted-foreground">
          Carregando sugestões…
        </div>
      ) : keyed.length === 0 ? (
        <div className="card-elevated flex h-[320px] flex-col items-center justify-center gap-2 text-[13px] text-muted-foreground">
          <Sparkles className="h-6 w-6" />
          Nenhuma sugestão pendente para os filtros aplicados.
        </div>
      ) : (
        <div className="space-y-3">
          {keyed.map(({ key, payload }) => (
            <TaskSuggestionCard
              key={key}
              payload={payload}
              accepted={accepted.has(key)}
              onToggle={() => toggleAccept(key)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function TaskSuggestionCard({
  payload,
  accepted,
  onToggle,
}: {
  payload: TaskSuggestionPayload
  accepted: boolean
  onToggle: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const conf = payload.confidence_score ?? 0
  const pct = Math.max(0, Math.min(1, conf))
  const nBank = payload["N bank"] ?? payload.bank_ids.length
  const nBook = payload["N book"] ?? payload.journal_entries_ids.length
  const sumBank = Number(payload.sum_bank ?? 0)
  const sumBook = Number(payload.sum_book ?? 0)
  const diff = Math.abs(Number(payload.difference ?? 0))
  const relDiff = Math.max(Math.abs(sumBank), Math.abs(sumBook)) > 0
    ? diff / Math.max(Math.abs(sumBank), Math.abs(sumBook))
    : 0
  const balanced = diff <= 0.005
  const banks = payload.bank_transaction_details ?? []
  const books = payload.journal_entry_details ?? []
  const avgDateDelta = payload.avg_date_diff ?? 0

  // Compute per-side description sets and the shared-word vocabulary so
  // highlights are stable across rows (children reuse the same Set).
  const { bankTexts, bookTexts, shared, bankDates, bookDates, maxDateDelta } = useMemo(() => {
    const bankTexts: string[] = []
    const bankDates: string[] = []
    for (const b of banks) {
      if (b.description) bankTexts.push(b.description)
      if (b.bank_account?.name) bankTexts.push(b.bank_account.name)
      if (b.date) bankDates.push(b.date)
    }
    const bookTexts: string[] = []
    const bookDates: string[] = []
    for (const b of books) {
      // Prefer the transaction narrative; only add the journal `description`
      // when it differs (avoids "Banco Inter · Banco Inter" duplication for
      // the common case where they're copies of each other).
      const txDesc = b.transaction?.description?.trim() || ""
      const jeDesc = b.description?.trim() || ""
      if (txDesc) bookTexts.push(txDesc)
      if (jeDesc && jeDesc.toLowerCase() !== txDesc.toLowerCase()) bookTexts.push(jeDesc)
      if (b.transaction?.entity?.name) bookTexts.push(b.transaction.entity.name)
      if (b.account?.name) bookTexts.push(b.account.name)
      if (b.date) bookDates.push(b.date)
    }
    // Compute max pairwise date delta across both sides (not just average)
    let maxDateDelta = 0
    for (const bd of bankDates) {
      for (const jd of bookDates) {
        const dd = dayDiff(bd, jd)
        if (dd != null && dd > maxDateDelta) maxDateDelta = dd
      }
    }
    return {
      bankTexts,
      bookTexts,
      shared: sharedVocab(bankTexts, bookTexts),
      bankDates,
      bookDates,
      maxDateDelta,
    }
  }, [banks, books])

  const bankRange = dateRange(bankDates)
  const bookRange = dateRange(bookDates)

  return (
    <div
      className={cn(
        "card-elevated overflow-hidden transition-colors",
        accepted && "ring-1 ring-success/50 bg-success/[0.03]",
      )}
    >
      {/* === HEADER === */}
      <div className="flex items-start gap-3 p-3">
        {/* Left rail: match_type + confidence + size */}
        <div className="flex w-[160px] shrink-0 flex-col gap-1.5">
          <span
            className={cn(
              "inline-flex h-5 w-fit items-center rounded-sm px-1.5 text-[10px] font-medium uppercase tracking-wider",
              (payload.match_type ?? "").includes("parallel")
                ? "bg-info/15 text-info"
                : "bg-primary/15 text-primary",
            )}
          >
            {payload.match_type ?? "match"}
          </span>
          <div className="flex items-center gap-1.5">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
              <div
                className={cn(
                  "h-full",
                  pct >= 0.9 ? "bg-success" : pct >= 0.7 ? "bg-warning" : "bg-danger",
                )}
                style={{ width: `${pct * 100}%` }}
              />
            </div>
            <span className="w-10 text-right text-[11px] font-semibold tabular-nums">
              {(pct * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
            <span className="rounded-sm bg-surface-2 px-1.5 py-0.5">
              {nBank}b × {nBook}r
            </span>
            {(avgDateDelta > 0 || maxDateDelta > 0) && (
              <span className="inline-flex items-center gap-1" title="Δ data: média / máximo">
                <CalendarDays className="h-3 w-3" />
                {avgDateDelta.toFixed(1)}
                {maxDateDelta > 0 ? ` / ${maxDateDelta}` : ""}d
              </span>
            )}
            {shared.size > 0 && (
              <span
                className="inline-flex items-center gap-1 text-primary"
                title="Palavras em comum bank ↔ razão"
              >
                <Sparkles className="h-3 w-3" /> {shared.size}
              </span>
            )}
          </div>
        </div>

        {/* Middle: bank/book lines with highlighted descriptions */}
        <div className="flex min-w-0 flex-1 flex-col gap-1 text-[12px]">
          <SideSummary
            icon={<Banknote className="h-3 w-3" />}
            label="banco"
            amount={sumBank}
            range={bankRange}
            texts={bankTexts}
            shared={shared}
          />
          <SideSummary
            icon={<BookOpen className="h-3 w-3" />}
            label="razão"
            amount={sumBook}
            range={bookRange}
            texts={bookTexts}
            shared={shared}
          />
          <div className="flex flex-wrap items-center gap-3 pt-0.5 text-[11px]">
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Calculator className="h-3 w-3" /> Δ valor
            </span>
            <span
              className={cn(
                "tabular-nums font-semibold",
                balanced ? "text-success" : "text-danger",
              )}
            >
              {formatCurrency(diff)}
              {!balanced && relDiff > 0 && (
                <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                  ({(relDiff * 100).toFixed(1)}%)
                </span>
              )}
            </span>
            {avgDateDelta > 0 && (
              <>
                <span className="text-muted-foreground">·</span>
                <span className="inline-flex items-center gap-1 text-muted-foreground">
                  <CalendarDays className="h-3 w-3" /> Δ data méd.
                </span>
                <span className="tabular-nums">{avgDateDelta.toFixed(2)}d</span>
              </>
            )}
          </div>
        </div>

        {/* Right: actions */}
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onToggle}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] font-medium",
              accepted
                ? "border-success/40 bg-success/10 text-success hover:bg-success/15"
                : "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20",
            )}
          >
            <Check className="h-3 w-3" /> {accepted ? "Aceita" : "Aceitar"}
          </button>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className={cn(
              "grid h-7 w-7 place-items-center rounded-md border border-border hover:bg-accent transition-transform",
              expanded && "rotate-180",
            )}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* === EXPANDED DETAILS === */}
      {expanded && (
        <div className="grid grid-cols-1 gap-0 border-t border-border/60 bg-surface-1 md:grid-cols-2">
          <div className="border-r border-border/60 p-3">
            <div className="mb-2 flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-2">
                <Banknote className="h-3 w-3" /> Banco ({banks.length || payload.bank_ids.length})
              </span>
              <span className="tabular-nums normal-case text-[10px]">
                {formatCurrency(sumBank)}
              </span>
            </div>
            {banks.length > 0 ? (
              <div className="space-y-2">
                {banks.map((b) => {
                  // Closest date delta vs any book on the other side.
                  let minDelta: number | null = null
                  for (const jd of bookDates) {
                    const dd = dayDiff(b.date ?? null, jd)
                    if (dd != null && (minDelta == null || dd < minDelta)) minDelta = dd
                  }
                  return (
                    <DetailRow
                      key={b.id}
                      id={b.id}
                      date={b.date}
                      amount={b.amount}
                      title={b.description ?? ""}
                      subtitle={b.bank_account?.name ?? ""}
                      closestDayDelta={minDelta}
                      shared={shared}
                    />
                  )
                })}
              </div>
            ) : (
              <div className="font-mono text-[11px] text-muted-foreground">
                IDs: {payload.bank_ids.join(", ")}
              </div>
            )}
            {payload.bank_transaction_summary && (
              <details className="mt-2 text-[10px] text-muted-foreground">
                <summary className="cursor-pointer">raw summary</summary>
                <pre className="mt-1 whitespace-pre-wrap font-mono leading-tight">{payload.bank_transaction_summary}</pre>
              </details>
            )}
          </div>
          <div className="p-3">
            <div className="mb-2 flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-2">
                <BookOpen className="h-3 w-3" /> Razão ({books.length || payload.journal_entries_ids.length})
              </span>
              <span className="tabular-nums normal-case text-[10px]">
                {formatCurrency(sumBook)}
              </span>
            </div>
            {books.length > 0 ? (
              <div className="space-y-2">
                {books.map((b) => {
                  let minDelta: number | null = null
                  for (const bd of bankDates) {
                    const dd = dayDiff(b.date ?? null, bd)
                    if (dd != null && (minDelta == null || dd < minDelta)) minDelta = dd
                  }
                  return (
                    <DetailRow
                      key={b.id}
                      id={b.id}
                      date={b.date}
                      amount={b.amount}
                      title={b.transaction?.description || b.description || ""}
                      subtitle={
                        b.account
                          ? `${b.account.account_code ?? ""} ${b.account.name ?? ""}`.trim()
                          : b.transaction?.entity?.name
                            ? b.transaction.entity.name
                            : b.description &&
                                b.transaction?.description &&
                                b.description.trim().toLowerCase() !==
                                  b.transaction.description.trim().toLowerCase()
                              ? b.description
                              : ""
                      }
                      closestDayDelta={minDelta}
                      shared={shared}
                    />
                  )
                })}
              </div>
            ) : (
              <div className="font-mono text-[11px] text-muted-foreground">
                IDs: {payload.journal_entries_ids.join(", ")}
              </div>
            )}
            {payload.journal_entries_summary && (
              <details className="mt-2 text-[10px] text-muted-foreground">
                <summary className="cursor-pointer">raw summary</summary>
                <pre className="mt-1 whitespace-pre-wrap font-mono leading-tight">{payload.journal_entries_summary}</pre>
              </details>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Compact one-liner for the card header showing the side's total amount,
 * date range and a concatenation of descriptions (with shared words
 * highlighted). Keeps to one line with truncate overflow.
 */
function SideSummary({
  icon,
  label,
  amount,
  range,
  texts,
  shared,
}: {
  icon: ReactNode
  label: string
  amount: number
  range: { min: string | null; max: string | null }
  texts: string[]
  shared: Set<string>
}) {
  const combined = texts.filter(Boolean).join(" · ")
  const dateLabel = (() => {
    if (!range.min) return null
    if (!range.max || range.min === range.max) return formatDate(range.min)
    return `${formatDate(range.min)} → ${formatDate(range.max)}`
  })()
  // Two-row layout: row 1 keeps the metric columns aligned (label / amount /
  // date), row 2 dedicates the *full* card width to the description with
  // ``line-clamp-2`` + ``break-words`` so long bank/book narratives can wrap
  // to a second line instead of being clipped to a sliver of the card.
  // ``[overflow-wrap:anywhere]`` forces wrapping inside long unbroken
  // sequences (e.g. URLs, boletos) that ``break-words`` alone won't split.
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <div className="flex min-w-0 items-center gap-2">
        <span className="inline-flex w-14 shrink-0 items-center gap-1 text-muted-foreground">
          {icon} {label}
        </span>
        <span className="w-24 shrink-0 tabular-nums font-semibold">{formatCurrency(amount)}</span>
        {dateLabel && (
          <span className="shrink-0 text-[11px] text-muted-foreground">{dateLabel}</span>
        )}
      </div>
      <div
        className="ml-[3.75rem] line-clamp-2 break-words text-[11px] leading-snug text-muted-foreground [overflow-wrap:anywhere]"
        title={combined || undefined}
      >
        <Highlighted text={combined || "—"} shared={shared} />
      </div>
    </div>
  )
}

function DetailRow({
  id,
  date,
  amount,
  title,
  subtitle,
  closestDayDelta,
  shared,
}: {
  id: number
  date?: string | null
  amount?: number | null
  title?: string
  subtitle?: string
  closestDayDelta?: number | null
  shared: Set<string>
}) {
  return (
    <div className="flex items-start gap-2 text-[11px]">
      <span className="w-14 shrink-0 font-mono text-[10px] text-muted-foreground">#{id}</span>
      <div className="w-20 shrink-0 text-muted-foreground">
        <div>{date ? formatDate(date) : "—"}</div>
        {closestDayDelta != null && (
          <div
            className={cn(
              "text-[9px]",
              closestDayDelta === 0
                ? "text-success"
                : closestDayDelta <= 3
                  ? "text-muted-foreground"
                  : "text-warning",
            )}
            title="Menor diferença de data vs outro lado"
          >
            Δ {closestDayDelta}d
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words leading-snug">
          <Highlighted text={title || "—"} shared={shared} />
        </div>
        {subtitle && (
          <div className="truncate text-[10px] text-muted-foreground">
            <Highlighted text={subtitle} shared={shared} />
          </div>
        )}
      </div>
      <span
        className={cn(
          "shrink-0 tabular-nums font-semibold",
          amount != null && amount < 0 ? "text-danger" : "",
        )}
      >
        {amount != null ? formatCurrency(amount) : ""}
      </span>
    </div>
  )
}

function Stat({
  label,
  value,
  tabular,
  tone,
}: {
  label: string
  value: string
  tabular?: boolean
  tone?: "success" | "danger"
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          "font-semibold",
          tabular && "tabular-nums",
          tone === "success" && "text-success",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </span>
    </div>
  )
}


// ---------------------------------------------------------------------------
// MANUAL MODE — original workflow (pick bank txs + generate suggestions).
// ---------------------------------------------------------------------------

type SelectedMap = Map<number, SuggestionItem>

function ManualSuggestionsView() {
  const { t } = useTranslation(["reconciliation", "common"])
  const [selectedBankIds, setSelectedBankIds] = useState<Set<number>>(new Set())
  const [minConfidence, setMinConfidence] = useState(0.5)
  const [maxPerBank, setMaxPerBank] = useState(5)
  const [minMatchCount, setMinMatchCount] = useState(1)
  const [acceptThreshold, setAcceptThreshold] = useState(0.9)

  const { data: bankTxs = [] } = useBankTransactions({
    unreconciled: true,
    ordering: "-date",
    date_after: isoDaysAgo(60),
    limit: 200,
  })

  const suggest = useSuggestMatches()
  const createSuggestions = useCreateSuggestions()

  const [result, setResult] = useState<SuggestMatchResponse | null>(null)
  const [accepted, setAccepted] = useState<SelectedMap>(new Map())

  const onGenerate = () => {
    if (selectedBankIds.size === 0) {
      toast.error(t("suggestions.select_bank_txs") ?? "Select items")
      return
    }
    suggest.mutate(
      {
        bank_transaction_ids: Array.from(selectedBankIds),
        max_suggestions_per_bank: maxPerBank,
        min_confidence: minConfidence,
        min_match_count: minMatchCount,
      },
      {
        onSuccess: (res) => {
          setResult(res)
          setAccepted(new Map())
        },
        onError: (err: unknown) => {
          toast.error(err instanceof Error ? err.message : "Erro")
        },
      },
    )
  }

  const toggleBank = (id: number) => {
    setSelectedBankIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const acceptItem = (bankId: number, item: SuggestionItem) => {
    setAccepted((prev) => {
      const next = new Map(prev)
      next.set(bankId, item)
      return next
    })
  }

  const rejectItem = (bankId: number) => {
    setAccepted((prev) => {
      const next = new Map(prev)
      next.delete(bankId)
      return next
    })
  }

  const bulkAccept = () => {
    if (!result) return
    setAccepted((prev) => {
      const next = new Map(prev)
      for (const bank of result.suggestions) {
        const best = bank.suggestions[0]
        if (best && best.confidence_score >= acceptThreshold) next.set(bank.bank_transaction_id, best)
      }
      return next
    })
  }

  const applySelected = () => {
    if (accepted.size === 0) return
    const suggestions = Array.from(accepted.entries()).map(([bankId, item]) => {
      if (item.suggestion_type === "use_existing_book") {
        return {
          suggestion_type: "use_existing_book",
          bank_transaction_id: bankId,
          existing_journal_entry_id: item.existing_journal_entry?.id,
          complementing_journal_entries: item.complementing_journal_entries ?? [],
        }
      }
      return {
        suggestion_type: "create_new",
        bank_transaction_id: bankId,
        transaction: item.transaction,
        journal_entries: item.journal_entries ?? [],
      }
    })
    createSuggestions.mutate(
      { suggestions },
      {
        onSuccess: (res) => {
          toast.success(`${t("suggestions.applied_toast")} (${res.created_transactions?.length ?? 0})`)
          setAccepted(new Map())
          setResult((r) =>
            r ? { ...r, suggestions: r.suggestions.filter((s) => !accepted.has(s.bank_transaction_id)) } : r,
          )
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  const eligibleCount = useMemo(
    () => result?.suggestions.filter((b) => (b.suggestions[0]?.confidence_score ?? 0) >= acceptThreshold).length ?? 0,
    [result, acceptThreshold],
  )

  // Ensure we drop the pinned result if user re-enters manual mode after
  // clearing a task_id — otherwise stale task data can remain mounted.
  useEffect(() => {
    setResult(null)
    setAccepted(new Map())
  }, [])

  return (
    <div className="space-y-4">
      <SectionHeader
        title={t("suggestions.title")}
        subtitle={t("suggestions.subtitle") ?? ""}
        actions={
          <button
            onClick={onGenerate}
            disabled={suggest.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Sparkles className="h-3.5 w-3.5" /> {t("suggestions.generate")}
          </button>
        }
      />

      <div className="card-elevated flex flex-wrap items-end gap-4 p-3">
        <NumField label={t("suggestions.min_confidence")} value={minConfidence} step={0.05} min={0} max={1} onChange={(v) => v != null && setMinConfidence(v)} />
        <NumField label={t("suggestions.max_per_bank")} value={maxPerBank} step={1} min={1} max={20} onChange={(v) => v != null && setMaxPerBank(v)} />
        <NumField label={t("suggestions.min_match_count")} value={minMatchCount} step={1} min={1} max={10} onChange={(v) => v != null && setMinMatchCount(v)} />
        <div className="ml-auto text-[12px] text-muted-foreground">
          {selectedBankIds.size > 0
            ? `${selectedBankIds.size} transações selecionadas`
            : t("suggestions.select_bank_txs")}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[320px_1fr]">
        <div className="card-elevated flex h-[540px] flex-col overflow-hidden">
          <div className="flex h-9 shrink-0 items-center justify-between border-b border-border px-3">
            <span className="text-[12px] font-semibold">Transações bancárias</span>
            <span className="text-[10px] text-muted-foreground">{bankTxs.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {bankTxs.map((bt) => {
              const sel = selectedBankIds.has(bt.id)
              return (
                <button
                  key={bt.id}
                  onClick={() => toggleBank(bt.id)}
                  className={cn(
                    "flex w-full items-center gap-2 border-b border-border/60 px-3 py-2 text-left text-[12px] transition-colors",
                    sel ? "bg-primary/10" : "hover:bg-accent/50",
                  )}
                >
                  <input type="checkbox" checked={sel} readOnly className="h-3.5 w-3.5 accent-primary" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[12px]">{bt.description}</span>
                    <span className="text-[10px] text-muted-foreground">{formatDate(bt.date)} · {bt.entity_name}</span>
                  </div>
                  <span className={cn("tabular-nums text-[11px] font-semibold", Number(bt.amount) < 0 ? "text-danger" : "")}>
                    {formatCurrency(Number(bt.amount))}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-3">
          {!result ? (
            <div className="card-elevated flex h-[540px] flex-col items-center justify-center gap-2 text-[13px] text-muted-foreground">
              <Sparkles className="h-6 w-6" />
              {t("suggestions.no_suggestions")}
            </div>
          ) : result.suggestions.length === 0 ? (
            <div className="card-elevated flex h-[240px] flex-col items-center justify-center gap-2 text-[13px] text-muted-foreground">
              Nenhuma sugestão encontrada para os filtros aplicados.
            </div>
          ) : (
            <>
              <div className="card-elevated flex flex-wrap items-center gap-3 p-3 text-[12px]">
                <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Aceitar automaticamente acima de</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={acceptThreshold}
                  onChange={(e) => setAcceptThreshold(Number(e.target.value))}
                  className="h-7 w-16 rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
                />
                <span className="text-muted-foreground">({eligibleCount} elegíveis)</span>
                <button
                  onClick={bulkAccept}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2.5 text-[11px] font-medium text-primary hover:bg-primary/15"
                >
                  <Check className="h-3 w-3" /> {t("suggestions.bulk_accept_above", { value: acceptThreshold })}
                </button>
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-muted-foreground">{accepted.size} aceitas</span>
                  <button
                    onClick={applySelected}
                    disabled={accepted.size === 0 || createSuggestions.isPending}
                    className="inline-flex h-7 items-center gap-1.5 rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    <PlayCircle className="h-3 w-3" /> {t("suggestions.apply_selected")}
                  </button>
                </div>
              </div>

              {result.suggestions.map((bank) => (
                <SuggestionCard
                  key={bank.bank_transaction_id}
                  bank={bank}
                  accepted={accepted.get(bank.bank_transaction_id) ?? null}
                  onAccept={(item) => acceptItem(bank.bank_transaction_id, item)}
                  onReject={() => rejectItem(bank.bank_transaction_id)}
                />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** Single-threshold percent input: "pass if value ≥ X%". Value is kept as an
 *  integer percent (0..100); 0 is treated as "no filter" by the caller so we
 *  don't need an explicit null state. */
function PctFloorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="relative">
        <input
          type="number"
          value={value}
          step={5}
          min={0}
          max={100}
          onChange={(e) => onChange(Math.max(0, Math.min(100, Number(e.target.value))))}
          className="h-8 w-20 rounded-md border border-border bg-background pl-2 pr-6 text-[12px] tabular-nums outline-none focus:border-ring"
        />
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
          %
        </span>
      </div>
    </div>
  )
}

function NumField({
  label,
  value,
  step,
  min,
  max,
  onChange,
  allowNull,
}: {
  label: string
  /** `null` = filter disabled; any number (including 0) = active filter. */
  value: number | null
  step?: number
  min?: number
  max?: number
  onChange: (v: number | null) => void
  /** When true, show an × button that nulls the field. 0 is a valid value. */
  allowNull?: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="relative">
        <input
          type="number"
          value={value ?? ""}
          step={step}
          min={min}
          max={max}
          onChange={(e) => {
            const s = e.target.value
            if (s === "") { onChange(allowNull ? null : 0); return }
            onChange(Number(s))
          }}
          placeholder={allowNull ? "—" : undefined}
          className={cn(
            "h-8 w-24 rounded-md border border-border bg-background px-2 text-[12px] tabular-nums outline-none focus:border-ring",
            allowNull && "pr-6",
          )}
        />
        {allowNull && value !== null && (
          <button
            type="button"
            onClick={() => onChange(null)}
            title="Limpar filtro"
            aria-label="Limpar filtro"
            className="absolute right-1 top-1/2 grid h-4 w-4 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  )
}

function SuggestionCard({
  bank,
  accepted,
  onAccept,
  onReject,
}: {
  bank: SuggestMatchResponse["suggestions"][number]
  accepted: SuggestionItem | null
  onAccept: (item: SuggestionItem) => void
  onReject: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const best = bank.suggestions[0]
  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex items-start gap-3 p-3">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground">#{bank.bank_transaction_id}</span>
            <span className="truncate text-[13px] font-medium">{bank.bank_transaction.description}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>{formatDate(bank.bank_transaction.date)}</span>
            <span>·</span>
            <span className={cn("tabular-nums font-semibold", Number(bank.bank_transaction.amount) < 0 ? "text-danger" : "text-foreground")}>
              {formatCurrency(Number(bank.bank_transaction.amount))}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {accepted ? (
            <>
              <span className="inline-flex h-6 items-center gap-1 rounded-full border border-success/40 bg-success/10 px-2 text-[11px] font-medium text-success">
                <Check className="h-3 w-3" /> aceita
              </span>
              <button
                onClick={onReject}
                className="grid h-6 w-6 place-items-center rounded-md border border-border hover:bg-accent"
                title="Rejeitar"
              >
                <X className="h-3 w-3" />
              </button>
            </>
          ) : best ? (
            <>
              <button
                onClick={() => onAccept(best)}
                className="inline-flex h-7 items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 text-[11px] font-medium text-primary hover:bg-primary/20"
              >
                <Check className="h-3 w-3" /> Aceitar melhor
              </button>
            </>
          ) : null}
          <button
            onClick={() => setExpanded((v) => !v)}
            className={cn(
              "grid h-7 w-7 place-items-center rounded-md border border-border hover:bg-accent",
              expanded && "rotate-180",
            )}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border/60 bg-surface-1">
          {bank.suggestions.length === 0 ? (
            <div className="p-3 text-[12px] text-muted-foreground">Sem alternativas.</div>
          ) : (
            bank.suggestions.map((item, i) => (
              <AlternativeRow
                key={i}
                item={item}
                isAccepted={accepted === item}
                onAccept={() => onAccept(item)}
                onReject={onReject}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

function AlternativeRow({
  item,
  isAccepted,
  onAccept,
  onReject,
}: {
  item: SuggestionItem
  isAccepted: boolean
  onAccept: () => void
  onReject: () => void
}) {
  const pct = Math.max(0, Math.min(1, item.confidence_score))
  const badge = item.suggestion_type === "use_existing_book" ? "Usar existente" : "Criar novo"
  return (
    <div className="flex items-start gap-3 border-b border-border/60 p-3 last:border-b-0">
      <div className="flex w-[120px] shrink-0 flex-col gap-1">
        <span
          className={cn(
            "inline-flex h-4 w-fit items-center rounded-sm px-1.5 text-[10px] font-medium",
            item.suggestion_type === "use_existing_book"
              ? "bg-info/10 text-info"
              : "bg-primary/15 text-primary",
          )}
        >
          {badge}
        </span>
        <div className="flex items-center gap-1">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
            <div
              className={cn(
                "h-full",
                pct >= 0.85 ? "bg-success" : pct >= 0.7 ? "bg-warning" : "bg-danger",
              )}
              style={{ width: `${pct * 100}%` }}
            />
          </div>
          <span className="w-8 text-right text-[10px] tabular-nums">{(pct * 100).toFixed(0)}%</span>
        </div>
        {item.match_count != null && (
          <span className="text-[10px] text-muted-foreground">{item.match_count} matches hist.</span>
        )}
        {item.amount_difference && (
          <span className="text-[10px] text-muted-foreground tabular-nums">
            Δ {formatCurrency(Number(item.amount_difference))}
          </span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1 text-[12px]">
        {item.suggestion_type === "use_existing_book" && item.existing_journal_entry && (
          <>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Lançamento</span>
              <span className="font-mono text-[10px] text-muted-foreground">#{item.existing_journal_entry.id}</span>
              <span className="truncate">{item.existing_journal_entry.description}</span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {item.existing_journal_entry.account_code} {item.existing_journal_entry.account_name}
            </div>
            {(item.complementing_journal_entries ?? []).length > 0 && (
              <div className="mt-1 rounded-md border border-border bg-surface-2 p-2 text-[11px]">
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Complementos</div>
                {(item.complementing_journal_entries ?? []).map((je, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span>{je.account_code} {je.account_name}</span>
                    <span className="tabular-nums">
                      {je.debit_amount ? `D ${formatCurrency(Number(je.debit_amount))}` : ""}
                      {je.credit_amount ? `C ${formatCurrency(Number(je.credit_amount))}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {item.suggestion_type === "create_new" && item.transaction && (
          <>
            <div className="flex items-center gap-2">
              <span className="truncate">{item.transaction.description}</span>
              <span className="tabular-nums font-semibold">{formatCurrency(Number(item.transaction.amount))}</span>
            </div>
            {(item.journal_entries ?? []).length > 0 && (
              <div className="mt-1 rounded-md border border-border bg-surface-2 p-2 text-[11px]">
                {(item.journal_entries ?? []).map((je, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span>{je.account_code} {je.account_name}</span>
                    <span className="tabular-nums">
                      {je.debit_amount ? `D ${formatCurrency(Number(je.debit_amount))}` : ""}
                      {je.credit_amount ? `C ${formatCurrency(Number(je.credit_amount))}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="shrink-0">
        {isAccepted ? (
          <button
            onClick={onReject}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] font-medium hover:bg-accent"
          >
            <X className="h-3 w-3" /> Desfazer
          </button>
        ) : (
          <button
            onClick={onAccept}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 text-[11px] font-medium text-primary hover:bg-primary/20"
          >
            <Check className="h-3 w-3" /> Aceitar
          </button>
        )}
      </div>
    </div>
  )
}
