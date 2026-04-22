import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, Search, X } from "lucide-react"
import type { AccountLite } from "@/features/reconciliation/types"
import { cn } from "@/lib/utils"

/**
 * Minimal searchable account picker. Built from scratch (no cmdk) so the
 * accounts list stays rendered inline in a scrollable popup without stealing
 * focus to a command palette. Renders `code · path` so operators can find an
 * account by either column.
 *
 * Shared by every Bancada surface that lets an operator pick a posting
 * target (mass-match drawer, manual "adicionar lançamentos" drawer, etc.)
 * so new dropdowns get searchability for free.
 */
export function SearchableAccountSelect({
  accounts,
  value,
  onChange,
  placeholder = "Conta",
  compact = false,
  buttonClassName,
}: {
  accounts: AccountLite[]
  value: number | null
  onChange: (id: number | null) => void
  placeholder?: string
  /** Compact mode is used inside table cells. */
  compact?: boolean
  buttonClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = value != null ? accounts.find((a) => a.id === value) : null

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return accounts
    return accounts.filter((a) => {
      const hay = [a.account_code, a.name, a.path].filter(Boolean).join(" ").toLowerCase()
      return hay.includes(qq)
    })
  }, [q, accounts])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!containerRef.current) return
      if (!containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const label = selected
    ? `${selected.account_code ? `${selected.account_code} · ` : ""}${selected.path ?? selected.name}`
    : placeholder

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        // `title` gives operators a native tooltip with the full path when
        // the label truncates — the button itself stays fixed-height so
        // table rows keep their rhythm.
        title={selected ? label : undefined}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2 text-[12px] hover:bg-accent",
          compact ? "h-7 w-full" : "h-8 min-w-[260px]",
          !selected && "text-muted-foreground",
          buttonClassName,
        )}
      >
        <span className="truncate">{label}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </button>
      {open && (
        // A deeply-nested CoA path (e.g. "Ativo > Ativo Circulante >
        // Estoques > Matérias-Primas > Matérias-Primas - Produto >
        // Descontos Obtidos Matéria-Prima") blew past the old 480px cap
        // and had to be truncated. Bumping the max to 640px (capped at
        // 95vw so it stays on-screen on narrow tablets) plus wrapping
        // each option lets operators read the whole path before picking.
        <div className="absolute z-50 mt-1 w-[min(640px,95vw)] rounded-md border border-border bg-popover p-1 shadow-xl">
          <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por código, nome ou caminho…"
              className="h-8 flex-1 bg-transparent text-[12px] outline-none"
            />
            {q && (
              <button onClick={() => setQ("")} className="text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="mt-1 max-h-72 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-[12px] text-muted-foreground">
                Nenhuma conta encontrada.
              </div>
            ) : (
              filtered.slice(0, 300).map((a) => {
                const pathLabel = a.path ?? a.name
                const tooltip = a.account_code ? `${a.account_code} · ${pathLabel}` : pathLabel
                return (
                  <button
                    type="button"
                    key={a.id}
                    onClick={() => {
                      onChange(a.id)
                      setOpen(false)
                      setQ("")
                    }}
                    // items-start (not items-center) so the code column
                    // aligns with the *first* line of a wrapped path.
                    className={cn(
                      "flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-[12px] hover:bg-accent",
                      value === a.id && "bg-accent",
                    )}
                    title={tooltip}
                  >
                    {a.account_code && (
                      <span className="shrink-0 pt-px font-mono text-[11px] text-muted-foreground">
                        {a.account_code}
                      </span>
                    )}
                    {/* `break-words` + `min-w-0` lets long, unbroken
                        identifiers wrap inside the flex row instead of
                        forcing the popup to scroll horizontally. */}
                    <span className="min-w-0 flex-1 whitespace-normal break-words">{pathLabel}</span>
                  </button>
                )
              })
            )}
            {filtered.length > 300 && (
              <div className="px-2 py-1 text-center text-[11px] text-muted-foreground">
                Mostrando 300 de {filtered.length} — refine a busca.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
