import { useState } from "react"
import { CheckCircle2, XCircle, MinusCircle, RefreshCw, Clock } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAiKeyStatus } from "@/features/reports"
import type { AiProviderStatus } from "@/features/reports"

/**
 * Side-by-side cards for each AI provider showing whether the shared key
 * is configured, whether a live ping went through, and how long it took.
 *
 * The backend caches ping results for 5 minutes so repeat renders don't
 * hammer the providers. ``Testar novamente`` bypasses the cache.
 */
export function KeyStatusCards() {
  const { data, isLoading, refresh, isError } = useAiKeyStatus()
  const [refreshing, setRefreshing] = useState(false)

  const onRefresh = async () => {
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }

  const providers = data?.providers ?? []

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
          Chaves de API
        </h2>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
          Testar novamente
        </button>
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {isLoading && providers.length === 0 ? (
          Array.from({ length: 2 }).map((_, i) => <KeySkeleton key={i} />)
        ) : isError ? (
          <div className="col-span-full rounded-md border border-red-500/40 bg-red-500/10 p-3 text-[11px] text-red-700 dark:text-red-300">
            Falha ao consultar status das chaves.
          </div>
        ) : (
          providers.map((p) => <KeyStatusCard key={p.provider} p={p} />)
        )}
      </div>
    </div>
  )
}

function KeyStatusCard({ p }: { p: AiProviderStatus }) {
  const tone = toneFor(p.status)
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-md border p-3",
        tone.border,
        tone.bg,
      )}
    >
      <div className={cn("mt-0.5 rounded-full p-1", tone.iconBg)}>
        {p.status === "ok" ? (
          <CheckCircle2 className={cn("h-4 w-4", tone.icon)} />
        ) : p.status === "error" ? (
          <XCircle className={cn("h-4 w-4", tone.icon)} />
        ) : (
          <MinusCircle className={cn("h-4 w-4", tone.icon)} />
        )}
      </div>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold capitalize">{p.provider}</span>
          <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-medium", tone.badge)}>
            {statusLabel(p.status)}
          </span>
          {p.from_cache && (
            <span
              title={`Resultado em cache (re-testar em ~5min)`}
              className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
            >
              <Clock className="h-2.5 w-2.5" /> cache
            </span>
          )}
        </div>

        <div className="text-[11px] text-muted-foreground">
          Modelo: <span className="font-mono text-foreground">{p.model ?? "—"}</span>
          {p.latency_ms != null && p.status === "ok" && (
            <span className="ml-2">Latência: <span className="font-mono">{p.latency_ms}ms</span></span>
          )}
        </div>

        {p.status === "error" && p.error_message && (
          <div
            title={p.error_message}
            className="max-w-full truncate rounded-md bg-red-500/10 px-1.5 py-1 font-mono text-[10px] text-red-700 dark:text-red-300"
          >
            {p.error_type ?? "Erro"}: {p.error_message}
          </div>
        )}

        {p.status === "not_configured" && (
          <div className="text-[10px] text-muted-foreground">
            Nenhuma chave configurada para este provedor.
          </div>
        )}

        {p.checked_at && (
          <div className="text-[10px] text-muted-foreground/80">
            Verificado: {formatTime(p.checked_at)}
          </div>
        )}
      </div>
    </div>
  )
}

function KeySkeleton() {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-background/40 p-3">
      <div className="h-6 w-6 animate-pulse rounded-full bg-muted" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-24 animate-pulse rounded bg-muted" />
        <div className="h-3 w-32 animate-pulse rounded bg-muted/60" />
      </div>
    </div>
  )
}

function toneFor(s: AiProviderStatus["status"]) {
  if (s === "ok") {
    return {
      border: "border-emerald-500/30",
      bg: "bg-emerald-500/5",
      iconBg: "bg-emerald-500/10",
      icon: "text-emerald-600",
      badge: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400",
    }
  }
  if (s === "error") {
    return {
      border: "border-red-500/30",
      bg: "bg-red-500/5",
      iconBg: "bg-red-500/10",
      icon: "text-red-600",
      badge: "bg-red-500/20 text-red-700 dark:text-red-400",
    }
  }
  return {
    border: "border-border",
    bg: "bg-muted/20",
    iconBg: "bg-muted",
    icon: "text-muted-foreground",
    badge: "bg-muted text-muted-foreground",
  }
}

function statusLabel(s: AiProviderStatus["status"]): string {
  if (s === "ok") return "saudável"
  if (s === "error") return "com erro"
  return "não configurado"
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    })
  } catch {
    return iso
  }
}
