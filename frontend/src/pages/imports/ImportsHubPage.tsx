import { useCallback } from "react"
import { useSearchParams } from "react-router-dom"
import { FileSpreadsheet, FileText, FileCode, FileCog } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"
import { ImportQueuePanel } from "@/components/imports/ImportQueuePanel"
import { SessionDetailView } from "@/components/imports/SessionDetailView"
import { EtlImportPage } from "./EtlImportPage"
import { OfxImportPage } from "./OfxImportPage"
import { NfImportPage } from "./NfImportPage"
import { ImportTemplatesPage } from "./ImportTemplatesPage"
import { cn } from "@/lib/utils"

/**
 * One-stop landing page for file imports. Hosts the four upload flows
 * (ETL / OFX / NF-e / bulk workbook) as tabs. Below the tab content,
 * the v2 queue panel shows recent sessions live (Phase 6.z-b);
 * clicking a row expands it inline into a read-only audit view
 * (Phase 6.z-c). Substitution rules live on their own page
 * (/imports/substitutions) because they're a long-lived CRUD
 * surface rather than a per-upload concern.
 *
 * Deep-linking: ``?tab=<tab>&session=<id>`` — the session id selects
 * and expands a row in the queue. Operators can share URLs that point
 * directly at a specific import's audit view. Closing the detail
 * clears the param so the URL stays clean.
 */

type Tab = "etl" | "ofx" | "nf" | "templates"

const TABS: Array<{
  id: Tab
  label: string
  hint: string
  icon: typeof FileSpreadsheet
}> = [
  { id: "etl", label: "ETL (Excel)", hint: "Importação genérica via planilha", icon: FileSpreadsheet },
  { id: "ofx", label: "OFX", hint: "Extratos bancários", icon: FileText },
  { id: "nf", label: "NF-e", hint: "XMLs de nota fiscal", icon: FileCode },
  { id: "templates", label: "Templates", hint: "Importação multi-modelo via planilha mestre", icon: FileCog },
]

const VALID_TABS: Tab[] = ["etl", "ofx", "nf", "templates"]

export function ImportsHubPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const urlTab = searchParams.get("tab") as Tab | null
  const tab: Tab = urlTab && VALID_TABS.includes(urlTab) ? urlTab : "etl"
  const setTab = (t: Tab) => {
    const next = new URLSearchParams(searchParams)
    next.set("tab", t)
    setSearchParams(next, { replace: true })
  }

  // Deep-linked session (Phase 6.z-c). Parses ``?session=<id>`` into a
  // number; ignores garbage so a malformed link doesn't crash the
  // page. Queue row clicks update the param so operators can share
  // the URL mid-triage.
  const urlSessionRaw = searchParams.get("session")
  const selectedSessionId =
    urlSessionRaw && /^\d+$/.test(urlSessionRaw)
      ? Number(urlSessionRaw)
      : null

  const setSelectedSessionId = useCallback(
    (id: number | null) => {
      const next = new URLSearchParams(searchParams)
      if (id != null) {
        next.set("session", String(id))
      } else {
        next.delete("session")
      }
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  // Queue currently covers ETL + Templates (v2 only). OFX / NF-e still
  // use their own v1 endpoints and don't produce ImportSession rows,
  // so we hide the queue on those tabs instead of showing an empty one.
  const showQueue = tab === "etl" || tab === "templates"

  return (
    <div className="flex flex-col gap-4">
      <SectionHeader
        title="Importações"
        subtitle="Envie arquivos; o backend faz o parse, validação e commit"
      />

      {/* Two-column layout when the queue is visible (ETL + Templates
          tabs): upload flow on the left, live queue on the right as a
          vertical card. OFX / NF-e fall back to full-width because
          they don't use ImportSession yet. */}
      <div
        className={cn(
          "flex gap-4",
          showQueue ? "flex-col lg:flex-row lg:items-start" : "flex-col",
        )}
      >
        <div
          className={cn(
            "flex flex-1 flex-col gap-4",
            showQueue && "lg:min-w-0",
          )}
        >
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

          {/* Selected session detail — stays below the upload flow in
              the left column. Rendered here (not in the right card)
              because it can grow large and the right column is
              narrow. The queue highlights the selected row so the
              relationship stays obvious. */}
          {showQueue && selectedSessionId != null && (
            <SessionDetailView
              sessionId={selectedSessionId}
              onClose={() => setSelectedSessionId(null)}
            />
          )}
        </div>

        {showQueue && (
          <aside
            className={cn(
              "w-full lg:w-80 lg:shrink-0",
              // Stretch from the tabs down to the bottom of the viewport
              // on wide screens, with its own scroll so the upload
              // column doesn't push it off-screen.
              "lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]",
            )}
          >
            <div className="lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              <ImportQueuePanel
                selectedSessionId={selectedSessionId}
                onSelectSession={setSelectedSessionId}
                pageSize={25}
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
