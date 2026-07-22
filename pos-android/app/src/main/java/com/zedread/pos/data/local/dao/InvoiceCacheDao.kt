package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for the local invoice history cache — powers offline invoice search. */
@Dao
interface InvoiceCacheDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(invoice: InvoiceCacheEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(invoices: List<InvoiceCacheEntity>)

    /** Re-key a pending row from its client_ref placeholder id to the real synced server id. */
    @Query("DELETE FROM invoice_cache WHERE id = :clientRefId")
    suspend fun deleteById(clientRefId: String)

    /**
     * Filtered, most-recent-first search over the local cache — works fully offline.
     * Each filter is applied only when its argument is non-null (`:x IS NULL OR ...`).
     */
    @Query(
        """
        SELECT * FROM invoice_cache
        WHERE (:status IS NULL OR status = :status)
          AND (:paymentMethod IS NULL OR payment_method = :paymentMethod)
          AND (:fromMillis IS NULL OR created_at_millis >= :fromMillis)
          AND (:toMillis IS NULL OR created_at_millis <= :toMillis)
        ORDER BY created_at_millis DESC
        """
    )
    fun search(
        status: String?,
        paymentMethod: String?,
        fromMillis: Long?,
        toMillis: Long?,
    ): Flow<List<InvoiceCacheEntity>>

    @Query("DELETE FROM invoice_cache")
    suspend fun clearAll()
}
