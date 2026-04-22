import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useHotkeys } from "react-hotkeys-hook"
import { useUrlFilters } from "@/lib/use-url-state"
import { ShortcutHelp } from "@/components/ui/shortcut-help"
import { SavedFiltersMenu } from "@/components/ui/saved-filters-menu"
import { toast } from "sonner"
import { Drawer } from "vaul"
import {
  Wallet, BookOpen, Check, X, Sparkles, ArrowLeftRight, AlertCircle, AlertTriangle,
  Plus, Trash2, CheckCircle2, Search, RotateCcw, Loader2, Wand2,
  ArrowUp, ArrowDown, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { ColumnMenu } from "@/components/ui/column-menu"
import { DownloadXlsxButton } from "@/components/ui/download-xlsx-button"
import { logAction, logError } from "@/lib/activity-beacon"
import { useColumnVisibility, type ColumnDef } from "@/stores/column-visibility"
import { RunRuleDrawer } from "@/components/reconciliation/RunRuleDrawer"
import { MassReconcileDrawer } from "@/components/reconciliation/MassReconcileDrawer"
import {
  useAccounts,
  useBankAccountsList,
  useBankTransactions,
  useCreateSuggestions,
  useEntities,
  useFinalizeMatches,
  useSuggestMatches,
  useUnmatchedJournalEntries,
  workbenchFiltersToStacks,
} from "@/features/reconciliation"
import type {
  AccountLite, BankTransaction, JournalEntry, SuggestMatchResponse, SuggestionItem,
} from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

interface Filters {
  // Bank-pane scoped
  bankDateFrom: string
  bankDateTo: string
  bankAccount: number | ""
  bankEntity: number | ""
  bankSearch: string
  bankAmountMin: string
  bankAmountMax: string
  bankStatus: string
  // Book-pane scoped
  bookDateFrom: string
  bookDateTo: string
  bookBankAccount: number | ""
  bookSearch: string
  bookAmountMin: string
  bookAmountMax: string
  bookStatus: string
}

// Empty by default so we don't silently hide rows; users opt into a date
// window explicitly. Keeping the helper around because the Reset buttons
// restore it to empty (same constant). Previously defaulted to last 60 days.
const DEFAULT_DATE_FROM = ""
const DEFAULT_DATE_TO = ""

/**
 * Parse an amount filter input. Returns:
 *   - null when the input is empty (filter off)
 *   - null when the value isn't a finite number (ignore malformed input
 *     instead of killing the whole list)
 *   - the numeric value otherwise — including 0, which must be a valid
 *     filter value (was being coerced to null via `Number(x) || null`).
 */
function parseFilterAmount(raw: string): number | null {
  const t = raw.trim()
  if (t === "") return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

/**
 * Search a bank row across every available column — including hidden ones —
 * so "find by boleto" or "find by CNPJ" works even when those columns
 * aren't currently shown. `q` is expected pre-lowercased; we avoid
 * re-normalising it on every row.
 */
function bankMatchesSearch(
  b: BankTransaction,
  q: string,
  bankAccNameById: Record<number, string>,
): boolean {
  const bankAcc = b.bank_account != null ? bankAccNameById[b.bank_account] : undefined
  const hay = [
    String(b.id),
    b.description,
    b.entity_name,
    bankAcc,
    b.erp_id,
    b.cnpj,
    (b.numeros_boleto ?? []).join(" "),
    b.reconciliation_status,
    b.tag,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
  return hay.includes(q)
}

function bookMatchesSearch(je: JournalEntry, q: string): boolean {
  const acctRef = je as unknown as {
    account?: { name?: string; account_code?: string } | null
    account_name?: string
  }
  const hay = [
    String(je.id),
    String(je.transaction_id),
    je.description,
    je.transaction_description,
    je.bank_account?.name,
    acctRef.account?.name,
    acctRef.account?.account_code,
    acctRef.account_name,
    je.erp_id,
    je.cnpj,
    je.nf_number,
    je.numero_boleto,
    je.reconciliation_status,
    je.tag,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
  return hay.includes(q)
}

// Columns available for each bancada table. Defaults match what the pane
// used to render pre-picker; operators can hide/show optional columns via
// the ColumnMenu in each pane header. Amount + description are always on
// (the rows don't make sense without them).
const BANK_COLUMNS: ColumnDef[] = [
  { key: "id", label: "ID", defaultVisible: true },
  { key: "description", label: "Descrição", alwaysVisible: true },
  { key: "date", label: "Data", defaultVisible: true },
  { key: "entity", label: "Entidade", defaultVisible: true },
  { key: "status", label: "Status", defaultVisible: true },
  { key: "bank_account", label: "Conta bancária", defaultVisible: true },
  { key: "erp_id", label: "ERP id", defaultVisible: false },
  { key: "cnpj", label: "CNPJ", defaultVisible: false },
  { key: "boletos", label: "Boletos", defaultVisible: false },
  { key: "amount", label: "Valor", alwaysVisible: true },
]

const BOOK_COLUMNS: ColumnDef[] = [
  { key: "id", label: "ID", defaultVisible: true },
  { key: "description", label: "Descrição", alwaysVisible: true },
  { key: "date", label: "Data", defaultVisible: true },
  { key: "bank_account", label: "Conta bancária", defaultVisible: true },
  { key: "status", label: "Status", defaultVisible: true },
  { key: "account", label: "Conta contábil", defaultVisible: false },
  { key: "erp_id", label: "ERP id", defaultVisible: false },
  { key: "cnpj", label: "CNPJ", defaultVisible: false },
  { key: "nf_number", label: "NF", defaultVisible: false },
  { key: "boleto", label: "Boleto", defaultVisible: false },
  { key: "amount", label: "Valor", alwaysVisible: true },
]

/**
 * Sort keys available in each pane. Client-side only (the server-side
 * endpoint returns the full unreconciled set), operating on the already
 * filtered rows before pagination slices them.
 */
type BankSortKey = "id" | "date" | "description" | "amount" | "entity" | "status" | "bank_account"
type BookSortKey = "id" | "date" | "description" | "amount" | "bank_account" | "status" | "account"
type SortDir = "asc" | "desc"

interface SortState<K extends string> {
  key: K
  dir: SortDir
}

const BANK_SORT_OPTIONS: Array<{ key: BankSortKey; label: string }> = [
  { key: "date", label: "Data" },
  { key: "amount", label: "Valor" },
  { key: "description", label: "Descrição" },
  { key: "id", label: "ID" },
  { key: "entity", label: "Entidade" },
  { key: "status", label: "Status" },
  { key: "bank_account", label: "Conta" },
]

const BOOK_SORT_OPTIONS: Array<{ key: BookSortKey; label: string }> = [
  { key: "date", label: "Data" },
  { key: "amount", label: "Valor" },
  { key: "description", label: "Descrição" },
  { key: "id", label: "ID" },
  { key: "bank_account", label: "Conta bancária" },
  { key: "account", label: "Conta contábil" },
  { key: "status", label: "Status" },
]

/** Page-size options for the per-pane pager. `0` = all (disables paging). */
const PAGE_SIZE_OPTIONS = [50, 100, 250, 500, 0] as const

const BLANK_FILTERS: Filters = {
  bankDateFrom: DEFAULT_DATE_FROM,
  bankDateTo: DEFAULT_DATE_TO,
  bankAccount: "",
  bankEntity: "",
  bankSearch: "",
  bankAmountMin: "",
  bankAmountMax: "",
  bankStatus: "",
  bookDateFrom: DEFAULT_DATE_FROM,
  bookDateTo: DEFAULT_DATE_TO,
  bookBankAccount: "",
  bookSearch: "",
  bookAmountMin: "",
  bookAmountMax: "",
  bookStatus: "",
}

export function WorkbenchPage() {
  const { t } = useTranslation(["reconciliation", "common"])
  const [filters, setFiltersPatch] = useUrlFilters<Filters>(BLANK_FILTERS)
  const setFilters = (updater: Filters | ((f: Filters) => Filters)) => {
    const next = typeof updater === "function" ? (updater as (f: Filters) => Filters)(filters) : updater
    const patch: Partial<Filters> = {}
    for (const k of Object.keys(next) as (keyof Filters)[]) {
      if (next[k] !== filters[k]) (patch as Record<string, unknown>)[k] = next[k]
    }
    setFiltersPatch(patch)
  }

  const { data: bankAccounts } = useBankAccountsList()
  const { data: entities } = useEntities()
  const bankAccNameById = useMemo(
    () => Object.fromEntries((bankAccounts ?? []).map((b) => [b.id, b.name])) as Record<number, string>,
    [bankAccounts],
  )

  // Column visibility for each pane (persisted in zustand). Used to control
  // which meta fields render per row + exposed via the ColumnMenu in the
  // pane header.
  const bankCols = useColumnVisibility("recon.workbench.bank", BANK_COLUMNS)
  const bookCols = useColumnVisibility("recon.workbench.book", BOOK_COLUMNS)

  // NOTE: reconciliation candidates must all be visible for consistent
  // selection; the backend opts these endpoints out of pagination, but we
  // still pass a large page_size as defense-in-depth in case a proxy / future
  // change re-enables it. Date/entity/bank filters are the real cap.
  const txParams = useMemo(
    () => ({
      // Use the dedicated ?unreconciled=true switch (mirrors /api/journal_entries/unmatched/).
      // This is Retool's proven pattern: a single-purpose boolean that's cheaper and
      // more explicit than the three-state reconciliation_status filter.
      unreconciled: true,
      bank_account: filters.bankAccount || undefined,
      date_after: filters.bankDateFrom || undefined,
      date_before: filters.bankDateTo || undefined,
      ordering: "-date",
      page_size: 5000,
    }),
    [filters.bankAccount, filters.bankDateFrom, filters.bankDateTo],
  )

  // Book pane: use the dedicated /api/journal_entries/unmatched/ endpoint
  // (same pattern used in Retool). It filters bank-linked JEs server-side
  // and excludes already-matched/approved reconciliations — matches the
  // "pending" semantics the workbench cares about.
  const jeParams = useMemo(
    () => ({
      date_from: filters.bookDateFrom || undefined,
      date_to: filters.bookDateTo || undefined,
      bank_account: filters.bookBankAccount || undefined,
    }),
    [filters.bookBankAccount, filters.bookDateFrom, filters.bookDateTo],
  )

  const {
    data: rawBankTxs = [],
    isLoading: bankLoading,
    isFetching: bankFetching,
  } = useBankTransactions(txParams)
  const {
    data: rawJournalEntries = [],
    isLoading: bookLoading,
    isFetching: bookFetching,
  } = useUnmatchedJournalEntries(jeParams)

  // Client-side filtering: each pane owns its own filters; values below are
  // applied on top of the server-side filters (amount/search/status/entity
  // run client-side for instant feedback).
  const bankTxs = useMemo(() => {
    const min = parseFilterAmount(filters.bankAmountMin)
    const max = parseFilterAmount(filters.bankAmountMax)
    const q = filters.bankSearch.trim().toLowerCase()
    const entId = filters.bankEntity || null
    const status = filters.bankStatus
    return rawBankTxs.filter((b) => {
      if (entId && b.entity !== entId) return false
      if (status && b.reconciliation_status !== status) return false
      const n = Number(b.amount)
      if (min != null && n < min) return false
      if (max != null && n > max) return false
      if (q && !bankMatchesSearch(b, q, bankAccNameById)) return false
      return true
    })
  }, [
    rawBankTxs,
    filters.bankAmountMin,
    filters.bankAmountMax,
    filters.bankSearch,
    filters.bankEntity,
    filters.bankStatus,
    bankAccNameById,
  ])

  const journalEntries = useMemo(() => {
    const min = parseFilterAmount(filters.bookAmountMin)
    const max = parseFilterAmount(filters.bookAmountMax)
    const q = filters.bookSearch.trim().toLowerCase()
    const status = filters.bookStatus
    return rawJournalEntries.filter((je) => {
      if (status && je.reconciliation_status !== status) return false
      const n = Number(je.transaction_value)
      if (min != null && n < min) return false
      if (max != null && n > max) return false
      if (q && !bookMatchesSearch(je, q)) return false
      return true
    })
  }, [
    rawJournalEntries,
    filters.bookAmountMin,
    filters.bookAmountMax,
    filters.bookSearch,
    filters.bookStatus,
  ])

  // Per-pane sort state (client-side, applied after filtering).
  // Default to newest-first by date — matches the server ordering previously
  // used and the most common workflow ("newest unreconciled at top").
  const [bankSort, setBankSort] = useState<SortState<BankSortKey>>({ key: "date", dir: "desc" })
  const [bookSort, setBookSort] = useState<SortState<BookSortKey>>({ key: "date", dir: "desc" })

  // Per-pane pagination state. `size = 0` means "all" — pager hidden, full
  // list sent to the virtualizer (previous behaviour). Default to 100/page
  // so the pager surfaces immediately once the dataset is non-trivial.
  const [bankPage, setBankPage] = useState(1)
  const [bookPage, setBookPage] = useState(1)
  const [bankPageSize, setBankPageSize] = useState<number>(100)
  const [bookPageSize, setBookPageSize] = useState<number>(100)

  // Sorted views (applied to the client-filtered arrays above). The sort
  // runs over the already-narrow filtered list so cost stays bounded even
  // with 5k rows loaded.
  const sortedBankTxs = useMemo(() => {
    const arr = [...bankTxs]
    const dir = bankSort.dir === "asc" ? 1 : -1
    arr.sort((a, b) => {
      switch (bankSort.key) {
        case "id":
          return (a.id - b.id) * dir
        case "date":
          return a.date.localeCompare(b.date) * dir
        case "description":
          return (a.description ?? "").localeCompare(b.description ?? "", "pt-BR", { sensitivity: "base" }) * dir
        case "amount":
          return (Number(a.amount) - Number(b.amount)) * dir
        case "entity":
          return (a.entity_name ?? "").localeCompare(b.entity_name ?? "", "pt-BR", { sensitivity: "base" }) * dir
        case "status":
          return (a.reconciliation_status ?? "").localeCompare(b.reconciliation_status ?? "") * dir
        case "bank_account":
          return ((a.bank_account ?? 0) - (b.bank_account ?? 0)) * dir
        default:
          return 0
      }
    })
    return arr
  }, [bankTxs, bankSort])

  const sortedJournalEntries = useMemo(() => {
    const arr = [...journalEntries]
    const dir = bookSort.dir === "asc" ? 1 : -1
    arr.sort((a, b) => {
      switch (bookSort.key) {
        case "id":
          return (a.id - b.id) * dir
        case "date":
          return (a.transaction_date ?? "").localeCompare(b.transaction_date ?? "") * dir
        case "description":
          return (a.description ?? "").localeCompare(b.description ?? "", "pt-BR", { sensitivity: "base" }) * dir
        case "amount":
          return (Number(a.transaction_value) - Number(b.transaction_value)) * dir
        case "bank_account":
          return (a.bank_account?.name ?? "").localeCompare(b.bank_account?.name ?? "", "pt-BR", { sensitivity: "base" }) * dir
        case "status":
          return (a.reconciliation_status ?? "").localeCompare(b.reconciliation_status ?? "") * dir
        case "account": {
          const la = (a as unknown as { account?: { name?: string }; account_name?: string })
          const lb = (b as unknown as { account?: { name?: string }; account_name?: string })
          const sa = la.account?.name ?? la.account_name ?? ""
          const sb = lb.account?.name ?? lb.account_name ?? ""
          return sa.localeCompare(sb, "pt-BR", { sensitivity: "base" }) * dir
        }
        default:
          return 0
      }
    })
    return arr
  }, [journalEntries, bookSort])

  // Reset to page 1 whenever the underlying filtered/sorted count changes
  // (filter edits, new data, or a sort toggle that reorders the list).
  // Without this, paging state can point past the end of the dataset.
  useEffect(() => { setBankPage(1) }, [
    bankSort.key, bankSort.dir, bankTxs.length, bankPageSize,
  ])
  useEffect(() => { setBookPage(1) }, [
    bookSort.key, bookSort.dir, journalEntries.length, bookPageSize,
  ])

  // Paged slices — the virtualizer receives exactly these items. `size = 0`
  // bypasses paging (render everything).
  const bankPageCount = bankPageSize > 0 ? Math.max(1, Math.ceil(sortedBankTxs.length / bankPageSize)) : 1
  const bookPageCount = bookPageSize > 0 ? Math.max(1, Math.ceil(sortedJournalEntries.length / bookPageSize)) : 1
  const pagedBankTxs = useMemo(() => {
    if (bankPageSize === 0) return sortedBankTxs
    const start = (bankPage - 1) * bankPageSize
    return sortedBankTxs.slice(start, start + bankPageSize)
  }, [sortedBankTxs, bankPage, bankPageSize])
  const pagedJournalEntries = useMemo(() => {
    if (bookPageSize === 0) return sortedJournalEntries
    const start = (bookPage - 1) * bookPageSize
    return sortedJournalEntries.slice(start, start + bookPageSize)
  }, [sortedJournalEntries, bookPage, bookPageSize])

  // Footer sums — visible (post-filter) vs. raw (pre-filter). The pager
  // surfaces both so operators can sanity-check that a filter hides the
  // rows they expected (and nothing else).
  const bankSumVisible = useMemo(
    () => bankTxs.reduce((s, b) => s + Number(b.amount), 0),
    [bankTxs],
  )
  const bankSumTotal = useMemo(
    () => rawBankTxs.reduce((s, b) => s + Number(b.amount), 0),
    [rawBankTxs],
  )
  const bookSumVisible = useMemo(
    () => journalEntries.reduce((s, je) => s + Number(je.transaction_value), 0),
    [journalEntries],
  )
  const bookSumTotal = useMemo(
    () => rawJournalEntries.reduce((s, je) => s + Number(je.transaction_value), 0),
    [rawJournalEntries],
  )

  const [selectedBank, setSelectedBank] = useState<Set<number>>(new Set())
  const [selectedBook, setSelectedBook] = useState<Set<number>>(new Set())
  const [suggestion, setSuggestion] = useState<SuggestMatchResponse["suggestions"][number] | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [massOpen, setMassOpen] = useState(false)
  const [runRuleOpen, setRunRuleOpen] = useState(false)

  // Keyboard-driven cursor state
  const [activePane, setActivePane] = useState<"bank" | "book">("bank")
  const [cursorBank, setCursorBank] = useState(0)
  const [cursorBook, setCursorBook] = useState(0)

  const toggleBank = (id: number) => {
    setSuggestion(null)
    setSelectedBank((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleBook = (id: number) => {
    setSuggestion(null)
    setSelectedBook((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const clearSelection = () => {
    setSelectedBank(new Set())
    setSelectedBook(new Set())
    setSuggestion(null)
  }

  const selectedBankItems = useMemo(() => bankTxs.filter((x) => selectedBank.has(x.id)), [bankTxs, selectedBank])
  const selectedBookItems = useMemo(() => journalEntries.filter((x) => selectedBook.has(x.id)), [journalEntries, selectedBook])

  const bankSum = selectedBankItems.reduce((s, x) => s + Number(x.amount), 0)
  const bookSum = selectedBookItems.reduce((s, x) => s + Number(x.transaction_value), 0)
  const delta = bankSum - bookSum
  const balanced = Math.abs(delta) < 0.005
  const hasSelection = selectedBank.size > 0 || selectedBook.size > 0

  const [adjustment, setAdjustment] = useState<"none" | "bank" | "journal">("none")
  const finalize = useFinalizeMatches()
  const suggestApi = useSuggestMatches()
  const createSuggestions = useCreateSuggestions()

  const onMatch = () => {
    if (selectedBank.size === 0 || selectedBook.size === 0) {
      toast.error("Selecione ao menos 1 bancária e 1 contábil")
      return
    }
    const t0 = performance.now()
    finalize.mutate(
      {
        matches: [
          {
            bank_transaction_ids: Array.from(selectedBank),
            journal_entry_ids: Array.from(selectedBook),
            adjustment_side: adjustment,
          },
        ],
        adjustment_side: adjustment,
      },
      {
        onSuccess: (res) => {
          // Telemetry: matching is the primary workbench win-state.
          // Meta captures the selection shape so the admin funnel
          // view can distinguish 1:1 from 3:2 matches, etc.
          logAction("recon.match", {
            duration_ms: Math.round(performance.now() - t0),
            meta: {
              num_bank: selectedBank.size,
              num_book: selectedBook.size,
              adjustment_side: adjustment,
              created: res.created?.length ?? 0,
              problems: res.problems?.length ?? 0,
            },
          })
          if (res.problems?.length) toast.warning(`${res.created.length} criados, ${res.problems.length} com problemas`)
          else toast.success(t("workbench.matched_toast") ?? "Matched")
          clearSelection()
        },
        onError: (err: unknown) => {
          logError(err, { meta: { action: "recon.match", num_bank: selectedBank.size, num_book: selectedBook.size } })
          toast.error(err instanceof Error ? err.message : "Erro")
        },
      },
    )
  }

  // Keyboard navigation — cursor is relative to the rows currently
  // *displayed* (i.e. the paged slice), so j/k moves don't skip into items
  // the user can't see. Selection state still lives on the full filtered
  // set, so marked rows persist across pages.
  const paneLength = activePane === "bank" ? pagedBankTxs.length : pagedJournalEntries.length
  const setCursor = activePane === "bank" ? setCursorBank : setCursorBook
  const move = (delta: number) => {
    if (paneLength === 0) return
    setCursor((c) => Math.max(0, Math.min(paneLength - 1, c + delta)))
  }
  const toggleCursor = () => {
    if (paneLength === 0) return
    if (activePane === "bank") {
      const item = pagedBankTxs[cursorBank]
      if (item) toggleBank(item.id)
    } else {
      const item = pagedJournalEntries[cursorBook]
      if (item) toggleBook(item.id)
    }
  }

  useHotkeys("j, arrowdown", () => move(1), { enableOnFormTags: false })
  useHotkeys("k, arrowup", () => move(-1), { enableOnFormTags: false })
  useHotkeys("tab", (e) => { e.preventDefault(); setActivePane((p) => (p === "bank" ? "book" : "bank")) }, { enableOnFormTags: false })
  useHotkeys("x, space", (e) => { e.preventDefault(); toggleCursor() }, { enableOnFormTags: false })
  useHotkeys("shift+x", () => { clearSelection() }, { enableOnFormTags: false })
  useHotkeys("m", () => { if (selectedBank.size && selectedBook.size) onMatch() }, { enableOnFormTags: false })
  useHotkeys("s", () => { if (selectedBank.size === 1 && selectedBook.size === 0) onGenerateSuggestion() }, { enableOnFormTags: false })
  useHotkeys("slash", (e) => {
    e.preventDefault()
    const input = document.querySelector<HTMLInputElement>('input[placeholder="Descrição..."]')
    input?.focus()
  }, { enableOnFormTags: false })

  const onGenerateSuggestion = () => {
    if (selectedBank.size !== 1) return
    const id = Array.from(selectedBank)[0]!
    suggestApi.mutate(
      { bank_transaction_ids: [id], max_suggestions_per_bank: 3, min_confidence: 0.3 },
      {
        onSuccess: (res) => {
          setSuggestion(res.suggestions[0] ?? null)
          if (!res.suggestions[0] || res.suggestions[0].suggestions.length === 0) {
            toast.info(t("suggest_inline.no_suggestion") ?? "Sem sugestão")
          }
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  const onAcceptSuggestion = () => {
    if (!suggestion) return
    const item = suggestion.suggestions[0]
    if (!item) return
    const payload =
      item.suggestion_type === "use_existing_book"
        ? {
            suggestion_type: "use_existing_book",
            bank_transaction_id: suggestion.bank_transaction_id,
            existing_journal_entry_id: item.existing_journal_entry?.id,
            complementing_journal_entries: item.complementing_journal_entries ?? [],
          }
        : {
            suggestion_type: "create_new",
            bank_transaction_id: suggestion.bank_transaction_id,
            transaction: item.transaction,
            journal_entries: item.journal_entries ?? [],
          }
    createSuggestions.mutate(
      { suggestions: [payload] },
      {
        onSuccess: () => {
          toast.success(t("suggestions.applied_toast") ?? "Aplicado")
          clearSelection()
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <div className="flex h-[calc(100dvh-72px)] flex-col gap-3 md:h-[calc(100dvh-88px)] md:gap-4">
      <SectionHeader
        title={t("workbench.title")}
        subtitle={t("workbench.subtitle") ?? ""}
        actions={
          <div className="flex items-center gap-2">
            <SavedFiltersMenu
              tableKey="recon.workbench"
              currentParams={filters as unknown as Record<string, unknown>}
              onApply={(p) => setFilters({ ...BLANK_FILTERS, ...(p as unknown as Filters) })}
              isActive={(saved, current) => JSON.stringify(saved.params) === JSON.stringify(current)}
            />
            <button
              onClick={() => setRunRuleOpen(true)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90"
              title="Executar regra com os filtros atuais desta tela"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Executar regra
            </button>
          </div>
        }
      />

      <div className="grid min-h-0 flex-1 auto-rows-fr grid-cols-1 gap-2 md:grid-cols-2 md:auto-rows-auto md:gap-3">
        <Pane
          title={t("workbench.bank_pane")}
          icon={<Wallet className="h-3.5 w-3.5" />}
          count={bankTxs.length}
          rawCount={rawBankTxs.length}
          selectedCount={selectedBank.size}
          isLoading={bankLoading}
          isFetching={bankFetching}
          empty={t("workbench.empty")}
          active={activePane === "bank"}
          onFocus={() => setActivePane("bank")}
          headerAction={
            <div className="flex items-center gap-1.5">
              <SortMenu
                options={BANK_SORT_OPTIONS}
                value={bankSort}
                onChange={setBankSort}
              />
              <ColumnMenu
                columns={BANK_COLUMNS}
                isVisible={bankCols.isVisible}
                toggle={bankCols.toggle}
                showAll={bankCols.showAll}
                resetDefaults={bankCols.resetDefaults}
                label="Colunas"
              />
              <DownloadXlsxButton
                path="/api/bank_transactions/export_xlsx/"
                params={{
                  unreconciled: true,
                  bank_account: filters.bankAccount || undefined,
                  date_after: filters.bankDateFrom || undefined,
                  date_before: filters.bankDateTo || undefined,
                  ordering: "-date",
                }}
                label=""
                title="Baixar extratos filtrados (.xlsx)"
                className="px-2"
              />
            </div>
          }
          filters={
            <BankPaneFilters
              filters={filters}
              setFilters={setFilters}
              entities={entities ?? []}
              bankAccounts={bankAccounts ?? []}
            />
          }
          footer={
            <Pager
              total={sortedBankTxs.length}
              page={bankPage}
              pageCount={bankPageCount}
              pageSize={bankPageSize}
              onPage={setBankPage}
              onPageSize={setBankPageSize}
              sumVisible={bankSumVisible}
              sumTotal={bankSumTotal}
              rawTotal={rawBankTxs.length}
            />
          }
        >
          <BankList
            items={pagedBankTxs}
            selected={selectedBank}
            onToggle={toggleBank}
            cursorIndex={activePane === "bank" ? cursorBank : -1}
            isVisible={bankCols.isVisible}
            bankAccounts={bankAccounts ?? []}
          />
        </Pane>
        <Pane
          title={t("workbench.book_pane")}
          icon={<BookOpen className="h-3.5 w-3.5" />}
          count={journalEntries.length}
          rawCount={rawJournalEntries.length}
          selectedCount={selectedBook.size}
          isLoading={bookLoading}
          isFetching={bookFetching}
          empty={t("workbench.empty")}
          active={activePane === "book"}
          onFocus={() => setActivePane("book")}
          headerAction={
            <div className="flex items-center gap-1.5">
              <SortMenu
                options={BOOK_SORT_OPTIONS}
                value={bookSort}
                onChange={setBookSort}
              />
              <ColumnMenu
                columns={BOOK_COLUMNS}
                isVisible={bookCols.isVisible}
                toggle={bookCols.toggle}
                showAll={bookCols.showAll}
                resetDefaults={bookCols.resetDefaults}
                label="Colunas"
              />
              <DownloadXlsxButton
                path="/api/journal_entries/unmatched/"
                params={{
                  export: "xlsx",
                  date_from: filters.bookDateFrom || undefined,
                  date_to: filters.bookDateTo || undefined,
                  bank_account: filters.bookBankAccount || undefined,
                }}
                filename="lancamentos_pendentes.xlsx"
                label=""
                title="Baixar lançamentos filtrados (.xlsx)"
                className="px-2"
              />
            </div>
          }
          filters={
            <BookPaneFilters
              filters={filters}
              setFilters={setFilters}
              bankAccounts={bankAccounts ?? []}
            />
          }
          footer={
            <Pager
              total={sortedJournalEntries.length}
              page={bookPage}
              pageCount={bookPageCount}
              pageSize={bookPageSize}
              onPage={setBookPage}
              onPageSize={setBookPageSize}
              sumVisible={bookSumVisible}
              sumTotal={bookSumTotal}
              rawTotal={rawJournalEntries.length}
            />
          }
        >
          <BookList
            items={pagedJournalEntries}
            selected={selectedBook}
            onToggle={toggleBook}
            cursorIndex={activePane === "book" ? cursorBook : -1}
            isVisible={bookCols.isVisible}
          />
        </Pane>
      </div>

      {/* Selection panel — docked as a flex child at the bottom of the
          viewport column so the pane grid above naturally shrinks to fit
          (instead of being occluded by a `position: fixed` bar). The
          shadow keeps the visual separation of the previous sticky bar. */}
      <div className="shrink-0 rounded-md border border-border surface-2 px-3 py-2 shadow-[0_-4px_20px_-6px_rgba(0,0,0,0.4)] backdrop-blur md:px-4 md:py-3">
        {!hasSelection ? (
          <div className="flex items-center justify-center gap-2 text-[12px] text-muted-foreground">
            <AlertCircle className="h-3.5 w-3.5" />
            {t("summary.hint_empty")}
          </div>
        ) : (
          <SelectionSummary
            bankItems={selectedBankItems}
            bookItems={selectedBookItems}
            bankSum={bankSum}
            bookSum={bookSum}
            delta={delta}
            balanced={balanced}
            bankAccounts={bankAccounts ?? []}
            adjustment={adjustment}
            setAdjustment={setAdjustment}
            onClear={clearSelection}
            onMatch={onMatch}
            onSuggest={onGenerateSuggestion}
            onAddEntries={() => setAddOpen(true)}
            onMassReconcile={() => setMassOpen(true)}
            canSuggest={selectedBank.size === 1 && selectedBook.size === 0}
            suggestLoading={suggestApi.isPending}
            matching={finalize.isPending}
          />
        )}
        {suggestion && suggestion.suggestions[0] && (
          <SuggestionInline
            suggestion={suggestion}
            onAccept={onAcceptSuggestion}
            onClose={() => setSuggestion(null)}
            isPending={createSuggestions.isPending}
          />
        )}
      </div>

      <AddEntriesDrawer
        open={addOpen}
        onClose={() => setAddOpen(false)}
        bankItems={selectedBankItems}
        bookItems={selectedBookItems}
        bankSum={bankSum}
        bookSum={bookSum}
        delta={delta}
        bankAccounts={bankAccounts ?? []}
        onCreated={clearSelection}
      />

      <MassReconcileDrawer
        open={massOpen}
        onClose={() => setMassOpen(false)}
        bankItems={selectedBankItems}
        onCreated={clearSelection}
      />

      <RunRuleDrawer
        open={runRuleOpen}
        onClose={() => setRunRuleOpen(false)}
        initialBankFilters={workbenchFiltersToStacks(filters).bank}
        initialBookFilters={workbenchFiltersToStacks(filters).book}
        initialBankIds={Array.from(selectedBank)}
        initialBookIds={Array.from(selectedBook)}
        filtersHint="Usando os filtros atuais da bancada. Ajuste abaixo antes de executar."
      />

      <ShortcutHelp
        extra={[
          {
            title: "Bancada",
            items: [
              { keys: ["J", "↓"], label: "Cursor para baixo na coluna ativa" },
              { keys: ["K", "↑"], label: "Cursor para cima" },
              { keys: ["Tab"], label: "Alternar coluna (extrato ↔ livro)" },
              { keys: ["Space"], label: "Marcar/desmarcar linha do cursor" },
              { keys: ["X"], label: "Marcar/desmarcar linha do cursor" },
              { keys: ["Shift", "X"], label: "Limpar seleção" },
              { keys: ["M"], label: "Conciliar seleção atual" },
              { keys: ["S"], label: "Sugerir (1 extrato selecionado)" },
              { keys: ["/"], label: "Focar busca de descrição" },
            ],
          },
        ]}
      />
    </div>
  )
}

/* ---------------- Panes ---------------- */

function Pane({
  title, icon, count, rawCount, selectedCount, isLoading, isFetching, empty, children, active, onFocus, filters, headerAction, footer,
}: {
  title: string
  icon: React.ReactNode
  count: number
  rawCount?: number
  selectedCount: number
  isLoading: boolean
  isFetching?: boolean
  empty: string
  children: React.ReactNode
  active?: boolean
  onFocus?: () => void
  filters?: React.ReactNode
  /** Right-aligned slot in the pane header (e.g. column picker). */
  headerAction?: React.ReactNode
  /** Sticky footer slot (typically the pager). Rendered outside the
   *  scrolling/virtualised body so it's always visible and doesn't move
   *  with the rows. */
  footer?: React.ReactNode
}) {
  const isFiltered = rawCount != null && rawCount !== count
  const showRefreshSpinner = !!isFetching && !isLoading
  return (
    <div
      onClick={onFocus}
      className={cn(
        "card-elevated flex min-h-0 flex-col overflow-hidden transition-[box-shadow,border-color]",
        active && "ring-1 ring-primary/40",
      )}
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold">
          {icon}
          <span>{title}</span>
          <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground">
            <span className="tabular-nums">{count.toLocaleString("pt-BR")}</span>
            {isFiltered && (
              <span className="text-muted-foreground/70">/ {rawCount!.toLocaleString("pt-BR")}</span>
            )}
            {showRefreshSpinner && <Loader2 className="h-3 w-3 animate-spin text-primary/80" />}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {selectedCount > 0 && (
            <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
              {selectedCount} selecionados
            </span>
          )}
          {headerAction}
        </div>
      </div>
      {filters && (
        <div className="shrink-0 border-b border-border/60 bg-muted/20 px-3 py-2">{filters}</div>
      )}
      {/* Fetch progress bar — visible during background refetches */}
      {showRefreshSpinner && (
        <div className="h-px shrink-0 overflow-hidden bg-border">
          <div className="h-px w-1/3 animate-loadbar bg-primary/70" />
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        {isLoading ? (
          <div className="p-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="mb-2 h-10 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : count === 0 ? (
          <div className="flex h-full items-center justify-center gap-2 text-[12px] text-muted-foreground">
            <AlertCircle className="h-4 w-4" /> {empty}
          </div>
        ) : (
          children
        )}
      </div>
      {footer && (
        <div className="shrink-0 border-t border-border/60 bg-muted/10 px-2 py-1.5">
          {footer}
        </div>
      )}
    </div>
  )
}

/* ---------------- Sort menu (per pane) ---------------- */

/**
 * Compact inline sort control: a `<select>` for the field and a toggle
 * button for the direction. Renders in the right-aligned pane header slot
 * next to the column picker. Client-side only — the heavy lifting happens
 * in the sort `useMemo` in `WorkbenchPage`.
 */
function SortMenu<K extends string>({
  options,
  value,
  onChange,
}: {
  options: ReadonlyArray<{ key: K; label: string }>
  value: SortState<K>
  onChange: (v: SortState<K>) => void
}) {
  const toggleDir = () => onChange({ ...value, dir: value.dir === "asc" ? "desc" : "asc" })
  return (
    <div className="inline-flex h-7 items-center overflow-hidden rounded-md border border-border bg-background text-[11px] text-foreground">
      <span className="px-2 text-muted-foreground">Ordenar</span>
      {/* Native <select> intentionally takes `bg-background text-foreground`
          directly — the browser popup uses the element's own bg/fg, and
          `bg-transparent` defaults to the OS/browser light palette, which
          is why it rendered as an all-white dropdown on dark theme. */}
      <select
        value={value.key}
        onChange={(e) => onChange({ ...value, key: e.target.value as K })}
        className="h-7 bg-background pr-1 text-[11px] text-foreground outline-none [color-scheme:dark]"
        aria-label="Campo de ordenação"
      >
        {options.map((o) => (
          <option key={o.key} value={o.key} className="bg-background text-foreground">{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={toggleDir}
        className="inline-flex h-7 w-7 items-center justify-center border-l border-border hover:bg-accent"
        title={value.dir === "asc" ? "Crescente" : "Decrescente"}
        aria-label={value.dir === "asc" ? "Crescente" : "Decrescente"}
      >
        {value.dir === "asc"
          ? <ArrowUp className="h-3 w-3" />
          : <ArrowDown className="h-3 w-3" />}
      </button>
    </div>
  )
}

/* ---------------- Pager (per pane) ---------------- */

/**
 * Per-pane pagination controls. Reports "X–Y de N", offers a page-size
 * picker (50 / 100 / 250 / 500 / all), and first/prev/next/last buttons.
 * Driven entirely by client-side slicing — the underlying API still
 * returns the full unreconciled set so selection/sort work across pages.
 */
function Pager({
  total,
  page,
  pageCount,
  pageSize,
  onPage,
  onPageSize,
  sumVisible,
  sumTotal,
  rawTotal,
}: {
  total: number
  page: number
  pageCount: number
  pageSize: number
  onPage: (p: number) => void
  onPageSize: (s: number) => void
  /** Sum of the currently-filtered rows (what the user sees). */
  sumVisible?: number
  /** Sum of the unfiltered, server-returned rows (the "all" baseline). */
  sumTotal?: number
  /** Unfiltered row count, shown alongside sumTotal when filters are active. */
  rawTotal?: number
}) {
  const showAll = pageSize === 0
  const from = total === 0 ? 0 : showAll ? 1 : (page - 1) * pageSize + 1
  const to = showAll ? total : Math.min(total, page * pageSize)
  const goto = (p: number) => onPage(Math.max(1, Math.min(pageCount, p)))
  const isFiltered = rawTotal != null && rawTotal !== total

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-muted-foreground">
        <span>
          <span className="tabular-nums">{from.toLocaleString("pt-BR")}</span>
          <span className="mx-0.5">–</span>
          <span className="tabular-nums">{to.toLocaleString("pt-BR")}</span>
          <span className="mx-1">de</span>
          <span className="tabular-nums">{total.toLocaleString("pt-BR")}</span>
        </span>
        {sumVisible != null && (
          <span>
            <span className="mr-1">Soma visível:</span>
            <span className="tabular-nums text-foreground">{formatCurrency(sumVisible)}</span>
          </span>
        )}
        {isFiltered && sumTotal != null && (
          <span>
            <span className="mr-1">Total ({rawTotal!.toLocaleString("pt-BR")}):</span>
            <span className="tabular-nums">{formatCurrency(sumTotal)}</span>
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <select
          value={pageSize}
          onChange={(e) => onPageSize(Number(e.target.value))}
          className="h-6 rounded-md border border-border bg-background px-1.5 text-[11px] outline-none focus:border-ring"
          aria-label="Tamanho da página"
        >
          {PAGE_SIZE_OPTIONS.map((s) => (
            <option key={s} value={s}>{s === 0 ? "Todos" : `${s}/pág`}</option>
          ))}
        </select>
        {!showAll && (
          <div className="inline-flex items-center overflow-hidden rounded-md border border-border bg-background">
            <button
              type="button"
              onClick={() => goto(1)}
              disabled={page <= 1}
              className="inline-flex h-6 w-6 items-center justify-center hover:bg-accent disabled:opacity-40"
              aria-label="Primeira página"
            >
              <ChevronsLeft className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={() => goto(page - 1)}
              disabled={page <= 1}
              className="inline-flex h-6 w-6 items-center justify-center border-l border-border hover:bg-accent disabled:opacity-40"
              aria-label="Página anterior"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
            <span className="border-l border-border px-2 tabular-nums text-muted-foreground">
              {page}/{pageCount}
            </span>
            <button
              type="button"
              onClick={() => goto(page + 1)}
              disabled={page >= pageCount}
              className="inline-flex h-6 w-6 items-center justify-center border-l border-border hover:bg-accent disabled:opacity-40"
              aria-label="Próxima página"
            >
              <ChevronRight className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={() => goto(pageCount)}
              disabled={page >= pageCount}
              className="inline-flex h-6 w-6 items-center justify-center border-l border-border hover:bg-accent disabled:opacity-40"
              aria-label="Última página"
            >
              <ChevronsRight className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------- Per-pane filter rows ---------------- */

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Todos" },
  { value: "pending", label: "Pendente" },
  { value: "suggested", label: "Sugerido" },
  { value: "matched", label: "Conciliado" },
  { value: "cancelled", label: "Cancelado" },
]

/**
 * Compact date+date+select "scope row" displayed above the per-pane filter
 * chips. Keeps the server-side filters (date range + bank account) visible
 * and editable inline on the pane they affect.
 */
function ScopeRow({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-1.5">{children}</div>
}

/**
 * Compact amount filter input with an inline × clear button. Kept in this
 * file because it's specific to the workbench filter bar — zero should be a
 * valid filter value, and an empty string must be explicitly representable
 * (not "any falsy"). See parseFilterAmount for the predicate side.
 */
function AmountFilterInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (next: string) => void
  placeholder?: string
}) {
  const hasValue = value.trim() !== ""
  return (
    <div className="relative w-16 md:w-24">
      <input
        type="number"
        step="0.01"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-7 w-full rounded-md border border-border bg-background pl-2 pr-5 text-[11px] tabular-nums outline-none focus:border-ring"
      />
      {hasValue && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Limpar filtro"
          className="absolute right-1 top-1/2 grid h-4 w-4 -translate-y-1/2 place-items-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

function DateRange({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string
  to: string
  onFrom: (v: string) => void
  onTo: (v: string) => void
}) {
  return (
    <div className="flex items-center gap-1">
      <input
        type="date"
        value={from}
        onChange={(e) => onFrom(e.target.value)}
        className="h-7 rounded-md border border-border bg-background px-1.5 text-[11px] outline-none focus:border-ring"
      />
      <span className="text-[11px] text-muted-foreground">→</span>
      <input
        type="date"
        value={to}
        onChange={(e) => onTo(e.target.value)}
        className="h-7 rounded-md border border-border bg-background px-1.5 text-[11px] outline-none focus:border-ring"
      />
    </div>
  )
}

function BankPaneFilters({
  filters,
  setFilters,
  entities,
  bankAccounts,
}: {
  filters: Filters
  setFilters: React.Dispatch<React.SetStateAction<Filters>>
  entities: Array<{ id: number; name: string; path: string }>
  bankAccounts: Array<{ id: number; name: string }>
}) {
  const hasClientFilters =
    !!(filters.bankSearch || filters.bankAmountMin || filters.bankAmountMax ||
      filters.bankStatus || filters.bankEntity)
  const hasScopeFilters =
    filters.bankAccount !== "" ||
    filters.bankDateFrom !== DEFAULT_DATE_FROM ||
    filters.bankDateTo !== DEFAULT_DATE_TO

  return (
    <div className="flex flex-col gap-1.5">
      {/* Scope row (server-side): date range + bank account */}
      <ScopeRow>
        <DateRange
          from={filters.bankDateFrom}
          to={filters.bankDateTo}
          onFrom={(v) => setFilters((f) => ({ ...f, bankDateFrom: v }))}
          onTo={(v) => setFilters((f) => ({ ...f, bankDateTo: v }))}
        />
        <select
          value={filters.bankAccount}
          onChange={(e) => setFilters((f) => ({ ...f, bankAccount: e.target.value ? Number(e.target.value) : "" }))}
          className="h-7 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring md:max-w-[200px] md:flex-initial"
        >
          <option value="">Todas contas</option>
          {bankAccounts.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
        {hasScopeFilters && (
          <button
            onClick={() =>
              setFilters((f) => ({
                ...f,
                bankDateFrom: DEFAULT_DATE_FROM,
                bankDateTo: DEFAULT_DATE_TO,
                bankAccount: "",
              }))
            }
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] text-muted-foreground hover:bg-accent"
            title="Redefinir escopo do banco"
          >
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </ScopeRow>

      {/* Chip row (client-side refinement) */}
      <div className="flex flex-wrap items-center gap-1.5 md:gap-2">
        <div className="relative min-w-[140px] flex-1 basis-[140px] md:max-w-[220px] md:flex-initial">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filters.bankSearch}
            onChange={(e) => setFilters((f) => ({ ...f, bankSearch: e.target.value }))}
            placeholder="Descrição…"
            className="h-7 w-full rounded-md border border-border bg-background pl-7 pr-2 text-[11px] outline-none focus:border-ring"
          />
        </div>
        <AmountFilterInput
          value={filters.bankAmountMin}
          onChange={(v) => setFilters((f) => ({ ...f, bankAmountMin: v }))}
          placeholder="Min"
        />
        <AmountFilterInput
          value={filters.bankAmountMax}
          onChange={(v) => setFilters((f) => ({ ...f, bankAmountMax: v }))}
          placeholder="Max"
        />
        <select
          value={filters.bankEntity}
          onChange={(e) => setFilters((f) => ({ ...f, bankEntity: e.target.value ? Number(e.target.value) : "" }))}
          className="h-7 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring md:max-w-[160px] md:flex-initial"
        >
          <option value="">Todas entidades</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>{e.path ?? e.name}</option>
          ))}
        </select>
        <select
          value={filters.bankStatus}
          onChange={(e) => setFilters((f) => ({ ...f, bankStatus: e.target.value }))}
          className="h-7 rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {hasClientFilters && (
          <button
            onClick={() =>
              setFilters((f) => ({
                ...f,
                bankSearch: "",
                bankAmountMin: "",
                bankAmountMax: "",
                bankStatus: "",
                bankEntity: "",
              }))
            }
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] text-muted-foreground hover:bg-accent"
            title="Limpar filtros do banco"
          >
            <RotateCcw className="h-3 w-3" />
            <span className="hidden sm:inline">Limpar</span>
          </button>
        )}
      </div>
    </div>
  )
}

function BookPaneFilters({
  filters,
  setFilters,
  bankAccounts,
}: {
  filters: Filters
  setFilters: React.Dispatch<React.SetStateAction<Filters>>
  bankAccounts: Array<{ id: number; name: string }>
}) {
  const hasClientFilters =
    !!(filters.bookSearch || filters.bookAmountMin || filters.bookAmountMax ||
      filters.bookStatus)
  const hasScopeFilters =
    filters.bookBankAccount !== "" ||
    filters.bookDateFrom !== DEFAULT_DATE_FROM ||
    filters.bookDateTo !== DEFAULT_DATE_TO

  return (
    <div className="flex flex-col gap-1.5">
      <ScopeRow>
        <DateRange
          from={filters.bookDateFrom}
          to={filters.bookDateTo}
          onFrom={(v) => setFilters((f) => ({ ...f, bookDateFrom: v }))}
          onTo={(v) => setFilters((f) => ({ ...f, bookDateTo: v }))}
        />
        <select
          value={filters.bookBankAccount}
          onChange={(e) => setFilters((f) => ({ ...f, bookBankAccount: e.target.value ? Number(e.target.value) : "" }))}
          className="h-7 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring md:max-w-[200px] md:flex-initial"
        >
          <option value="">Todas contas</option>
          {bankAccounts.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
        {hasScopeFilters && (
          <button
            onClick={() =>
              setFilters((f) => ({
                ...f,
                bookDateFrom: DEFAULT_DATE_FROM,
                bookDateTo: DEFAULT_DATE_TO,
                bookBankAccount: "",
              }))
            }
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] text-muted-foreground hover:bg-accent"
            title="Redefinir escopo contábil"
          >
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </ScopeRow>

      <div className="flex flex-wrap items-center gap-1.5 md:gap-2">
        <div className="relative min-w-[140px] flex-1 basis-[140px] md:max-w-[220px] md:flex-initial">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filters.bookSearch}
            onChange={(e) => setFilters((f) => ({ ...f, bookSearch: e.target.value }))}
            placeholder="Descrição…"
            className="h-7 w-full rounded-md border border-border bg-background pl-7 pr-2 text-[11px] outline-none focus:border-ring"
          />
        </div>
        <AmountFilterInput
          value={filters.bookAmountMin}
          onChange={(v) => setFilters((f) => ({ ...f, bookAmountMin: v }))}
          placeholder="Min"
        />
        <AmountFilterInput
          value={filters.bookAmountMax}
          onChange={(v) => setFilters((f) => ({ ...f, bookAmountMax: v }))}
          placeholder="Max"
        />
        <select
          value={filters.bookStatus}
          onChange={(e) => setFilters((f) => ({ ...f, bookStatus: e.target.value }))}
          className="h-7 rounded-md border border-border bg-background px-2 text-[11px] outline-none focus:border-ring"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {hasClientFilters && (
          <button
            onClick={() =>
              setFilters((f) => ({
                ...f,
                bookSearch: "",
                bookAmountMin: "",
                bookAmountMax: "",
                bookStatus: "",
              }))
            }
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] text-muted-foreground hover:bg-accent"
            title="Limpar filtros contábeis"
          >
            <RotateCcw className="h-3 w-3" />
            <span className="hidden sm:inline">Limpar</span>
          </button>
        )}
      </div>
    </div>
  )
}

function BankList({
  items, selected, onToggle, cursorIndex = -1, isVisible, bankAccounts = [],
}: {
  items: BankTransaction[]
  selected: Set<number>
  onToggle: (id: number) => void
  cursorIndex?: number
  isVisible?: (key: string) => boolean
  bankAccounts?: Array<{ id: number; name: string }>
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virt = useVirtualizer({ count: items.length, getScrollElement: () => parentRef.current, estimateSize: () => 52, overscan: 10 })
  const vis = isVisible ?? (() => true)
  const bankAccNameById = useMemo(
    () => Object.fromEntries(bankAccounts.map((b) => [b.id, b.name])),
    [bankAccounts],
  )

  // Keep the cursor row in view
  useEffect(() => {
    if (cursorIndex >= 0) virt.scrollToIndex(cursorIndex, { align: "auto" })
  }, [cursorIndex, virt])

  return (
    <div ref={parentRef} className="h-full overflow-y-auto">
      <div style={{ height: virt.getTotalSize(), position: "relative" }}>
        {virt.getVirtualItems().map((vi) => {
          const item = items[vi.index]!
          const isSel = selected.has(item.id)
          const isCursor = vi.index === cursorIndex
          const bankAccName = item.bank_account != null ? bankAccNameById[item.bank_account] : undefined
          return (
            <button
              key={item.id}
              onClick={() => onToggle(item.id)}
              style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vi.start}px)`, height: vi.size }}
              className={cn(
                "flex w-full items-center gap-2 border-b border-border/60 px-3 text-left text-[12px] transition-colors",
                isSel ? "bg-primary/10 hover:bg-primary/15" : "hover:bg-accent/50",
                isCursor && "ring-1 ring-inset ring-primary/60",
              )}
            >
              <input type="checkbox" checked={isSel} readOnly className="h-3.5 w-3.5 shrink-0 accent-primary" />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center gap-2">
                  {vis("id") && (
                    <span className="font-mono text-[10px] text-muted-foreground">#{item.id}</span>
                  )}
                  <span className="truncate">{item.description}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                  {vis("date") && <span>{formatDate(item.date)}</span>}
                  {vis("entity") && item.entity_name && <span>· {item.entity_name}</span>}
                  {vis("bank_account") && bankAccName && <span>· {bankAccName}</span>}
                  {vis("erp_id") && item.erp_id && (
                    <span className="font-mono">· erp {item.erp_id}</span>
                  )}
                  {vis("cnpj") && item.cnpj && (
                    <span className="font-mono">· {item.cnpj}</span>
                  )}
                  {vis("boletos") && item.numeros_boleto && item.numeros_boleto.length > 0 && (
                    <span className="font-mono">
                      · bol {item.numeros_boleto.slice(0, 2).join(", ")}
                      {item.numeros_boleto.length > 2 ? ` +${item.numeros_boleto.length - 2}` : ""}
                    </span>
                  )}
                  {vis("status") && <StatusBadge status={item.reconciliation_status} className="h-4" />}
                </div>
              </div>
              <div className={cn("shrink-0 text-right tabular-nums font-semibold", Number(item.amount) < 0 ? "text-muted-foreground" : "text-foreground")}>
                {formatCurrency(Number(item.amount))}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function BookList({
  items, selected, onToggle, cursorIndex = -1, isVisible,
}: {
  items: JournalEntry[]
  selected: Set<number>
  onToggle: (id: number) => void
  cursorIndex?: number
  isVisible?: (key: string) => boolean
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virt = useVirtualizer({ count: items.length, getScrollElement: () => parentRef.current, estimateSize: () => 52, overscan: 10 })
  const vis = isVisible ?? (() => true)

  useEffect(() => {
    if (cursorIndex >= 0) virt.scrollToIndex(cursorIndex, { align: "auto" })
  }, [cursorIndex, virt])

  return (
    <div ref={parentRef} className="h-full overflow-y-auto">
      <div style={{ height: virt.getTotalSize(), position: "relative" }}>
        {virt.getVirtualItems().map((vi) => {
          const item = items[vi.index]!
          const isSel = selected.has(item.id)
          const amt = Number(item.transaction_value)
          const isCursor = vi.index === cursorIndex
          // Account name (the contra/ledger account the JE posts to). The
          // JournalEntry shape exposes account as a reference object or a
          // plain name string depending on serializer context; fall back
          // gracefully either way.
          const acctRef = (item as unknown as { account?: { name?: string; account_code?: string } | null; account_name?: string })
          const acctLabel = acctRef.account?.name ?? acctRef.account_name
          return (
            <button
              key={item.id}
              onClick={() => onToggle(item.id)}
              style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vi.start}px)`, height: vi.size }}
              className={cn(
                "flex w-full items-center gap-2 border-b border-border/60 px-3 text-left text-[12px] transition-colors",
                isSel ? "bg-primary/10 hover:bg-primary/15" : "hover:bg-accent/50",
                isCursor && "ring-1 ring-inset ring-primary/60",
              )}
            >
              <input type="checkbox" checked={isSel} readOnly className="h-3.5 w-3.5 shrink-0 accent-primary" />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center gap-2">
                  {vis("id") && (
                    <span className="font-mono text-[10px] text-muted-foreground">#{item.id}</span>
                  )}
                  <span className="truncate">{item.description}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                  {vis("date") && <span>{formatDate(item.transaction_date)}</span>}
                  {vis("bank_account") && item.bank_account?.name && <span>· {item.bank_account.name}</span>}
                  {vis("account") && acctLabel && <span>· {acctLabel}</span>}
                  {vis("erp_id") && item.erp_id && (
                    <span className="font-mono">· erp {item.erp_id}</span>
                  )}
                  {vis("cnpj") && item.cnpj && (
                    <span className="font-mono">· {item.cnpj}</span>
                  )}
                  {vis("nf_number") && item.nf_number && (
                    <span className="font-mono">· NF {item.nf_number}</span>
                  )}
                  {vis("boleto") && item.numero_boleto && (
                    <span className="font-mono">· bol {item.numero_boleto}</span>
                  )}
                  {vis("status") && <StatusBadge status={item.reconciliation_status} className="h-4" />}
                </div>
              </div>
              <div className={cn("shrink-0 text-right tabular-nums font-semibold", amt < 0 ? "text-muted-foreground" : "text-foreground")}>
                {formatCurrency(amt)}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ---------------- Selection summary panel ---------------- */

function SelectionSummary({
  bankItems, bookItems, bankSum, bookSum, delta, balanced,
  bankAccounts, adjustment, setAdjustment,
  onClear, onMatch, onSuggest, onAddEntries, onMassReconcile,
  canSuggest, suggestLoading, matching,
}: {
  bankItems: BankTransaction[]
  bookItems: JournalEntry[]
  bankSum: number
  bookSum: number
  delta: number
  balanced: boolean
  bankAccounts: Array<{ id: number; name: string; currency?: { code: string } | null }>
  adjustment: "none" | "bank" | "journal"
  setAdjustment: (v: "none" | "bank" | "journal") => void
  onClear: () => void
  onMatch: () => void
  onSuggest: () => void
  onAddEntries: () => void
  onMassReconcile: () => void
  canSuggest: boolean
  suggestLoading: boolean
  matching: boolean
}) {
  const { t } = useTranslation(["reconciliation", "common"])

  // Compatibility checks
  const bankEntities = new Set(bankItems.map((b) => b.entity).filter(Boolean))
  const bookAccountIds = new Set(bookItems.map((b) => b.bank_account?.id).filter(Boolean))
  const sameEntity = bankEntities.size <= 1

  const bankDates = bankItems.map((b) => b.date).sort()
  const bookDates = bookItems.map((b) => b.transaction_date).sort()
  const allDates = [...bankDates, ...bookDates].sort()
  const dateFrom = allDates[0]
  const dateTo = allDates[allDates.length - 1]
  const dateSpanDays =
    dateFrom && dateTo ? Math.abs((new Date(dateTo).getTime() - new Date(dateFrom).getTime()) / 86400000) : 0
  const datesClose = dateSpanDays <= 7

  // Currency: inferred from first bank account
  const firstBankAccId = bankItems[0]?.bank_account
  const bankAcc = firstBankAccId ? bankAccounts.find((b) => b.id === firstBankAccId) : null
  const currencyCode = bankAcc?.currency?.code ?? "BRL"

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <div className="flex items-center gap-1 rounded-md border border-border bg-surface-3 px-2 py-1">
          <Wallet className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">{bankItems.length}</span>
          <span className="tabular-nums font-semibold">{formatCurrency(bankSum, currencyCode)}</span>
        </div>
        <ArrowLeftRight className="h-3 w-3 text-muted-foreground" />
        <div className="flex items-center gap-1 rounded-md border border-border bg-surface-3 px-2 py-1">
          <BookOpen className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">{bookItems.length}</span>
          <span className="tabular-nums font-semibold">{formatCurrency(bookSum, currencyCode)}</span>
        </div>
        <div
          className={cn(
            "flex items-center gap-1 rounded-md border px-2 py-1 tabular-nums font-semibold",
            balanced
              ? "border-border bg-surface-3 text-muted-foreground"
              : "border-warning/30 bg-warning/10 text-warning",
          )}
        >
          Δ {formatCurrency(delta, currencyCode)}
        </div>

        {/* Compatibility — only render chips when not OK */}
        {!sameEntity && (
          <CheckChip ok={false} okText="" warnText={t("summary.checks.entity_mismatch")} />
        )}
        {!datesClose && (
          <CheckChip
            ok={false}
            okText=""
            warnText={t("summary.checks.date_far", { days: dateSpanDays.toFixed(0) })}
          />
        )}
        {dateFrom && dateTo && (
          <span className="text-[11px] text-muted-foreground">
            {formatDate(dateFrom)} – {formatDate(dateTo)}
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {!balanced && bookItems.length > 0 && (
            <select
              value={adjustment}
              onChange={(e) => setAdjustment(e.target.value as "none" | "bank" | "journal")}
              className="h-8 rounded-md border border-border bg-background px-2 text-[12px]"
            >
              <option value="none">{t("workbench.adjustment.none")}</option>
              <option value="bank">{t("workbench.adjustment.bank")}</option>
              <option value="journal">{t("workbench.adjustment.journal")}</option>
            </select>
          )}
          <button
            onClick={onSuggest}
            disabled={!canSuggest || suggestLoading}
            title={!canSuggest ? t("suggest_inline.only_one_bank") ?? "" : undefined}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
          >
            <Sparkles className={cn("h-3.5 w-3.5", suggestLoading && "animate-pulse")} />
            {t("suggest_inline.generate")}
          </button>
          <button
            onClick={onAddEntries}
            disabled={bankItems.length === 0}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            {t("add_entries.title")}
          </button>
          {/* Mass 1-to-1 reconciliation: pop open a list of the selected
              bank rows and let the operator assign an account to many at
              once. Only surfaces when the selection is bank-only (2+) —
              for mixed bank/book selections the single-reconciliation
              drawer (AddEntriesDrawer) is the right entry point. */}
          <button
            onClick={onMassReconcile}
            disabled={bankItems.length < 2 || bookItems.length > 0}
            title={
              bookItems.length > 0
                ? "Desmarque lançamentos contábeis para usar conciliação em massa"
                : bankItems.length < 2
                ? "Selecione 2 ou mais bancárias"
                : `Conciliação em massa (${bankItems.length} bancárias)`
            }
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-50"
          >
            <Wand2 className="h-3.5 w-3.5" />
            Em massa
          </button>
          <button
            onClick={onClear}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            <X className="h-3.5 w-3.5" />
            {t("workbench.selection.clear")}
          </button>
          <button
            onClick={onMatch}
            disabled={matching || bookItems.length === 0}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Check className="h-3.5 w-3.5" />
            {t("workbench.selection.match")}
          </button>
        </div>
      </div>
      {bookAccountIds.size > 0 && firstBankAccId && !bookAccountIds.has(firstBankAccId) && (
        <div className="flex items-center gap-1.5 text-[11px] text-warning">
          <AlertTriangle className="h-3 w-3" /> A conta bancária dos lançamentos não coincide com a do extrato selecionado.
        </div>
      )}
    </div>
  )
}

function CheckChip({ ok, okText, warnText }: { ok: boolean; okText: string; warnText: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        ok
          ? "border-success/30 bg-success/10 text-success"
          : "border-warning/30 bg-warning/10 text-warning",
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
      {ok ? okText : warnText}
    </span>
  )
}

/* ---------------- Inline suggestion card ---------------- */

function SuggestionInline({
  suggestion, onAccept, onClose, isPending,
}: {
  suggestion: SuggestMatchResponse["suggestions"][number]
  onAccept: () => void
  onClose: () => void
  isPending: boolean
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const best = suggestion.suggestions[0]
  if (!best) return null
  const pct = Math.max(0, Math.min(1, best.confidence_score))
  const kind = best.suggestion_type === "use_existing_book" ? t("suggest_inline.use_existing_hint") : t("suggest_inline.create_new_hint")

  return (
    <div className="mt-2 flex items-start gap-3 rounded-md border border-info/30 bg-info/10 p-2.5 text-[12px]">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-info" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{t("suggest_inline.title")}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">{kind}</span>
          <div className="ml-2 flex items-center gap-1.5">
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-3">
              <div
                className={cn("h-full", pct >= 0.85 ? "bg-success" : pct >= 0.7 ? "bg-warning" : "bg-danger")}
                style={{ width: `${pct * 100}%` }}
              />
            </div>
            <span className="w-10 text-right text-[10px] tabular-nums">{(pct * 100).toFixed(0)}%</span>
          </div>
        </div>
        <SuggestionBody item={best} />
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          onClick={onAccept}
          disabled={isPending}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2.5 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
        >
          <Check className="h-3 w-3" />
          {t("suggest_inline.accept")}
        </button>
        <button
          onClick={onClose}
          className="grid h-7 w-7 place-items-center rounded-md border border-border hover:bg-accent"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

function SuggestionBody({ item }: { item: SuggestionItem }) {
  if (item.suggestion_type === "use_existing_book" && item.existing_journal_entry) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-mono">#{item.existing_journal_entry.id}</span>
        <span>{item.existing_journal_entry.account_code} {item.existing_journal_entry.account_name}</span>
        {(item.complementing_journal_entries ?? []).length > 0 && (
          <span>· {item.complementing_journal_entries!.length} complemento(s)</span>
        )}
      </div>
    )
  }
  if (item.suggestion_type === "create_new" && item.transaction) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>{item.transaction.description}</span>
        <span>· {(item.journal_entries ?? []).length} lançamento(s)</span>
        {item.match_count != null && <span>· {item.match_count} matches hist.</span>}
      </div>
    )
  }
  return null
}

/* ---------------- Add entries drawer ---------------- */

type EntryRow = {
  account_id: number | ""
  side: "debit" | "credit"
  amount: string
  description: string
  /** YYYY-MM-DD; empty means "inherit from the transaction". */
  date: string
}

function newEntryRow(partial: Partial<EntryRow> = {}): EntryRow {
  return { account_id: "", side: "debit", amount: "", description: "", date: "", ...partial }
}

/**
 * Raw ``debit − credit`` for a row, ignoring direction. Used for
 * the Transaction-balance check: the new adjustment Transaction the
 * backend builds must satisfy ``Σdebit == Σcredit``, which is a raw-
 * number invariant, not an effective-amount one.
 *
 * (An earlier version of this helper multiplied by account direction
 * to match the reconciliation-closure check; that was a mistake for
 * mixed-direction contras — see the test
 * ``test_case2_mixed_direction_contra_balances`` for the concrete
 * case where effective-sum ≠ 0 but the transaction is perfectly
 * balanced.)
 */
function rowRawAmount(r: EntryRow): number {
  const amt = Number(r.amount || 0)
  if (!Number.isFinite(amt)) return 0
  return r.side === "debit" ? amt : -amt
}

/**
 * The contra row's raw side (debit/credit) is the **mirror** of the
 * auto-booked cash leg's side, because a balanced Transaction needs
 * Σdebit == Σcredit. With the standard Ativo-Circulante cash account
 * (direction=1):
 *
 *   delta < 0 (bank outflow) → cash credits |δ| → contra **debits** |δ|
 *   delta > 0 (bank inflow)  → cash debits  |δ| → contra **credits** |δ|
 *   delta = 0 → caller shouldn't open the drawer; default debit.
 *
 * An earlier version used ``delta >= 0 ? "debit" : "credit"`` — the
 * PR-C convention where the row itself was the book entry. That was
 * wrong in the PR-8 world: the row is the *contra*, the cash leg is
 * auto-booked, and the two sides must net to zero in raw terms.
 */
function contraSideForDelta(delta: number): "debit" | "credit" {
  return delta < 0 ? "debit" : "credit"
}

/**
 * Build the default first row from the bank transaction + delta. We
 * pre-populate the amount with the remaining difference and pre-fill the
 * description from the bank record so the user starts from a full row they
 * can tweak rather than a blank one.
 */
function seedInitialRows(bank: BankTransaction | undefined, delta: number): EntryRow[] {
  if (!bank) return [newEntryRow()]
  const amt = Math.abs(delta) > 0.005 ? Math.abs(delta).toFixed(2) : ""
  return [newEntryRow({
    amount: amt,
    side: contraSideForDelta(delta),
    description: bank.description ?? "",
    date: bank.date ?? "",
  })]
}

function AddEntriesDrawer({
  open, onClose, bankItems, bookItems, bankSum, bookSum, delta,
  bankAccounts, onCreated,
}: {
  open: boolean
  onClose: () => void
  bankItems: BankTransaction[]
  bookItems: JournalEntry[]
  /** Effective sum of selected bank rows (just bankItems[i].amount). */
  bankSum: number
  /** Effective sum of selected book rows — direction-aware, so this is
   *  the same baseline the reconciliation engine uses when summing. */
  bookSum: number
  /** bankSum − bookSum; target the new entries need to close. */
  delta: number
  /** Ledger of bank accounts — just for the cash-leg preview row. */
  bankAccounts: Array<{ id: number; name: string }>
  onCreated: () => void
}) {
  const { t } = useTranslation(["reconciliation", "common"])
  const { data: accounts = [] } = useAccounts()
  const createSuggestions = useCreateSuggestions()

  // Restrict the dropdown to leaf accounts — journal entries should never
  // post to a group / parent. We derive leaf-ness client-side by checking
  // whether any other account has this one as parent (the serializer
  // doesn't expose is_leaf directly).
  const leafAccounts = useMemo<AccountLite[]>(() => {
    const parents = new Set<number>()
    for (const a of accounts) {
      if (a.parent != null) parents.add(a.parent)
    }
    return (accounts as AccountLite[])
      .filter((a) => a.is_active !== false && !parents.has(a.id))
      .sort((a, b) => (a.account_code ?? "").localeCompare(b.account_code ?? "", undefined, { numeric: true })
        || a.path.localeCompare(b.path, undefined, { numeric: true }))
  }, [accounts])

  const [rows, setRows] = useState<EntryRow[]>([newEntryRow()])

  useEffect(() => {
    if (open) {
      setRows(seedInitialRows(bankItems[0], delta))
    }
  }, [open, bankItems, delta])

  const updateRow = (i: number, patch: Partial<EntryRow>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const removeRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i))
  const addRow = () => {
    // New rows inherit the bank description so the operator doesn't retype
    // it on every split; the pre-filled side absorbs the *remaining*
    // gap toward the contra target (= -delta). Same mirror-of-cash rule
    // as seedInitialRows: a positive remaining means "need more debits".
    const bank = bankItems[0]
    setRows((rs) => {
      const contraTarget = -delta  // total raw sum contras must hit
      const contraSoFar = rs.reduce((s, r) => s + rowRawAmount(r), 0)
      const remaining = contraTarget - contraSoFar
      return [
        ...rs,
        newEntryRow({
          description: bank?.description ?? "",
          date: bank?.date ?? "",
          // remaining > 0 → need positive raw (debit). remaining < 0 → credit.
          side: remaining >= 0 ? "debit" : "credit",
          amount: Math.abs(remaining) > 0.005 ? Math.abs(remaining).toFixed(2) : "",
        }),
      ]
    })
  }

  // PR 8 semantic shift: the drawer's contra entries no longer enter
  // the reconciliation directly. The backend creates a separate,
  // balanced adjustment Transaction: a cash leg on the bank's CoA
  // account (effective == delta → recon closes automatically) plus
  // the contra legs the operator typed here. For the new Transaction
  // to satisfy Σdebit == Σcredit, the raw contra sum must equal
  // ``-delta`` (assuming the cash account direction = 1, which is
  // the standard for Brazilian bank CoA accounts).
  //
  //   Bank outflow (delta < 0) → contras must net to a DEBIT of |delta|
  //   Bank inflow  (delta > 0) → contras must net to a CREDIT of |delta|
  const contraRawSum = rows.reduce((s, r) => s + rowRawAmount(r), 0)
  const target = -delta  // what Σ(debit - credit) of contras must equal
  const balanceOk = Math.abs(contraRawSum - target) < 0.005
  const hasRows = rows.some((r) => r.account_id && Number(r.amount) > 0)
  // The backend now enforces Σdebit == Σcredit on the new
  // adjustment Transaction — no "create anyway" escape hatch.
  const canSubmit = hasRows && balanceOk

  const submit = () => {
    if (!hasRows) {
      toast.error(t("add_entries.must_have_rows") ?? "Adicione linhas")
      return
    }
    if (!balanceOk) {
      toast.error(t("add_entries.must_balance_toast") ?? "Deve fechar")
      return
    }
    if (bankItems.length !== 1) {
      toast.error("Selecione exatamente 1 transação bancária")
      return
    }
    const bank = bankItems[0]!

    const complementing = rows
      .filter((r) => r.account_id && Number(r.amount) > 0)
      .map((r) => ({
        account_id: r.account_id as number,
        debit_amount: r.side === "debit" ? String(Number(r.amount)) : null,
        credit_amount: r.side === "credit" ? String(Number(r.amount)) : null,
        // Per-row description: no global consolidated field anymore. Falls
        // back to the bank description only if the row itself is empty.
        description: r.description?.trim() || bank.description,
        // Per-row date: operators can stamp each split with its own date
        // (e.g. a tariff posted on a later ledger close). The backend
        // falls back to the transaction date when this is empty, so the
        // existing bank-date default is preserved for untouched rows.
        date: r.date?.trim() || undefined,
        cost_center_id: null,
      }))

    const payload =
      bookItems.length > 0 && bookItems[0]
        ? {
            suggestion_type: "use_existing_book",
            bank_transaction_id: bank.id,
            existing_journal_entry_id: bookItems[0].id,
            complementing_journal_entries: complementing,
          }
        : {
            suggestion_type: "create_new",
            bank_transaction_id: bank.id,
            transaction: {
              date: bank.date,
              entity_id: bank.entity ?? null,
              description: bank.description,
              amount: String(Math.abs(Number(bank.amount))),
              currency_id: bank.currency,
              state: "pending",
            },
            journal_entries: complementing,
          }

    createSuggestions.mutate(
      { suggestions: [payload] },
      {
        onSuccess: () => {
          toast.success(t("add_entries.created_toast") ?? "Criado")
          onCreated()
          onClose()
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Erro"),
      },
    )
  }

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[640px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Plus className="h-3.5 w-3.5 text-muted-foreground" />
              {t("add_entries.title")}
            </Drawer.Title>
            <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <p className="text-muted-foreground">{t("add_entries.subtitle")}</p>

            {/* Context — surfaces both sides so the user sees which way
                the reconciliation is currently tilting. bookSum here uses
                the direction-aware effective amount (same value the
                Conciliações page sums), so the "Diferença" agrees with
                what the backend will compute post-match. */}
            <div className="rounded-md border border-border bg-surface-3 p-2.5 text-[11px]">
              <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">Contexto</div>
              <div className="mb-2 text-muted-foreground">
                {bankItems.length} bancária(s), {bookItems.length} contábil(eis) selecionados
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Soma bancária</div>
                  <div className="tabular-nums font-semibold">{formatCurrency(bankSum)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Soma contábil</div>
                  <div className="tabular-nums font-semibold">{formatCurrency(bookSum)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Diferença</div>
                  <div className={cn(
                    "tabular-nums font-semibold",
                    Math.abs(delta) < 0.005 ? "text-success" : "text-warning",
                  )}>{formatCurrency(delta)}</div>
                </div>
              </div>
            </div>

            {/* Entry rows: each row carries its own description, pre-filled
                from the bank record. There is no longer a single
                "consolidated" transaction-level description — the new
                journal entries each keep the description on their row. */}
            <div className="space-y-2">
              {rows.map((r, i) => (
                <EntryRowEditor
                  key={i}
                  row={r}
                  accounts={leafAccounts}
                  onChange={(p) => updateRow(i, p)}
                  onRemove={rows.length > 1 ? () => removeRow(i) : undefined}
                />
              ))}
              <button
                onClick={addRow}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-dashed border-border bg-transparent px-3 text-[12px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <Plus className="h-3.5 w-3.5" />
                {t("add_entries.add_row")}
              </button>
            </div>

            {/* Cash-leg preview + balance check.
                The backend auto-books the cash leg on the bank's CoA
                account; we show what that leg will look like so the
                operator sees the full double-entry before submit.
                The balance chip confirms their contra rows will
                close the Transaction (Σdebit == Σcredit). */}
            <div className="rounded-md border border-border bg-surface-3 p-2.5 text-[12px]">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Perna de caixa (automática)
                </div>
                <div
                  className={cn(
                    "flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium",
                    balanceOk ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                  )}
                >
                  {balanceOk ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                  {balanceOk ? "Lançamento equilibrado" : "Desequilibrado"}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Conta caixa</div>
                  <div className="truncate font-medium">
                    {/* We don't render the account name without a
                         round-trip; the bank account's name is close
                         enough for the preview. The backend resolves
                         the CoA account at write time. */}
                    Vinculada a {bankItems[0]
                      ? (bankAccounts.find((ba) => ba.id === bankItems[0]!.bank_account)?.name ?? `#${bankItems[0]!.bank_account}`)
                      : "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Lado + valor</div>
                  <div className="tabular-nums font-semibold">
                    {delta === 0
                      ? "—"
                      : `${delta > 0 ? "Débito" : "Crédito"} ${formatCurrency(Math.abs(delta))}`}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Soma contra (Σd − Σc)</div>
                  <div className={cn("tabular-nums font-semibold", balanceOk ? "text-success" : "text-warning")}>
                    {formatCurrency(contraRawSum)}
                    <span className="ml-1 text-[10px] text-muted-foreground">/ alvo {formatCurrency(target)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* When the contras don't close the Transaction, explain
                *why* the submit is blocked. The backend (PR 8) refuses
                unbalanced adjustment Transactions outright — no escape
                hatch here anymore. */}
            {!balanceOk && (
              <div className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 p-2.5 text-[11px]">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                <div className="flex-1 text-muted-foreground">
                  Para fechar o lançamento, a soma dos débitos e créditos dos
                  contras precisa compensar a perna de caixa automática.
                  Ajuste os valores ou o lado das linhas acima.
                </div>
              </div>
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              {t("actions.cancel", { ns: "common" })}
            </button>
            <button
              onClick={submit}
              disabled={createSuggestions.isPending || !canSubmit}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md px-3 text-[12px] font-medium disabled:opacity-50",
                balanceOk
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-warning text-warning-foreground hover:bg-warning/90",
              )}
            >
              {balanceOk ? <Check className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
              {balanceOk
                ? t("add_entries.submit")
                : (t("add_entries.submit_partial") ?? "Criar parcial")}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function EntryRowEditor({
  row, accounts, onChange, onRemove,
}: {
  row: EntryRow
  /** Already filtered to leaf accounts by the parent. */
  accounts: AccountLite[]
  onChange: (p: Partial<EntryRow>) => void
  onRemove?: () => void
}) {
  const { t } = useTranslation(["reconciliation"])
  return (
    <div className="grid grid-cols-[1fr_90px_110px_120px_1fr_auto] items-end gap-2 rounded-md border border-border bg-surface-1 p-2">
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {t("add_entries.account")}
        </span>
        <select
          value={row.account_id}
          onChange={(e) => onChange({ account_id: e.target.value ? Number(e.target.value) : "" })}
          className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          <option value="">—</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.account_code ? `${a.account_code} · ` : ""}{a.path}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Lado</span>
        <select
          value={row.side}
          onChange={(e) => onChange({ side: e.target.value as "debit" | "credit" })}
          className="h-8 rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring"
        >
          <option value="debit">{t("add_entries.debit")}</option>
          <option value="credit">{t("add_entries.credit")}</option>
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Data</span>
        <input
          type="date"
          value={row.date}
          onChange={(e) => onChange({ date: e.target.value })}
          className="h-8 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-ring [color-scheme:dark]"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {t("add_entries.amount")}
        </span>
        <input
          type="number"
          step="0.01"
          value={row.amount}
          onChange={(e) => onChange({ amount: e.target.value })}
          className="h-8 w-full rounded-md border border-border bg-background px-2 tabular-nums outline-none focus:border-ring"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {t("add_entries.description")}
        </span>
        <input
          value={row.description}
          onChange={(e) => onChange({ description: e.target.value })}
          className="h-8 w-full rounded-md border border-border bg-background px-2 outline-none focus:border-ring"
        />
      </label>
      {onRemove && (
        <button
          onClick={onRemove}
          className="mb-0.5 grid h-8 w-8 place-items-center rounded-md border border-border text-muted-foreground hover:bg-accent hover:text-danger"
          title={t("add_entries.remove") ?? "Remover"}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
