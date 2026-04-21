import { useState } from "react"
import {
  Activity, DollarSign, AlertTriangle, Gauge, Users, List, Server,
} from "lucide-react"
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { SectionHeader } from "@/components/ui/section-header"
import { cn } from "@/lib/utils"
import { useAiUsage } from "@/features/reports"
import type {
  AiUsageByEndpoint, AiUsageByProvider, AiUsageByUser, AiUsageDailyPoint,
  AiUsageRecentError,
} from "@/features/reports"
import { KeyStatusCards } from "./KeyStatusCards"

const WINDOW_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "Hoje" },
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
]

const ENDPOINT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Todos endpoints" },
  { value: "generate_template", label: "Gerar modelo" },
  { value: "generate_template.repair", label: "Gerar (repair)" },
  { value: "refine.normalize_labels", label: "Refinar: normalizar" },
  { value: "refine.translate_en", label: "Refinar: traduzir EN" },
  { value: "refine.translate_pt", label: "Refinar: traduzir PT" },
  { value: "refine.suggest_subtotals", label: "Refinar: subtotais" },
  { value: "refine.add_missing_accounts", label: "Refinar: contas" },
  { value: "chat", label: "Chat" },
  { value: "explain", label: "Explain" },
]

export function AiUsagePage() {
  const [days, setDays] = useState(30)
  const [endpoint, setEndpoint] = useState<string>("")
  const { data, isLoading } = useAiUsage({
    days,
    endpoint: endpoint || undefined,
  })

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Uso da IA"
        subtitle="Chamadas, tokens e custo estimado do motor de demonstrativos"
      />

      <KeyStatusCards />

      <div className="card-elevated flex flex-wrap items-center gap-2 p-2 text-[12px]">
        <span className="text-muted-foreground">Janela:</span>
        <div className="inline-flex overflow-hidden rounded-md border border-border bg-background">
          {WINDOW_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setDays(o.value)}
              className={cn(
                "h-7 px-2 text-[11px] transition-colors",
                days === o.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
        <span className="ml-3 text-muted-foreground">Endpoint:</span>
        <select
          value={endpoint}
          onChange={(e) => setEndpoint(e.target.value)}
          className="h-7 rounded-md border border-border bg-background px-2 text-[11px]"
        >
          {ENDPOINT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {isLoading && <span className="ml-auto text-[10px] text-muted-foreground">Atualizando...</span>}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat icon={<Activity className="h-3.5 w-3.5" />} label="Chamadas" value={formatNum(data?.totals.calls ?? 0)} />
        <Stat icon={<Gauge className="h-3.5 w-3.5" />} label="Tokens" value={formatNum(data?.totals.tokens ?? 0)} />
        <Stat icon={<DollarSign className="h-3.5 w-3.5" />} label="Custo (est.)" value={formatUSD(data?.totals.cost_usd ?? 0)} />
        <Stat icon={<AlertTriangle className="h-3.5 w-3.5" />} label="Sucesso" value={`${((data?.totals.success_rate ?? 1) * 100).toFixed(1)}%`}
          color={(data?.totals.success_rate ?? 1) >= 0.95 ? "emerald" : "amber"} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="Tokens por dia">
          <DailyTokens daily={data?.daily ?? []} />
        </Panel>
        <Panel title="Chamadas por endpoint">
          <EndpointBars rows={data?.by_endpoint ?? []} />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title={<span className="inline-flex items-center gap-1"><Users className="h-3 w-3" /> Usuários (top 10 por tokens)</span>}>
          <UserTable rows={(data?.by_user ?? []).slice(0, 10)} />
        </Panel>
        <Panel title={<span className="inline-flex items-center gap-1"><Server className="h-3 w-3" /> Provedor / modelo</span>}>
          <ProviderTable rows={data?.by_provider ?? []} />
        </Panel>
      </div>

      <Panel title={<span className="inline-flex items-center gap-1"><List className="h-3 w-3" /> Erros recentes</span>}>
        <ErrorsTable rows={data?.recent_errors ?? []} />
      </Panel>
    </div>
  )
}

// --- Presentational helpers ------------------------------------------------

function Stat({
  icon, label, value, color,
}: {
  icon: React.ReactNode
  label: string
  value: string
  color?: "emerald" | "amber"
}) {
  const tone = color === "emerald"
    ? "text-emerald-700 dark:text-emerald-400"
    : color === "amber"
      ? "text-amber-700 dark:text-amber-400"
      : "text-foreground"
  return (
    <div className="card-elevated p-3">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
        {icon}<span>{label}</span>
      </div>
      <div className={cn("mt-1 text-[22px] font-semibold tabular-nums", tone)}>{value}</div>
    </div>
  )
}

function Panel({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="card-elevated space-y-2 p-3">
      <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h2>
      {children}
    </div>
  )
}

function DailyTokens({ daily }: { daily: AiUsageDailyPoint[] }) {
  if (!daily.length) return <Empty />
  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={daily}>
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
              <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
          <XAxis dataKey="day" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Area type="monotone" dataKey="tokens" stroke="hsl(var(--primary))" fill="url(#g)" strokeWidth={1.5} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function EndpointBars({ rows }: { rows: AiUsageByEndpoint[] }) {
  if (!rows.length) return <Empty />
  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows.slice(0, 12)} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
          <XAxis type="number" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="endpoint" tick={{ fontSize: 10 }} width={140} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Bar dataKey="calls" fill="hsl(var(--primary))" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function UserTable({ rows }: { rows: AiUsageByUser[] }) {
  if (!rows.length) return <Empty />
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-[11px]">
        <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Usuário</th>
            <th className="h-7 px-2 text-right">Calls</th>
            <th className="h-7 px-2 text-right">Tokens</th>
            <th className="h-7 px-2 text-right">Custo (US$)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50">
              <td className="h-7 px-2">{r.user__username ?? "—"}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatNum(r.calls)}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatNum(r.tokens)}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatUSD(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProviderTable({ rows }: { rows: AiUsageByProvider[] }) {
  if (!rows.length) return <Empty />
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-[11px]">
        <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Provedor</th>
            <th className="h-7 px-2">Modelo</th>
            <th className="h-7 px-2 text-right">Calls</th>
            <th className="h-7 px-2 text-right">Tokens</th>
            <th className="h-7 px-2 text-right">Custo (US$)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50">
              <td className="h-7 px-2 font-mono">{r.provider}</td>
              <td className="h-7 px-2 font-mono text-muted-foreground">{r.model}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatNum(r.calls)}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatNum(r.tokens)}</td>
              <td className="h-7 px-2 text-right tabular-nums">{formatUSD(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ErrorsTable({ rows }: { rows: AiUsageRecentError[] }) {
  if (!rows.length) {
    return <div className="py-6 text-center text-[11px] text-muted-foreground">Sem erros na janela selecionada ✨</div>
  }
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-[11px]">
        <thead className="bg-surface-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="h-7 px-2">Quando</th>
            <th className="h-7 px-2">Usuário</th>
            <th className="h-7 px-2">Endpoint</th>
            <th className="h-7 px-2">Provedor</th>
            <th className="h-7 px-2">Tipo</th>
            <th className="h-7 px-2">Mensagem</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50">
              <td className="h-7 px-2 text-muted-foreground">{formatDateTime(r.created_at)}</td>
              <td className="h-7 px-2">{r.user__username ?? "—"}</td>
              <td className="h-7 px-2 font-mono">{r.endpoint}</td>
              <td className="h-7 px-2 font-mono text-muted-foreground">{r.provider} / {r.model}</td>
              <td className="h-7 px-2 text-red-600">{r.error_type ?? "—"}</td>
              <td className="h-7 max-w-[320px] truncate px-2" title={r.error_message ?? ""}>{r.error_message ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Empty() {
  return <div className="py-6 text-center text-[11px] text-muted-foreground">Sem dados na janela selecionada</div>
}

// --- Formatters -----------------------------------------------------------

function formatNum(n: number): string {
  return new Intl.NumberFormat("pt-BR").format(n)
}
function formatUSD(n: number): string {
  return "$" + new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(n)
}
function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
  } catch { return iso }
}
