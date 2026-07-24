package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity caching one print template — its elements are stored as a JSON
 * blob ([elementsJson], decoded via [com.zedread.pos.printing.TemplateDocketRenderer]'s
 * own Moshi adapter to `List<com.zedread.pos.data.api.PosPrintTemplateElementDto>`),
 * same "not worth normalizing a re-derivable cache" call as
 * [ProductModifierCacheEntity]. [templateType] is one of 'invoice' | 'docket' |
 * 'register_summary' | 'cash_in_slip'; [printerLocationId] is set only for a
 * 'docket' template and matches a [PrinterLocationEntity.id].
 */
@Entity(tableName = "print_templates")
data class PrintTemplateEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "template_type") val templateType: String,
    @ColumnInfo(name = "printer_location_id") val printerLocationId: String?,
    val name: String,
    @ColumnInfo(name = "elements_json") val elementsJson: String,
)
