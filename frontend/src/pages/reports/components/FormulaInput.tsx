import { useMemo } from "react"
import { AlertCircle, Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { checkFormula } from "@/features/reports"

/**
 * Formula input with live parse validation.
 *
 * Shows:
 * - red border + tooltip when the formula has a parse error
 * - amber border + tooltip when every token parses but one or more block-id
 *   references are unresolved against the caller-supplied ``validIds``
 * - green check when the formula is good
 *
 * Syntax-highlighting the tokens in-place would need a contenteditable or
 * overlay with character measurement; deferred to PR10 (Monaco text mode).
 * Error cues here are enough for the inline editor.
 */
export function FormulaInput({
  value,
  onChange,
  validIds,
  placeholder = "fórmula (ex. sum(children) ou revenue - taxes)",
  className,
}: {
  value: string
  onChange: (next: string) => void
  validIds: Set<string>
  placeholder?: string
  className?: string
}) {
  const result = useMemo(() => checkFormula(value, validIds), [value, validIds])
  const empty = !value.trim()
  const hasError = !result.ok && !empty
  const hasUnresolved = !!result.error && result.refs.length > 0 && result.unresolvedRefs.length > 0

  const borderCls = empty
    ? "border-border"
    : hasError
      ? hasUnresolved
        ? "border-amber-500"
        : "border-red-500"
      : "border-emerald-500/60"

  return (
    <div className={cn("relative", className)}>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "h-6 w-full rounded-md border bg-background px-1.5 pr-6 font-mono text-[11px] outline-none focus:border-ring",
          borderCls,
        )}
      />
      {!empty && (
        <div
          className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2"
          title={result.error?.message ?? "fórmula válida"}
        >
          {hasError ? (
            <AlertCircle
              className={cn(
                "h-3 w-3",
                hasUnresolved ? "text-amber-500" : "text-red-500",
              )}
            />
          ) : (
            <Check className="h-3 w-3 text-emerald-500" />
          )}
        </div>
      )}

      {/* Inline error message on focus-within, so users don't need to hover
          the icon to see what's wrong. */}
      {hasError && (
        <div
          className={cn(
            "absolute left-0 top-[calc(100%+2px)] z-20 hidden rounded-md border bg-popover px-2 py-1 text-[10px] shadow-md peer-focus:block group-focus-within:block",
            hasUnresolved
              ? "border-amber-500/50 text-amber-700 dark:text-amber-300"
              : "border-red-500/50 text-red-700 dark:text-red-300",
          )}
        >
          {result.error?.message}
        </div>
      )}
    </div>
  )
}
