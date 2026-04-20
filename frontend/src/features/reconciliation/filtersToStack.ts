import type { FilterStack, FilterStackRow } from "./types"

export interface WorkbenchFilters {
  // Bank-pane scoped
  bankDateFrom: string
  bankDateTo: string
  bankAccount: number | ""
  bankEntity: number | ""
  bankSearch: string
  bankAmountMin: string
  bankAmountMax: string
  // Book-pane scoped
  bookDateFrom: string
  bookDateTo: string
  bookBankAccount: number | ""
  bookSearch: string
  bookAmountMin: string
  bookAmountMax: string
}

function addDateRange(rows: FilterStackRow[], from: string, to: string) {
  if (from && to) rows.push({ column_id: "date", operator: "between", value: [from, to] })
  else if (from) rows.push({ column_id: "date", operator: "gte", value: from })
  else if (to) rows.push({ column_id: "date", operator: "lte", value: to })
}

/**
 * Build bank + book filter stacks from the Workbench UI filter object.
 *
 * Each pane now owns its own date range + bank-account filter, so the two
 * stacks are built independently rather than from shared fields.
 */
export function workbenchFiltersToStacks(f: WorkbenchFilters): {
  bank: FilterStack | null
  book: FilterStack | null
} {
  const bankRows: FilterStackRow[] = []
  const bookRows: FilterStackRow[] = []

  addDateRange(bankRows, f.bankDateFrom, f.bankDateTo)
  addDateRange(bookRows, f.bookDateFrom, f.bookDateTo)

  if (f.bankAccount) {
    bankRows.push({ column_id: "bank_account", operator: "eq", value: Number(f.bankAccount) })
  }
  if (f.bookBankAccount) {
    // Book side: filter JE.account.bank_account indirectly; the filter compiler
    // resolves via the account→bank_account relation. Safe no-op if not wired.
    bookRows.push({ column_id: "bank_account", operator: "eq", value: Number(f.bookBankAccount) })
  }
  if (f.bankEntity) {
    bankRows.push({ column_id: "entity", operator: "eq", value: Number(f.bankEntity) })
  }

  if (f.bankAmountMin) {
    bankRows.push({ column_id: "amount", operator: "gte", value: Number(f.bankAmountMin) })
  }
  if (f.bankAmountMax) {
    bankRows.push({ column_id: "amount", operator: "lte", value: Number(f.bankAmountMax) })
  }

  if (f.bankSearch.trim()) {
    bankRows.push({ column_id: "description", operator: "icontains", value: f.bankSearch.trim() })
  }
  if (f.bookSearch.trim()) {
    bookRows.push({ column_id: "description", operator: "icontains", value: f.bookSearch.trim() })
  }

  return {
    bank: bankRows.length ? { operator: "and", filters: bankRows } : null,
    book: bookRows.length ? { operator: "and", filters: bookRows } : null,
  }
}
