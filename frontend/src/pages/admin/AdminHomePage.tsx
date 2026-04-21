import { Link } from "react-router-dom"
import { Activity, ShieldCheck, Users } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { useAuth } from "@/providers/AuthProvider"

/**
 * Landing page for the platform-admin area. Intentionally bare right now —
 * PR 1 only establishes the route + the guard. The cards below are
 * placeholders pointing at what PR 2 (user management) and PR 3-5
 * (activity tracking + dashboards) will add.
 */
export function AdminHomePage() {
  const { user } = useAuth()
  return (
    <div className="space-y-4">
      <SectionHeader
        title="Administração da plataforma"
        subtitle={`Olá, ${user?.username ?? ""} — área visível apenas a superusuários.`}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
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
          subtitle="Tempo por área, gargalos, sinais de fricção nos fluxos."
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
