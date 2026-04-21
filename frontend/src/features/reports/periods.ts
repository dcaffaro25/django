// Client-side helpers to build common period[] layouts. Mirrors the
// Período presets surfaced in the builder UI. Deliberately small — no DB
// access, pure date math.

import type { Period, ReportType } from "./types"

export type PeriodPreset =
  | "single"          // just one period (current)
  | "yoy"             // current year + previous year + variance (abs + %)
  | "qoq_4"           // last 4 quarters
  | "mom_12"          // last 12 months
  | "ytd_vs_ytd"      // year-to-date current vs prior-year same range
  | "balance_now_vs_prior"  // BP only: as_of today vs as_of 1y prior

interface BuildOpts {
  /** Reference ISO date — the "as of" anchor for all derivations. */
  ref: string
  /** Used to pick between range (DRE/CF) and as_of (BP). */
  reportType: ReportType
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function parseISO(s: string): Date {
  return new Date(s + "T00:00:00")
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}

function startOfYear(d: Date): Date {
  return new Date(d.getFullYear(), 0, 1)
}

function endOfYear(d: Date): Date {
  return new Date(d.getFullYear(), 11, 31)
}

function addYears(d: Date, n: number): Date {
  return new Date(d.getFullYear() + n, d.getMonth(), d.getDate())
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, d.getDate())
}

function quarterOf(d: Date): number {
  return Math.floor(d.getMonth() / 3) + 1
}

function startOfQuarter(d: Date): Date {
  const q = quarterOf(d)
  return new Date(d.getFullYear(), (q - 1) * 3, 1)
}

function endOfQuarter(d: Date): Date {
  const q = quarterOf(d)
  return new Date(d.getFullYear(), q * 3, 0)
}

export function buildPresetPeriods({ ref, reportType }: BuildOpts, preset: PeriodPreset): Period[] {
  const refDate = parseISO(ref)

  if (preset === "single") {
    if (reportType === "balance_sheet") {
      return [{
        id: "cur", label: iso(refDate), type: "as_of", date: iso(refDate),
      }]
    }
    const s = startOfYear(refDate)
    return [{
      id: "cur", label: String(refDate.getFullYear()), type: "range",
      start: iso(s), end: iso(refDate),
    }]
  }

  if (preset === "balance_now_vs_prior") {
    const cur = iso(refDate)
    const prev = iso(addYears(refDate, -1))
    return [
      { id: "cur", label: cur, type: "as_of", date: cur },
      { id: "prev", label: prev, type: "as_of", date: prev },
    ]
  }

  if (preset === "yoy") {
    if (reportType === "balance_sheet") {
      const cur = iso(refDate)
      const prev = iso(addYears(refDate, -1))
      return [
        { id: "cur", label: cur, type: "as_of", date: cur },
        { id: "prev", label: prev, type: "as_of", date: prev },
      ]
    }
    const curStart = startOfYear(refDate)
    const curEnd = endOfYear(refDate)
    const prevStart = addYears(curStart, -1)
    const prevEnd = addYears(curEnd, -1)
    return [
      { id: "cur", label: String(refDate.getFullYear()), type: "range",
        start: iso(curStart), end: iso(curEnd) },
      { id: "prev", label: String(refDate.getFullYear() - 1), type: "range",
        start: iso(prevStart), end: iso(prevEnd) },
      { id: "var_abs", label: "Δ", type: "variance_abs", base: "prev", compare: "cur" },
      { id: "var_pct", label: "%", type: "variance_pct", base: "prev", compare: "cur" },
    ]
  }

  if (preset === "ytd_vs_ytd") {
    if (reportType === "balance_sheet") {
      // Doesn't really apply to BP; fall back to balance_now_vs_prior
      return buildPresetPeriods({ ref, reportType }, "balance_now_vs_prior")
    }
    const curStart = startOfYear(refDate)
    const prevStart = addYears(curStart, -1)
    const prevEnd = addYears(refDate, -1)
    return [
      { id: "cur", label: "YTD", type: "range", start: iso(curStart), end: iso(refDate) },
      { id: "prev", label: "YTD-1", type: "range", start: iso(prevStart), end: iso(prevEnd) },
      { id: "var_pct", label: "%", type: "variance_pct", base: "prev", compare: "cur" },
    ]
  }

  if (preset === "mom_12") {
    const out: Period[] = []
    for (let i = 11; i >= 0; i--) {
      const anchor = addMonths(refDate, -i)
      const s = startOfMonth(anchor)
      const e = endOfMonth(anchor)
      const label = `${anchor.getFullYear()}-${String(anchor.getMonth() + 1).padStart(2, "0")}`
      out.push({ id: `m${i}`, label, type: "range", start: iso(s), end: iso(e) })
    }
    return out
  }

  if (preset === "qoq_4") {
    const out: Period[] = []
    // Last 4 completed quarters including the current
    let anchor = refDate
    for (let i = 0; i < 4; i++) {
      const s = startOfQuarter(anchor)
      const e = endOfQuarter(anchor)
      const label = `${anchor.getFullYear()}-Q${quarterOf(anchor)}`
      out.unshift({ id: `q${i}`, label, type: "range", start: iso(s), end: iso(e) })
      anchor = addMonths(s, -1)
    }
    return out
  }

  return []
}

export const PRESET_OPTIONS: { value: PeriodPreset; label: string }[] = [
  { value: "single", label: "Período único" },
  { value: "yoy", label: "Ano vs ano anterior" },
  { value: "ytd_vs_ytd", label: "YTD vs YTD anterior" },
  { value: "qoq_4", label: "Últimos 4 trimestres" },
  { value: "mom_12", label: "Últimos 12 meses" },
  { value: "balance_now_vs_prior", label: "Saldo atual vs 1 ano antes" },
]
