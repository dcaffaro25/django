/**
 * Color helpers that bridge the backend (which stores brand palettes
 * as 6-digit hex strings) to the frontend's CSS variable system,
 * which expects the body of an ``hsl(...)`` call: ``"H S% L%"``.
 *
 * Kept dependency-free on purpose -- chroma.js / culori would each
 * pull in 14-30 KB of color machinery we don't need for plain
 * conversions and contrast checks.
 */

/** Parse a 3- or 6-digit hex string to ``[r, g, b]`` in 0-255. Returns
 *  ``null`` if the input doesn't look like a hex color. */
export function hexToRgb(hex: string): [number, number, number] | null {
  if (!hex) return null
  let s = hex.trim().replace(/^#/, "")
  if (s.length === 3) {
    s = s.split("").map((c) => c + c).join("")
  }
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null
  const r = parseInt(s.slice(0, 2), 16)
  const g = parseInt(s.slice(2, 4), 16)
  const b = parseInt(s.slice(4, 6), 16)
  return [r, g, b]
}

/** Convert RGB (0-255) to HSL components ``[h, s, l]`` where ``h`` is
 *  0-360 and ``s`` / ``l`` are 0-100. */
export function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  let h = 0
  let s = 0
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case rn:
        h = (gn - bn) / d + (gn < bn ? 6 : 0)
        break
      case gn:
        h = (bn - rn) / d + 2
        break
      case bn:
        h = (rn - gn) / d + 4
        break
    }
    h *= 60
  }
  return [Math.round(h), Math.round(s * 100), Math.round(l * 100)]
}

/** Convert a hex color (``#015736``) to the body of an ``hsl(...)``
 *  call (``"155 98% 17%"``) so it can be slotted into a CSS custom
 *  property and consumed by ``hsl(var(--token))`` like the rest of
 *  the design system. Returns ``null`` for invalid input. */
export function hexToHslVar(hex: string): string | null {
  const rgb = hexToRgb(hex)
  if (!rgb) return null
  const [h, s, l] = rgbToHsl(rgb[0], rgb[1], rgb[2])
  return `${h} ${s}% ${l}%`
}

/** Pick a foreground hex (``"#FFFFFF"`` or ``"#000000"``) that gives
 *  the highest contrast against the supplied background hex. Used to
 *  auto-derive ``*_foreground`` tokens when the operator only sets
 *  the background colour. */
export function contrastForeground(bgHex: string): string {
  const rgb = hexToRgb(bgHex)
  if (!rgb) return "#000000"
  // Standard relative-luminance formula (sRGB).
  const [r, g, b] = rgb.map((c) => {
    const cs = c / 255
    return cs <= 0.03928 ? cs / 12.92 : Math.pow((cs + 0.055) / 1.055, 2.4)
  })
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luminance > 0.55 ? "#000000" : "#FFFFFF"
}
