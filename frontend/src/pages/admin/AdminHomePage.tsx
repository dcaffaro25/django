import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  Activity, AlertTriangle, Bug, GitBranch, Loader2, Mail, Scale, Server, ShieldCheck, Users,
} from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useAuth } from "@/providers/AuthProvider"
import { adminApi, type LedgerIntegrityResponse } from "@/features/admin/api"
import { cn } from "@/lib/utils"

/**
 * Landing page for the platform-admin area. Intentionally bare right now —
 * PR 1 only establishes the route + the guard. The cards below are
 * placeholders pointing at what PR 2 (user management) and PR 3-5
 * (activity tracking + dashboards) will add.
 */
export function AdminHomePage() {
  const { user } = useAuth()
  const [digestLoading, setDigestLoading] = useState<null | "dry" | "send">(null)
  const [integrity, setIntegrity] = useState<LedgerIntegrityResponse | null>(null)

  // Small fire-and-forget fetch on mount — the KPI banner only
  // renders when the count > 0, so the common "nothing broken"
  // case stays visually quiet. Failures are silent; this is a
  // dashboard card, not a critical-path load.
  useEffect(() => {
    let cancelled = false
    void adminApi.ledgerIntegrity()
      .then((res) => { if (!cancelled) setIntegrity(res) })
      .catch(() => { /* silent */ })
    return () => { cancelled = true }
  }, [])

  const runDigest = async (dry: boolean) => {
    setDigestLoading(dry ? "dry" : "send")
    try {
      const res = await adminApi.runActivityDigest({ days: 7, dry_run: dry })
      if (res.sent) {
        toast.success(`Digest enviado para ${res.recipient}`)
      } else if (dry) {
        toast.success(
          `Prévia gerada (${(res.xlsx_bytes ?? 0).toLocaleString("pt-BR")} bytes) — destinatário: ${res.recipient ?? "—"}`,
          { duration: 6000 },
        )
      } else {
        toast.warning(`Não enviado: ${res.reason ?? "sem destinatário"}`)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao rodar digest")
    } finally {
      setDigestLoading(null)
    }
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Administração da plataforma"
        subtitle={`Olá, ${user?.username ?? ""} — área visível apenas a superusuários.`}
        actions={
          <>
            <button
              onClick={() => void runDigest(true)}
              disabled={digestLoading != null}
              title="Gera o XLSX com os números desta semana sem enviar e-mail."
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-60"
            >
              {digestLoading === "dry" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
              Prévia digest
            </button>
            <button
              onClick={() => void runDigest(false)}
              disabled={digestLoading != null}
              title="Envia o digest semanal agora para o destinatário configurado."
              className="inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {digestLoading === "send" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
              Enviar digest agora
            </button>
          </>
        }
      />
      {/* Integrity banner — only renders when the ledger actually has
          broken transactions, so a healthy platform stays quiet. */}
      {integrity && integrity.total > 0 && (
        <div className={cn(
          "card-elevated rounded-md border border-warning/40 bg-warning/5 p-3",
        )}>
          <div className="flex items-start gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-warning/15 text-warning">
              <Scale className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2 text-[13px] font-semibold">
                <span>Integridade contábil</span>
                <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning">
                  {integrity.total} descompensada{integrity.total === 1 ? "" : "s"}
                </span>
              </div>
              <p className="mt-0.5 text-[12px] text-muted-foreground">
                Transações com Σdébito ≠ Σcrédito (legado do fluxo anterior do
                PR 8). Soma do desequilíbrio: <span className="tabular-nums font-mono">{integrity.imbalance_sum}</span>.
                Rode <code className="rounded bg-muted px-1 py-0.5 text-[11px]">python manage.py reconcile_missing_cash_legs --dry-run</code> e,
                quando estiver satisfeito, <code className="rounded bg-muted px-1 py-0.5 text-[11px]">--apply</code>.
              </p>
              {integrity.by_company.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                  {integrity.by_company.slice(0, 6).map((r) => (
                    <span
                      key={r.company_id}
                      className="rounded-md border border-border bg-surface-3 px-2 py-0.5"
                      title={`Imbalance: ${r.imbalance_sum}`}
                    >
                      {r.company_name || `Company #${r.company_id}`}: {r.count}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <AdminCard
          to="/admin/users"
          icon={<Users className="h-4 w-4" />}
          title="Usuários"
          subtitle="Criar, editar, bloquear e associar a empresas."
        />
        <AdminCard
          to="/admin/activity"
          icon={<Activity className="h-4 w-4" />}
          title="Atividade"
          subtitle="Tempo por usuário × área nos últimos dias."
        />
        <AdminCard
          to="/admin/activity/funnels"
          icon={<GitBranch className="h-4 w-4" />}
          title="Funis de workflow"
          subtitle="Passos, quedas e tempos entre passos nos fluxos principais."
        />
        <AdminCard
          to="/admin/activity/friction"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="Sinais de fricção"
          subtitle="Ciclos A→B→A, ações lentas, erros repetidos, tempo sem ação."
        />
        <AdminCard
          to="/admin/activity/errors"
          icon={<Bug className="h-4 w-4" />}
          title="Erros da aplicação"
          subtitle="Grupos de erro (frontend + backend), stack, usuários afetados, breadcrumbs."
        />
        <AdminCard
          to="/admin/runtime"
          icon={<Server className="h-4 w-4" />}
          title="Runtime config"
          subtitle="O que os serviços web / worker / beat carregaram ao subir. Atualiza ao vivo."
        />
        <AdminCard
          to="/admin/audit"
          icon={<ShieldCheck className="h-4 w-4" />}
          title="Auditoria"
          subtitle="Eventos de negócio, logins, ações sensíveis."
          status="Em breve"
        />
      </div>
    </div>
  )
}

function AdminCard({
  to, icon, title, subtitle, status,
}: {
  to: string
  icon: React.ReactNode
  title: string
  subtitle: string
  status?: string
}) {
  return (
    <Link
      to={to}
      className="card-elevated flex flex-col gap-2 rounded-md border border-border p-3 transition-[box-shadow] hover:shadow-lg"
    >
      <div className="flex items-center gap-2 text-[13px] font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-primary/10 text-primary">
          {icon}
        </span>
        {title}
        {status && (
          <span className="ml-auto rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {status}
          </span>
        )}
      </div>
      <p className="text-[12px] text-muted-foreground">{subtitle}</p>
    </Link>
  )
}
