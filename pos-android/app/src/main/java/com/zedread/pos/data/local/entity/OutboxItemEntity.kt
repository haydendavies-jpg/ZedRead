package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity for the offline write-queue outbox.
 *
 * One row per complete unit of work the device couldn't sync immediately —
 * a whole sale (invoice + its lines/modifiers + payment, bundled so the
 * worker can replay it as one causally-ordered sequence of API calls
 * without a separate id-resolution table) or one register-session event
 * (open/close). Rows are drained strictly in [id] order (insertion order),
 * which is sufficient to keep a session's open before its close and a
 * sale's create before its pay — the app only ever enqueues in that order
 * in the first place.
 *
 * Never deleted on failure — only on a confirmed successful sync — so a
 * queued sale can never be silently lost; a definitive server rejection
 * (e.g. a checksum mismatch) is recorded via [status]/[lastError] instead
 * of dropping the row, matching the "never expiring or discarding an item"
 * requirement.
 */
@Entity(tableName = "outbox_items")
data class OutboxItemEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    /** [com.zedread.pos.data.sync.OutboxOperation] name. */
    val operation: String,
    /** Client-generated idempotency key sent as `client_ref` to the server. */
    @ColumnInfo(name = "client_ref") val clientRef: String,
    /** Operation-specific payload, JSON-encoded via Moshi — see OutboxModels.kt. */
    @ColumnInfo(name = "payload_json") val payloadJson: String,
    /** PENDING (queued, will retry) or FAILED ([com.zedread.pos.data.sync.OutboxStatus]). */
    val status: String,
    @ColumnInfo(name = "attempt_count") val attemptCount: Int = 0,
    /** Plain-language failure reason for the sync panel — null while PENDING or once synced. */
    @ColumnInfo(name = "last_error") val lastError: String? = null,
    @ColumnInfo(name = "created_at") val createdAtMillis: Long,
)
