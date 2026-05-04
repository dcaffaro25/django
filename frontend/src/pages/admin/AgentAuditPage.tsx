/**
 * Admin page for inspecting the agent's runtime audit trail.
 *
 * Two tabs:
 *  * **Tool calls** — every dispatch the runtime made, including
 *    rejected (rate-limited) and errored ones. Filter by tool name,
 *    status, and conversation.
 *  * **Writes** — every attempted mutation (dry-run, applied, undone,
 *    failed). Includes the undo_token + before/after state so an
 *    operator can replay or reverse a decision.
 *
 * Tenant-scoped via the api.tenant.* helpers. Auto-refreshes every
 * 15s while the page is mounted.
 */
import { useMemo, useState } from "react"
import {
  AlertCircle, CheckCircle2, Clock, Database, FileText, Loader2,
  RotateCcw, Wrench,
} from "lucide-react"

import { Card } from "@/components/ui/card"
import { SectionHeader } from "@/components/ui/section-header"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  useAgentToolCallLog,
  useAgentWriteAudit,
} from "@/features/agent/hooks"
import {
  type AgentToolCallLogRow,
  type AgentWriteAuditRow,
} from "@/features/agent/api"


type Tab = "tool_calls" | "writes"


function fmtRelative(iso: string): string {
  const t = new Date(iso).getTime()
  const delta = Date.now() - t
  if (delta < 60_000) return "agora"
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m atrás`
  if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h atrás`
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short", timeStyle: "short",
  })
}


function ToolCallStatusPill({ status }: { status: AgentToolCallLogRow["status"] }) {
  const map = {
    ok: { tone: "emerald", icon: CheckCircle2, label: "ok" },
    warn: { tone: "amber", icon: AlertCircle, label: "warn" },
    error: { tone: "red", icon: AlertCircle, label: "error" },
    rejected: { tone: "zinc", icon: AlertCircle, label: "rate-limit" },
  }[status] ?? { tone: "zinc", icon: AlertCircle, label: status }
  const Icon = map.icon
  const tones: Record<string, string> = {
    emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    amber:   "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    red:     "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    zinc:    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  }
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
      tones[map.tone],
    )}>
      <Icon className="h-3 w-3" />
      {map.label}
    </span>
  )
}


function WriteStatusPill({ status }: { status: AgentWriteAuditRow["status"] }) {
  const tones: Record<AgentWriteAuditRow["status"], string> = {
    dry_run:  "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    proposed: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    applied:  "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    rejected: "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300",
    failed:   "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    undone:   "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  }
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
      tones[status],
    )}>
      {status}
    </span>
  )
}


function FilterBar(props: {
  toolFilter: string
  statusFilter: string
  conversationFilter: string
  statusOptions: string[]
  onChange: (next: { tool?: string; status?: string; conversation?: string }) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
      <div className="flex items-center gap-1">
        <span className="text-zinc-500">tool</span>
        <input
          value={props.toolFilter}
          onChange={(e) => props.onChange({ tool: e.target.value })}
          placeholder="ex: fetch_cnpj"
          className="w-40 rounded border border-zinc-200 bg-white px-1.5 py-0.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-900"
        />
      </div>
      <div className="flex items-center gap-1">
        <span className="text-zinc-500">status</span>
        <select
          value={props.statusFilter}
          onChange={(e) => props.onChange({ status: e.target.value })}
          className="rounded border border-zinc-200 bg-white px-1.5 py-0.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">todos</option>
          {props.statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-1">
        <span className="text-zinc-500">conv id</span>
        <input
          value={props.conversationFilter}
          onChange={(e) => props.onChange({ conversation: e.target.value })}
          placeholder="número"
          inputMode="numeric"
          className="w-20 rounded border border-zinc-200 bg-white px-1.5 py-0.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-900"
        />
      </div>
    </div>
  )
}


function ToolCallsTab() {
  const [tool, setTool] = useState("")
  const [status, setStatus] = useState("")
  const [conversation, setConversation] = useState("")

  const filters = useMemo(() => {
    const out: { tool?: string; status?: string; conversation?: number; limit?: number } = { limit: 200 }
    if (tool.trim()) out.tool = tool.trim()
    if (status) out.status = status
    if (conversation && /^\d+$/.test(conversation)) out.conversation = Number(conversation)
    return out
  }, [tool, status, conversation])

  const query = useAgentToolCallLog(filters)

  return (
    <Card className="p-0">
      <FilterBar
        toolFilter={tool}
        statusFilter={status}
        conversationFilter={conversation}
        statusOptions={["ok", "warn", "error", "rejected"]}
        onChange={(next) => {
          if (next.tool !== undefined) setTool(next.tool)
          if (next.status !== undefined) setStatus(next.status)
          if (next.conversation !== undefined) setConversation(next.conversation)
        }}
      />
      {query.isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-zinc-400" /></div>
      ) : (query.data?.tool_calls?.length ?? 0) === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-zinc-500">
          Nenhum tool call no período. Tente alargar os filtros.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr className="[&>th]:px-2 [&>th]:py-1.5 [&>th]:text-left [&>th]:font-medium">
                <th>quando</th>
                <th>tool</th>
                <th>domínio</th>
                <th>status</th>
                <th>latência</th>
                <th>iter</th>
                <th>conv</th>
                <th className="min-w-[180px]">args</th>
                <th>erro</th>
              </tr>
            </thead>
            <tbody className="[&>tr]:border-b [&>tr]:border-zinc-100 dark:[&>tr]:border-zinc-800/60">
              {query.data!.tool_calls.map((r) => (
                <tr key={r.id} className="[&>td]:px-2 [&>td]:py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                  <td title={r.created_at}>{fmtRelative(r.created_at)}</td>
                  <td className="font-mono text-[11px]">{r.tool_name}</td>
                  <td className="text-zinc-500">{r.tool_domain || "—"}</td>
                  <td><ToolCallStatusPill status={r.status} /></td>
                  <td className="tabular-nums text-zinc-600">{r.latency_ms != null ? `${r.latency_ms}ms` : "—"}</td>
                  <td className="text-zinc-500">{r.iteration ?? "—"}</td>
                  <td className="text-zinc-500">{r.conversation_id ?? "—"}</td>
                  <td className="truncate font-mono text-[10px] text-zinc-600" title={r.args_summary}>
                    {r.args_summary.length > 80 ? r.args_summary.slice(0, 80) + "…" : r.args_summary}
                  </td>
                  <td className="text-[10px] text-red-700 dark:text-red-400" title={r.error_message}>
                    {r.error_message ? r.error_message.slice(0, 60) + (r.error_message.length > 60 ? "…" : "") : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="border-t border-zinc-200 px-3 py-1.5 text-[11px] text-zinc-500 dark:border-zinc-800">
        {query.data?.count ?? 0} linhas · auto-refresh 15s
      </div>
    </Card>
  )
}


function WriteAuditTab() {
  const [tool, setTool] = useState("")
  const [status, setStatus] = useState("")
  const [conversation, setConversation] = useState("")

  const filters = useMemo(() => {
    const out: { tool?: string; status?: string; conversation?: number; limit?: number } = { limit: 100 }
    if (tool.trim()) out.tool = tool.trim()
    if (status) out.status = status
    if (conversation && /^\d+$/.test(conversation)) out.conversation = Number(conversation)
    return out
  }, [tool, status, conversation])

  const query = useAgentWriteAudit(filters)
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <Card className="p-0">
      <FilterBar
        toolFilter={tool}
        statusFilter={status}
        conversationFilter={conversation}
        statusOptions={["dry_run", "proposed", "applied", "rejected", "failed", "undone"]}
        onChange={(next) => {
          if (next.tool !== undefined) setTool(next.tool)
          if (next.status !== undefined) setStatus(next.status)
          if (next.conversation !== undefined) setConversation(next.conversation)
        }}
      />
      {query.isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-zinc-400" /></div>
      ) : (query.data?.writes?.length ?? 0) === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-zinc-500">
          Nenhuma escrita registrada. Habilite ``AGENT_ALLOW_WRITES`` no
          ambiente para que o agente comece a aplicar mudanças.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr className="[&>th]:px-2 [&>th]:py-1.5 [&>th]:text-left [&>th]:font-medium">
                <th>quando</th>
                <th>tool</th>
                <th>status</th>
                <th>alvo</th>
                <th>linhas</th>
                <th>undo_token</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="[&>tr]:border-b [&>tr]:border-zinc-100 dark:[&>tr]:border-zinc-800/60">
              {query.data!.writes.map((r) => (
                <>
                  <tr key={r.id} className="[&>td]:px-2 [&>td]:py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td title={r.created_at}>{fmtRelative(r.created_at)}</td>
                    <td className="font-mono text-[11px]">{r.tool_name}</td>
                    <td><WriteStatusPill status={r.status} /></td>
                    <td className="text-zinc-600">{r.target_model || "—"}</td>
                    <td className="text-zinc-500">{r.target_ids?.length ?? 0}</td>
                    <td className="font-mono text-[10px] text-zinc-500">
                      {r.undo_token ? r.undo_token.slice(0, 12) + "…" : "—"}
                    </td>
                    <td>
                      <Button
                        size="sm" variant="ghost"
                        onClick={() => setExpanded((cur) => cur === r.id ? null : r.id)}
                      >
                        {expanded === r.id ? "fechar" : "abrir"}
                      </Button>
                    </td>
                  </tr>
                  {expanded === r.id && (
                    <tr className="bg-zinc-50 dark:bg-zinc-900/40">
                      <td colSpan={7} className="px-3 py-2">
                        <div className="grid grid-cols-2 gap-3 text-[11px]">
                          <div>
                            <div className="mb-1 font-semibold text-zinc-600 dark:text-zinc-400">args</div>
                            <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono dark:bg-zinc-900">
                              {r.args_summary || "(empty)"}
                            </pre>
                          </div>
                          <div>
                            <div className="mb-1 font-semibold text-zinc-600 dark:text-zinc-400">target_ids</div>
                            <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono dark:bg-zinc-900">
                              {JSON.stringify(r.target_ids, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="mb-1 font-semibold text-zinc-600 dark:text-zinc-400">before</div>
                            <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono dark:bg-zinc-900">
                              {JSON.stringify(r.before_state, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="mb-1 font-semibold text-zinc-600 dark:text-zinc-400">after</div>
                            <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono dark:bg-zinc-900">
                              {JSON.stringify(r.after_state, null, 2)}
                            </pre>
                          </div>
                          {r.error_message && (
                            <div className="col-span-2">
                              <div className="mb-1 font-semibold text-red-700 dark:text-red-400">erro</div>
                              <pre className="max-h-32 overflow-auto rounded bg-red-50 p-2 font-mono text-red-800 dark:bg-red-900/30 dark:text-red-300">
                                {r.error_type}: {r.error_message}
                              </pre>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="border-t border-zinc-200 px-3 py-1.5 text-[11px] text-zinc-500 dark:border-zinc-800">
        {query.data?.count ?? 0} linhas · auto-refresh 15s
      </div>
    </Card>
  )
}


export function AgentAuditPage() {
  const [tab, setTab] = useState<Tab>("tool_calls")

  return (
    <div className="space-y-4 p-4">
      <SectionHeader
        title="Auditoria do agente"
        description="Histórico de tool calls e escritas do agente para o tenant atual."
      />
      <div className="flex gap-2 border-b border-zinc-200 dark:border-zinc-800">
        <button
          type="button"
          onClick={() => setTab("tool_calls")}
          className={cn(
            "flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-sm transition",
            tab === "tool_calls"
              ? "border-primary text-primary"
              : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
          )}
        >
          <Wrench className="h-3.5 w-3.5" /> Tool calls
        </button>
        <button
          type="button"
          onClick={() => setTab("writes")}
          className={cn(
            "flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-sm transition",
            tab === "writes"
              ? "border-primary text-primary"
              : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
          )}
        >
          <Database className="h-3.5 w-3.5" /> Escritas
        </button>
      </div>
      {tab === "tool_calls" ? <ToolCallsTab /> : <WriteAuditTab />}
    </div>
  )
}
