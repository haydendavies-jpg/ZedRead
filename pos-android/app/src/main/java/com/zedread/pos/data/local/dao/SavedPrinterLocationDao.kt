package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.data.local.entity.SavedPrinterLocationEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for which printer locations a saved printer is assigned to (local-only — see SavedPrinterLocationEntity's own doc). */
@Dao
interface SavedPrinterLocationDao {

    @Query("SELECT printer_location_id FROM saved_printer_locations WHERE printer_id = :printerId")
    fun observeLocationIdsForPrinter(printerId: String): Flow<List<String>>

    @Query("DELETE FROM saved_printer_locations WHERE printer_id = :printerId")
    suspend fun clearForPrinter(printerId: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(assignments: List<SavedPrinterLocationEntity>)

    /** Replace one printer's complete set of location assignments — the Printers screen's chip-toggle save action. */
    @Transaction
    suspend fun setForPrinter(printerId: String, locationIds: List<String>) {
        clearForPrinter(printerId)
        insertAll(locationIds.map { SavedPrinterLocationEntity(printerId = printerId, printerLocationId = it) })
    }

    /** Every enabled saved printer assigned to [printerLocationId] — what a completed order docket for that location fans out to. */
    @Query(
        """
        SELECT sp.* FROM saved_printers sp
        INNER JOIN saved_printer_locations spl ON spl.printer_id = sp.id
        WHERE spl.printer_location_id = :printerLocationId AND sp.is_enabled = 1
        """
    )
    suspend fun getEnabledPrintersForLocation(printerLocationId: String): List<SavedPrinterEntity>
}
