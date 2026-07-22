package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import com.zedread.pos.data.local.entity.OutboxItemEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for the offline write-queue outbox. */
@Dao
interface OutboxDao {

    /** Observe every outbox row (PENDING and FAILED) for the sync panel, oldest first. */
    @Query("SELECT * FROM outbox_items ORDER BY id ASC")
    fun observeAll(): Flow<List<OutboxItemEntity>>

    /** Observe the count of PENDING rows — backs the "N pending" badge, updated the instant a row is enqueued. */
    @Query("SELECT COUNT(*) FROM outbox_items WHERE status = 'PENDING'")
    fun observePendingCount(): Flow<Int>

    /** Rows still due a sync attempt, oldest first — the worker's drain order. */
    @Query("SELECT * FROM outbox_items WHERE status = 'PENDING' ORDER BY id ASC")
    suspend fun getPending(): List<OutboxItemEntity>

    /** PENDING rows of one operation kind — used to check for a queued-but-unsynced register-session event. */
    @Query("SELECT * FROM outbox_items WHERE status = 'PENDING' AND operation = :operation ORDER BY id ASC")
    suspend fun getPendingByOperation(operation: String): List<OutboxItemEntity>

    @Insert
    suspend fun insert(item: OutboxItemEntity): Long

    /** Confirmed synced — the only case a row is ever removed. */
    @Query("DELETE FROM outbox_items WHERE id = :id")
    suspend fun deleteById(id: Long)

    /** Record a transient (network) failure — stays PENDING, retried by WorkManager's backoff. */
    @Query("UPDATE outbox_items SET attempt_count = attempt_count + 1 WHERE id = :id")
    suspend fun recordRetry(id: Long)

    /** Record a definitive server rejection — kept for visibility, excluded from further auto-retry. */
    @Query("UPDATE outbox_items SET status = 'FAILED', attempt_count = attempt_count + 1, last_error = :reason WHERE id = :id")
    suspend fun markFailed(id: Long, reason: String)
}
