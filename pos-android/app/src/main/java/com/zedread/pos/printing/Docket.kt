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
)
