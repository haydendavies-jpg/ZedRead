package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

/**
 * Which printer locations a saved printer has been assigned to print — local
 * to this terminal only, same as [SavedPrinterEntity] itself (a multi-printer
 * site may have different registers seeing different printers on their own
 * LAN segment). More than one saved printer may share a location (e.g. two
 * kitchen printers both printing the Kitchen docket), and one printer may be
 * assigned more than one location.
 *
 * [printerLocationId] matches a synced [PrinterLocationEntity.id] — not
 * enforced as a Room foreign key (that table is a wipeable cache refreshed on
 * every sync, so a stale reference would otherwise cascade-delete a live
 * assignment on the next print-config refresh); [printerId] IS a real FK back
 * to [SavedPrinterEntity], cascading on delete so removing a saved printer
 * cleans up its assignments too.
 */
@Entity(
    tableName = "saved_printer_locations",
    primaryKeys = ["printer_id", "printer_location_id"],
    foreignKeys = [
        ForeignKey(
            entity = SavedPrinterEntity::class,
            parentColumns = ["id"],
            childColumns = ["printer_id"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("printer_id"), Index("printer_location_id")],
)
data class SavedPrinterLocationEntity(
    @ColumnInfo(name = "printer_id") val printerId: String,
    @ColumnInfo(name = "printer_location_id") val printerLocationId: String,
)
