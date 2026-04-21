/**
 * Global frontend error capture.
 *
 * Three feeds:
 *
 *   1. ``window.onerror`` — synchronous runtime errors.
 *   2. ``window.addEventListener('unhandledrejection')`` — promise
 *      rejections that nobody caught.
 *   3. Axios response interceptor — 4xx/5xx from any tenant API call,
 *      so "the server said 500" also lands in the error dashboard.
 *
 * Everything funnels through :func:`logError` in the activity beacon,
 * which bundles breadcrumbs + stack and ships to
 * ``/api/activity/batch/``. The backend fingerprints + upserts into
 * ``ErrorReport`` from there.
 *
 * Idempotent — calling :func:`installErrorCapture` twice is a no-op.
 */

import axios, { AxiosError } from "axios"
import { logError } from "@/lib/activity-beacon"

let installed = false

export function installErrorCapture(): void {
  if (installed || typeof window === "undefined") return
  installed = true

  // 1. Runtime errors.
  window.addEventListener("error", (e) => {
    // Browser ``error`` event fires for both script errors and
    // resource load failures; we only care about the former —
    // filter on ``error`` being an actual Error object.
    if (e.error instanceof Error) {
      logError(e.error, { meta: { source: "window.onerror" } })
    } else if (e.message) {
      logError(new Error(e.message), { meta: { source: "window.onerror" } })
    }
  })

  // 2. Unhandled promise rejections. Many async paths end here
  // when a ``.catch`` is missing.
  window.addEventListener("unhandledrejection", (e) => {
    const reason = (e as PromiseRejectionEvent).reason
    if (reason instanceof Error) {
      logError(reason, { meta: { source: "unhandledrejection" } })
    } else {
      logError(new Error(typeof reason === "string" ? reason : JSON.stringify(reason)),
               { meta: { source: "unhandledrejection" } })
    }
  })

  // 3. Axios response interceptor.
  //
  // We attach to the default axios instance here because the app's
  // api-client creates its own instance with its own interceptors —
  // for THAT one we install a parallel hook below via the exported
  // helper :func:`attachAxiosErrorCapture`.
  attachAxiosErrorCapture(axios)
}

/**
 * Install the error-capture response interceptor on an axios
 * instance. Call this once per instance used by the app (the main
 * api-client has a dedicated one).
 */
export function attachAxiosErrorCapture(instance: typeof axios | ReturnType<typeof axios.create>): void {
  const i = instance as ReturnType<typeof axios.create>
  i.interceptors.response.use(
    (r) => r,
    (error: AxiosError) => {
      try {
        // Skip anything that's already known-noisy: 401 is handled
        // by the app's auth interceptor (logout + redirect),
        // 404 during normal navigation is expected, and canceled
        // requests aren't real errors.
        const status = error.response?.status
        if (error.code === "ERR_CANCELED" || axios.isCancel?.(error)) return Promise.reject(error)
        if (status === 401) return Promise.reject(error)

        const method = (error.config?.method || "").toUpperCase()
        const path = error.config?.url || ""
        const message =
          (error.response?.data as { detail?: string } | undefined)?.detail
          || error.message
          || "Request failed"
        const error_class = `${error.name || "AxiosError"}(${status ?? "net"})`
        logError(new Error(message), {
          meta: {
            source: "axios",
            error_class,
            method,
            status_code: status,
            path,
            // Limit the response body so a huge 500 HTML page
            // doesn't balloon our payload.
            response_preview: truncateBody(error.response?.data),
          },
        })
      } catch {
        /* never let capture block a rejection */
      }
      return Promise.reject(error)
    },
  )
}

function truncateBody(body: unknown): string {
  if (body == null) return ""
  try {
    const s = typeof body === "string" ? body : JSON.stringify(body)
    return s.length > 1000 ? `${s.slice(0, 1000)}…` : s
  } catch {
    return ""
  }
}
