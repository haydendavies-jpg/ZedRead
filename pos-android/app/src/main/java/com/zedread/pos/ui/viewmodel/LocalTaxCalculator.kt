package com.zedread.pos.ui.viewmodel

import com.zedread.pos.data.local.entity.ProductEntity

/** Unit price, subtotal, and tax for one line — see [computeLocalLineTax]. */
data class LocalLineTax(val unitPriceCents: Long, val subtotalCents: Long, val taxCents: Long)

/**
 * Computes a line item's tax entirely on-device, mirroring
 * `invoice_service.add_line_item()` on the backend exactly — that route
 * does NOT run the general TaxRate/TaxCategory engine per sale; each
 * product already stores a tax-inclusive price (`base_price_cents`) and a
 * derived tax-exclusive price (`price_ex_cents`, computed at save time from
 * the brand's country rate), and `is_taxable` picks which one is charged:
 *
 * - Taxable: charge the inclusive price; tax = (inclusive − exclusive) × qty
 *   (the GST already embedded in the price, extracted rather than added).
 * - Not taxable: charge the exclusive price; no tax.
 *
 * Because both prices are snapshotted on the product row itself, this needs
 * no separate tax-rate sync — [ProductEntity.priceExCents]/[ProductEntity.isTaxable]
 * (already part of the ordinary catalog cache) are the only inputs. This is
 * what lets the Register show a correct running total while building the
 * cart entirely locally, with no per-item network round trip.
 */
fun computeLocalLineTax(product: ProductEntity, quantity: Int): LocalLineTax {
    return if (product.isTaxable) {
        val unitPriceCents = product.basePriceCents
        val subtotalCents = unitPriceCents * quantity
        val taxCents = (product.basePriceCents - product.priceExCents) * quantity
        LocalLineTax(unitPriceCents, subtotalCents, taxCents)
    } else {
        val unitPriceCents = product.priceExCents
        LocalLineTax(unitPriceCents, unitPriceCents * quantity, 0L)
    }
}
