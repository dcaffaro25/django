import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number | string, currency = "BRL", locale = "pt-BR") {
  const n = typeof value === "string" ? Number(value) : value
  if (!Number.isFinite(n)) return "—"
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(n)
}

export function formatNumber(value: number | string, locale = "pt-BR", opts?: Intl.NumberFormatOptions) {
  const n = typeof value === "string" ? Number(value) : value
  if (!Number.isFinite(n)) return "—"
  return new Intl.NumberFormat(locale, opts).format(n)
}

export function formatDate(value: string | Date, locale = "pt-BR") {
  const d = typeof value === "string" ? new Date(value) : value
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "—"
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(d)
}

export function formatDateTime(value: string | Date, locale = "pt-BR") {
  const d = typeof value === "string" ? new Date(value) : value
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "—"
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(d)
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—"
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}
