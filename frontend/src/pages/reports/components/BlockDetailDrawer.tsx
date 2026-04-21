import { Drawer } from "vaul"
import {
  X, Sparkles, Bold as BoldIcon, Hash, Indent, Outdent,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type {
  Block, CalculationMethod, LineBlock, Scale, SectionBlock, SignPolicy,
  SubtotalBlock, TotalBlock,
} from "@/features/reports"
import { FormulaInput } from "./FormulaInput"
import { AccountTreePicker } from "./AccountTreePicker"

/**
 * Per-block settings drawer. Opens on the right when the user clicks the ⋯
 * button on a BlockRow. All block fields live here — the inline row keeps
 * only the essentials (drag, type icon, label, id, overflow).
 *
 * Block type drives which fields render:
 *   section  → defaults (applied to children)
 *   line     → accounts + calc/sign/scale/manual_value
 *   subtotal → accounts (optional) + formula + sign/scale
 *   total    → formula + sign/scale
 *   header   → just the basics
 *   spacer   → nothing except the id (immutable here)
 */
export function BlockDetailDrawer({
  open,
  block,
  validIds,
  onChange,
  onClose,
}: {
  open: boolean
  block: Block | null
  validIds: Set<string>
  onChange: (patch: Partial<Block>) => void
  onClose: () => void
}) {
  if (!open || !block) return null

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[480px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <span className="rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] uppercase">
                {block.type}
              </span>
              <code className="text-[11px] text-muted-foreground">{block.id}</code>
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            {/* AI explanation (client-only metadata; stripped on save by design) */}
            {(block as { ai_explanation?: string | null }).ai_explanation && (
              <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-[11px]">
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                <div>
                  <div className="font-medium text-amber-700 dark:text-amber-400">
                    Sugerido pela IA
                  </div>
                  <div className="text-muted-foreground">
                    {(block as { ai_explanation?: string }).ai_explanation}
                  </div>
                </div>
              </div>
            )}

            <CommonFields block={block} onChange={onChange} />

            {block.type === "section" && (
              <SectionFields block={block} onChange={onChange} />
            )}
            {block.type === "line" && (
              <LineFields block={block} onChange={onChange} />
            )}
            {block.type === "subtotal" && (
              <SubtotalFields block={block} validIds={validIds} onChange={onChange} />
            )}
            {block.type === "total" && (
              <TotalFields block={block} validIds={validIds} onChange={onChange} />
            )}
          </div>

          <div className="hairline flex shrink-0 items-center justify-end gap-2 border-t border-border p-3">
            <button
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
            >
              Fechar
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

// ------- Field groups ------------------------------------------------------

function CommonFields({
  block, onChange,
}: {
  block: Block
  onChange: (patch: Partial<Block>) => void
}) {
  const canLabel = block.type !== "spacer"
  const hasIndent = block.type !== "spacer"
  const hasBold =
    block.type !== "spacer" && block.type !== "section" && block.type !== "header"
  const label = (block as { label?: string | null }).label ?? ""
  const bold = !!(block as { bold?: boolean | null }).bold
  const indent = (block as { indent?: number | null }).indent ?? 0

  return (
    <Section title="Geral">
      {canLabel && (
        <Field label="Rótulo">
          <input
            value={label}
            onChange={(e) => onChange({ label: e.target.value } as Partial<Block>)}
            className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
          />
        </Field>
      )}

      <div className="flex items-end gap-3">
        {hasBold && (
          <button
            onClick={() => onChange({ bold: !bold } as Partial<Block>)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[11px] font-medium",
              bold ? "border-primary bg-primary/10" : "border-border bg-background hover:bg-accent",
            )}
          >
            <BoldIcon className="h-3 w-3" /> Negrito
          </button>
        )}

        {hasIndent && (
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-muted-foreground">Indent</span>
            <button
              onClick={() => onChange({ indent: Math.max(0, indent - 1) } as Partial<Block>)}
              className="grid h-7 w-7 place-items-center rounded-md border border-border hover:bg-accent"
            >
              <Outdent className="h-3 w-3" />
            </button>
            <span className="w-4 text-center text-[11px] tabular-nums">{indent}</span>
            <button
              onClick={() => onChange({ indent: indent + 1 } as Partial<Block>)}
              className="grid h-7 w-7 place-items-center rounded-md border border-border hover:bg-accent"
            >
              <Indent className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      <Field label="ID">
        <div className="flex items-center gap-2">
          <Hash className="h-3 w-3 text-muted-foreground" />
          <code className="text-[11px]">{block.id}</code>
          <span className="text-[10px] text-muted-foreground">
            (somente leitura — recriar para mudar)
          </span>
        </div>
      </Field>
    </Section>
  )
}

function SectionFields({
  block, onChange,
}: {
  block: SectionBlock
  onChange: (patch: Partial<SectionBlock>) => void
}) {
  const d = block.defaults ?? {}
  const set = <K extends keyof NonNullable<SectionBlock["defaults"]>>(
    key: K,
    value: NonNullable<SectionBlock["defaults"]>[K],
  ) => {
    onChange({ defaults: { ...d, [key]: value } } as Partial<SectionBlock>)
  }
  return (
    <Section title="Defaults da seção">
      <p className="text-[10px] text-muted-foreground">
        Aplicados aos filhos, a menos que sobrescritos.
      </p>
      <Field label="Método de cálculo (padrão)">
        <CalcMethodSelect
          value={d.calculation_method ?? null}
          onChange={(v) => set("calculation_method", v)}
        />
      </Field>
      <Field label="Política de sinal (padrão)">
        <SignSelect value={d.sign_policy ?? null} onChange={(v) => set("sign_policy", v)} />
      </Field>
      <Field label="Escala (padrão)">
        <ScaleSelect value={d.scale ?? null} onChange={(v) => set("scale", v)} />
      </Field>
    </Section>
  )
}

function LineFields({
  block, onChange,
}: {
  block: LineBlock
  onChange: (patch: Partial<LineBlock>) => void
}) {
  return (
    <Section title="Linha">
      <Field label="Contas">
        <AccountTreePicker
          value={block.accounts ?? null}
          onChange={(sel) => onChange({ accounts: sel })}
        />
      </Field>
      <Field label="Método de cálculo">
        <CalcMethodSelect
          value={block.calculation_method ?? null}
          onChange={(v) => onChange({ calculation_method: v })}
        />
      </Field>
      <Field label="Política de sinal">
        <SignSelect value={block.sign_policy ?? null} onChange={(v) => onChange({ sign_policy: v })} />
      </Field>
      <Field label="Escala">
        <ScaleSelect value={block.scale ?? null} onChange={(v) => onChange({ scale: v })} />
      </Field>
      <Field label="Valor manual (só para calc_method = manual_input)">
        <input
          value={block.manual_value ?? ""}
          onChange={(e) => onChange({ manual_value: e.target.value || null })}
          placeholder="0.00"
          className="h-7 w-full rounded-md border border-border bg-background px-2 font-mono tabular-nums text-[12px]"
        />
      </Field>
    </Section>
  )
}

function SubtotalFields({
  block, validIds, onChange,
}: {
  block: SubtotalBlock
  validIds: Set<string>
  onChange: (patch: Partial<SubtotalBlock>) => void
}) {
  return (
    <Section title="Subtotal">
      <Field label="Fórmula">
        <FormulaInput
          value={block.formula ?? ""}
          validIds={validIds}
          onChange={(v) => onChange({ formula: v || null })}
        />
      </Field>
      <p className="text-[10px] text-muted-foreground">
        Se vazia, usa a soma dos irmãos linha anteriores (sum(children)).
      </p>
      <Field label="Contas (opcional — para subtotal direto sobre contas)">
        <AccountTreePicker
          value={block.accounts ?? null}
          onChange={(sel) => onChange({ accounts: sel })}
        />
      </Field>
      <Field label="Política de sinal">
        <SignSelect value={block.sign_policy ?? null} onChange={(v) => onChange({ sign_policy: v })} />
      </Field>
    </Section>
  )
}

function TotalFields({
  block, validIds, onChange,
}: {
  block: TotalBlock
  validIds: Set<string>
  onChange: (patch: Partial<TotalBlock>) => void
}) {
  return (
    <Section title="Total">
      <Field label="Fórmula">
        <FormulaInput
          value={block.formula ?? ""}
          validIds={validIds}
          onChange={(v) => onChange({ formula: v || null })}
        />
      </Field>
      <Field label="Política de sinal">
        <SignSelect value={block.sign_policy ?? null} onChange={(v) => onChange({ sign_policy: v })} />
      </Field>
      <Field label="Escala">
        <ScaleSelect value={block.scale ?? null} onChange={(v) => onChange({ scale: v })} />
      </Field>
    </Section>
  )
}

// ------- Primitives --------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-background/40 p-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

const CALC_METHODS: { value: CalculationMethod | ""; label: string }[] = [
  { value: "", label: "(herdado)" },
  { value: "ending_balance", label: "Saldo final" },
  { value: "opening_balance", label: "Saldo inicial" },
  { value: "net_movement", label: "Movimento líquido" },
  { value: "debit_total", label: "Total de débitos" },
  { value: "credit_total", label: "Total de créditos" },
  { value: "change_in_balance", label: "Variação de saldo" },
  { value: "rollup_children", label: "Soma dos filhos" },
  { value: "formula", label: "Fórmula" },
  { value: "manual_input", label: "Valor manual" },
]
const SIGNS: { value: SignPolicy | ""; label: string }[] = [
  { value: "", label: "(herdado)" },
  { value: "natural", label: "Natural" },
  { value: "invert", label: "Inverter" },
  { value: "absolute", label: "Absoluto" },
]
const SCALES: { value: Scale | ""; label: string }[] = [
  { value: "", label: "(herdado)" },
  { value: "none", label: "Sem escala" },
  { value: "K", label: "Milhares" },
  { value: "M", label: "Milhões" },
  { value: "B", label: "Bilhões" },
]

function CalcMethodSelect({
  value, onChange,
}: {
  value: CalculationMethod | null
  onChange: (v: CalculationMethod | null) => void
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange((e.target.value || null) as CalculationMethod | null)}
      className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
    >
      {CALC_METHODS.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}

function SignSelect({
  value, onChange,
}: {
  value: SignPolicy | null
  onChange: (v: SignPolicy | null) => void
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange((e.target.value || null) as SignPolicy | null)}
      className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
    >
      {SIGNS.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}

function ScaleSelect({
  value, onChange,
}: {
  value: Scale | null
  onChange: (v: Scale | null) => void
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange((e.target.value || null) as Scale | null)}
      className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px]"
    >
      {SCALES.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}
