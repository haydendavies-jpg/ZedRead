package com.zedread.pos.printing

import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.PosPrintTemplateElementDto
import com.zedread.pos.data.local.entity.CompanyProfileCacheEntity
import com.zedread.pos.data.local.entity.PrintTemplateEntity
import com.zedread.pos.data.repository.PrintConfigRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Context data a template's fields render from — not every field is
 * populated for every template type (e.g. [lineItems] is empty for a
 * register-summary render), matching which field_keys are actually valid
 * for that template_type/section server-side (app/constants/print_fields.py).
 */
data class DocketRenderContext(
    val companyProfile: CompanyProfileCacheEntity?,
    val lineItems: List<LineItemDto> = emptyList(),
    val servedBy: String = "",
    val invoiceRef: String = "",
    // Order/item free-text notes -- not yet implemented in the POS cart (no
    // UI to enter them), so these are always blank today. Flagged, not
    // silently dropped -- see the project's own "flag rather than assume
    // it's covered" convention.
    val orderNotes: String = "",
    val dateTime: String = "",
    val openingCashCents: Long = 0,
    val closingCashCents: Long? = null,
    val varianceCents: Long? = null,
    val paymentBreakdownCents: Map<String, Long> = emptyMap(),
    val countedBy: String = "",
)

/**
 * Renders a [PrintTemplateEntity]'s elements into a driver-neutral
 * [RenderedLine] list, using the SAME field-by-field alignment/padding logic
 * (see [PrintLineLayout.kt]) as the portal's live preview -- so what a
 * manager designed in the editor is what actually comes out of the printer.
 * Replaces [DocketFormatter]'s single hardcoded layout as the one rendering
 * path both the generic ESC/POS drivers and the Epson driver read from (via
 * [Docket.renderedLines] -- see that class's own doc).
 */
@Singleton
class TemplateDocketRenderer @Inject constructor(
    private val printConfigRepo: PrintConfigRepository,
) {
    /** Render the docket template for one printer location, or null if that location has none cached yet. */
    suspend fun renderDocketForLocation(printerLocationId: String, ctx: DocketRenderContext): List<RenderedLine>? {
        val template = printConfigRepo.getDocketForLocation(printerLocationId) ?: return null
        return render(template, ctx)
    }

    /** Render one of the three brand-wide singleton templates ('invoice' | 'register_summary' | 'cash_in_slip'), or null if not cached yet. */
    suspend fun renderByType(templateType: String, ctx: DocketRenderContext): List<RenderedLine>? {
        val template = printConfigRepo.getTemplateByType(templateType) ?: return null
        return render(template, ctx)
    }

    private fun render(template: PrintTemplateEntity, ctx: DocketRenderContext): List<RenderedLine> {
        val elements = printConfigRepo.decodeElements(template.elementsJson)
            .sortedWith(compareBy({ SECTION_ORDER[it.section] ?: Int.MAX_VALUE }, { it.displayOrder }))
        val lines = mutableListOf<RenderedLine>()

        for (el in elements) {
            when (el.fieldKey) {
                "DIVIDER" -> lines += RenderedLine(dividerLine(PRINT_LINE_WIDTH), el.isBold, el.isItalic)
                "FREE_TEXT" -> lines += simpleLine(el.freeTextValue ?: "", el)
                "LOGO" -> {
                    // No raster-image support on the raw ESC/POS text path yet
                    // (would need GS v 0 bitmap commands + downloading/
                    // dithering the logo image) -- flagged gap, silently
                    // skipped rather than printing anything wrong.
                }
                "BRAND_NAME" -> lines += simpleLine(ctx.companyProfile?.brandName ?: "", el)
                "STORE_NAME" -> lines += simpleLine(ctx.companyProfile?.storeName ?: "", el)
                "ADDRESS" -> lines += simpleLine(ctx.companyProfile?.address ?: "", el)
                "STORE_PHONE" -> lines += simpleLine(ctx.companyProfile?.phone ?: "", el)
                "ABN" -> lines += simpleLine(ctx.companyProfile?.abn ?: "", el)
                "DATE_TIME" -> lines += simpleLine(ctx.dateTime, el)
                "INVOICE_NUMBER" -> lines += simpleLine(ctx.invoiceRef, el)
                "SERVED_BY" -> lines += simpleLine("Served by: ${ctx.servedBy}", el)
                "ORDER_NOTES" -> if (ctx.orderNotes.isNotBlank()) lines += simpleLine(ctx.orderNotes, el)
                "PRODUCT_LINE" -> ctx.lineItems.forEach { item ->
                    lines += RenderedLine(
                        threeColumnLine(item.productName, "x${item.quantity}", formatCentsForPrint(item.subtotalCents), PRINT_LINE_WIDTH),
                        el.isBold,
                        el.isItalic,
                    )
                }
                "MODIFIER_LINE" -> ctx.lineItems.forEach { item ->
                    item.modifiers.forEach { modifier ->
                        lines += simpleLine("+ ${modifier.modifierName}", el)
                    }
                }
                "ITEM_NOTES" -> {
                    // Item-level free-text notes -- not yet implemented in the
                    // POS cart, same flagged gap as ORDER_NOTES above.
                }
                "PAYMENT_METHOD_BREAKDOWN" -> ctx.paymentBreakdownCents.forEach { (method, cents) ->
                    lines += RenderedLine(
                        threeColumnLine(method.replaceFirstChar { it.uppercase() }, "", formatCentsForPrint(cents), PRINT_LINE_WIDTH),
                        el.isBold,
                        el.isItalic,
                    )
                }
                "CASH_VARIANCE" -> ctx.varianceCents?.let {
                    lines += RenderedLine(threeColumnLine("Variance", "", formatCentsForPrint(it), PRINT_LINE_WIDTH), el.isBold, el.isItalic)
                }
                "OPENING_CLOSING_CASH" -> {
                    lines += RenderedLine(threeColumnLine("Opening", "", formatCentsForPrint(ctx.openingCashCents), PRINT_LINE_WIDTH), el.isBold, el.isItalic)
                    ctx.closingCashCents?.let {
                        lines += RenderedLine(threeColumnLine("Closing", "", formatCentsForPrint(it), PRINT_LINE_WIDTH), el.isBold, el.isItalic)
                    }
                }
                "CASH_IN_AMOUNT" -> lines += RenderedLine(
                    threeColumnLine("Cash in", "", formatCentsForPrint(ctx.openingCashCents), PRINT_LINE_WIDTH),
                    el.isBold,
                    el.isItalic,
                )
                "COUNTED_BY" -> lines += simpleLine("Counted by: ${ctx.countedBy}", el)
                else -> {} // Unknown/future field_key -- render nothing rather than guess.
            }
        }
        return lines
    }

    private fun simpleLine(text: String, el: PosPrintTemplateElementDto): RenderedLine =
        RenderedLine(alignText(text, PRINT_LINE_WIDTH, el.alignment), el.isBold, el.isItalic)

    companion object {
        private val SECTION_ORDER = mapOf("header" to 0, "items" to 1, "footer" to 2)
    }
}
