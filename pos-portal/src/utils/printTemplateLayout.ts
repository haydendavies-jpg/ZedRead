/**
 * Shared line-layout logic for print template rendering — the SAME algorithm
 * the portal's live preview and the Android app's TemplateDocketRenderer must
 * both implement, so what a manager sees while editing a template matches
 * what actually comes out of the printer. Kept intentionally tiny and
 * dependency-free (pure string math) so it's trivial to port 1:1 into Kotlin.
 *
 * Real ESC/POS thermal printers render fixed-width monospace text line by
 * line — there is no freeform pixel canvas — so every alignment here is
 * plain character padding, not CSS text-align (which would not reproduce
 * what the printer actually does with a proportional-width simulation).
 */

import type { PrintFieldAlignment, PrintFieldSize, PrintTemplateElement } from '../types'

/** Matches DocketFormatter.LINE_WIDTH on the Android side — standard 58mm thermal paper. */
export const PRINT_LINE_WIDTH = 32

/**
 * Lay a piece of text out within a fixed character width per its alignment.
 *
 * - left: text, space-padded to width
 * - right: text, space-padded on the left
 * - center: text, padded evenly on both sides (extra space goes right)
 * - justify: words spread evenly to fill the width (typographic justify);
 *   falls back to left alignment for a single word, since there is nothing
 *   to distribute space between
 *
 * Text longer than width is truncated, never wrapped — matches
 * DocketFormatter's own `.take(LINE_WIDTH)` truncation, since a wrapped line
 * would silently push every later line's vertical position out of sync
 * between the preview and the real printer.
 *
 * @param text - The text to lay out.
 * @param width - The fixed character width to lay it out within.
 * @param alignment - One of 'left' | 'center' | 'right' | 'justify'.
 * @returns The text padded/aligned to exactly `width` characters.
 */
export function alignText(text: string, width: number, alignment: PrintFieldAlignment): string {
  const clipped = text.length > width ? text.slice(0, width) : text
  const spare = width - clipped.length

  if (alignment === 'right') return ' '.repeat(spare) + clipped
  if (alignment === 'center') {
    const left = Math.floor(spare / 2)
    return ' '.repeat(left) + clipped + ' '.repeat(spare - left)
  }
  if (alignment === 'justify') {
    const words = clipped.split(' ').filter(Boolean)
    if (words.length < 2) return clipped + ' '.repeat(spare)
    const totalWordLength = words.reduce((sum, w) => sum + w.length, 0)
    const totalGapSpace = width - totalWordLength
    const gaps = words.length - 1
    const baseGap = Math.floor(totalGapSpace / gaps)
    let extra = totalGapSpace - baseGap * gaps
    return words
      .map((word, i) => {
        if (i === words.length - 1) return word
        const gap = baseGap + (extra > 0 ? 1 : 0)
        if (extra > 0) extra -= 1
        return word + ' '.repeat(gap)
      })
      .join('')
  }
  // left (default)
  return clipped + ' '.repeat(spare)
}

/** A three-column row (label / middle / right) spread across the full width — mirrors DocketFormatter's item-line layout (name / qty / price). */
export function threeColumnLine(left: string, middle: string, right: string, width: number): string {
  const rightWidth = Math.max(right.length, 6)
  const middleWidth = Math.max(middle.length, 4)
  const leftWidth = Math.max(width - rightWidth - middleWidth, 1)
  return alignText(left, leftWidth, 'left') + alignText(middle, middleWidth, 'right') + alignText(right, rightWidth, 'right')
}

/** A horizontal divider line filling the full width — mirrors DocketFormatter.divider(). */
export function dividerLine(width: number): string {
  return '-'.repeat(width)
}

/** One rendered preview row — plain text plus the style flags the DOM preview applies via CSS. */
export interface PreviewLine {
  text: string
  isBold: boolean
  isItalic: boolean
  fontSize: PrintFieldSize
}

/** Sample values fed into the preview for each field_key — deliberately fake but realistic, so a manager can judge layout without a live order. */
const SAMPLE_VALUES: Record<string, string> = {
  LOGO: '[LOGO]',
  BRAND_NAME: 'ZedRead Cafe',
  STORE_NAME: 'City CBD',
  ADDRESS: '123 Example St, Sydney NSW 2000',
  STORE_PHONE: '(02) 5550 1234',
  ABN: 'ABN 12 345 678 901',
  DATE_TIME: '24 Jul 2026, 10:32am',
  INVOICE_NUMBER: 'INV-000042',
  SERVED_BY: 'Served by: Alex',
  ORDER_NOTES: 'No onions',
}

/**
 * Turn a template's ordered elements into preview rows using sample data —
 * the SAME field-by-field logic (alignment/padding) TemplateDocketRenderer
 * applies on-device, so this preview reads as close as possible to actual
 * printer output rather than an approximation.
 *
 * @param elements - The template's elements, already sorted into print order.
 * @param width - Fixed character width to lay each row out within.
 * @returns One PreviewLine per rendered row (an 'items' section element may render more than one row for its sample line items).
 */
export function buildPreviewLines(elements: PrintTemplateElement[], width: number = PRINT_LINE_WIDTH): PreviewLine[] {
  const lines: PreviewLine[] = []
  const push = (text: string, el: PrintTemplateElement) =>
    lines.push({ text, isBold: el.is_bold, isItalic: el.is_italic, fontSize: el.font_size })

  for (const el of elements) {
    switch (el.field_key) {
      case 'DIVIDER':
        push(dividerLine(width), el)
        break
      case 'FREE_TEXT':
        push(alignText(el.free_text_value ?? '', width, el.alignment), el)
        break
      case 'PRODUCT_LINE':
        push(threeColumnLine('Flat White', 'x2', '$9.00', width), el)
        push(threeColumnLine('Bacon & Egg Roll', 'x1', '$12.50', width), el)
        break
      case 'MODIFIER_LINE':
        push(alignText('+ Oat milk', width, el.alignment), el)
        break
      case 'ITEM_NOTES':
        push(alignText('No mayo', width, el.alignment), el)
        break
      case 'PAYMENT_METHOD_BREAKDOWN':
        push(threeColumnLine('Cash', '', '$45.00', width), el)
        push(threeColumnLine('Card', '', '$120.50', width), el)
        break
      case 'CASH_VARIANCE':
        push(threeColumnLine('Variance', '', '-$2.00', width), el)
        break
      case 'OPENING_CLOSING_CASH':
        push(threeColumnLine('Opening', '', '$200.00', width), el)
        push(threeColumnLine('Closing', '', '$243.00', width), el)
        break
      case 'CASH_IN_AMOUNT':
        push(threeColumnLine('Cash in', '', '$200.00', width), el)
        break
      case 'COUNTED_BY':
        push(alignText('Counted by: Alex', width, el.alignment), el)
        break
      default:
        push(alignText(SAMPLE_VALUES[el.field_key] ?? el.field_key, width, el.alignment), el)
    }
  }
  return lines
}
