import { useState } from "react"
import { FileSpreadsheet, FileText, FileCode } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { EtlImportPage } from "./EtlImportPage"
import { OfxImportPage } from "./OfxImportPage"
import { NfImportPage } from "./NfImportPage"
import { cn } from "@/lib/utils"

/**
 * One-stop landing page for file imports. Hosts the three distinct import
 * flows as tabs so operators don't need to remember three separate URLs.
 * Templates and Substitutions live on their own pages since their
 * lifecycle is different (CRUD, not transient upload → run → forget).
 */

type Tab = "etl" | "ofx" | "nf"

const TABS: Array<{
  id: Tab
  label: string
  hint: string
  icon: typeof FileSpreadsheet
}> = [
  { id: "etl", label: "ETL (Excel)", hint: "Importação genérica via planilha", icon: FileSpreadsheet },
  { id: "ofx", label: "OFX", hint: "Extratos bancários", icon: FileText },
  { id: "nf", label: "NF-e", hint: "XMLs de nota fiscal", icon: FileCode },
]

export function ImportsHubPage() {
  const [tab, setTab] = useState<Tab>("etl")

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
    </div>
  )
}
