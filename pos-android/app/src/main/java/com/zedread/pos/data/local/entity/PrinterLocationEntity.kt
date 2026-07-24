package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity caching a brand's printer locations — fetched via
 * GET /pos/print-config on sync only, never polled (see
 * [com.zedread.pos.data.repository.PrintConfigRepository]). [id] matches the
 * backend's printer_locations.id (same UUID used to link [PrintTemplateEntity]
 * and, locally, [SavedPrinterLocationEntity]).
 */
@Entity(tableName = "printer_locations")
data class PrinterLocationEntity(
    @PrimaryKey val id: String,
    val ref: String,
    val name: String,
    @ColumnInfo(name = "copy_count") val copyCount: Int,
)
