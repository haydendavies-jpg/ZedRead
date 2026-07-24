package com.zedread.pos.printing

import com.zedread.pos.data.api.LineItemDto

/**
 * A completed sale in the shape every [com.zedread.pos.printing.driver.PrinterDriver]
 * renders for its own printer, rather than a shared raw byte array.
 *
 * [DocketFormatter] (the raw ESC/POS path used by the generic drivers) turns
 * this into a `ByteArray`; the Epson driver instead reads these fields
 * directly into its own `Printer` builder calls
 * (`addText`/`addFeedLine`/`addCut`) — its SDK has no supported way to accept
 * pre-built ESC/POS bytes, so this is the one neutral input both paths share.
 */
data class Docket(
    val invoiceId: String,
    val siteName: String,
    val lineItems: List<LineItemDto>,
    val totalCents: Long,
    val paymentMethod: String,
    // Pre-rendered from a customisable print template (see
    // TemplateDocketRenderer) -- the driver-neutral shape both the generic
    // ESC/POS drivers (via renderedLinesToEscPosBytes) and the Epson driver
    // (iterated into its own addText/addTextStyle calls) consume. Null only
    // for PrintersViewModel's own "Test print" action, which has no template
    // context to render from and falls back to DocketFormatter's fixed layout.
    val renderedLines: List<RenderedLine>? = null,
)
