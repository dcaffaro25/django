import { useState } from "react"
import { toast } from "sonner"
import {
  Type, Languages, Sigma, ListPlus, Loader2, Wand2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type {
  AiRefineAction,
  AiRefineSummary,
  TemplateDocument,
} from "@/features/reports"
import { useAiRefine } from "@/features/reports"
import { AiDiffPreview } from "./AiDiffPreview"

interface Action {
  key: AiRefineAction
  label: string
  icon: React.ReactNode
  hint: string
}

const ACTIONS: Action[] = [
  {
    key: "normalize_labels",
    label: "Normalizar rótulos",
    icon: <Type className="h-3 w-3" />,
    hint: "Rótulos consistentes e concisos",
  },
  {
    key: "suggest_subtotals",
    label: "Sugerir subtotais",
    icon: <Sigma className="h-3 w-3" />,
    hint: "Insere subtotais em pontos lógicos",
  },
  {
    key: "add_missing_accounts",
    label: "Preencher contas faltantes",
    icon: <ListPlus className="h-3 w-3" />,
    hint: "Adiciona contas do plano ainda não referenciadas",
  },
  {
    key: "translate_en",
    label: "Traduzir (EN)",
    icon: <Languages className="h-3 w-3" />,
    hint: "Traduz rótulos para inglês",
  },
  {
    key: "translate_pt",
    label: "Traduzir (PT)",
    icon: <Languages className="h-3 w-3" />,
    hint: "Traduz rótulos para português",
  },
]

/**
 * Inline AI refine toolbar. Each button runs a one-shot action on the
 * current document and opens a diff preview so the user accepts or rejects
 * wholesale before anything mutates the editor state.
 */
export function AiActionsToolbar({
  doc,
  onApply,
  disabled,
}: {
  doc: TemplateDocument
  onApply: (next: TemplateDocument) => void
  disabled?: boolean
}) {
  const refine = useAiRefine()
  const [pending, setPending] = useState<AiRefineAction | null>(null)
  const [proposal, setProposal] = useState<{
    newDoc: TemplateDocument
    summary: AiRefineSummary
  } | null>(null)

  const runAction = async (action: AiRefineAction) => {
    if (doc.blocks.length === 0) {
      toast.error("Adicione ou gere blocos antes de refinar")
      return
    }
    setPending(action)
    try {
      const res = await refine.mutateAsync({ action, document: doc })
      setProposal({ newDoc: res.document, summary: res.summary })
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { error?: string } } })?.response?.data
      const msg = resp?.error ?? (err instanceof Error ? err.message : "Falha na IA")
      toast.error(msg)
    } finally {
      setPending(null)
    }
  }

  return (
    <>
      <div className="card-elevated flex flex-wrap items-center gap-1.5 p-2">
        <div className="flex items-center gap-1 pr-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <Wand2 className="h-3 w-3" /> Refinar com IA
        </div>
        {ACTIONS.map((a) => (
          <button
            key={a.key}
            title={a.hint}
            onClick={() => runAction(a.key)}
            disabled={disabled || pending !== null}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 text-[11px] font-medium hover:bg-accent disabled:opacity-50",
              pending === a.key && "bg-accent",
            )}
          >
            {pending === a.key ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              a.icon
            )}
            <span>{a.label}</span>
          </button>
        ))}
      </div>

      <AiDiffPreview
        open={proposal !== null}
        oldDoc={doc}
        newDoc={proposal?.newDoc ?? null}
        summary={proposal?.summary ?? null}
        onAccept={() => {
          if (proposal) {
            onApply(proposal.newDoc)
            toast.success("Alterações aplicadas")
          }
          setProposal(null)
        }}
        onReject={() => setProposal(null)}
      />
    </>
  )
}
