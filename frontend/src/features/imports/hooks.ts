import { useCallback, useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import {
  bulkImport,
  etlExecute,
  etlPreview,
  importsV2,
  nfeImport,
  ofxImport,
  ofxScan,
  substitutionRulesApi,
  type EtlExecuteParams,
  type ImportsV2ListParams,
} from "./api"
import type {
  ImportSession,
  ImportSessionStatus,
  ImportSessionSummary,
  Paginated,
  SubstitutionRule,
} from "./types"

// Re-export the list-params type so pages can import it from
// ``@/features/imports`` without reaching into ``./api``.
export type { ImportsV2ListParams } from "./api"

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

const qk = {
  substRules: (s: string) => ["imports", s, "substitution-rules"] as const,
}

export function useEtlExecute() {
  return useMutation({ mutationFn: (p: EtlExecuteParams) => etlExecute(p) })
}

/** Dry-run against /etl/preview — identical payload, backend rolls back. */
export function useEtlPreview() {
  return useMutation({ mutationFn: (p: EtlExecuteParams) => etlPreview(p) })
}

export function useOfxImport() {
  return useMutation({
    mutationFn: (args: { files: File[]; policy?: "records" | "files" }) =>
      ofxImport(args.files, args.policy),
  })
}

/** Scan-only against /import_ofx — reports duplicates without writing to DB. */
export function useOfxScan() {
  return useMutation({ mutationFn: (files: File[]) => ofxScan(files) })
}

export function useNfeImport() {
  return useMutation({
    mutationFn: (args: { files: File[]; dryRun?: boolean }) =>
      nfeImport(args.files, { dryRun: args.dryRun }),
  })
}

/**
 * Upload an Excel workbook to the master bulk-import endpoint. Pass
 * ``commit=false`` for a preview (backend wraps everything in a transaction
 * and rolls back) or ``commit=true`` to actually apply the changes.
 */
export function useBulkImport() {
  return useMutation({
    mutationFn: (args: { file: File; commit?: boolean }) =>
      bulkImport(args.file, { commit: args.commit }),
  })
}

export function useSubstitutionRules() {
  const sub = useSub()
  return useQuery({
    queryKey: qk.substRules(sub),
    queryFn: substitutionRulesApi.list,
    enabled: !!sub,
  })
}

export function useSaveSubstitutionRule() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Partial<SubstitutionRule> }) =>
      id ? substitutionRulesApi.update(id, body) : substitutionRulesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.substRules(sub) }),
  })
}

export function useDeleteSubstitutionRule() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => substitutionRulesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.substRules(sub) }),
  })
}

// ---- v2 queue + badge (Phase 6.z-b) ------------------------------------

const qkQueue = {
  runningCount: (s: string) => ["imports", s, "v2", "running-count"] as const,
  sessionsList: (s: string, params: ImportsV2ListParams) =>
    ["imports", s, "v2", "sessions-list", params] as const,
}

/**
 * Poll the ``running-count`` aggregate for the sidebar badge.
 *
 * Mounted globally by the sidebar — one timer for the whole app, so
 * we stay kind to the server. Polls every 10s by default; React
 * Query pauses the interval when the tab is backgrounded (``refetchIntervalInBackground: false``).
 *
 * The count covers all non-terminal sessions: ``analyzing`` +
 * ``committing`` + ``awaiting_resolve``. Separate buckets let the
 * sidebar switch dot colour (red when any row wants resolution,
 * amber when only background work is pending).
 */
export function useRunningImportCount(options?: { intervalMs?: number }) {
  const sub = useSub()
  const intervalMs = options?.intervalMs ?? 10_000
  return useQuery({
    queryKey: qkQueue.runningCount(sub),
    // Either namespace returns the same aggregate; template is the
    // arbitrary canonical choice.
    queryFn: () => importsV2.template.runningCount(),
    enabled: !!sub,
    refetchInterval: intervalMs,
    refetchIntervalInBackground: false,
    // Cheap enough that staleness doesn't matter — always trust the
    // latest tick.
    staleTime: 0,
  })
}

/**
 * Paginated queue list for the Imports hub panel.
 *
 * Auto-refreshes every ``activeIntervalMs`` while any row is still
 * running (``analyzing`` / ``committing`` / ``awaiting_resolve``).
 * When all rows are terminal, backs off to ``idleIntervalMs`` so we
 * don't thrash the API. The dynamic interval is computed from the
 * data itself — no separate "is anything running" query.
 */
export function useImportSessionsList(
  params: ImportsV2ListParams = {},
  options?: { activeIntervalMs?: number; idleIntervalMs?: number },
) {
  const sub = useSub()
  const activeIntervalMs = options?.activeIntervalMs ?? 3_000
  const idleIntervalMs = options?.idleIntervalMs ?? 15_000

  return useQuery<Paginated<ImportSessionSummary>>({
    queryKey: qkQueue.sessionsList(sub, params),
    queryFn: () => importsV2.template.listSessions(params),
    enabled: !!sub,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return activeIntervalMs
      const hasRunning = data.results.some(
        (r) =>
          r.status === "analyzing" ||
          r.status === "committing" ||
          r.status === "awaiting_resolve",
      )
      return hasRunning ? activeIntervalMs : idleIntervalMs
    },
    refetchIntervalInBackground: false,
    staleTime: 0,
  })
}

/**
 * Helper for host pages that just mutated queue state (e.g. "user
 * uploaded a new file"). Invalidates both the list and the badge
 * count so the UI updates before the next tick.
 */
export function useInvalidateImportQueue() {
  const qc = useQueryClient()
  const sub = useSub()
  return useCallback(() => {
    qc.invalidateQueries({ queryKey: ["imports", sub, "v2"] })
  }, [qc, sub])
}

// ---- v2 async session polling ------------------------------------------

/**
 * Terminal-status guard. A session in one of these states is done — the
 * poller can resolve and the UI can render whatever the backend wrote
 * to it (open_issues, preview, result).
 *
 * ``committed`` / ``error`` / ``discarded`` are the genuine terminals;
 * ``awaiting_resolve`` and ``ready`` are analyze outputs that mean
 * "the worker is done, hand control back to the operator".
 */
const NON_TERMINAL: ReadonlySet<ImportSessionStatus> = new Set([
  "analyzing",
  "committing",
])

/**
 * Poll ``GET /sessions/<id>/`` until the session leaves ``analyzing`` /
 * ``committing`` (Phase 6.z-a). The backend returns 202 for analyze +
 * commit now; the worker finishes in the background and the frontend
 * catches the final state here.
 *
 * ``namespace`` picks the URL prefix — ``"template"`` →
 * ``/api/core/imports/v2/...`` and ``"etl"`` → ``/api/core/etl/v2/...``.
 * Both share the same detail endpoint shape, so the hook is symmetric.
 *
 * ``intervalMs`` defaults to 2000 — fast enough to feel responsive for
 * a 30s analyze, slow enough to not hammer the server at the small-file
 * end. Callers tuning for big files can bump to 5000.
 *
 * Returns:
 *   * ``pollUntilDone(session)`` — a thenable that resolves with the
 *     final session. If ``session.status`` is already terminal when
 *     called, resolves immediately (zero network round-trips — eager
 *     mode + small-file path land here).
 *   * ``pollingId`` — the pk currently being polled, or null. Host
 *     pages can use it to render an "analisando…" spinner.
 *
 * Aborts cleanly on unmount: the in-flight promise resolves with the
 * last-seen session (not rejected — the UI doesn't care, it's going
 * away).
 */
export function useImportSessionPolling(
  namespace: "template" | "etl",
  options?: { intervalMs?: number },
) {
  const intervalMs = options?.intervalMs ?? 2000
  const [pollingId, setPollingId] = useState<number | null>(null)

  // ``activeTimer`` survives across renders so we can cancel a
  // pending setTimeout on unmount (stops the setState-after-unmount
  // warning and stops wasting bandwidth polling a page that's gone).
  const activeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    return () => {
      cancelledRef.current = true
      if (activeTimer.current) {
        clearTimeout(activeTimer.current)
        activeTimer.current = null
      }
    }
  }, [])

  const pollUntilDone = useCallback(
    (session: ImportSession): Promise<ImportSession> => {
      if (!NON_TERMINAL.has(session.status)) {
        // Eager mode / already-terminal fast path. No polling, no tick.
        return Promise.resolve(session)
      }
      setPollingId(session.id)
      return new Promise<ImportSession>((resolve, reject) => {
        let lastSeen = session
        const tick = async () => {
          if (cancelledRef.current) {
            // Component unmounted mid-poll. Resolve with the last
            // session we saw so any `await` call sites don't hang,
            // but don't touch state.
            resolve(lastSeen)
            return
          }
          try {
            const fresh = await importsV2[namespace].getSession(session.id)
            lastSeen = fresh
            if (!NON_TERMINAL.has(fresh.status)) {
              if (!cancelledRef.current) setPollingId(null)
              resolve(fresh)
              return
            }
            activeTimer.current = setTimeout(tick, intervalMs)
          } catch (err) {
            if (!cancelledRef.current) setPollingId(null)
            reject(err)
          }
        }
        activeTimer.current = setTimeout(tick, intervalMs)
      })
    },
    [namespace, intervalMs],
  )

  return { pollUntilDone, pollingId }
}
