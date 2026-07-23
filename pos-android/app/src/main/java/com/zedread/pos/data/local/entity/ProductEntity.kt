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
    @ColumnInfo(name = "photo_url") val photoUrl: String?,
    @ColumnInfo(name = "display_order") val displayOrder: Int,
    @ColumnInfo(name = "is_active") val isActive: Boolean,
    // Long-press product popup: greys the tile out with "SOLD OUT" written
    // over it and blocks adding it to an order until toggled off again.
    @ColumnInfo(name = "is_sold_out") val isSoldOut: Boolean,
    @ColumnInfo(name = "category_color") val categoryColor: String,
    @ColumnInfo(name = "modifier_names") val modifierNames: String?,
)
