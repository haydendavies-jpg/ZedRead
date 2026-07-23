package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for this terminal's saved printers. */
@Dao
interface SavedPrinterDao {

    /** Every saved printer, oldest-added first. */
    @Query("SELECT * FROM saved_printers ORDER BY created_at_millis ASC")
    fun observeAll(): Flow<List<SavedPrinterEntity>>

    /** Only the printers currently toggled on — a print job fans out to each of these. */
    @Query("SELECT * FROM saved_printers WHERE is_enabled = 1 ORDER BY created_at_millis ASC")
    fun observeEnabled(): Flow<List<SavedPrinterEntity>>

    @Query("SELECT * FROM saved_printers WHERE mac_address = :macAddress LIMIT 1")
    suspend fun findByMac(macAddress: String): SavedPrinterEntity?

    @Query("SELECT * FROM saved_printers WHERE id = :id LIMIT 1")
    suspend fun findById(id: String): SavedPrinterEntity?

    /** Insert a newly-saved printer, or replace an existing row sharing its id (mac_address's own unique index is enforced separately — see PrinterRepository.savePrinter). */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(printer: SavedPrinterEntity)

    @Query("UPDATE saved_printers SET is_enabled = :isEnabled WHERE id = :id")
    suspend fun setEnabled(id: String, isEnabled: Boolean)

    /** Patches a saved row's IP by MAC — the stale-IP recovery write path (see PrinterRepository.rediscoverByMac). */
    @Query("UPDATE saved_printers SET last_known_ip = :ip, last_seen_at_millis = :seenAtMillis WHERE mac_address = :macAddress")
    suspend fun updateIpByMac(macAddress: String, ip: String, seenAtMillis: Long)

    @Query("UPDATE saved_printers SET last_connected_at_millis = :atMillis WHERE id = :id")
    suspend fun markConnected(id: String, atMillis: Long)

    @Query("DELETE FROM saved_printers WHERE id = :id")
    suspend fun delete(id: String)
}
