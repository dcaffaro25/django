import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { ChevronDown, Search, X } from "lucide-react"
import type { AccountLite } from "@/features/reconciliation/types"
import { cn } from "@/lib/utils"

/** Desired popover width. Large enough to render a 6-level path on one
 *  line; when the viewport can't spare this much, we clamp to the
 *  available horizontal space minus a small safety margin. */
const PREFERRED_POPOVER_WIDTH = 640
/** Minimum width before we force a clamp. */
const MIN_POPOVER_WIDTH = 320
/** Viewport-edge safety margin — keeps the popover off the literal edge
 *  of the window so the shadow doesn't get clipped. */
const EDGE_MARGIN = 8
/** Vertical gap between the trigger button and the popover. */
const POPOVER_GAP = 4

/**
 * Minimal searchable account picker.
 *
 * Design decisions (learned the hard way — see the screenshots in the
 * PR thread that drove this component):
 *
 *   * **Popover is portaled to ``document.body``**. Host drawers
 *     (AdjustmentDrawer, AddEntriesDrawer, MassReconcileDrawer) apply
 *     ``overflow-y-auto`` on their body which, per CSS spec, also
 *     clips the X axis once the cross-axis is non-``visible``. Inline
 *     ``absolute`` popovers got sliced to a thin strip at the drawer's
 *     left edge. Rendering into ``<body>`` with ``position: fixed``
 *     dodges every ancestor overflow completely.
 *
 *   * **Trigger shows ``code · name``, not ``code · path``**. The
 *     selected-state label used to be the full path — but drawers put
 *     the trigger in tight grid cells (~150–260px wide) and the path
 *     always got truncated mid-hierarchy, hiding the leaf (the one
 *     bit operators need to confirm they picked the right row).
 *     ``code · name`` is short enough to fit most triggers; the full
 *     path stays visible in the popover and via ``title`` tooltip.
 *
 *   * **Viewport-aware placement** — on open we measure the trigger's
 *     rect and pick between left-anchor / right-anchor / clamped
 *     width based on which side has more room. Re-runs on scroll +
 *     resize so the popover follows its trigger.
 *
 * Built from scratch (no cmdk) so the accounts list stays rendered
 * inline in a scrollable popup without stealing focus to a command
 * palette.
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
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  // Computed popover position + size in viewport coordinates. Populated
  // by the layout effect below and consumed by the portaled popover
  // ``<div>`` as inline style.
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({
    position: "fixed",
    top: 0,
    left: 0,
    width: PREFERRED_POPOVER_WIDTH,
    visibility: "hidden",
  })

  const selected = value != null ? accounts.find((a) => a.id === value) : null

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return accounts
    return accounts.filter((a) => {
      const hay = [a.account_code, a.name, a.path].filter(Boolean).join(" ").toLowerCase()
      return hay.includes(qq)
    })
  }, [q, accounts])

  // Close on click-outside. Covers BOTH the trigger's subtree and the
  // portaled popover — without the popover check, clicking inside the
  // portaled popover (outside the trigger's DOM subtree) would close it.
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node
      if (triggerRef.current?.contains(t)) return
      if (popoverRef.current?.contains(t)) return
      setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Compute viewport-anchored coordinates on open / resize / scroll.
  // We prefer to open the popover aligned to the trigger's LEFT edge
  // (growing rightward) but flip to RIGHT-edge alignment when there's
  // not enough room on the right. Width clamps to the larger available
  // side when neither fits the preferred size.
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const el = triggerRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const viewportW = window.innerWidth
      const viewportH = window.innerHeight

      // Horizontal placement.
      const spaceRight = viewportW - rect.left - EDGE_MARGIN
      const spaceLeft = rect.right - EDGE_MARGIN
      let width: number
      let leftPx: number
      if (spaceRight >= PREFERRED_POPOVER_WIDTH) {
        width = PREFERRED_POPOVER_WIDTH
        leftPx = rect.left
      } else if (spaceLeft >= PREFERRED_POPOVER_WIDTH) {
        width = PREFERRED_POPOVER_WIDTH
        leftPx = rect.right - PREFERRED_POPOVER_WIDTH
      } else {
        // Cramped — use the larger side and clamp.
        width = Math.max(MIN_POPOVER_WIDTH, Math.max(spaceRight, spaceLeft))
        if (spaceRight >= spaceLeft) {
          leftPx = rect.left
        } else {
          leftPx = rect.right - width
        }
      }
      // Final safety: keep the popover fully inside the viewport.
      leftPx = Math.max(EDGE_MARGIN, Math.min(leftPx, viewportW - width - EDGE_MARGIN))

      // Vertical placement: open below the trigger by default; flip
      // upward if the button is too close to the bottom edge.
      const desiredHeight = 380 // rough cap; popover's own max-height handles the rest
      const spaceBelow = viewportH - rect.bottom - EDGE_MARGIN
      const openAbove = spaceBelow < desiredHeight && rect.top > spaceBelow
      const topPx = openAbove
        ? Math.max(EDGE_MARGIN, rect.top - desiredHeight - POPOVER_GAP)
        : rect.bottom + POPOVER_GAP

      setPopoverStyle({
        position: "fixed",
        top: topPx,
        left: leftPx,
        width,
        visibility: "visible",
      })
    }
    place()
    window.addEventListener("resize", place)
    // capture:true so we catch scroll on ANY ancestor (drawer body's
    // overflow-y-auto, the page itself, etc.) — the popover needs to
    // re-measure whenever its trigger moves.
    window.addEventListener("scroll", place, true)
    return () => {
      window.removeEventListener("resize", place)
      window.removeEventListener("scroll", place, true)
    }
  }, [open])

  // Short label for the trigger button: ``code · name`` (leaf), not the
  // full path. Rationale in the component doc-comment above. We still
  // expose the full ``code · path`` via the button's ``title`` so a
  // hover tooltip gives operators the hierarchy when they need it.
  const shortLabel = selected
    ? `${selected.account_code ? `${selected.account_code} · ` : ""}${selected.name}`
    : placeholder
  const fullLabel = selected
    ? `${selected.account_code ? `${selected.account_code} · ` : ""}${selected.path ?? selected.name}`
    : ""

  const popover = open ? (
    <div
      ref={popoverRef}
      style={popoverStyle}
      // ``z-[60]`` stays above the Vaul drawer overlay (z-50). The
      // portal lives in ``<body>`` so there's no ancestor overflow to
      // fight.
      className="z-[60] rounded-md border border-border bg-popover p-1 shadow-xl"
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
                // items-start so the code column aligns with the *first*
                // line of a wrapped path.
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
                {/* break-words + min-w-0 lets long, unbroken identifiers
                    wrap inside the flex row instead of forcing the
                    popup to scroll horizontally. */}
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
  ) : null

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        // ``title`` carries the full ``code · path`` so operators who want
        // the hierarchy can hover; the visible label is the leaf for
        // readability in narrow grid cells.
        title={selected ? fullLabel : undefined}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2 text-[12px] hover:bg-accent",
          compact ? "h-7 w-full" : "h-8 min-w-[260px]",
          !selected && "text-muted-foreground",
          buttonClassName,
        )}
      >
        <span className="truncate">{shortLabel}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </button>
      {popover && typeof document !== "undefined"
        ? createPortal(popover, document.body)
        : null}
    </div>
  )
}
