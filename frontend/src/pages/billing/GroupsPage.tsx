import { useState } from "react"
import {
  CheckCircle2, XCircle, ChevronRight, ChevronDown,
  GitMerge, Crown, Network, Tag, RefreshCw, Sparkles, GitBranch,
  Trash2, Lock,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs"
import {
  useBusinessPartnerAliases,
  useBusinessPartnerGroups,
  useCnpjRootClusters,
  useDeleteMembership,
  useGroupMemberships,
  useAcceptAlias,
  useAcceptMembership,
  useMaterializeCnpjRoot,
  useMergeGroup,
  usePromoteGroupPrimary,
  useRejectAlias,
  useRejectMembership,
} from "@/features/billing"
import type {
  BusinessPartnerAlias,
  BusinessPartnerGroup,
  BusinessPartnerGroupMembership,
  CnpjRootCluster,
} from "@/features/billing"
import { ConfidenceBadge } from "./components/ConfidenceBadge"
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

function PartnerTypeChip({ type }: { type: string }) {
  const tone =
    type === "client"
      ? "bg-info/10 text-info"
      : type === "vendor"
        ? "bg-warning/10 text-warning"
        : "bg-muted text-muted-foreground"
  return (
    <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wide", tone)}>
      {type}
    </span>
  )
}

function isMergeSuggestion(m: BusinessPartnerGroupMembership): boolean {
  return (m.evidence ?? []).some((e) => e?.kind === "merge")
}

// =====================================================
// Section 1: pending suggestions
// =====================================================

function SuggestionsSection({ mergeOnly }: { mergeOnly: boolean }) {
  const memberships = useGroupMemberships({
    review_status: "suggested",
    ...(mergeOnly ? { merge_only: 1 } : {}),
  })
  const accept = useAcceptMembership()
  const reject = useRejectMembership()

  if (memberships.isLoading) {
    return <div className="py-8 text-center text-muted-foreground">Carregando…</div>
  }
  const items = memberships.data ?? []
  if (items.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        {mergeOnly
          ? "Nenhuma sugestão de mesclagem pendente."
          : "Nenhuma sugestão de agrupamento pendente."}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {items.map((m) => {
        const isMerge = isMergeSuggestion(m)
        return (
          <div
            key={m.id}
            className={cn(
              "rounded-lg border bg-card p-3",
              isMerge ? "border-warning/40" : "border-border",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-sm">
                  {isMerge ? (
                    <span className="inline-flex items-center gap-1 rounded bg-warning/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-warning">
                      <GitMerge className="h-3 w-3" /> merge
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded bg-info/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-info">
                      <Network className="h-3 w-3" /> grupo
                    </span>
                  )}
                  <ConfidenceBadge value={m.confidence} />
                  <span className="text-xs text-muted-foreground">hits {m.hit_count}</span>
                </div>
                <div className="mt-1 grid grid-cols-1 gap-1 sm:grid-cols-2">
                  <div className="rounded border border-border/60 bg-muted/30 p-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      adicionar a
                    </div>
                    <div className="font-medium text-sm">{m.group_name}</div>
                  </div>
                  <div className="rounded border border-border/60 bg-muted/30 p-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      parceiro
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium truncate">{m.business_partner_name}</span>
                      <PartnerTypeChip type={m.business_partner_partner_type} />
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      {fmtCnpj(m.business_partner_identifier)}
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 flex-col gap-1.5">
                <Button
                  size="sm"
                  variant="default"
                  disabled={accept.isPending}
                  onClick={() => accept.mutate(m.id)}
                >
                  <CheckCircle2 className="h-4 w-4 mr-1" />
                  Aceitar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={reject.isPending}
                  onClick={() => reject.mutate(m.id)}
                >
                  <XCircle className="h-4 w-4 mr-1" />
                  Rejeitar
                </Button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// =====================================================
// Section 2: existing groups
// =====================================================

function isAutoRootMembership(m: BusinessPartnerGroupMembership): boolean {
  return (m.evidence ?? []).some((e) => e?.method === "auto_root")
}

function GroupRow({ group }: { group: BusinessPartnerGroup }) {
  const [open, setOpen] = useState(false)
  const promote = usePromoteGroupPrimary()
  const reject = useRejectMembership()
  const accept = useAcceptMembership()
  const removeMember = useDeleteMembership()
  const merge = useMergeGroup()
  const [mergeId, setMergeId] = useState<string>("")

  const accepted = (group.memberships ?? []).filter((m) => m.review_status === "accepted")
  const suggested = (group.memberships ?? []).filter((m) => m.review_status === "suggested")

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/30"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <Crown className="h-4 w-4 text-amber-500" />
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{group.name}</div>
          <div className="font-mono text-[11px] text-muted-foreground">
            {fmtCnpj(group.primary_partner_identifier)}
          </div>
        </div>
        <span className="text-xs text-muted-foreground">
          {group.accepted_member_count} aceitos · {group.member_count} total
        </span>
      </button>

      {open ? (
        <div className="border-t border-border/60 p-3 space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Membros
          </div>
          {accepted.map((m) => {
            const auto = isAutoRootMembership(m)
            const isPrimary = m.role === "primary"
            const removeTitle = isPrimary
              ? "Promova outro membro a primary antes de remover este."
              : auto
                ? "Membro auto-criado por raiz CNPJ — alterar o identifier do parceiro para dissociar."
                : "Remover do grupo"
            return (
              <div
                key={m.id}
                className="flex items-center gap-2 rounded border border-border/60 bg-muted/20 px-2 py-1.5 text-sm"
              >
                {isPrimary ? (
                  <Crown className="h-3.5 w-3.5 text-amber-500" />
                ) : (
                  <span className="h-3.5 w-3.5" />
                )}
                <span className="flex-1 truncate">{m.business_partner_name}</span>
                <PartnerTypeChip type={m.business_partner_partner_type} />
                <span className="font-mono text-[11px] text-muted-foreground">
                  {fmtCnpj(m.business_partner_identifier)}
                </span>
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
                    onClick={() =>
                      promote.mutate({ groupId: group.id, membershipId: m.id })
                    }
                    title="Promover a primary"
                    disabled={promote.isPending}
                  >
                    <Crown className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeMember.mutate(m.id)}
                  title={removeTitle}
                  disabled={removeMember.isPending || isPrimary || auto}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            )
          })}

          {suggested.length > 0 ? (
            <>
              <div className="pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Sugestões pendentes
              </div>
              {suggested.map((m) => {
                const isMerge = isMergeSuggestion(m)
                return (
                  <div
                    key={m.id}
                    className={cn(
                      "flex items-center gap-2 rounded border px-2 py-1.5 text-sm",
                      isMerge
                        ? "border-warning/40 bg-warning/5"
                        : "border-info/40 bg-info/5",
                    )}
                  >
                    {isMerge ? (
                      <GitMerge className="h-3.5 w-3.5 text-warning" />
                    ) : (
                      <Network className="h-3.5 w-3.5 text-info" />
                    )}
                    <span className="flex-1 truncate">{m.business_partner_name}</span>
                    <ConfidenceBadge value={m.confidence} />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => accept.mutate(m.id)}
                      disabled={accept.isPending}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => reject.mutate(m.id)}
                      disabled={reject.isPending}
                    >
                      <XCircle className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )
              })}
            </>
          ) : null}

          <div className="flex items-center gap-2 pt-2">
            <Input
              type="number"
              placeholder="ID do grupo origem para mesclar"
              value={mergeId}
              onChange={(e) => setMergeId(e.target.value)}
              className="h-8 max-w-xs text-xs"
            />
            <Button
              size="sm"
              variant="outline"
              disabled={!mergeId || merge.isPending}
              onClick={() => {
                const sourceGroupId = parseInt(mergeId, 10)
                if (!Number.isFinite(sourceGroupId)) return
                merge.mutate(
                  { targetId: group.id, sourceGroupId },
                  { onSuccess: () => setMergeId("") },
                )
              }}
            >
              <GitMerge className="h-3.5 w-3.5 mr-1" />
              Mesclar para cá
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function GroupsListSection() {
  const groups = useBusinessPartnerGroups({ is_active: 1 })

  if (groups.isLoading) {
    return <div className="py-8 text-center text-muted-foreground">Carregando…</div>
  }
  const items = groups.data ?? []
  if (items.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        Nenhum grupo cadastrado ainda — eles aparecem automaticamente
        conforme você aceita vínculos NF↔Tx ou conciliações entre CNPJs distintos.
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {items.map((g) => (
        <GroupRow key={g.id} group={g} />
      ))}
    </div>
  )
}

// =====================================================
// Section 3: aliases
// =====================================================

function AliasRow({ a }: { a: BusinessPartnerAlias }) {
  const accept = useAcceptAlias()
  const reject = useRejectAlias()

  const tone =
    a.review_status === "accepted"
      ? "border-success/30 bg-success/5"
      : a.review_status === "rejected"
        ? "border-border/40 bg-muted/10 opacity-60"
        : "border-info/30 bg-info/5"

  return (
    <div className={cn("rounded-lg border p-3", tone)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <Tag className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono">{fmtCnpj(a.alias_identifier)}</span>
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
            <span className="font-medium truncate">{a.business_partner_name}</span>
            <ConfidenceBadge value={a.confidence} />
            <span className="text-xs text-muted-foreground">hits {a.hit_count}</span>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            BP {fmtCnpj(a.business_partner_identifier)} · fonte {a.source}
          </div>
        </div>
        {a.review_status === "suggested" ? (
          <div className="flex shrink-0 flex-col gap-1.5">
            <Button
              size="sm"
              variant="default"
              onClick={() => accept.mutate(a.id)}
              disabled={accept.isPending}
            >
              <CheckCircle2 className="h-4 w-4 mr-1" />
              Aceitar
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => reject.mutate(a.id)}
              disabled={reject.isPending}
            >
              <XCircle className="h-4 w-4 mr-1" />
              Rejeitar
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function CnpjRootClusterRow({ cluster }: { cluster: CnpjRootCluster }) {
  const materialize = useMaterializeCnpjRoot()
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          className="flex flex-1 items-center gap-2 text-left"
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <GitBranch className="h-4 w-4 text-info" />
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate">{cluster.primary.name}</div>
            <div className="font-mono text-[11px] text-muted-foreground">
              raiz {cluster.cnpj_root} · {cluster.size} parceiros
            </div>
          </div>
          <span className="rounded-full bg-info/10 px-1.5 py-0.5 text-[10px] uppercase text-info">
            automático
          </span>
        </button>
        <Button
          size="sm"
          variant="outline"
          disabled={materialize.isPending}
          onClick={() => materialize.mutate(cluster.cnpj_root)}
          title="Promover este cluster a um Grupo curado"
        >
          <Sparkles className="h-3.5 w-3.5 mr-1" />
          Materializar
        </Button>
      </div>
      {open ? (
        <div className="border-t border-border/60 px-3 py-2 space-y-1">
          <div className="flex items-center gap-2 text-[12px]">
            <Crown className="h-3 w-3 text-amber-500" />
            <span className="font-medium">{cluster.primary.name}</span>
            <span className="font-mono text-[11px] text-muted-foreground">
              {fmtCnpj(cluster.primary.identifier)}
            </span>
          </div>
          {cluster.members.map((m) => (
            <div key={m.id} className="flex items-center gap-2 pl-5 text-[12px]">
              <span className="truncate">{m.name}</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {fmtCnpj(m.identifier)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function CnpjRootClustersSection() {
  const clusters = useCnpjRootClusters()
  if (clusters.isLoading) {
    return <div className="py-8 text-center text-muted-foreground">Carregando…</div>
  }
  const items = clusters.data?.results ?? []
  if (items.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        Nenhum cluster por raiz CNPJ pendente — todos os matriz/filial já estão
        materializados em grupos curados.
      </div>
    )
  }
  return (
    <div>
      <p className="mb-3 text-[12px] text-muted-foreground">
        Parceiros que compartilham os 8 primeiros dígitos do CNPJ (mesma pessoa
        jurídica, estabelecimentos diferentes) e ainda não foram promovidos a um
        Grupo curado. Use "Materializar" para criar o grupo, ou rode{" "}
        <code className="rounded bg-muted px-1 font-mono text-[11px]">
          backfill_bp_groups --tenant ...
        </code>{" "}
        para fazer em massa.
      </p>
      <div className="space-y-2">
        {items.map((c) => (
          <CnpjRootClusterRow key={c.cnpj_root} cluster={c} />
        ))}
      </div>
    </div>
  )
}

function AliasesSection() {
  const [status, setStatus] = useState<"suggested" | "accepted" | "rejected">("suggested")
  const aliases = useBusinessPartnerAliases({ review_status: status })

  return (
    <div>
      <div className="mb-3 flex gap-2">
        {(["suggested", "accepted", "rejected"] as const).map((s) => (
          <Button
            key={s}
            size="sm"
            variant={s === status ? "default" : "outline"}
            onClick={() => setStatus(s)}
          >
            {s === "suggested" ? "Sugeridos" : s === "accepted" ? "Aceitos" : "Rejeitados"}
          </Button>
        ))}
      </div>
      {aliases.isLoading ? (
        <div className="py-8 text-center text-muted-foreground">Carregando…</div>
      ) : (aliases.data ?? []).length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">
          Nenhum apelido {status === "suggested" ? "pendente" : status} no momento.
        </div>
      ) : (
        <div className="space-y-2">
          {(aliases.data ?? []).map((a) => (
            <AliasRow key={a.id} a={a} />
          ))}
        </div>
      )}
    </div>
  )
}

// =====================================================
// Page
// =====================================================

export function GroupsPage() {
  const memberships = useGroupMemberships({ review_status: "suggested" })
  const groupsHook = useBusinessPartnerGroups({ is_active: 1 })
  const clusters = useCnpjRootClusters()
  const suggestionCount = (memberships.data ?? []).length
  const groupCount = (groupsHook.data ?? []).length
  const clusterCount = clusters.data?.count ?? 0

  return (
    <div>
      <SectionHeader
        title="Grupos de Parceiros"
        subtitle="Consolide branches, CNPJs distintos e CPFs de um mesmo ator econômico. Matriz/filial são materializados automaticamente; cross-CNPJ aprende com vínculos NF↔Tx e conciliações."
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              memberships.refetch()
              groupsHook.refetch()
              clusters.refetch()
            }}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Recarregar
          </Button>
        }
      />

      <Tabs defaultValue="groups" className="mt-4">
        <TabsList>
          <TabsTrigger value="groups">
            Grupos {groupCount > 0 ? `(${groupCount})` : ""}
          </TabsTrigger>
          <TabsTrigger value="suggestions">
            Sugestões {suggestionCount > 0 ? `(${suggestionCount})` : ""}
          </TabsTrigger>
          <TabsTrigger value="merges">Mesclagens</TabsTrigger>
          <TabsTrigger value="cnpj-roots">
            Raiz CNPJ {clusterCount > 0 ? `(${clusterCount})` : ""}
          </TabsTrigger>
          <TabsTrigger value="aliases">Apelidos</TabsTrigger>
        </TabsList>

        <TabsContent value="groups" className="mt-4">
          <GroupsListSection />
        </TabsContent>
        <TabsContent value="suggestions" className="mt-4">
          <SuggestionsSection mergeOnly={false} />
        </TabsContent>
        <TabsContent value="merges" className="mt-4">
          <SuggestionsSection mergeOnly={true} />
        </TabsContent>
        <TabsContent value="cnpj-roots" className="mt-4">
          <CnpjRootClustersSection />
        </TabsContent>
        <TabsContent value="aliases" className="mt-4">
          <AliasesSection />
        </TabsContent>
      </Tabs>
    </div>
  )
}
