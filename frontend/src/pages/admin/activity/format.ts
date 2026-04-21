/**
 * Helpers for the activity dashboards. Tiny on purpose — the page
 * components should be the ones with business logic; this is just
 * formatters + a heatmap color ramp.
 */

export function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "—"
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remSeconds = seconds % 60
  if (minutes < 60) return remSeconds ? `${minutes}m ${remSeconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remMinutes = minutes % 60
  return remMinutes ? `${hours}h ${remMinutes}m` : `${hours}h`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    })
  } catch {
    return iso
  }
}

/**
 * Heatmap fill: interpolates between a muted dark background and the
 * primary color based on how close ``value`` is to ``max``. Using
 * ``hsl(var(--primary))`` means the ramp respects theme tokens.
 */
export function heatmapFill(value: number, max: number): string {
  if (!max || value <= 0) return "hsl(var(--muted) / 0.25)"
  const intensity = Math.max(0.08, Math.min(1, value / max))
  return `hsl(var(--primary) / ${intensity.toFixed(2)})`
}

/** Human label for a UA string — best-effort, not bulletproof. */
export function shortUserAgent(ua: string | undefined | null): string {
  if (!ua) return "desconhecido"
  // Crude extraction of browser / platform tokens.
  const m = /(Firefox|Edg|Chrome|Safari)\/(\d+)/.exec(ua)
  const plat = /Windows NT|Mac OS X|Linux|iPhone|iPad|Android/.exec(ua)
  const browser = m ? `${m[1]} ${m[2]}` : "?"
  return `${browser}${plat ? ` · ${plat[0]}` : ""}`
}
