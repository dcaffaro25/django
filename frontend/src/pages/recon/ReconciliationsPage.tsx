import { Fragment, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  Calculator,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Edit3,
  Loader2,
  RefreshCw,
  Search,
  Unlink2,
  X,
} from "lucide-react"

import { SectionHeader } from "@/components/ui/section-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  useRecalcUnpostedFlags,
  useReconciliationSummaries,
  useUnmatchReconciliation,
  useUpdateReconciliation,
} from "@/features/reconciliation"
import type { ReconciliationSummary } from "@/features/reconciliation/types"
import { cn, formatCurrency, formatDate } from "@/lib/utils"

type StatusScope = "closed" | "open" | "all"

const STATUS_SCOPE_PARAM: Record<StatusScope, string | undefined> = {
  closed: "matched,approved",
  open: "open,pending,review",
  // Everything except soft-deleted "unmatched"
  all: "matched,approved,open,pending,review,unmatched",
}

function n(v: number | null | undefined) {
  return v == null ? 0 : Number(v)
}

function matchesSearch(row: ReconciliationSummary, q: string) {
  if (!q) return true
  const hay = [
    row.reference ?? "",
    row.notes ?? "",
    row.bank_description,
    row.book_description,
    String(row.reconciliation_id),
  ]
    .join(" ")
    .toLowerCase()
  return hay.includes(q.toLowerCase())
}

export function ReconciliationsPage() {
  const { t } = useTranslation(["reconciliation", "common"])

  const [statusScope, setStatusScope] = useState<StatusScope>("closed")
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [selected, setSelected] = useState<Set<number>>(new Set())

  // Server-side status filter; search + selection run client-side for instant feedback.
  const summariesParams = useMemo(
    () => ({ status: STATUS_SCOPE_PARAM[statusScope], ordering: "-id" }),
    [statusScope],
  )
  const {
    data: rows = [],
    isLoading,
    isFetching,
    refetch,
  } = useReconciliationSummaries(summariesParams)

  const filtered = useMemo(() => {
    const q = search.trim()
    if (!q) return rows
    return rows.filter((r) => matchesSearch(r, q))
  }, [rows, search])

  const update = useUpdateReconciliation()
  const unmatch = useUnmatchReconciliation()
  const recalc = useRecalcUnpostedFlags()

  // Dialog state ------------------------------------------------------------
  const [approveTarget, setApproveTarget] = useState<ReconciliationSummary | null>(null)
  const [unmatchTarget, setUnmatchTarget] = useState<ReconciliationSummary | null>(null)
  const [unmatchReason, setUnmatchReason] = useState("")
  const [unmatchAlsoDelete, setUnmatchAlsoDelete] = useState(false)
  const [editTarget, setEditTarget] = useState<ReconciliationSummary | null>(null)
  const [editReference, setEditReference] = useState("")
  const [editNotes, setEditNotes] = useState("")

  const openUnmatch = (row: ReconciliationSummary) => {
    setUnmatchTarget(row)
    setUnmatchReason("")
    setUnmatchAlsoDelete(false)
  }

  const openEdit = (row: ReconciliationSummary) => {
    setEditTarget(row)
    setEditReference(row.reference ?? "")
    setEditNotes(row.notes ?? "")
  }

  const confirmApprove = () => {
    if (!approveTarget) return
    update.mutate(
      { id: approveTarget.reconciliation_id, body: { status: "approved" } },
      {
        onSuccess: () => {
          toast.success(t("matches.toasts.approved"))
          setApproveTarget(null)
        },
        onError: () => toast.error(t("matches.toasts.error")),
      },
    )
  }

  const confirmUnmatch = () => {
    if (!unmatchTarget) return
    const targetId = unmatchTarget.reconciliation_id
    unmatch.mutate(
      {
        id: targetId,
        reason: unmatchReason.trim() || undefined,
        delete: unmatchAlsoDelete,
      },
      {
        onSuccess: () => {
          toast.success(t("matches.toasts.unmatched"))
          setUnmatchTarget(null)
          setSelected((s) => {
            const next = new Set(s)
            next.delete(targetId)
            return next
          })
        },
        onError: () => toast.error(t("matches.toasts.error")),
      },
    )
  }

  const onRecalcClick = () => {
    recalc.mutate(undefined, {
      onSuccess: (res) =>
        toast.success(t("matches.toasts.recalc_queued", { task_id: res.task_id })),
      onError: () => toast.error(t("matches.toasts.error")),
    })
  }

  const confirmEdit = () => {
    if (!editTarget) return
    update.mutate(
      {
        id: editTarget.reconciliation_id,
        body: { reference: editReference, notes: editNotes },
      },
      {
        onSuccess: () => {
          toast.success(t("matches.toasts.updated"))
          setEditTarget(null)
        },
        onError: () => toast.error(t("matches.toasts.error")),
      },
    )
  }

  // Bulk actions ------------------------------------------------------------
  const bulkApprove = () => {
    const ids = [...selected]
    if (!ids.length) return
    Promise.all(
      ids.map((id) =>
        update.mutateAsync({ id, body: { status: "approved" } }).catch(() => null),
      ),
    ).then((results) => {
      const ok = results.filter(Boolean).length
      toast.success(t("matches.toasts.approved") + ` (${ok}/${ids.length})`)
      setSelected(new Set())
    })
  }

  // Selection helpers -------------------------------------------------------
  const allSelected = filtered.length > 0 && filtered.every((r) => selected.has(r.reconciliation_id))
  const someSelected = filtered.some((r) => selected.has(r.reconciliation_id)) && !allSelected
  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered.map((r) => r.reconciliation_id)))
    }
  }
  const toggleOne = (id: number) => {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleExpand = (id: number) => {
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Render ------------------------------------------------------------------
  const totalLabel = t("matches.total_count", { count: filtered.length })

  return (
    <div className="space-y-4">
      <SectionHeader
        title={t("matches.title")}
        subtitle={t("matches.subtitle") ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{totalLabel}</span>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              onClick={() => void refetch()}
              disabled={isFetching}
              title={t("common:actions.refresh") ?? ""}
            >
              <RefreshCw className={cn("mr-1 h-3.5 w-3.5", isFetching && "animate-spin")} />
              {t("common:actions.refresh")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              onClick={onRecalcClick}
              disabled={recalc.isPending}
              title={t("matches.actions.recalc") ?? ""}
            >
              {recalc.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Calculator className="mr-1 h-3.5 w-3.5" />
              )}
              {t("matches.actions.recalc")}
            </Button>
          </div>
        }
      />

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-2">
        <Select value={statusScope} onValueChange={(v) => setStatusScope(v as StatusScope)}>
          <SelectTrigger className="h-8 w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="closed">{t("matches.filters.status_closed")}</SelectItem>
            <SelectItem value="open">{t("matches.filters.status_open")}</SelectItem>
            <SelectItem value="all">{t("matches.filters.status_all")}</SelectItem>
          </SelectContent>
        </Select>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("matches.filters.search") ?? ""}
            className="h-8 w-64 pl-7 text-[13px]"
          />
        </div>

        {(search || statusScope !== "closed") && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8"
            onClick={() => {
              setSearch("")
              setStatusScope("closed")
            }}
          >
            <X className="mr-1 h-3.5 w-3.5" />
            {t("matches.filters.clear")}
          </Button>
        )}

        {/* Bulk actions anchored right */}
        {selected.size > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {t("matches.bulk.selected", { count: selected.size })}
            </span>
            <Button size="sm" variant="outline" onClick={bulkApprove}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              {t("matches.bulk.approve")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              {t("matches.bulk.clear")}
            </Button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 px-3">
                <Checkbox
                  checked={allSelected || (someSelected ? "indeterminate" : false)}
                  onCheckedChange={toggleAll}
                  aria-label="Select all"
                />
              </TableHead>
              <TableHead className="w-10 px-2" />
              <TableHead className="w-16">{t("matches.columns.id")}</TableHead>
              <TableHead className="w-28">{t("matches.columns.status")}</TableHead>
              <TableHead>{t("matches.columns.bank_records")}</TableHead>
              <TableHead>{t("matches.columns.book_records")}</TableHead>
              <TableHead className="text-right">{t("matches.columns.bank_sum")}</TableHead>
              <TableHead className="text-right">{t("matches.columns.book_sum")}</TableHead>
              <TableHead className="text-right">{t("matches.columns.difference")}</TableHead>
              <TableHead className="w-40">{t("matches.columns.dates")}</TableHead>
              <TableHead>{t("matches.columns.reference")}</TableHead>
              <TableHead className="w-[140px] text-right">
                {t("matches.columns.actions")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={12} className="py-10 text-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
                  {t("matches.loading")}
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={12} className="py-10 text-center text-sm text-muted-foreground">
                  {t("matches.empty")}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((row) => {
                const isExpanded = expanded.has(row.reconciliation_id)
                const isSelected = selected.has(row.reconciliation_id)
                const diff = n(row.difference)
                const hasDelta = Math.abs(diff) > 0.005
                const canApprove = row.status === "matched"
                return (
                  <Fragment key={row.reconciliation_id}>
                    <TableRow
                      data-state={isSelected ? "selected" : undefined}
                    >
                      <TableCell className="px-3">
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleOne(row.reconciliation_id)}
                          aria-label={`Select reconciliation ${row.reconciliation_id}`}
                        />
                      </TableCell>
                      <TableCell className="px-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={() => toggleExpand(row.reconciliation_id)}
                          aria-label={isExpanded ? t("matches.row.collapse") : t("matches.row.expand")}
                        >
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </Button>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.reconciliation_id}</TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <StatusBadge status={row.status} className="w-fit" />
                          {!row.same_entity && (
                            <span className="text-[10px] text-warning">
                              {t("matches.row.mismatch_entity")}
                            </span>
                          )}
                          {!row.same_company && (
                            <span className="text-[10px] text-danger">
                              {t("matches.row.mismatch_company")}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        {t("matches.row.bank_count", { count: row.bank_ids.length })}
                      </TableCell>
                      <TableCell className="text-xs">
                        {t("matches.row.book_count", { count: row.book_ids.length })}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {formatCurrency(n(row.bank_sum_value))}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {formatCurrency(n(row.book_sum_value))}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-mono text-xs",
                          hasDelta ? "text-warning" : "text-muted-foreground",
                        )}
                      >
                        {hasDelta ? formatCurrency(diff) : t("matches.row.exact")}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {row.min_date && row.max_date ? (
                          row.min_date === row.max_date ? (
                            formatDate(row.min_date)
                          ) : (
                            <>
                              {formatDate(row.min_date)} – {formatDate(row.max_date)}
                            </>
                          )
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="max-w-[180px] truncate text-xs" title={row.reference ?? ""}>
                        {row.reference || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          {canApprove && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0"
                              title={t("matches.actions.approve") ?? ""}
                              onClick={() => setApproveTarget(row)}
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 w-7 p-0"
                            title={t("matches.actions.edit") ?? ""}
                            onClick={() => openEdit(row)}
                          >
                            <Edit3 className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 w-7 p-0 text-danger hover:text-danger"
                            title={t("matches.actions.unmatch") ?? ""}
                            onClick={() => openUnmatch(row)}
                          >
                            <Unlink2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow className="bg-muted/20">
                        <TableCell colSpan={12} className="py-3">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                {t("matches.columns.bank_records")}
                              </div>
                              <pre className="whitespace-pre-wrap break-words rounded border bg-background p-2 text-[11px] font-mono">
                                {row.bank_description || "—"}
                              </pre>
                            </div>
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                {t("matches.columns.book_records")}
                              </div>
                              <pre className="whitespace-pre-wrap break-words rounded border bg-background p-2 text-[11px] font-mono">
                                {row.book_description || "—"}
                              </pre>
                            </div>
                            {row.notes && (
                              <div className="md:col-span-2">
                                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                  {t("matches.columns.notes")}
                                </div>
                                <div className="whitespace-pre-wrap rounded border bg-background p-2 text-[11px]">
                                  {row.notes}
                                </div>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Approve dialog */}
      <AlertDialog open={approveTarget !== null} onOpenChange={(o) => !o && setApproveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("matches.dialogs.approve_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("matches.dialogs.approve_description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common:actions.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmApprove} disabled={update.isPending}>
              {update.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              {t("matches.dialogs.approve_confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Unmatch dialog */}
      <AlertDialog open={unmatchTarget !== null} onOpenChange={(o) => !o && setUnmatchTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("matches.dialogs.unmatch_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("matches.dialogs.unmatch_description", {
                bank: unmatchTarget?.bank_ids.length ?? 0,
                book: unmatchTarget?.book_ids.length ?? 0,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">
                {t("matches.dialogs.unmatch_reason")}
              </label>
              <Textarea
                value={unmatchReason}
                onChange={(e) => setUnmatchReason(e.target.value)}
                rows={3}
              />
            </div>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox
                checked={unmatchAlsoDelete}
                onCheckedChange={(v) => setUnmatchAlsoDelete(v === true)}
              />
              {t("matches.dialogs.unmatch_delete")}
            </label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common:actions.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmUnmatch}
              disabled={unmatch.isPending}
              className="bg-danger text-danger-foreground hover:bg-danger/90"
            >
              {unmatch.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              {t("matches.dialogs.unmatch_confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit dialog */}
      <Dialog open={editTarget !== null} onOpenChange={(o) => !o && setEditTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("matches.dialogs.edit_title")}</DialogTitle>
            <DialogDescription>
              #{editTarget?.reconciliation_id} · <StatusBadge status={editTarget?.status ?? ""} />
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">
                {t("matches.dialogs.edit_reference")}
              </label>
              <Input
                value={editReference}
                onChange={(e) => setEditReference(e.target.value)}
                maxLength={50}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">
                {t("matches.dialogs.edit_notes")}
              </label>
              <Textarea
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              {t("common:actions.cancel")}
            </Button>
            <Button onClick={confirmEdit} disabled={update.isPending}>
              {update.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              {t("matches.dialogs.edit_save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
