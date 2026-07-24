package com.zedread.pos.printing

/**
 * Kotlin port of the portal's `src/utils/printTemplateLayout.ts` -- the SAME
 * character-padding algorithm, kept 1:1 so a template's live preview in the
 * portal matches what actually comes out of this printer. Real ESC/POS
 * thermal printers render fixed-width monospace text line by line -- every
 * alignment here is plain character padding, not a positioning command.
 */

/** Matches DocketFormatter.LINE_WIDTH -- standard 58mm thermal paper. */
const val PRINT_LINE_WIDTH = 32

/**
 * Lay [text] out within [width] characters per [alignment] ('left' | 'right' |
 * 'center' | 'justify'). Longer text is truncated, never wrapped -- a wrapped
 * line would push every later line out of sync with the portal's preview,
 * which also truncates (see printTemplateLayout.ts's own doc).
 */
fun alignText(text: String, width: Int, alignment: String): String {
    val clipped = if (text.length > width) text.take(width) else text
    val spare = width - clipped.length

    return when (alignment) {
        "right" -> " ".repeat(spare) + clipped
        "center" -> {
            val left = spare / 2
            " ".repeat(left) + clipped + " ".repeat(spare - left)
        }
        "justify" -> {
            val words = clipped.split(" ").filter { it.isNotEmpty() }
            if (words.size < 2) {
                clipped + " ".repeat(spare)
            } else {
                val totalWordLength = words.sumOf { it.length }
                val totalGapSpace = width - totalWordLength
                val gaps = words.size - 1
                val baseGap = totalGapSpace / gaps
                var extra = totalGapSpace - baseGap * gaps
                buildString {
                    words.forEachIndexed { i, word ->
                        append(word)
                        if (i < words.size - 1) {
                            val gap = baseGap + if (extra > 0) 1 else 0
                            if (extra > 0) extra -= 1
                            append(" ".repeat(gap))
                        }
                    }
                }
            }
        }
        else -> clipped + " ".repeat(spare) // left (default)
    }
}

/** A three-column row (left / middle / right) spread across the full width -- mirrors DocketFormatter's item-line layout (name / qty / price). */
fun threeColumnLine(left: String, middle: String, right: String, width: Int): String {
    val rightWidth = maxOf(right.length, 6)
    val middleWidth = maxOf(middle.length, 4)
    val leftWidth = maxOf(width - rightWidth - middleWidth, 1)
    return alignText(left, leftWidth, "left") + alignText(middle, middleWidth, "right") + alignText(right, rightWidth, "right")
}

/** A horizontal divider line filling the full width -- mirrors DocketFormatter.divider(). */
fun dividerLine(width: Int): String = "-".repeat(width)

/** Format cents as a signed dollar string, e.g. -150 -> "-$1.50" -- mirrors invoice_pdf_service's own `_cents_to_display`. */
fun formatCentsForPrint(cents: Long): String {
    val sign = if (cents < 0) "-" else ""
    val abs = kotlin.math.abs(cents)
    val dollars = abs / 100
    val remainder = abs % 100
    return "$sign\$$dollars.${remainder.toString().padStart(2, '0')}"
}

/** One rendered, print-order row -- plain text plus the style flags the driver applies (bold via ESC/POS command; italic has no widely-supported raw ESC/POS command, so generic drivers ignore it, the same limitation DocketFormatter already has). */
data class RenderedLine(
    val text: String,
    val isBold: Boolean = false,
    val isItalic: Boolean = false,
)

// Real ESC/POS control sequences, including their ESC (0x1B) / GS (0x1D)
// prefix bytes, built numerically via Char(codePoint) so this source file
// contains no literal control bytes or escape sequences at all -- unlike
// DocketFormatter's own BOLD_ON/BOLD_OFF/CUT constants (which omit the
// prefix byte entirely and so print as literal "E"/"VA" text rather than
// actual commands, a pre-existing gap this renderer does not repeat).
// Control bytes below 0x80 map 1:1 to UTF-8 single bytes, so building these
// as plain Kotlin strings and encoding via Charsets.UTF_8 produces the exact
// intended raw bytes.
private val ESC_BYTE = 0x1B.toChar().toString()
private val GS_BYTE = 0x1D.toChar().toString()
private val ESC_BOLD_ON = ESC_BYTE + "E" + 0x01.toChar() // ESC E 1 -- bold on
private val ESC_BOLD_OFF = ESC_BYTE + "E" + 0x00.toChar() // ESC E 0 -- bold off
private val GS_CUT_PARTIAL = GS_BYTE + "V" + 0x01.toChar() // GS V 1 -- partial cut

/**
 * Render a driver-neutral [RenderedLine] list (already padded/aligned as
 * plain text -- see [alignText]'s own doc) to raw ESC/POS bytes for the
 * generic network/Bluetooth drivers. The Epson driver instead iterates
 * [RenderedLine] directly into its own SDK's `addText`/`addTextStyle` calls
 * -- see [com.zedread.pos.printing.epson.EpsonPrinterDriver].
 */
fun renderedLinesToEscPosBytes(lines: List<RenderedLine>): ByteArray {
    val sb = StringBuilder()
    for (line in lines) {
        sb.append(if (line.isBold) ESC_BOLD_ON else ESC_BOLD_OFF)
        sb.append(line.text)
        sb.append('\n')
    }
    sb.append(ESC_BOLD_OFF).append('\n').append('\n')
    sb.append(GS_CUT_PARTIAL)
    return sb.toString().toByteArray(Charsets.UTF_8)
}

/**
 * ESC/POS cash-drawer "kick" command (`ESC p m t1 t2`) -- pin 2 (m=0), a
 * ~50ms on-pulse and ~500ms off-pulse (t1=25, t2=250, each in 2ms units),
 * the standard values virtually every drawer-equipped thermal printer
 * accepts out of the box. Sent as a raw byte array (not built via a Kotlin
 * string like the text commands above) since every byte here is > 0x7F-safe
 * only for the escape/pin bytes -- 0xFA itself is not valid single-byte
 * UTF-8, so string-encoding this command the same way as the text commands
 * would corrupt it.
 */
val CASH_DRAWER_KICK_BYTES: ByteArray = byteArrayOf(0x1B, 0x70, 0x00, 0x19, 0xFA.toByte())
