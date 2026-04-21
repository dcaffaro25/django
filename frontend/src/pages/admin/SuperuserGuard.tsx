import { type ReactNode } from "react"
import { Link } from "react-router-dom"
import { ShieldAlert } from "lucide-react"
import { useAuth } from "@/providers/AuthProvider"

/**
 * Wraps every page under ``/admin/*``. Non-superusers get a clear
 * "forbidden" screen instead of a silent redirect — a quiet redirect
 * to ``/`` would make the route look broken to someone who
 * intentionally pasted an admin link.
 *
 * The backend enforces the same rule independently via
 * :class:`multitenancy.permissions.IsSuperUser`; this frontend check
 * just keeps non-admins from seeing a half-rendered admin page
 * flicker before the API 403 lands.
 */
export function SuperuserGuard({ children }: { children: ReactNode }) {
  const { isSuperuser, isAuthenticated, user } = useAuth()

  // If we haven't loaded the user yet, render nothing — avoids a
  // flash of the "forbidden" screen before we know the real state.
  if (!isAuthenticated || user == null) return null

  if (!isSuperuser) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-16 text-center">
        <div className="grid h-10 w-10 place-items-center rounded-full bg-warning/10 text-warning">
          <ShieldAlert className="h-5 w-5" />
        </div>
        <h1 className="text-[15px] font-semibold">Área restrita</h1>
        <p className="text-[12px] text-muted-foreground">
          Esta área é visível apenas para administradores da plataforma.
          Se você precisa de acesso, peça para um superusuário habilitar
          sua conta.
        </p>
        <Link to="/" className="text-[12px] text-primary hover:underline">
          Voltar para o início
        </Link>
      </div>
    )
  }

  return <>{children}</>
}
