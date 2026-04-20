import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Bell, CheckCheck, Check, AlertCircle, XCircle, Sparkles } from "lucide-react"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTenant } from "@/providers/TenantProvider"
import { useNotificationsStore } from "@/stores/notifications-store"
import { reconApi } from "@/features/reconciliation/api"
import { cn, formatDateTime } from "@/lib/utils"

const ICON_BY_TYPE: Record<string, typeof Bell> = {
  task_completed: Check,
  task_failed: XCircle,
  task_cancelled: AlertCircle,
  reconciliation_matched: Sparkles,
  reconciliation_approved: CheckCheck,
}

const TONE_BY_TYPE: Record<string, string> = {
  task_completed: "text-success",
  task_failed: "text-danger",
  task_cancelled: "text-muted-foreground",
  reconciliation_matched: "text-primary",
  reconciliation_approved: "text-primary",
}

export function NotificationBell() {
  const navigate = useNavigate()
  const { tenant } = useTenant()
  const lastSeen = useNotificationsStore((s) => s.lastSeen)
  const markAllRead = useNotificationsStore((s) => s.markAllRead)
  const [open, setOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["notifications", tenant?.subdomain],
    queryFn: () => reconApi.getNotifications({ limit: 20 }).catch(() => ({ as_of: "", items: [] })),
    enabled: !!tenant?.subdomain,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: false,
  })

  const items = data?.items ?? []
  const unreadCount = useMemo(() => {
    if (!lastSeen) return items.length
    return items.filter((it) => !it.created_at || it.created_at > lastSeen).length
  }, [items, lastSeen])

  const onOpenChange = (v: boolean) => {
    setOpen(v)
    if (v && unreadCount > 0) {
      // Delay a tick so the badge doesn't flash to zero before the panel is visible
      setTimeout(() => markAllRead(), 150)
    }
  }

  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          className="relative grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Notificações"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-primary px-1 text-[9px] font-bold text-primary-foreground">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[360px] p-0">
        <div className="hairline flex h-10 items-center justify-between px-3">
          <span className="text-[12px] font-semibold">Notificações</span>
          {items.length > 0 && (
            <button
              onClick={() => markAllRead()}
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
            >
              <CheckCheck className="h-3 w-3" /> Marcar tudo lido
            </button>
          )}
        </div>
        <div className="max-h-[400px] overflow-y-auto">
          {isLoading ? (
            <div className="p-3 text-[12px] text-muted-foreground">Carregando…</div>
          ) : items.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-[12px] text-muted-foreground">
              Nenhuma atividade recente.
            </div>
          ) : (
            items.map((it) => {
              const Icon = ICON_BY_TYPE[it.type] ?? Bell
              const tone = TONE_BY_TYPE[it.type] ?? "text-muted-foreground"
              const isUnread = !lastSeen || (it.created_at && it.created_at > lastSeen)
              return (
                <button
                  key={it.key}
                  onClick={() => { navigate(it.url); setOpen(false) }}
                  className={cn(
                    "flex w-full items-start gap-2.5 border-b border-border/60 px-3 py-2.5 text-left text-[12px] transition-colors hover:bg-accent/50",
                  )}
                >
                  <div className={cn("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-muted", tone)}>
                    <Icon className="h-3 w-3" />
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium">{it.title}</span>
                      {isUnread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                    </div>
                    {it.subtitle && <span className="truncate text-[11px] text-muted-foreground">{it.subtitle}</span>}
                    {it.created_at && (
                      <span className="mt-0.5 text-[10px] text-muted-foreground/70">{formatDateTime(it.created_at)}</span>
                    )}
                  </div>
                </button>
              )
            })
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
