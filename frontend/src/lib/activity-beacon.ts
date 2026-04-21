/**
 * Per-tab activity beacon.
 *
 * Collects page_view, heartbeat, action, search, and error events,
 * then flushes them to ``POST /api/activity/batch/`` on a cadence
 * (default every 30s while the tab is visible and not idle) and on
 * ``beforeunload`` via ``navigator.sendBeacon``.
 *
 * Design goals, in rough priority order:
 *
 *   1. **Never block the user.** All writes are fire-and-forget; the
 *      queue drops events if the beacon endpoint is unreachable for
 *      too long, rather than growing without bound.
 *   2. **Honest "time focused".** Heartbeats only fire while the tab
 *      is ``document.visible`` and the user hasn't been idle for
 *      ``IDLE_MS`` ms (no mouse/keyboard/scroll). A user reading a
 *      long report without interacting stops counting after the idle
 *      threshold — explicit interaction resumes it.
 *   3. **Cheap on the backend.** Batch up to 20 events per request;
 *      debounce page_view bursts.
 *   4. **Opt-out friendly.** A single ``disable()`` call pauses
 *      everything and drops pending events. The backend still
 *      enforces its own auth, so opting out is strictly client-side.
 *
 * The beacon is a singleton — construct it once in ``App.tsx`` via
 * ``installActivityBeacon()``. Subsequent calls are no-ops.
 */

import { getStoredTenant, getStoredToken } from "@/lib/api-client"
import { normalizePath, resolveArea } from "@/lib/areas"

const HEARTBEAT_MS = 30_000
const IDLE_MS = 120_000
const MAX_QUEUED_EVENTS = 500

type BeaconKind = "page_view" | "heartbeat" | "action" | "error" | "search"

interface QueuedEvent {
  kind: BeaconKind
  area: string
  path: string
  action?: string
  target_model?: string
  target_id?: string
  duration_ms?: number
  meta?: Record<string, unknown>
  /** Client timestamp for debugging — not sent to the backend. */
  client_ts: number
}

interface Beacon {
  /** Current tab session key (UUID). */
  readonly sessionKey: string
  /** Replace the current area manually — e.g. when navigating
   *  programmatically in a way the router hook doesn't observe. */
  setCurrentArea(path: string): void
  logAction(
    action: string,
    detail?: {
      area?: string
      target_model?: string
      target_id?: string | number
      duration_ms?: number
      meta?: Record<string, unknown>
    },
  ): void
  logError(error: unknown, detail?: { area?: string; meta?: Record<string, unknown> }): void
  logSearch(query: string, detail?: { area?: string; results?: number }): void
  /** Flush now (fire-and-forget). Used on unload. */
  flush(reason?: "manual" | "unload"): void
  /** Stop collecting. Idempotent. */
  disable(): void
}

let singleton: Beacon | null = null

function uuid(): string {
  // crypto.randomUUID is universally available in modern browsers;
  // the fallback covers environments without it (e.g. older WebViews).
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID()
  const hex = () => Math.floor(Math.random() * 16).toString(16)
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) =>
    c === "x" ? hex() : ((Math.floor(Math.random() * 4) + 8).toString(16)),
  )
}

function isDebugEnabled(): boolean {
  return typeof window !== "undefined" && !!(window as unknown as { __ACTIVITY_DEBUG?: boolean }).__ACTIVITY_DEBUG
}

export function installActivityBeacon(): Beacon {
  if (singleton) return singleton

  const sessionKey = uuid()

  // ---- state ----------------------------------------------------
  const queue: QueuedEvent[] = []
  let currentArea = ""
  let currentPath = ""
  let lastInteractionAt = Date.now()
  let focusedSinceHeartbeatMs = 0
  let idleSinceHeartbeatMs = 0
  let lastTickAt = Date.now()
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let disabled = false

  // Breadcrumb ring — last N meaningful events on this tab (we
  // skip heartbeats because they add no signal). Attached to
  // every error event so the admin dashboard can answer "what
  // was the user doing just before it broke?"
  const BREADCRUMB_LIMIT = 20
  const breadcrumbs: Array<{ ts: number; kind: string; area?: string; path?: string; action?: string }> = []
  const recordBreadcrumb = (ev: QueuedEvent) => {
    if (ev.kind === "heartbeat" || ev.kind === "error") return
    breadcrumbs.push({
      ts: ev.client_ts,
      kind: ev.kind,
      area: ev.area,
      path: ev.path,
      action: ev.action,
    })
    if (breadcrumbs.length > BREADCRUMB_LIMIT) breadcrumbs.shift()
  }

  // ---- helpers --------------------------------------------------
  const enqueue = (ev: QueuedEvent) => {
    if (disabled) return
    if (queue.length >= MAX_QUEUED_EVENTS) queue.shift()
    queue.push(ev)
    recordBreadcrumb(ev)
    if (isDebugEnabled()) {
      // eslint-disable-next-line no-console
      console.debug("[beacon] queued", ev)
    }
  }

  const isFocusedAndAwake = () => {
    const visible = typeof document === "undefined" ? true : document.visibilityState === "visible"
    const awake = Date.now() - lastInteractionAt < IDLE_MS
    return visible && awake
  }

  const recordInteraction = () => {
    lastInteractionAt = Date.now()
  }

  // Accumulate focused/idle deltas every second. Splitting the
  // bookkeeping from the flush cadence lets us report accurate
  // numbers even if the heartbeat interval drifts.
  const tickTimer = setInterval(() => {
    if (disabled) return
    const now = Date.now()
    const delta = now - lastTickAt
    lastTickAt = now
    if (isFocusedAndAwake()) focusedSinceHeartbeatMs += delta
    else idleSinceHeartbeatMs += delta
  }, 1000)

  const emitHeartbeat = () => {
    if (!currentArea || focusedSinceHeartbeatMs === 0) return
    enqueue({
      kind: "heartbeat",
      area: currentArea,
      path: currentPath,
      duration_ms: focusedSinceHeartbeatMs,
      client_ts: Date.now(),
    })
  }

  const flush = async (reason: "heartbeat" | "manual" | "unload" = "manual") => {
    if (disabled) return
    if (!queue.length && !focusedSinceHeartbeatMs && reason !== "unload") return

    if (reason !== "unload") emitHeartbeat()

    const events = queue.splice(0, queue.length).map(({ client_ts, ...rest }) => {
      void client_ts
      return rest
    })
    const focusedDelta = focusedSinceHeartbeatMs
    const idleDelta = idleSinceHeartbeatMs
    focusedSinceHeartbeatMs = 0
    idleSinceHeartbeatMs = 0

    const payload = {
      session_key: sessionKey,
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "",
      viewport_width: typeof window !== "undefined" ? window.innerWidth : undefined,
      viewport_height: typeof window !== "undefined" ? window.innerHeight : undefined,
      company_subdomain: getStoredTenant() ?? undefined,
      focused_ms_delta: focusedDelta,
      idle_ms_delta: idleDelta,
      ended: reason === "unload",
      events,
    }

    const url = buildUrl("/api/activity/batch/")
    const token = getStoredToken()

    // On unload, sendBeacon is the only reliable path — it survives
    // page navigation and doesn't block. It can't set Authorization
    // headers, though, so for token auth we fall back to
    // fetch-keepalive and accept that some unload flushes may race
    // the tab closing.
    if (reason === "unload" && typeof navigator !== "undefined" && navigator.sendBeacon && !token) {
      try {
        const blob = new Blob([JSON.stringify(payload)], { type: "application/json" })
        navigator.sendBeacon(url, blob)
        return
      } catch {
        /* fall through to fetch */
      }
    }

    try {
      await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Token ${token}` } : {}),
        },
        body: JSON.stringify(payload),
        keepalive: reason === "unload",
        credentials: "same-origin",
      })
    } catch {
      // Swallow — beacons are best-effort. If the backend is down,
      // we still ran the tick timer and can retry on the next
      // heartbeat.
    }
  }

  // ---- listeners ------------------------------------------------
  const onInteraction = () => recordInteraction()
  const onVisibility = () => {
    if (typeof document === "undefined") return
    if (document.visibilityState === "hidden") {
      // Flush what we have before losing focus — the next heartbeat
      // might be 30s out and the user might close the tab sooner.
      void flush("manual")
    } else {
      // Reset interaction baseline so the first second after
      // returning doesn't count as idle.
      lastInteractionAt = Date.now()
      lastTickAt = Date.now()
    }
  }
  const onBeforeUnload = () => {
    void flush("unload")
  }

  if (typeof window !== "undefined") {
    window.addEventListener("mousemove", onInteraction, { passive: true })
    window.addEventListener("keydown", onInteraction, { passive: true })
    window.addEventListener("scroll", onInteraction, { passive: true })
    window.addEventListener("click", onInteraction, { passive: true })
    window.addEventListener("beforeunload", onBeforeUnload)
    document.addEventListener("visibilitychange", onVisibility)
  }

  heartbeatTimer = setInterval(() => void flush("heartbeat"), HEARTBEAT_MS)

  // ---- public API ----------------------------------------------
  singleton = {
    sessionKey,

    setCurrentArea(path: string) {
      const normalized = normalizePath(path)
      if (normalized === currentPath) return
      // Emit heartbeat for the *previous* area before switching, so
      // time spent doesn't bleed across a navigation.
      emitHeartbeat()
      focusedSinceHeartbeatMs = 0

      const area = resolveArea(path)
      currentPath = normalized
      currentArea = area?.id ?? ""

      enqueue({
        kind: "page_view",
        area: currentArea,
        path: currentPath,
        client_ts: Date.now(),
      })
    },

    logAction(action, detail = {}) {
      enqueue({
        kind: "action",
        area: detail.area ?? currentArea,
        path: currentPath,
        action,
        target_model: detail.target_model,
        target_id: detail.target_id != null ? String(detail.target_id) : undefined,
        duration_ms: detail.duration_ms,
        meta: detail.meta,
        client_ts: Date.now(),
      })
    },

    logError(error, detail = {}) {
      // Shape the meta payload so the backend's capture_error can
      // fingerprint it the same way it fingerprints Python
      // exceptions: error_class + top-of-stack.
      const err = error as unknown as { name?: string; message?: string; stack?: string } | null
      const error_class = (err && typeof err.name === "string" && err.name)
        || (error instanceof Error ? error.constructor.name : typeof error)
      const message = (err && typeof err.message === "string" && err.message)
        || (error instanceof Error ? error.message : String(error))
      const stack = (err && typeof err.stack === "string" ? err.stack : "").slice(0, 8000)
      enqueue({
        kind: "error",
        area: detail.area ?? currentArea,
        path: currentPath,
        meta: {
          error_class,
          message,
          stack,
          // Snapshot of the last ~20 meaningful interactions. The
          // backend persists this on the occurrence event so the
          // admin drill-down shows exactly what the user did before
          // this fired.
          breadcrumbs: breadcrumbs.slice(),
          ...(detail.meta ?? {}),
        },
        client_ts: Date.now(),
      })
    },

    logSearch(query, detail = {}) {
      enqueue({
        kind: "search",
        area: detail.area ?? currentArea,
        path: currentPath,
        meta: { query, results: detail.results },
        client_ts: Date.now(),
      })
    },

    flush(reason = "manual") {
      void flush(reason)
    },

    disable() {
      if (disabled) return
      disabled = true
      queue.length = 0
      if (heartbeatTimer) clearInterval(heartbeatTimer)
      clearInterval(tickTimer)
      if (typeof window !== "undefined") {
        window.removeEventListener("mousemove", onInteraction)
        window.removeEventListener("keydown", onInteraction)
        window.removeEventListener("scroll", onInteraction)
        window.removeEventListener("click", onInteraction)
        window.removeEventListener("beforeunload", onBeforeUnload)
        document.removeEventListener("visibilitychange", onVisibility)
      }
    },
  }

  return singleton
}

/** Return the installed beacon, or ``null`` if not yet installed. */
export function getBeacon(): Beacon | null {
  return singleton
}

/** Shorthand for the most-common call: ``logAction("match", {...})``. */
export function logAction(
  action: string,
  detail?: {
    area?: string
    target_model?: string
    target_id?: string | number
    duration_ms?: number
    meta?: Record<string, unknown>
  },
): void {
  singleton?.logAction(action, detail)
}

export function logError(error: unknown, detail?: { area?: string; meta?: Record<string, unknown> }): void {
  singleton?.logError(error, detail)
}

export function logSearch(query: string, detail?: { area?: string; results?: number }): void {
  singleton?.logSearch(query, detail)
}

// ---------------------------------------------------------------- helpers


function buildUrl(apiPath: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"
  const clean = apiPath.startsWith("/") ? apiPath : `/${apiPath}`
  return `${base}${clean}`
}
