import { Crown, Lock, Trash2 } from "lucide-react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import {
  useBusinessPartnerGroup,
  useDeleteMembership,
  usePromoteGroupPrimary,
} from "@/features/billing"
import type { BusinessPartnerGroupMembership } from "@/features/billing"
import { cn } from "@/lib/utils"

function fmtCnpj(d?: string | null) {
  if (!d) return ""
  const s = d.replace(/\D/g, "")
  if (s.length === 14) {
    return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`
  }
  if (s.length === 11) {
    return `${s.slice(0, 3)}.${s.slice(3, 6)}.${s.slice(6, 9)}-${s.slice(9)}`
  }
  return d
}

/**
 * True when a membership was created by ``ensure_root_group`` (matriz/filial
 * materialization). These rows can't be removed manually — the backend
 * refuses with 400 — because ``BusinessPartner.save`` would re-create them.
 */
function isAutoRoot(m: BusinessPartnerGroupMembership): boolean {
  return (m.evidence ?? []).some((e) => e?.method === "auto_root")
}

function MembershipRow({
  membership,
  onPromote,
  onRemove,
  busy,
}: {
  membership: BusinessPartnerGroupMembership
  onPromote: () => void
  onRemove: () => void
  busy: boolean
}) {
  const isPrimary = membership.role === "primary"
  const auto = isAutoRoot(membership)
  const cantRemoveReason = isPrimary
    ? "Promova outro membro a primary antes de remover este."
    : auto
      ? "Membro auto-criado por raiz CNPJ — alterar o identifier do parceiro para dissociar."
      : null

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-2 py-1.5 text-[13px]",
        isPrimary ? "border-amber-300/40 bg-amber-50/50 dark:bg-amber-500/10" : "border-border/60 bg-muted/20",
      )}
    >
      {isPrimary ? (
        <Crown className="h-3.5 w-3.5 text-amber-500" />
      ) : (
        <span className="h-3.5 w-3.5" />
      )}
      <div className="flex-1 min-w-0">
        <div className="truncate font-medium">{membership.business_partner_name}</div>
        <div className="font-mono text-[11px] text-muted-foreground">
          {fmtCnpj(membership.business_partner_identifier)}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        {auto ? (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-info/10 px-1.5 py-0.5 text-[10px] uppercase text-info"
            title="Auto-criado a partir da raiz CNPJ"
          >
            <Lock className="h-3 w-3" />
            auto
          </span>
        ) : null}
        {!isPrimary ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={onPromote}
            disabled={busy}
            title="Promover a primary"
          >
            <Crown className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          onClick={onRemove}
          disabled={busy || cantRemoveReason != null}
          title={cantRemoveReason ?? "Remover do grupo"}
          className={cn(
            "text-destructive hover:bg-destructive/10",
            cantRemoveReason && "opacity-50",
          )}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}

/**
 * Reusable modal that shows a Group's members (accepted only) with
 * inline promote-primary and remove-member actions. Used from:
 *   - NF↔Tx review row's "Ver grupo" badge
 *   - BP edit drawer's GroupSection
 *   - Anywhere else that needs to inspect/edit a Group inline.
 *
 * Pass ``groupId={null}`` to keep the modal closed.
 */
export function GroupDetailModal({
  groupId,
  onClose,
}: {
  groupId: number | null
  onClose: () => void
}) {
  const open = groupId != null
  const group = useBusinessPartnerGroup(groupId)
  const promote = usePromoteGroupPrimary()
  const remove = useDeleteMembership()
  const busy = promote.isPending || remove.isPending

  const accepted = (group.data?.memberships ?? []).filter(
    (m) => m.review_status === "accepted",
  )

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {group.data ? `Grupo: ${group.data.name}` : "Grupo"}
          </DialogTitle>
        </DialogHeader>
        {group.isLoading ? (
          <div className="py-6 text-center text-muted-foreground">Carregando…</div>
        ) : !group.data ? (
          <div className="py-6 text-center text-muted-foreground">Grupo não encontrado.</div>
        ) : (
          <div className="space-y-3">
            <p className="text-[12px] text-muted-foreground">
              {accepted.length} {accepted.length === 1 ? "membro aceito" : "membros aceitos"}.
              Membros marcados <span className="inline-flex items-center gap-1 rounded-full bg-info/10 px-1.5 text-[10px] uppercase text-info">auto</span>{" "}
              vêm da raiz CNPJ e só podem ser removidos alterando o identifier do parceiro.
            </p>
            <div className="max-h-[60vh] space-y-1 overflow-y-auto">
              {accepted.map((m) => (
                <MembershipRow
                  key={m.id}
                  membership={m}
                  busy={busy}
                  onPromote={() =>
                    promote.mutate({
                      groupId: group.data!.id,
                      membershipId: m.id,
                    })
                  }
                  onRemove={() => remove.mutate(m.id)}
                />
              ))}
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
