/**
 * Admin page for the OpenAI OAuth connection.
 *
 * Renders the singleton :class:`OpenAITokenStore` state and exposes the
 * three operations a platform superuser ever needs:
 *
 *  * Connect (kick off the OAuth flow → opens OpenAI in a new tab)
 *  * Reconnect (same as connect when already connected — token expired)
 *  * Disconnect (clear the singleton)
 *
 * The OAuth callback lands on the backend, which optionally redirects
 * back here with ``?connected=1`` or ``?error=…`` (set
 * ``OPENAI_OAUTH_POST_CONNECT_REDIRECT`` to this page's URL in env).
 */
import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertTriangle, CheckCircle2, ExternalLink, Loader2, PlugZap, Power, RefreshCw,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { SectionHeader } from "@/components/ui/section-header"
import { extractApiErrorMessage } from "@/lib/api-client"
import {
  useAgentConnectionStatus,
  useRevokeAgentConnection,
  useStartAgentConnection,
} from "@/features/agent/hooks"


function StatusPill({ connected, expired }: { connected: boolean; expired: boolean }) {
  if (!connected) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
        <Power className="h-3 w-3" /> Não conectado
      </span>
    )
  }
  if (expired) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
        <AlertTriangle className="h-3 w-3" /> Token expirado
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
      <CheckCircle2 className="h-3 w-3" /> Conectado
    </span>
  )
}


function formatDate(value: string | null | undefined): string {
  if (!value) return "—"
  try {
    return new Date(value).toLocaleString("pt-BR")
  } catch {
    return value
  }
}


export function AgentConnectionPage() {
  const [params, setParams] = useSearchParams()
  const status = useAgentConnectionStatus()
  const startMut = useStartAgentConnection()
  const revokeMut = useRevokeAgentConnection()
  const [confirmingRevoke, setConfirmingRevoke] = useState(false)

  // Surface the OAuth callback's outcome (set via the backend redirect).
  useEffect(() => {
    const connected = params.get("connected")
    const error = params.get("error")
    if (connected === "1") {
      toast.success("Conta OpenAI conectada.")
      void status.refetch()
    } else if (connected === "0" && error) {
      toast.error(`Falha na conexão: ${decodeURIComponent(error)}`)
    }
    if (connected !== null) {
      params.delete("connected")
      params.delete("error")
      setParams(params, { replace: true })
    }
    // params is a stable reference on each render but the values inside are
    // what matter — eslint disable is fine here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isConnected = status.data?.is_connected ?? false
  const isExpired = status.data?.is_expired ?? false

  const handleConnect = async () => {
    try {
      const res = await startMut.mutateAsync()
      // Open in a new tab so we don't blow away the SPA's session.
      window.open(res.authorization_url, "_blank", "noopener,noreferrer")
      toast.message("Conclua o login no OpenAI na nova aba.")
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao iniciar OAuth.")
    }
  }

  const handleRevoke = async () => {
    try {
      await revokeMut.mutateAsync()
      toast.success("Conexão removida.")
      setConfirmingRevoke(false)
    } catch (e) {
      toast.error(extractApiErrorMessage(e) ?? "Falha ao desconectar.")
    }
  }

  return (
    <div className="space-y-6 p-6">
      <SectionHeader
        title="Agente Sysnord — Conexão OpenAI"
        subtitle="Configura a conta OpenAI compartilhada por todos os tenants. Apenas superusuários da plataforma podem conectar ou revogar."
      />

      <Card className="space-y-5 p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm text-zinc-500 dark:text-zinc-400">Estado</div>
            <div className="mt-1">
              <StatusPill connected={isConnected} expired={isExpired} />
            </div>
          </div>
          {status.isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void status.refetch()}
              disabled={status.isFetching}
            >
              <RefreshCw className="mr-1.5 h-4 w-4" /> Atualizar
            </Button>
          )}
        </div>

        {isConnected && (
          <div className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Conta OpenAI</div>
              <div className="font-medium">
                {status.data?.account_email || status.data?.account_subject || "—"}
              </div>
            </div>
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Conectado por</div>
              <div className="font-medium">
                {status.data?.connected_by_username ?? "—"}
              </div>
            </div>
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Conectado em</div>
              <div className="font-medium">{formatDate(status.data?.connected_at)}</div>
            </div>
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Expira em</div>
              <div className="font-medium">{formatDate(status.data?.expires_at)}</div>
            </div>
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Último refresh</div>
              <div className="font-medium">{formatDate(status.data?.last_refreshed_at)}</div>
            </div>
            <div>
              <div className="text-zinc-500 dark:text-zinc-400">Escopos</div>
              <div className="font-mono text-xs">{status.data?.scopes || "—"}</div>
            </div>
          </div>
        )}

        {status.data?.last_error && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800/50 dark:bg-amber-900/20 dark:text-amber-200">
            <div className="flex items-center gap-1.5 font-medium">
              <AlertTriangle className="h-4 w-4" /> Último erro
            </div>
            <div className="mt-1 whitespace-pre-wrap font-mono text-xs">
              {status.data.last_error}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 pt-2">
          {!isConnected || isExpired ? (
            <Button onClick={handleConnect} disabled={startMut.isPending}>
              {startMut.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <PlugZap className="mr-1.5 h-4 w-4" />
              )}
              {isConnected && isExpired ? "Renovar conexão" : "Conectar conta OpenAI"}
              <ExternalLink className="ml-1.5 h-3.5 w-3.5 opacity-60" />
            </Button>
          ) : (
            <Button onClick={handleConnect} variant="outline" disabled={startMut.isPending}>
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Trocar conta
            </Button>
          )}

          {isConnected && (
            confirmingRevoke ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-zinc-700 dark:text-zinc-300">
                  Tem certeza?
                </span>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleRevoke}
                  disabled={revokeMut.isPending}
                >
                  Sim, desconectar
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmingRevoke(false)}
                  disabled={revokeMut.isPending}
                >
                  Cancelar
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                onClick={() => setConfirmingRevoke(true)}
                disabled={revokeMut.isPending}
              >
                Desconectar
              </Button>
            )
          )}
        </div>
      </Card>

      <Card className="space-y-2 p-6 text-sm text-zinc-600 dark:text-zinc-400">
        <div className="font-medium text-zinc-900 dark:text-zinc-100">Como funciona</div>
        <ul className="ml-4 list-disc space-y-1">
          <li>
            Uma única conta OpenAI é compartilhada entre todos os tenants e usuários do
            Sysnord. O agente flutuante usa essa conexão para chamar Chat Completions.
          </li>
          <li>
            O fluxo é OAuth 2.0 + PKCE. O <code>access_token</code> e o
            {" "}<code>refresh_token</code> ficam criptografados em
            disco (<code>AGENT_TOKEN_ENCRYPTION_KEY</code> com Fernet).
          </li>
          <li>
            O backend renova automaticamente o access token via refresh token.
            Se o refresh falhar (token revogado, escopo alterado), uma das chamadas
            do agente retorna 503 e esta página mostra o erro acima — basta clicar em
            "Renovar conexão".
          </li>
          <li>
            Histórico de conversas é privado <em>por usuário e por tenant</em>: trocar
            de tenant na mesma conta carrega outro conjunto de threads.
          </li>
        </ul>
      </Card>
    </div>
  )
}
