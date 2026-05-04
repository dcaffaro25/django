/**
 * Admin page for the OpenAI ChatGPT-subscription connection.
 *
 * The connection itself is NOT initiated from the browser — OpenAI's
 * Codex OAuth ``client_id`` is locked to ``http://localhost:1455/auth/callback``
 * (a loopback address), so a server-side browser-redirect flow is
 * impossible. Instead:
 *
 * 1. A platform superuser runs ``python manage.py openai_oauth_login``
 *    on their own laptop.
 * 2. That command opens a browser to ``auth.openai.com``, captures the
 *    OAuth callback locally, exchanges the code for tokens, and POSTs
 *    them to ``/api/agent/connection/import-tokens/``.
 * 3. Sysnord stores the tokens (encrypted) in the singleton
 *    ``OpenAITokenStore`` and the agent is live for all tenants.
 *
 * This page renders the current connection status and the exact CLI
 * command the operator needs to run, with their DRF token + the
 * deployment URL pre-filled.
 */
import { useMemo, useState } from "react"
import { toast } from "sonner"
import {
  AlertTriangle, CheckCircle2, ClipboardCopy, ExternalLink, Loader2, Power, RefreshCw, Terminal,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { SectionHeader } from "@/components/ui/section-header"
import { extractApiErrorMessage, getStoredToken } from "@/lib/api-client"
import {
  useAgentConnectionStatus,
  useRevokeAgentConnection,
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


/** Compose the CLI command the operator needs to run, with their token
 *  and the current deployment's backend URL pre-filled (best-effort —
 *  uses ``window.location.origin``; for cross-origin SPAs this needs a
 *  manual swap). The token field is masked but copyable. */
function CliCommandBlock() {
  const [revealToken, setRevealToken] = useState(false)
  const token = getStoredToken() || "<your-superuser-token>"
  const backendUrl = useMemo(() => {
    // VITE_API_BASE_URL is the canonical source; window.location.origin
    // is a sensible fallback when SPA + API are co-hosted.
    const fromEnv = (import.meta.env.VITE_API_BASE_URL as string | undefined)
    return (fromEnv && fromEnv.trim()) || window.location.origin
  }, [])

  const displayToken = revealToken ? token : "•".repeat(Math.min(token.length, 24))
  const cmd = `python manage.py openai_oauth_login \\
    --backend ${backendUrl} \\
    --token ${displayToken}`

  const handleCopy = async () => {
    const real = `python manage.py openai_oauth_login --backend ${backendUrl} --token ${token}`
    try {
      await navigator.clipboard.writeText(real)
      toast.success("Comando copiado.")
    } catch {
      toast.error("Não foi possível copiar — copie manualmente abaixo.")
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Terminal className="h-4 w-4 text-primary" /> Rode no terminal da sua máquina
      </div>
      <pre className="overflow-x-auto whitespace-pre rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs leading-relaxed dark:border-zinc-800 dark:bg-zinc-900">
{cmd}
      </pre>
      <div className="flex items-center gap-2 text-xs">
        <Button variant="outline" size="sm" onClick={handleCopy}>
          <ClipboardCopy className="mr-1.5 h-3.5 w-3.5" /> Copiar com token real
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setRevealToken((v) => !v)}>
          {revealToken ? "Ocultar token" : "Mostrar token"}
        </Button>
        <span className="ml-2 text-zinc-500">
          O token é o que você usa para autenticar no Sysnord.
        </span>
      </div>
    </div>
  )
}


export function AgentConnectionPage() {
  const status = useAgentConnectionStatus()
  const revokeMut = useRevokeAgentConnection()
  const [confirmingRevoke, setConfirmingRevoke] = useState(false)

  const isConnected = status.data?.is_connected ?? false
  const isExpired = status.data?.is_expired ?? false

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
        subtitle="Configura a conta ChatGPT compartilhada por todos os tenants. Apenas superusuários da plataforma podem conectar ou revogar."
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
              <div className="text-zinc-500 dark:text-zinc-400">Conta ChatGPT</div>
              <div className="font-medium">
                {status.data?.account_email || status.data?.chatgpt_account_id || "—"}
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
              <div className="text-zinc-500 dark:text-zinc-400">chatgpt_account_id</div>
              <div className="font-mono text-xs">
                {status.data?.chatgpt_account_id || "—"}
              </div>
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

        {isConnected && (
          <div className="flex flex-wrap items-center gap-3 pt-2">
            {confirmingRevoke ? (
              <div className="flex items-center gap-2">
                <span className="text-sm">Tem certeza?</span>
                <Button
                  variant="destructive" size="sm"
                  onClick={handleRevoke} disabled={revokeMut.isPending}
                >Sim, desconectar</Button>
                <Button
                  variant="ghost" size="sm"
                  onClick={() => setConfirmingRevoke(false)}
                  disabled={revokeMut.isPending}
                >Cancelar</Button>
              </div>
            ) : (
              <Button
                variant="outline"
                onClick={() => setConfirmingRevoke(true)}
                disabled={revokeMut.isPending}
              >Desconectar</Button>
            )}
          </div>
        )}
      </Card>

      <Card className="space-y-4 p-6">
        <div className="text-sm font-medium">
          {isConnected
            ? (isExpired ? "Reconectar (token expirado)" : "Trocar conta")
            : "Conectar agora"}
        </div>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          O fluxo é OAuth 2.1 + PKCE contra <code>auth.openai.com</code>. Como o
          OpenAI restringe o redirect a <code>http://localhost:1455</code>, a
          autenticação roda no <strong>seu computador</strong>. O comando abaixo
          abre o navegador, captura o callback local e envia os tokens para o
          Sysnord automaticamente.
        </p>
        <CliCommandBlock />
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <ExternalLink className="h-3.5 w-3.5" />
          O <code>client_id</code> usado é o público da OpenAI Codex CLI
          (<code>app_EMoamEEZ73f0CkXaXp7hrann</code>) — mesmo que OpenClaw e
          Claude Code usam.
        </div>
      </Card>

      <Card className="space-y-2 p-6 text-sm text-zinc-600 dark:text-zinc-400">
        <div className="font-medium text-zinc-900 dark:text-zinc-100">Como funciona</div>
        <ul className="ml-4 list-disc space-y-1">
          <li>
            Uma única conta ChatGPT é compartilhada entre todos os tenants e
            usuários do Sysnord. O agente flutuante usa essa conexão para chamar
            a Codex Responses API (<code>chatgpt.com/backend-api/codex</code>).
          </li>
          <li>
            <code>access_token</code> e <code>refresh_token</code> ficam
            criptografados em disco com Fernet
            (<code>AGENT_TOKEN_ENCRYPTION_KEY</code>). O
            {" "}<code>chatgpt_account_id</code> também é persistido — ele vai
            como header em toda chamada da API.
          </li>
          <li>
            O backend renova automaticamente o access token via refresh token.
            Se o refresh falhar (token revogado, escopo alterado), uma das
            chamadas do agente retorna 503 e esta página mostra o erro acima —
            basta rodar o comando novamente.
          </li>
          <li>
            Histórico de conversas é privado <em>por usuário e por tenant</em>:
            trocar de tenant na mesma conta carrega outro conjunto de threads.
          </li>
        </ul>
      </Card>
    </div>
  )
}
