/** Shared constants/helpers for the Menu Studio redesign (Products/Modifiers/Categories/Menus). */

/** Curated colour palette for category swatches and (future) POS button colours. */
export const MENU_STUDIO_PALETTE = [
  '#A82040', '#C56A1A', '#B8892B', '#4E7A51', '#2E6F7E',
  '#3B5A8C', '#6B4E8C', '#9C3D5A', '#7A5C3E', '#5A5550',
]

export const DEFAULT_CATEGORY_COLOR = '#5A5550'

/** Pick readable text colour (near-black or white) for a given background hex. */
export function textColorOn(hex: string): string {
  if (!hex || hex[0] !== '#' || hex.length < 7) return '#fff'
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.62 ? '#241f1a' : '#ffffff'
}

export function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}
