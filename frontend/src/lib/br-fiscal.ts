/**
 * Shared closed-enum lists + masking helpers for the Brazilian
 * legal/fiscal fields that live on both ``Entity`` and ``Company``
 * (Phase E2). Single source of truth so the EntityEditor and the
 * CompanyInfoEditor agree on labels, ordering, and CNPJ/CEP
 * normalization.
 */

export const ENTITY_TYPE_OPTIONS: Array<[string, string]> = [
  ["matriz", "Matriz"],
  ["filial", "Filial"],
  ["holding", "Holding"],
  ["sociedade", "Sociedade Simples"],
  ["fundo", "Fundo de Investimento"],
  ["departamento", "Departamento"],
  ["centro_de_custo", "Centro de Custo"],
  ["projeto", "Projeto"],
  ["outro", "Outro"],
]

export const REGIME_TRIBUTARIO_OPTIONS: Array<[string, string]> = [
  ["simples", "Simples Nacional"],
  ["lucro_presumido", "Lucro Presumido"],
  ["lucro_real", "Lucro Real"],
  ["mei", "MEI"],
  ["imune", "Imune / Isento"],
  ["nao_aplicavel", "Não se aplica"],
]

export const UF_OPTIONS = [
  "AC","AL","AM","AP","BA","CE","DF","ES","GO",
  "MA","MG","MS","MT","PA","PB","PE","PI","PR",
  "RJ","RN","RO","RR","RS","SC","SE","SP","TO","EX",
] as const

export function formatCnpjInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 14)
  const parts = [
    digits.slice(0, 2),
    digits.slice(2, 5),
    digits.slice(5, 8),
    digits.slice(8, 12),
    digits.slice(12, 14),
  ]
  let out = parts[0]
  if (parts[1]) out += "." + parts[1]
  if (parts[2]) out += "." + parts[2]
  if (parts[3]) out += "/" + parts[3]
  if (parts[4]) out += "-" + parts[4]
  return out
}

export function formatCepInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8)
  if (digits.length <= 5) return digits
  return digits.slice(0, 5) + "-" + digits.slice(5)
}

/** Common ISO 4217 currency codes operators choose from. The
 *  backend stores the raw 3-letter code so any value is accepted;
 *  this list just makes the dropdown ergonomic. */
export const CURRENCY_OPTIONS: Array<[string, string]> = [
  ["BRL", "Real (BRL)"],
  ["USD", "Dólar americano (USD)"],
  ["EUR", "Euro (EUR)"],
  ["GBP", "Libra esterlina (GBP)"],
  ["ARS", "Peso argentino (ARS)"],
  ["CLP", "Peso chileno (CLP)"],
  ["UYU", "Peso uruguaio (UYU)"],
  ["MXN", "Peso mexicano (MXN)"],
]
