import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { AccountLite } from "@/features/reconciliation/types"

/**
 * Searchable account select used everywhere an operator picks a Chart-of-
 * Accounts entry. Intentionally built from scratch (no cmdk) so the list
 * renders inline in a scrollable popover without stealing focus.
 *
 * Path visibility — WHY this component exists in its current shape:
 *   Account paths in Brazilian charts easily run 6+ levels:
 *     ``Ativo > Circulante > Disponibilidades > Bancos > BB > CC 12345``
 *   The old 480px popover + ``truncate`` class cut these mid-hierarchy,
 *   so operators couldn't tell which "Bancos > …" they were picking. The
 *   popover is now ``720px`` (or 95vw on narrow screens) and each row is
 *   two lines: bold code+name on top, muted full path below, allowed to
 *   wrap instead of truncate. ``title`` attrs on the row and the button
 *   are belt-and-braces tooltips for operators who want the raw string.
 *
 * Previously lived inline in ``MassReconcileDrawer`` — extracted so
 * AddEntriesDrawer and any future caller share exactly one picker UX.
 */
export interface SearchableAccountSelectProps {
  accounts: AccountLite[]
  value: number | null
  onChange: (id: number | null) => void
  placeholder?: string
  /** Compact mode renders at h-7 with w-full — for table cells. */
  compact?: boolean
  buttonClassName?: string
  /** Disable the button (e.g. while another action runs). */
  disabled?: boolean
}

export function SearchableAccountSelect({
  accounts,
  value,
  onChange,
  placeholder = "Conta",
  compact = false,
  buttonClassName,
  disabled = false,
}: SearchableAccountSelectProps) {
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

  // Close on click-outside. ``mousedown`` (not ``click``) so the popover
  // closes before the button's click handler re-opens it.
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!containerRef.current) return
      if (!containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  // Focus search input on open
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // The button displays the FULL "code · path" — not the leaf name — so
  // the operator reading a collapsed row can still see where this account
  // sits in the hierarchy. When it overflows the button width (tight
  // grid cells, compact mode) CSS truncates; the ``title`` attr keeps
  // the full string accessible on hover.
  const fullLabel = selected
    ? `${selected.account_code ? `${selected.account_code} · ` : ""}${selected.path ?? selected.name}`
    : ""
  const buttonLabel = selected ? fullLabel : placeholder

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        title={selected ? fullLabel : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2 text-[12px] hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60",
          compact ? "h-7 w-full" : "h-8 min-w-[260px]",
          !selected && "text-muted-foreground",
          buttonClassName,
        )}
      >
        <span className="truncate">{buttonLabel}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </button>
      {open && (
        <div
          className="absolute z-50 mt-1 w-[min(720px,95vw)] rounded-md border border-border bg-popover p-1 shadow-xl"
          role="listbox"
        >
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
              <button
                onClick={() => setQ("")}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Limpar busca"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="mt-1 max-h-[22rem] overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-[12px] text-muted-foreground">
                Nenhuma conta encontrada.
              </div>
            ) : (
              filtered.slice(0, 300).map((a) => {
                return (
                  <button
                    type="button"
                    key={a.id}
                    title={a.path || a.name}
                    onClick={() => {
                      onChange(a.id)
                      setOpen(false)
                      setQ("")
                    }}
                    className={cn(
                      // Two-line row: bold code+name on top, muted full
                      // path below. ``break-words`` lets a deep path
                      // wrap to a second line rather than truncate —
                      // the 720px popover leaves enough room that most
                      // paths fit on one line anyway.
                      "flex w-full flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left hover:bg-accent",
                      value === a.id && "bg-accent",
                    )}
                  >
                    <span className="flex w-full items-baseline gap-2 text-[12px] font-medium">
                      {a.account_code && (
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {a.account_code}
                        </span>
                      )}
                      <span className="truncate">{a.name}</span>
                    </span>
                    {a.path && a.path !== a.name && (
                      <span className="block w-full break-words text-[11px] leading-snug text-muted-foreground">
                        {a.path}
                      </span>
                    )}
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
