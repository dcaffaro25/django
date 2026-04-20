import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useQuery } from "@tanstack/react-query"
import { Command } from "cmdk"
import {
  LayoutDashboard, ArrowLeftRight, ListChecks, Sparkles, SlidersHorizontal, Workflow, Scale,
  Wallet, Receipt, BookOpen, FileCog, FileBarChart, CreditCard, Users, Boxes, Settings,
  Building2, Loader2, Search, Brain,
} from "lucide-react"
import { useAppStore } from "@/stores/app-store"
import { useTenant } from "@/providers/TenantProvider"
import { reconApi } from "@/features/reconciliation/api"
import { cn } from "@/lib/utils"

type Item = { key: string; path: string; icon: typeof LayoutDashboard; group: string }

const ITEMS: Item[] = [
  { key: "reconciliation_dashboard", path: "/recon", icon: LayoutDashboard, group: "reconciliation" },
  { key: "reconciliation_workbench", path: "/recon/workbench", icon: ArrowLeftRight, group: "reconciliation" },
  { key: "reconciliation_tasks", path: "/recon/tasks", icon: ListChecks, group: "reconciliation" },
  { key: "reconciliation_suggestions", path: "/recon/suggestions", icon: Sparkles, group: "reconciliation" },
  { key: "reconciliation_configs", path: "/recon/configs", icon: SlidersHorizontal, group: "reconciliation" },
  { key: "reconciliation_pipelines", path: "/recon/pipelines", icon: Workflow, group: "reconciliation" },
  { key: "reconciliation_embeddings", path: "/recon/embeddings", icon: Brain, group: "reconciliation" },
  { key: "reconciliation_balances", path: "/recon/balances", icon: Scale, group: "reconciliation" },
  { key: "bank_accounts", path: "/accounting/bank-accounts", icon: Wallet, group: "accounting" },
  { key: "bank_transactions", path: "/accounting/bank-transactions", icon: Wallet, group: "accounting" },
  { key: "transactions", path: "/accounting/transactions", icon: Receipt, group: "accounting" },
  { key: "journal_entries", path: "/accounting/journal-entries", icon: BookOpen, group: "accounting" },
  { key: "accounts", path: "/accounting/accounts", icon: FileCog, group: "accounting" },
  { key: "statements", path: "/statements", icon: FileBarChart, group: "financial_statements" },
  { key: "billing", path: "/billing", icon: CreditCard, group: "other" },
  { key: "hr", path: "/hr", icon: Users, group: "other" },
  { key: "inventory", path: "/inventory", icon: Boxes, group: "other" },
  { key: "entities", path: "/settings/entities", icon: Building2, group: "other" },
  { key: "settings", path: "/settings", icon: Settings, group: "other" },
]

const GROUP_ICON: Record<string, typeof LayoutDashboard> = {
  transaction: Receipt,
  bank_transaction: Wallet,
  journal_entry: BookOpen,
  entity: Building2,
  account: FileCog,
  bank_account: Wallet,
  reconciliation_config: SlidersHorizontal,
  reconciliation_pipeline: Workflow,
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return v
}

export function CommandPalette() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = useAppStore((s) => s.commandOpen)
  const setOpen = useAppStore((s) => s.setCommandOpen)
  const { tenants, switchTenant, tenant } = useTenant()

  const [query, setQuery] = useState("")
  const debounced = useDebounced(query.trim(), 200)
  const shouldSearch = !!tenant?.subdomain && debounced.length >= 2

  const { data, isFetching } = useQuery({
    queryKey: ["search", tenant?.subdomain, debounced],
    queryFn: () => reconApi.search(debounced, 8),
    enabled: shouldSearch,
    staleTime: 30_000,
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [setOpen])

  // Reset input when palette closes
  useEffect(() => {
    if (!open) setQuery("")
  }, [open])

  const go = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  const navGroups = Array.from(new Set(ITEMS.map((i) => i.group)))
  const resultGroups = data?.groups ?? []
  const hasResults = resultGroups.length > 0

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label={t("command.placeholder")}
      shouldFilter={!shouldSearch /* when searching, backend filters; otherwise cmdk fuzzy-filters nav */}
      className={cn(
        "fixed left-1/2 top-[18%] z-50 w-[720px] max-w-[92vw] -translate-x-1/2",
        "animate-slide-up overflow-hidden rounded-xl border border-border surface-2 shadow-elev",
      )}
    >
      <div className="pointer-events-auto">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder={t("command.placeholder") ?? ""}
            className="h-11 w-full border-0 border-b border-border bg-transparent pl-10 pr-10 text-sm outline-none placeholder:text-muted-foreground"
          />
          {isFetching && shouldSearch && (
            <Loader2 className="absolute right-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-muted-foreground" />
          )}
        </div>
        <Command.List className="max-h-[480px] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
            {shouldSearch ? (hasResults ? null : `Nenhum resultado para "${debounced}"`) : t("command.empty")}
          </Command.Empty>

          {/* Backend search results (grouped) */}
          {shouldSearch && resultGroups.map((g) => (
            <Command.Group
              key={g.type}
              heading={g.label}
              className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground/70"
            >
              {g.items.map((it) => {
                const Icon = GROUP_ICON[g.type] ?? Search
                return (
                  <Command.Item
                    key={`${g.type}-${it.id}`}
                    value={`${g.type} ${it.id} ${it.title} ${it.subtitle ?? ""}`}
                    onSelect={() => go(it.url)}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] aria-selected:bg-accent aria-selected:text-foreground"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate">{it.title}</span>
                      {it.subtitle && (
                        <span className="truncate text-[11px] text-muted-foreground">{it.subtitle}</span>
                      )}
                    </div>
                    <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">#{it.id}</span>
                  </Command.Item>
                )
              })}
            </Command.Group>
          ))}

          {/* Static nav — always shown, cmdk fuzzy-filters when not searching backend */}
          {!shouldSearch && navGroups.map((g) => (
            <Command.Group key={g} heading={t(`nav.${g}`)} className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground/70">
              {ITEMS.filter((i) => i.group === g).map((i) => {
                const Icon = i.icon
                return (
                  <Command.Item
                    key={i.path}
                    value={`${t(`nav.${i.key}`)} ${i.path}`}
                    onSelect={() => go(i.path)}
                    className="flex h-8 cursor-pointer items-center gap-2.5 rounded-md px-2 text-[13px] aria-selected:bg-accent aria-selected:text-foreground"
                  >
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span>{t(`nav.${i.key}`)}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground/70">{i.path}</span>
                  </Command.Item>
                )
              })}
            </Command.Group>
          ))}

          {!shouldSearch && tenants.length > 1 && (
            <Command.Group heading={t("tenant.workspace")} className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground/70">
              {tenants.map((ten) => (
                <Command.Item
                  key={ten.id}
                  value={`tenant ${ten.name} ${ten.subdomain}`}
                  onSelect={() => { switchTenant(ten.subdomain); setOpen(false) }}
                  className="flex h-8 cursor-pointer items-center gap-2.5 rounded-md px-2 text-[13px] aria-selected:bg-accent"
                >
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{ten.name}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    {tenant?.id === ten.id ? "✓ " : ""}{ten.subdomain}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>

        <div className="hairline border-t bg-surface-1 px-3 py-1.5 text-[10px] text-muted-foreground/70">
          {shouldSearch
            ? `Busca global · ${data?.total ?? 0} resultado${(data?.total ?? 0) === 1 ? "" : "s"}`
            : "Digite 2+ letras para buscar em todo o sistema · ↵ para selecionar"}
        </div>
      </div>
    </Command.Dialog>
  )
}
