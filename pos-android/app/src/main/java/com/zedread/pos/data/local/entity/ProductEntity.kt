package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/** Room entity caching a site-resolved product for offline catalog display. */
@Entity(tableName = "products")
data class ProductEntity(
    @PrimaryKey val id: String,
    // Matches a menu_buttons.product_ref value — lets the menu selector filter this cache by layout.
    val ref: String,
    @ColumnInfo(name = "category_id") val categoryId: String,
    val name: String,
    val description: String?,
    @ColumnInfo(name = "base_price_cents") val basePriceCents: Long,
    // Tax-exclusive price and taxability — cached so the Register can compute
    // a line's tax on-device (see LocalTaxCalculator), mirroring
    // invoice_service.add_line_item()'s own formula exactly, instead of
    // needing a live add-line-item round trip to know the correct total.
    @ColumnInfo(name = "price_ex_cents") val priceExCents: Long,
    @ColumnInfo(name = "is_taxable") val isTaxable: Boolean,
    @ColumnInfo(name = "photo_url") val photoUrl: String?,
    @ColumnInfo(name = "display_order") val displayOrder: Int,
    @ColumnInfo(name = "is_active") val isActive: Boolean,
    // Long-press product popup: greys the tile out with "SOLD OUT" written
    // over it and blocks adding it to an order until toggled off again.
    @ColumnInfo(name = "is_sold_out") val isSoldOut: Boolean,
    @ColumnInfo(name = "category_color") val categoryColor: String,
    @ColumnInfo(name = "modifier_names") val modifierNames: String?,
    // Which order-docket print station this product groups under — null means
    // it prints on no docket. Carried onto LineItemDto at add-to-cart time so
    // SellViewModel's docket coordinator can group a cart by location without
    // a separate lookup — see LineItemDto.printerLocationId's own doc.
    @ColumnInfo(name = "printer_location_id") val printerLocationId: String?,
)
