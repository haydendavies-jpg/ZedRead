package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.PrinterLocationEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for cached printer locations (see PrintConfigRepository.refresh). */
@Dao
interface PrinterLocationDao {

    @Query("SELECT * FROM printer_locations ORDER BY name ASC")
    fun observeAll(): Flow<List<PrinterLocationEntity>>

    @Query("SELECT * FROM printer_locations ORDER BY name ASC")
    suspend fun getAll(): List<PrinterLocationEntity>

    /** Replace the entire cache after a successful network fetch. */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun replaceAll(locations: List<PrinterLocationEntity>)

    /** Wipe the cache (called on logout). */
    @Query("DELETE FROM printer_locations")
    suspend fun clearAll()
}
