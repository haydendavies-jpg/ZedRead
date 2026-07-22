package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity caching invoice history for offline search.
 *
 * [id] is the real server invoice id once synced, or the sale's own
 * `client_ref` while it's still queued in the outbox — so a pending sale
 * appears in search immediately (see [isSynced]) and is re-keyed to its
 * real id once [com.zedread.pos.data.sync.OutboxSyncWorker] confirms it
 * (upsert with the real id, delete of the client_ref-keyed row).
 * [paymentMethod] is only known for sales rung up on this device (recorded
 * at pay time); rows backfilled from `GET /invoices` for other devices'
 * sales leave it null — a known gap, see ANDROID_POS_BUILD_PLAN.md.
 */
@Entity(tableName = "invoice_cache")
data class InvoiceCacheEntity(
    @PrimaryKey val id: String,
    val status: String,
    @ColumnInfo(name = "total_cents") val totalCents: Long,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
    @ColumnInfo(name = "payment_method") val paymentMethod: String?,
    @ColumnInfo(name = "is_synced") val isSynced: Boolean,
)
