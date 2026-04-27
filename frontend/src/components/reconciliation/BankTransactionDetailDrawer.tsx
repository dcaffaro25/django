import { useState } from "react"
import { Drawer } from "vaul"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  History,
  Info,
  Loader2,
  X,
} from "lucide-react"

import { useBankTxReconciliationHistory } from "@/features/reconciliation"
import type {
  BankTransaction,
  BankTxReconciliationHistoryEntry,
} from "@/features/reconciliation/types"
import { StatusBadge } from "@/components/ui/status-badge"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

/**
 * Reusable per-bank-transaction detail drawer.
 *
 * Used by:
 *   - Bank Account Detail page (Page 2) -- transactions table row click.
 *   - Bank Transactions Management page (Page 3) -- same.
 *   - Workbench (future) -- could replace the row's "history" icon
 *     with a richer drawer; today the row click still toggles
 *     selection, so the drawer is a separate entry point.
 *
 * Three tabs:
 *   - **Detalhes**: full row metadata + match-progress (data already
 *     on the BankTransaction row -- no extra fetch).
 *   - **Conciliações**: every Reconciliation group this tx has been
 *     part of (re-uses ``useBankTxReconciliationHistory``, the same
 *     hook that powers the standalone history drawer).
 *   - **Atividade**: placeholder until the bank-account-scoped
 *     activity feed lands. Hidden behind a "soon" indicator so
 *     the layout is stable when it ships.
 *
 * The drawer is intentionally read-only in v1; edit/delete actions
 * live in the bulk toolbar of the management page. A follow-up can
 * add inline edit here once the operator workflow stabilises.
 */
export function BankTransactionDetailDrawer({
  open,
  onClose,
  source,
}: {
  open: boolean
  onClose: () => void
  /** The bank tx the operator clicked. ``null`` = closed. */
  source: BankTransaction | null
}) {
  const bankTxId = source?.id ?? null
  const [tab, setTab] = useState<"detail" | "history" | "activity">("detail")

  return (
    <Drawer.Root open={open} onOpenChange={(o) => !o && onClose()} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Drawer.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[820px] flex-col border-l border-border surface-2 outline-none">
          <div className="hairline flex h-12 shrink-0 items-center justify-between px-4">
            <Drawer.Title className="flex items-center gap-2 text-[13px] font-semibold">
              <Info className="h-3.5 w-3.5 text-muted-foreground" />
              Transação bancária
              {bankTxId != null && <span className="text-muted-foreground">· #{bankTxId}</span>}
            </Drawer.Title>
            <button
              onClick={onClose}
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Tab strip */}
          <div className="hairline flex shrink-0 items-stretch text-[12px]">
            <TabButton active={tab === "detail"} onClick={() => setTab("detail")}>
              <Info className="h-3 w-3" /> Detalhes
            </TabButton>
            <TabButton active={tab === "history"} onClick={() => setTab("history")}>
              <History className="h-3 w-3" /> Conciliações
            </TabButton>
            <TabButton
              active={tab === "activity"}
              onClick={() => setTab("activity")}
              title="Disponível em breve"
            >
              <Clock className="h-3 w-3" /> Atividade
              <span className="ml-1 rounded-sm bg-muted px-1 text-[9px] uppercase tracking-wider text-muted-foreground">
                em breve
              </span>
            </TabButton>
          </div>

          <div className="flex-1 overflow-y-auto p-3 text-[12px]">
            {tab === "detail" && <DetailTab source={source} />}
            {tab === "history" && <HistoryTab bankTxId={bankTxId} />}
            {tab === "activity" && <ActivityTabPlaceholder />}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

function TabButton({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "flex h-9 items-center gap-1.5 px-3 text-muted-foreground transition-colors",
        active
          ? "border-b-2 border-primary text-foreground"
          : "border-b-2 border-transparent hover:bg-accent/40 hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}

function DetailTab({ source }: { source: BankTransaction | null }) {
  if (!source) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-4 text-center text-muted-foreground">
        Selecione uma transação.
      </div>
    )
  }
  const pct = source.match_progress_pct
  const remaining = source.amount_remaining
  const isPartial = pct !== undefined && pct > 0 && pct < 100

  return (
    <div className="space-y-4">
      {/* Header: amount + status + match progress at a glance. */}
      <div className="rounded-md border border-border bg-muted/20 p-3">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Valor
        </div>
        <div className="mt-0.5 flex items-baseline gap-3">
          <div
            className={cn(
              "text-[20px] font-semibold tabular-nums",
              Number(source.amount) < 0 ? "text-muted-foreground" : "text-foreground",
            )}
          >
            {formatCurrency(Number(source.amount))}
          </div>
          <StatusBadge status={source.reconciliation_status} className="h-4" />
          {isPartial && (
            <span className="text-[11px] font-medium text-amber-600">
              {pct}% · {formatCurrency(remaining ?? "0")} restante
            </span>
          )}
        </div>
      </div>

      {/* Field grid: shows every operator-relevant column without
          pretending to be the row in the workbench. Single source of
          truth for "what does this transaction look like". */}
      <Field label="Data" value={formatDate(source.date)} />
      <Field label="Descrição" value={source.description} multiline />
      {source.entity_name && <Field label="Entidade" value={source.entity_name} />}
      <Field label="Conta bancária" value={`#${source.bank_account ?? "—"}`} mono />
      <Field label="Moeda" value={`#${source.currency}`} mono />
      {source.erp_id && <Field label="ERP id" value={source.erp_id} mono />}
      {source.cnpj && <Field label="CNPJ" value={source.cnpj} mono />}
      {source.numeros_boleto && source.numeros_boleto.length > 0 && (
        <Field
          label="Boletos"
          value={source.numeros_boleto.join(", ")}
          mono
          multiline
        />
      )}
      {source.tag && <Field label="Tag" value={source.tag} />}
      {source.status && <Field label="Status" value={source.status} />}

      {source.amount_reconciled !== undefined && (
        <div className="rounded-md border border-border bg-background p-3">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
            Progresso de conciliação
          </div>
          <div className="grid grid-cols-3 gap-3 tabular-nums">
            <Stat label="Conciliado" value={formatCurrency(source.amount_reconciled)} kind="ok" />
            <Stat label="Restante" value={formatCurrency(source.amount_remaining ?? "0")} kind={isPartial ? "warn" : "muted"} />
            <Stat label="%" value={`${pct ?? 0}%`} kind={pct === 100 ? "ok" : isPartial ? "warn" : "muted"} />
          </div>
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  mono,
  multiline,
}: {
  label: string
  value: string | null | undefined
  mono?: boolean
  multiline?: boolean
}) {
  if (value == null || value === "") return null
  return (
    <div className="grid grid-cols-[minmax(110px,140px)_1fr] items-baseline gap-3 border-b border-border/50 pb-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "text-[12px]",
          mono && "font-mono text-[11px]",
          multiline ? "break-words" : "truncate",
        )}
      >
        {value}
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  kind,
}: {
  label: string
  value: string
  kind: "ok" | "warn" | "muted"
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 font-semibold",
          kind === "ok" && "text-emerald-600",
          kind === "warn" && "text-amber-600",
          kind === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </div>
    </div>
  )
}

function HistoryTab({ bankTxId }: { bankTxId: number | null }) {
  const { data, isLoading, isError, error } = useBankTxReconciliationHistory(bankTxId)
  const entries = data ?? []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando…
      </div>
    )
  }
  if (isError) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive">
        {error instanceof Error ? error.message : "Falha ao carregar histórico."}
      </div>
    )
  }
  if (entries.length === 0) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-4 text-center text-muted-foreground">
        Esta transação ainda não foi conciliada nenhuma vez.
      </div>
    )
  }
  return <HistoryTable entries={entries} />
}

function HistoryTable({ entries }: { entries: BankTxReconciliationHistoryEntry[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/40 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Data</th>
            <th className="h-7 px-2">Status</th>
            <th className="h-7 px-2 text-right">Bank</th>
            <th className="h-7 px-2 text-right">Livro</th>
            <th className="h-7 px-2 text-right">Δ</th>
            <th className="h-7 px-2 text-right">Itens</th>
            <th className="h-7 px-2">Referência / notas</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => {
            const isBalanced = Math.abs(Number(e.discrepancy)) < 0.005
            return (
              <tr
                key={e.id}
                className={cn(
                  "border-t border-border/60",
                  e.is_deleted && "opacity-60 line-through decoration-muted-foreground/40",
                )}
              >
                <td className="px-2 py-1.5 align-top text-muted-foreground tabular-nums">
                  {formatDate(e.created_at)}
                </td>
                <td className="px-2 py-1.5 align-top">
                  <StatusBadge status={e.status} className="h-4" />
                  {e.is_deleted && (
                    <span className="ml-1 text-[10px] text-muted-foreground">(removida)</span>
                  )}
                </td>
                <td className="px-2 py-1.5 align-top text-right tabular-nums">
                  {formatCurrency(e.total_bank_amount)}
                </td>
                <td className="px-2 py-1.5 align-top text-right tabular-nums">
                  {formatCurrency(e.total_journal_amount)}
                </td>
                <td
                  className={cn(
                    "px-2 py-1.5 align-top text-right tabular-nums font-medium",
                    isBalanced ? "text-emerald-600" : "text-amber-600",
                  )}
                >
                  {formatCurrency(e.discrepancy)}
                </td>
                <td className="px-2 py-1.5 align-top text-right text-muted-foreground tabular-nums">
                  {e.bank_transaction_count}b · {e.journal_entry_count}j
                </td>
                <td className="px-2 py-1.5 align-top text-muted-foreground">
                  {e.reference && (
                    <div className="font-mono text-[10px]">{e.reference}</div>
                  )}
                  {e.notes && (
                    <div className="line-clamp-2 break-words text-[11px]">{e.notes}</div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ActivityTabPlaceholder() {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/10 p-6 text-center text-muted-foreground">
      <Clock className="mx-auto mb-2 h-5 w-5" />
      <div className="text-[12px]">
        Linha do tempo de atividade do operador disponível em breve.
      </div>
      <div className="mt-1 text-[11px]">
        Exibirá quem editou, marcou ou conciliou esta transação, com
        timestamps e contexto.
      </div>
    </div>
  )
}
