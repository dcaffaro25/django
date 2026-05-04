/**
 * Page context store.
 *
 * Pages register a snapshot of "what the user is currently looking at"
 * so the agent widget can include it in chat requests when the user
 * opts in (via the per-conversation ``include_page_context`` toggle).
 *
 * Pattern (recommended):
 *
 *     useEffect(() => {
 *       setPageContext({
 *         route: "/billing/invoices",
 *         title: "Faturas",
 *         summary: "Lista de faturas com filtro status=issued, partner=All.",
 *         data: { filters: { status: "issued" }, page: 1, total: 142 },
 *       })
 *       return () => clearPageContext()
 *     }, [filters, page, total])
 *
 * What goes in ``data``:
 *  - filters / search terms / pagination state
 *  - selected row IDs (not full rows — IDs are enough; the agent has tools)
 *  - small summaries that would be expensive for the agent to derive
 *
 * What does NOT belong:
 *  - full datasets (the agent has read tools — let it fetch)
 *  - secrets, tokens, API keys
 *
 * The blob is sent verbatim; keep it small (the runtime truncates at
 * ~1.5 kB anyway). Privacy: only sent when the active conversation has
 * ``include_page_context=true`` AND the user has the toggle on.
 */
import { create } from "zustand"

export interface PageContext {
  /** Pathname / route, for the agent's situational awareness. */
  route: string
  /** Short human title ("Faturas", "Conciliação Bancária"). */
  title: string
  /** 1-2 sentence summary of what's on screen. */
  summary?: string
  /** Structured data the agent might need to reason. JSON-serialisable. */
  data?: Record<string, unknown>
}

interface PageContextStore {
  context: PageContext | null
  setContext: (ctx: PageContext) => void
  clearContext: () => void
}

export const usePageContextStore = create<PageContextStore>((set) => ({
  context: null,
  setContext: (ctx) => set({ context: ctx }),
  clearContext: () => set({ context: null }),
}))


/** Convenience hook for pages: register + auto-clean on unmount. */
import { useEffect } from "react"

export function usePageContext(ctx: PageContext | null) {
  const setContext = usePageContextStore((s) => s.setContext)
  const clearContext = usePageContextStore((s) => s.clearContext)

  useEffect(() => {
    if (ctx) setContext(ctx)
    return () => clearContext()
    // The caller is responsible for memoising ``ctx`` if they want fewer
    // re-registrations; we re-set on every render that gets a new object.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(ctx)])
}
