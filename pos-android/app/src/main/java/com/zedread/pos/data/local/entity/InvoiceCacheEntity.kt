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
 * [paymentMethod] is a comma-joined list for a split sale (e.g. "cash,
 * card") — for a sale rung up on this device it's recorded at pay time
 * (currently only the LAST leg — a known gap, see
 * ANDROID_POS_BUILD_PLAN.md); rows backfilled from `GET /invoices` for
 * other devices' sales now resolve every distinct method via
 * InvoiceDto.paymentMethods (previously always null — see
 * InvoiceRepository.refreshCacheFromServer's doc).
 */
@Entity(tableName = "invoice_cache")
data class InvoiceCacheEntity(
    @PrimaryKey val id: String,
    // Human-readable INV-000001-style reference — what a cashier actually
    // searches by; the raw id is a UUID and was never a real "invoice number".
    val ref: String,
    val status: String,
    @ColumnInfo(name = "total_cents") val totalCents: Long,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
    @ColumnInfo(name = "payment_method") val paymentMethod: String?,
    @ColumnInfo(name = "is_synced") val isSynced: Boolean,
    // Whether this invoice already has a refund against it — a paid, not-yet-
    // refunded invoice is the only kind the Refund action offers. Defaults
    // false so every pre-existing InvoiceCacheEntity(...) call site (sales
    // recorded locally at pay time, which are never already refunded) still
    // compiles unchanged.
    @ColumnInfo(name = "is_refunded", defaultValue = "0") val isRefunded: Boolean = false,
)
