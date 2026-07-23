package com.zedread.pos.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity caching a product's modifier-group definitions as a JSON blob
 * (the nested groups → options → linked-groups shape doesn't fit a flat
 * table without several join tables, and this cache is re-derivable from
 * the server at any time — same "not worth normalizing" call as
 * [com.zedread.pos.data.local.entity.InvoiceCacheEntity]'s own doc).
 *
 * User-testing feedback: opening the customise sheet for a product with
 * modifiers always hit the network first, showing a visible load on every
 * tap — this cache makes the second-and-later tap for the same product
 * instant. [json] decodes to `List<ProductModifierGroupDto>` via
 * CatalogRepository's own Moshi adapter.
 */
@Entity(tableName = "product_modifier_cache")
data class ProductModifierCacheEntity(
    @PrimaryKey val productId: String,
    val json: String,
)
