import { useEffect, useState } from "react"
import { ExternalLink, Save, X } from "lucide-react"
import { Link } from "react-router-dom"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useSaveAccount } from "@/features/reconciliation"
import {
  CATEGORY_CODES_BY_ORDER,
  REPORT_CATEGORY_STYLES,
  TAG_LABELS,
} from "@/features/reconciliation/taxonomy_labels"
import { cn } from "@/lib/utils"
import type { AccountLite } from "@/features/reconciliation/types"

/**
 * In-place editor for an account's report wiring (``report_category``
 * + ``tags``). Opened from any account row on the Demonstrativos
 * page so operators can fix mis-classifications without navigating
 * away from the report.
 *
 * Scope is intentionally tight:
 *   * Only ``report_category`` and ``tags`` are editable here. Name,
 *     parent, MPTT structure, currency etc. stay on the dedicated
 *     Plano-de-contas page where the tree context matters.
 *   * Saving PATCHes the account and invalidates the accounts query
 *     in ``useSaveAccount`` — the report numbers update on the next
 *     React Query refetch (typically immediately after the modal
 *     closes thanks to the ``staleTime`` of the accounts hook).
 *
 * The pencil icon on every account row in the DRE / Balanço / DFC
 * drill is the entry point. Closing the modal without changes is
 * cheap; we only PATCH on Save.
 */
export function AccountWiringModal({
  account,
  open,
  onClose,
}: {
  account: AccountLite | null
  open: boolean
  onClose: () => void
}) {
  // Local copy of the wiring so the form is unaffected by background
  // refetches while it's open. Reset whenever the target changes.
  const [category, setCategory] = useState<string>("")
  const [tags, setTags] = useState<Set<string>>(new Set())
  const save = useSaveAccount()

  useEffect(() => {
    if (account) {
      setCategory(account.report_category ?? "")
      setTags(new Set(account.tags ?? []))
    }
  }, [account?.id, open])

  if (!account) return null

  const dirty =
    (account.report_category ?? "") !== category ||
    !setsEqual(new Set(account.tags ?? []), tags)

  const submit = async () => {
    if (!dirty) {
      onClose()
      return
    }
    await save.mutateAsync({
      id: account.id,
      body: {
        report_category: category || null,
        tags: Array.from(tags),
      },
    })
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="truncate">{account.name}</span>
            <Link
              to={`/accounting/accounts?focus=${account.id}`}
              onClick={onClose}
              className="text-muted-foreground hover:text-primary"
              title="Abrir no Plano de contas"
            >
              <ExternalLink className="h-4 w-4" />
            </Link>
          </DialogTitle>
          <DialogDescription>
            Edite a categoria e os marcadores que determinam onde esta
            conta aparece nos demonstrativos. Salvar atualiza os
            relatórios sem fechar o painel.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Categoria de relatório
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-8 w-full rounded-md border border-border bg-surface-2 px-2 text-[12px] outline-none"
            >
              <option value="">— sem categoria (herda do pai) —</option>
              {CATEGORY_CODES_BY_ORDER.map((code) => (
                <option key={code} value={code}>
                  {REPORT_CATEGORY_STYLES[code]?.label ?? code}
                </option>
              ))}
            </select>
            {account.effective_category &&
              account.effective_category !== account.report_category && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  Atualmente herda{" "}
                  <code className="text-foreground">
                    {REPORT_CATEGORY_STYLES[account.effective_category]?.label ??
                      account.effective_category}
                  </code>{" "}
                  do ancestral. Defina aqui para sobrepor.
                </div>
              )}
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Marcadores ({tags.size})
            </label>
            <div className="grid grid-cols-3 gap-1">
              {Object.entries(TAG_LABELS).map(([code, label]) => {
                const checked = tags.has(code)
                return (
                  <button
                    key={code}
                    type="button"
                    onClick={() => {
                      const next = new Set(tags)
                      if (checked) next.delete(code)
                      else next.add(code)
                      setTags(next)
                    }}
                    className={cn(
                      "h-7 rounded-md border px-2 text-left text-[11px] transition-colors",
                      checked
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-border bg-surface-2 text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              Marcadores sobrepõem a categoria para fins de DFC (ex.
              <code className="mx-1 text-foreground">debt</code>→ FCF,
              <code className="mx-1 text-foreground">fixed_asset</code>→ FCI).
            </div>
          </div>
        </div>

        <DialogFooter className="mt-2 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent"
          >
            <X className="h-3.5 w-3.5" /> Cancelar
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!dirty || save.isPending}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90",
              (!dirty || save.isPending) && "opacity-50 cursor-not-allowed",
            )}
          >
            <Save className="h-3.5 w-3.5" />
            {save.isPending ? "Salvando…" : "Salvar"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function setsEqual<T>(a: Set<T>, b: Set<T>) {
  if (a.size !== b.size) return false
  for (const v of a) if (!b.has(v)) return false
  return true
}
