import { useSearchParams } from "react-router-dom"
import { FileSpreadsheet, FileText, FileCode, FileCog, Replace } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { EtlImportPage } from "./EtlImportPage"
import { OfxImportPage } from "./OfxImportPage"
import { NfImportPage } from "./NfImportPage"
import { ImportTemplatesPage } from "./ImportTemplatesPage"
import { SubstitutionRulesPage } from "./SubstitutionRulesPage"
import { cn } from "@/lib/utils"

/**
 * One-stop landing page for file imports. Hosts the upload flows (ETL / OFX /
 * NF-e) side-by-side with the CRUD pages (templates + substitution rules) so
 * operators can manage mapping rules without changing pages mid-task.
 */

type Tab = "etl" | "ofx" | "nf" | "templates" | "substitutions"

const TABS: Array<{
  id: Tab
  label: string
  hint: string
  icon: typeof FileSpreadsheet
}> = [
  { id: "etl", label: "ETL (Excel)", hint: "Importação genérica via planilha", icon: FileSpreadsheet },
  { id: "ofx", label: "OFX", hint: "Extratos bancários", icon: FileText },
  { id: "nf", label: "NF-e", hint: "XMLs de nota fiscal", icon: FileCode },
  { id: "templates", label: "Templates", hint: "Regras de transformação reutilizáveis", icon: FileCog },
  { id: "substitutions", label: "Substituições", hint: "Regras de-para aplicadas nos imports", icon: Replace },
]

const VALID_TABS: Tab[] = ["etl", "ofx", "nf", "templates", "substitutions"]

export function ImportsHubPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const urlTab = searchParams.get("tab") as Tab | null
  const tab: Tab = urlTab && VALID_TABS.includes(urlTab) ? urlTab : "etl"
  const setTab = (t: Tab) => {
    const next = new URLSearchParams(searchParams)
    next.set("tab", t)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Importações"
        subtitle="Envie arquivos; o backend faz o parse, validação e commit"
      />

      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-2 p-1">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              title={t.hint}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-sm px-3 py-1.5 text-[12px] font-medium transition-colors",
                active
                  ? "bg-background text-foreground shadow-soft"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          )
        })}
      </div>

      {tab === "etl" && <EtlImportPage />}
      {tab === "ofx" && <OfxImportPage />}
      {tab === "nf" && <NfImportPage />}
      {tab === "templates" && <ImportTemplatesPage />}
      {tab === "substitutions" && <SubstitutionRulesPage />}
    </div>
  )
}
