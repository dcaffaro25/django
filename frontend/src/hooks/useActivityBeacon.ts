import { useEffect, useRef } from "react"
import { useLocation } from "react-router-dom"
import { useAuth } from "@/providers/AuthProvider"
import { getBeacon, installActivityBeacon } from "@/lib/activity-beacon"

/**
 * Wire the activity beacon into React:
 *
 *   * Install the singleton once the user is authenticated (no
 *     point tracking anonymous /login visits — the user isn't
 *     identified yet).
 *   * On every route change, tell the beacon to emit a ``page_view``.
 *   * On logout, tear the beacon down and drop the queue.
 *
 * Mount **once**, near the top of the tree (in AppShell). Calling
 * this from multiple components is safe (install is idempotent) but
 * wasteful.
 */
export function useActivityBeacon(): void {
  const location = useLocation()
  const { isAuthenticated } = useAuth()
  const installedRef = useRef(false)

  // Install on first authenticated render.
  useEffect(() => {
    if (!isAuthenticated) return
    if (!installedRef.current) {
      installActivityBeacon()
      installedRef.current = true
    }
  }, [isAuthenticated])

  // On logout, stop collecting.
  useEffect(() => {
    if (!isAuthenticated && installedRef.current) {
      getBeacon()?.disable()
      installedRef.current = false
    }
  }, [isAuthenticated])

  // Emit page_view on route change.
  useEffect(() => {
    if (!isAuthenticated) return
    getBeacon()?.setCurrentArea(location.pathname + location.search)
  }, [isAuthenticated, location.pathname, location.search])
}
