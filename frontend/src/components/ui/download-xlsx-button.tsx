import { useState } from "react"
import { Download, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { getStoredTenant, getStoredToken } from "@/lib/api-client"
import { cn } from "@/lib/utils"

/**
 * "Download XLSX" button.
 *
 * Calls a tenant-scoped endpoint that returns an xlsx binary, reads it as
 * a Blob, and triggers a browser download. The endpoint is expected to
 * honour the same querystring filters the list view uses — so what the
 * user downloads matches what they're looking at, minus the pagination
 * cap.
 */
export function DownloadXlsxButton({
  /** Tenant-scoped path, e.g. `"/api/bank_transactions/export_xlsx/"`. */
  path,
  /** Extra query parameters appended to the URL. Keys with `undefined`/`""`
   *  values are dropped so callers can pass filter state verbatim. */
  params,
  filename,
  label = "Excel",
  title = "Baixar como Excel (toda a lista filtrada)",
  className,
}: {
  path: string
  params?: Record<string, string | number | boolean | undefined | null>
  filename?: string
  label?: string
  title?: string
  className?: string
}) {
  const [loading, setLoading] = useState(false)

  const onClick = async () => {
    const tenant = getStoredTenant()
    if (!tenant) {
      toast.error("Nenhum tenant selecionado")
      return
    }
    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"
    const qs = new URLSearchParams()
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === null || v === "") continue
        qs.set(k, String(v))
      }
    }
    const cleanPath = path.startsWith("/") ? path : `/${path}`
    const url = `${base}/${tenant}${cleanPath}${qs.toString() ? `?${qs.toString()}` : ""}`

    setLoading(true)
    try {
      const token = getStoredToken()
      const res = await fetch(url, {
        method: "GET",
        headers: token ? { Authorization: `Token ${token}` } : {},
      })
      if (!res.ok) {
        const text = await res.text().catch(() => "")
        throw new Error(text || `HTTP ${res.status}`)
      }
      const blob = await res.blob()
      // Prefer the server-provided filename (Content-Disposition) when
      // the caller didn't pin one; the backend sets RFC5987-style
      // `filename*=UTF-8''…` so non-ASCII names survive.
      const resolved =
        filename ??
        parseFilenameFromCD(res.headers.get("Content-Disposition")) ??
        "export.xlsx"
      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = objUrl
      a.download = resolved
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(objUrl)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha no download")
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      title={title}
      className={cn(
        "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-[12px] font-medium hover:bg-accent disabled:opacity-60",
        className,
      )}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
      {label}
    </button>
  )
}

function parseFilenameFromCD(cd: string | null): string | null {
  if (!cd) return null
  // RFC5987 form: filename*=UTF-8''encoded%20name.xlsx
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (star) {
    try {
      return decodeURIComponent(star[1]!.trim())
    } catch {
      // fall through to the plain form
    }
  }
  const plain = /filename="?([^"]+)"?/i.exec(cd)
  return plain ? plain[1]!.trim() : null
}
