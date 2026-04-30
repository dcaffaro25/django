import { Hash, Building2, DollarSign, Calendar } from "lucide-react"
import { cn } from "@/lib/utils"
import type { NFTransactionLink } from "@/features/billing"

/**
 * Per-dimension breakdown of an NF↔Tx match. We expose this as a
 * pure function so the same logic powers both the visual chips
 * (this component) and the filter/sort predicates in the review
 * page.
 */
export type DimensionKey = "nf" | "cnpj" | "amount" | "date"

export type DimensionMatch = "full" | "partial" | "none" | "na"

export interface DimensionInfo {
  key: DimensionKey
  label: string
  match: DimensionMatch
  detail: string
  weight: number // contribution to confidence (0..1)
}

const DAY_MS = 24 * 60 * 60 * 1000

function dateDiffDays(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (Number.isNaN(ta) || Number.isNaN(tb)) return null
  return Math.round(Math.abs(ta - tb) / DAY_MS)
}

function pctDiff(a?: string | null, b?: string | null): number | null {
  const an = parseFloat(a ?? "")
  const bn = parseFloat(b ?? "")
  if (!Number.isFinite(an) || !Number.isFinite(bn) || bn === 0) return null
  return Math.abs(an - bn) / Math.abs(bn)
}

export function computeDimensions(link: NFTransactionLink): DimensionInfo[] {
  const fields = new Set(link.matched_fields ?? [])

  // --- NF# dimension ---
  const txNf = (link.transaction_nf_number ?? "").trim()
  const nfNum = String(link.nf_numero ?? "")
  const nfBaseWeight =
    link.method === "nf_number" ? 0.5 :
    link.method === "description_regex" ? 0.3 :
    link.method === "bank_description" ? 0.3 :
    0
  let nfInfo: DimensionInfo
  if (fields.has("nf_number")) {
    nfInfo = {
      key: "nf",
      label: "NF#",
      match: "full",
      detail: `NF ${nfNum}`,
      weight: nfBaseWeight,
    }
  } else if (link.method === "manual") {
    nfInfo = { key: "nf", label: "NF#", match: "na", detail: "manual", weight: 0 }
  } else if (!txNf && !nfNum) {
    nfInfo = { key: "nf", label: "NF#", match: "na", detail: "—", weight: 0 }
  } else {
    nfInfo = {
      key: "nf",
      label: "NF#",
      match: "none",
      detail: `Tx ${txNf || "∅"} ≠ NF ${nfNum || "∅"}`,
      weight: 0,
    }
  }

  // --- CNPJ dimension ---
  let cnpjInfo: DimensionInfo
  if (fields.has("cnpj")) {
    cnpjInfo = {
      key: "cnpj",
      label: "CNPJ",
      match: "full",
      detail: "exato",
      weight: 0.25,
    }
  } else if (fields.has("cnpj_root")) {
    cnpjInfo = {
      key: "cnpj",
      label: "CNPJ",
      match: "partial",
      detail: "raiz (matriz↔filial)",
      weight: 0.2,
    }
  } else if (fields.has("cnpj_alias")) {
    cnpjInfo = {
      key: "cnpj",
      label: "CNPJ",
      match: "partial",
      detail: "apelido aprendido",
      weight: 0.18,
    }
  } else if (fields.has("cnpj_group")) {
    cnpjInfo = {
      key: "cnpj",
      label: "CNPJ",
      match: "partial",
      detail: "mesmo grupo",
      weight: 0.22,
    }
  } else if (!link.transaction_cnpj) {
    cnpjInfo = { key: "cnpj", label: "CNPJ", match: "na", detail: "Tx sem CNPJ", weight: 0 }
  } else {
    cnpjInfo = { key: "cnpj", label: "CNPJ", match: "none", detail: "divergente", weight: 0 }
  }

  // --- Amount dimension ---
  const pct = pctDiff(link.transaction_amount, link.nf_valor_nota)
  let amountInfo: DimensionInfo
  if (fields.has("amount")) {
    amountInfo = {
      key: "amount",
      label: "Valor",
      match: "full",
      detail: pct == null ? "exato" : `Δ ${(pct * 100).toFixed(2)}%`,
      weight: 0.1,
    }
  } else if (pct == null) {
    amountInfo = { key: "amount", label: "Valor", match: "na", detail: "—", weight: 0 }
  } else {
    amountInfo = {
      key: "amount",
      label: "Valor",
      match: "none",
      detail: `Δ ${(pct * 100).toFixed(2)}%`,
      weight: 0,
    }
  }

  // --- Date dimension ---
  const days = dateDiffDays(link.transaction_date, link.nf_data_emissao)
  let dateInfo: DimensionInfo
  if (fields.has("date")) {
    dateInfo = {
      key: "date",
      label: "Data",
      match: "full",
      detail: days == null ? "dentro da janela" : `Δ ${days} ${days === 1 ? "dia" : "dias"}`,
      weight: 0.15,
    }
  } else if (days == null) {
    dateInfo = { key: "date", label: "Data", match: "na", detail: "—", weight: 0 }
  } else {
    dateInfo = {
      key: "date",
      label: "Data",
      match: "none",
      detail: `Δ ${days} ${days === 1 ? "dia" : "dias"}`,
      weight: 0,
    }
  }

  return [nfInfo, cnpjInfo, amountInfo, dateInfo]
}

const ICON: Record<DimensionKey, typeof Hash> = {
  nf: Hash,
  cnpj: Building2,
  amount: DollarSign,
  date: Calendar,
}

const TONE: Record<DimensionMatch, string> = {
  full: "border-success/40 bg-success/10 text-success",
  partial: "border-warning/40 bg-warning/10 text-warning",
  none: "border-destructive/40 bg-destructive/10 text-destructive",
  na: "border-border bg-muted/40 text-muted-foreground",
}

export function DimensionChip({ info }: { info: DimensionInfo }) {
  const Icon = ICON[info.key]
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full border px-1.5 text-[10px] font-medium tabular-nums",
        TONE[info.match],
      )}
      title={`${info.label}: ${info.detail}${info.weight > 0 ? ` (+${(info.weight * 100).toFixed(0)}%)` : ""}`}
    >
      <Icon className="h-3 w-3" />
      <span>{info.label}</span>
      <span className="text-[10px] opacity-80">·</span>
      <span className="font-normal">{info.detail}</span>
    </span>
  )
}

export function DimensionScores({ link }: { link: NFTransactionLink }) {
  const dims = computeDimensions(link)
  return (
    <div className="flex flex-wrap items-center gap-1">
      {dims.map((d) => (
        <DimensionChip key={d.key} info={d} />
      ))}
    </div>
  )
}
