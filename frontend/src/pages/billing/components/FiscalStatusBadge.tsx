import { cn } from "@/lib/utils"
import type { InvoiceFiscalStatus } from "@/features/billing"
import {
  AlertTriangle,
  Ban,
  Bell,
  CheckCircle2,
  CornerDownLeft,
  HelpCircle,
  RotateCcw,
} from "lucide-react"

const STYLE: Record<
  InvoiceFiscalStatus,
  { label: string; cls: string; icon: typeof CheckCircle2 }
> = {
  pending_nf: {
    label: "Pendente de NF",
    cls: "bg-muted text-muted-foreground border-transparent",
    icon: HelpCircle,
  },
  invoiced: {
    label: "Faturada",
    cls: "bg-info/10 text-info border-info/20",
    icon: CheckCircle2,
  },
  partially_returned: {
    label: "Devolvida (parcial)",
    cls: "bg-warning/10 text-warning border-warning/30",
    icon: CornerDownLeft,
  },
  fully_returned: {
    label: "Devolvida",
    cls: "bg-warning/10 text-warning border-warning/30",
    icon: RotateCcw,
  },
  fiscally_cancelled: {
    label: "NF cancelada",
    cls: "bg-danger/10 text-danger border-danger/30",
    icon: Ban,
  },
  mixed: {
    label: "Misto",
    cls: "bg-warning/10 text-warning border-warning/30",
    icon: AlertTriangle,
  },
}

export function FiscalStatusBadge({
  status,
  pendingCorrections,
  className,
}: {
  status: InvoiceFiscalStatus
  pendingCorrections?: boolean
  className?: string
}) {
  const conf = STYLE[status] ?? STYLE.pending_nf
  const Icon = conf.icon
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
          conf.cls,
        )}
        title={conf.label}
      >
        <Icon className="h-3 w-3" />
        <span>{conf.label}</span>
      </span>
      {pendingCorrections ? (
        <span
          className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-warning/15 text-warning"
          title="CCe pendente — esta fatura tem uma Carta de Correção registrada na NF vinculada"
          aria-label="CCe pendente"
        >
          <Bell className="h-3 w-3" />
        </span>
      ) : null}
    </span>
  )
}
