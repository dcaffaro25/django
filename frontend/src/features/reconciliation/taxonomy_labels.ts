/**
 * Client-side mirror of the closed-enum labels from
 * ``accounting/services/taxonomy_meta.py``. Kept in sync by
 * convention -- if either side changes the keys, this file gets a
 * matching update. The backend file is the source of truth; this
 * module just maps codes to display strings + colours.
 *
 * Intentionally a static lookup, not a fetched config -- the labels
 * are stable per release and don't justify a request on every page
 * load. When the closed enum changes, adding entries here is part
 * of the same PR as the backend change.
 */

export interface CategoryStyle {
  /** Human-readable Portuguese label. */
  label: string
  /** Tailwind color class for the badge background (low-saturation). */
  bgClass: string
  /** Tailwind color class for the badge foreground / text. */
  fgClass: string
  /** Order key for charts -- lower comes first in the bar list. */
  order: number
}

export const REPORT_CATEGORY_STYLES: Record<string, CategoryStyle> = {
  ativo_circulante: {
    label: "Ativo Circulante",
    bgClass: "bg-emerald-500/10",
    fgClass: "text-emerald-600",
    order: 1,
  },
  ativo_nao_circulante: {
    label: "Ativo Não Circulante",
    bgClass: "bg-teal-500/10",
    fgClass: "text-teal-600",
    order: 2,
  },
  passivo_circulante: {
    label: "Passivo Circulante",
    bgClass: "bg-orange-500/10",
    fgClass: "text-orange-600",
    order: 3,
  },
  passivo_nao_circulante: {
    label: "Passivo Não Circulante",
    bgClass: "bg-amber-500/10",
    fgClass: "text-amber-600",
    order: 4,
  },
  patrimonio_liquido: {
    label: "Patrimônio Líquido",
    bgClass: "bg-blue-500/10",
    fgClass: "text-blue-600",
    order: 5,
  },
  receita_bruta: {
    label: "Receita Bruta",
    bgClass: "bg-green-500/10",
    fgClass: "text-green-600",
    order: 6,
  },
  deducao_receita: {
    label: "Deduções da Receita",
    bgClass: "bg-rose-500/10",
    fgClass: "text-rose-600",
    order: 7,
  },
  custo: {
    label: "Custo",
    bgClass: "bg-red-500/10",
    fgClass: "text-red-600",
    order: 8,
  },
  despesa_operacional: {
    label: "Despesa Operacional",
    bgClass: "bg-pink-500/10",
    fgClass: "text-pink-600",
    order: 9,
  },
  receita_financeira: {
    label: "Receita Financeira",
    bgClass: "bg-cyan-500/10",
    fgClass: "text-cyan-600",
    order: 10,
  },
  despesa_financeira: {
    label: "Despesa Financeira",
    bgClass: "bg-violet-500/10",
    fgClass: "text-violet-600",
    order: 11,
  },
  outras_receitas: {
    label: "Outras Receitas/Despesas",
    bgClass: "bg-slate-500/10",
    fgClass: "text-slate-600",
    order: 12,
  },
  imposto_sobre_lucro: {
    label: "Tributos sobre Lucro",
    bgClass: "bg-yellow-500/10",
    fgClass: "text-yellow-700",
    order: 13,
  },
  memo: {
    label: "Memo",
    bgClass: "bg-zinc-500/10",
    fgClass: "text-zinc-500",
    order: 14,
  },
}

export const TAG_LABELS: Record<string, string> = {
  cash: "Caixa",
  bank_account: "Conta bancária",
  restricted_cash: "Caixa restrito",
  contra_account: "Retificadora",
  non_cash: "Não-caixa",
  working_capital: "Capital de giro",
  ebitda_addback: "EBITDA addback",
  non_recurring: "Não-recorrente",
  value_added_input: "Insumo DVA",
  fixed_asset: "Imobilizado",
  intangible_asset: "Intangível",
  debt: "Dívida",
  short_term: "Curto prazo",
  long_term: "Longo prazo",
  icms: "ICMS",
  pis: "PIS",
  cofins: "COFINS",
  iss: "ISS",
  ipi: "IPI",
  inss: "INSS",
  fgts: "FGTS",
  irrf: "IRRF",
  foreign_currency: "Moeda estrangeira",
  intercompany: "Intercompany",
  elimination: "Eliminação",
  accrual: "Provisão",
  prepaid: "Antecipado",
  product_sales: "Venda de produtos",
  service_revenue: "Serviços",
  subscription_revenue: "Assinatura",
  export_revenue: "Exportação",
  jcp: "JCP",
  dividends: "Dividendos",
  comprehensive_income: "ORA",
  ifrs16_lease: "Arrendamento IFRS16",
  guaranteed: "Garantia",
}

/** Convenience: ordered list of (code, style) for the charts that
 *  need deterministic colours. */
export const CATEGORY_CODES_BY_ORDER: string[] = Object.entries(REPORT_CATEGORY_STYLES)
  .sort(([, a], [, b]) => a.order - b.order)
  .map(([code]) => code)
