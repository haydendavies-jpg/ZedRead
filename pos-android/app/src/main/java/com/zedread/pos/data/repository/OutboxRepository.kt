package com.zedread.pos.data.repository

import android.content.Context
import com.squareup.moshi.Moshi
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.dao.OutboxDao
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.data.local.entity.OutboxItemEntity
import com.zedread.pos.data.sync.CloseSessionPayload
import com.zedread.pos.data.sync.OpenSessionPayload
import com.zedread.pos.data.sync.OutboxOperation
import com.zedread.pos.data.sync.OutboxPayloads
import com.zedread.pos.data.sync.OutboxScheduler
import com.zedread.pos.data.sync.OutboxSaleLine
import com.zedread.pos.data.sync.OutboxStatus
import com.zedread.pos.data.sync.SyncSalePayload
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The offline write-queue's single entry point: enqueues sales and
 * register-session events a caller couldn't sync immediately, exposes the
 * queue for the sync-status badge/panel, and kicks an immediate drain
 * attempt (the periodic WorkManager job is the fallback, not the primary
 * trigger — see [OutboxScheduler]).
 */
@Singleton
class OutboxRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val outboxDao: OutboxDao,
    private val invoiceCacheDao: InvoiceCacheDao,
    private val moshi: Moshi,
) {
    /** Every outbox row (PENDING and FAILED), oldest first — the sync panel's list. */
    fun observeItems(): Flow<List<OutboxItemEntity>> = outboxDao.observeAll()

    /** Count of rows still awaiting a successful sync — the "N pending" badge, live from the instant of enqueue. */
    fun observePendingCount(): Flow<Int> = outboxDao.observePendingCount()

    /**
     * Queue a completed sale for background sync and reflect it in the local
     * invoice-history cache immediately (keyed by [clientRef] until the
     * worker re-keys it to the real invoice id) so it shows up in Invoice
     * Search as "pending" right away — not after the eventual round trip.
     *
     * Returns the minted [clientRef] so the caller can show it to the user
     * if needed (e.g. a receipt reference for an unsynced sale).
     */
    suspend fun enqueueSale(
        lines: List<OutboxSaleLine>,
        method: String,
        amountCents: Long,
        reference: String?,
    ): String {
        val clientRef = UUID.randomUUID().toString()
        val payload = SyncSalePayload(lines, method, amountCents, reference)
        outboxDao.insert(
            OutboxItemEntity(
                operation = OutboxOperation.SYNC_SALE.name,
                clientRef = clientRef,
                payloadJson = OutboxPayloads.encodeSale(moshi, payload),
                status = OutboxStatus.PENDING.name,
                createdAtMillis = System.currentTimeMillis(),
            )
        )
        invoiceCacheDao.upsert(
            InvoiceCacheEntity(
                id = clientRef,
                status = "paid",
                totalCents = amountCents,
                createdAtMillis = System.currentTimeMillis(),
                paymentMethod = method,
                isSynced = false,
            )
        )
        OutboxScheduler.requestImmediateSync(context)
        return clientRef
    }

    /** Queue a start-of-day cash-in that couldn't be opened online. Returns the minted client_ref. */
    suspend fun enqueueOpenSession(openedAtIso: String, openingCashCents: Long): String {
        val clientRef = UUID.randomUUID().toString()
        outboxDao.insert(
            OutboxItemEntity(
                operation = OutboxOperation.OPEN_REGISTER_SESSION.name,
                clientRef = clientRef,
                payloadJson = OutboxPayloads.encodeOpenSession(moshi, OpenSessionPayload(openedAtIso, openingCashCents)),
                status = OutboxStatus.PENDING.name,
                createdAtMillis = System.currentTimeMillis(),
            )
        )
        OutboxScheduler.requestImmediateSync(context)
        return clientRef
    }

    /**
     * Queue an end-of-day cash-up that couldn't be closed online.
     *
     * [sessionId] is the real server id if the session was opened online;
     * pass [openClientRef] instead (the client_ref this repository minted
     * for the matching [enqueueOpenSession] call) when the open itself is
     * still queued — the worker resolves it once that row syncs.
     */
    suspend fun enqueueCloseSession(
        sessionId: String?,
        openClientRef: String?,
        closedAtIso: String,
        closingCashCents: Long,
    ): String {
        val clientRef = UUID.randomUUID().toString()
        val payload = CloseSessionPayload(sessionId, openClientRef, closedAtIso, closingCashCents)
        outboxDao.insert(
            OutboxItemEntity(
                operation = OutboxOperation.CLOSE_REGISTER_SESSION.name,
                clientRef = clientRef,
                payloadJson = OutboxPayloads.encodeCloseSession(moshi, payload),
                status = OutboxStatus.PENDING.name,
                createdAtMillis = System.currentTimeMillis(),
            )
        )
        OutboxScheduler.requestImmediateSync(context)
        return clientRef
    }

    /** The sync panel's manual "Sync now" action — forces an immediate drain attempt regardless of backoff timing. */
    fun syncNow() { OutboxScheduler.requestImmediateSync(context) }

    /**
     * Find a queued start-of-day open with no matching queued close yet —
     * i.e. the till this device believes is currently open, even though
     * the server has no record of it. Used by [RegisterSessionViewModel]
     * so the register gate and cash-up screens don't block on a round trip
     * that isn't happening while offline.
     */
    suspend fun latestQueuedOpenSessionWithoutClose(): QueuedOpenSession? {
        val opens = outboxDao.getPendingByOperation(OutboxOperation.OPEN_REGISTER_SESSION.name)
        if (opens.isEmpty()) return null
        val closes = outboxDao.getPendingByOperation(OutboxOperation.CLOSE_REGISTER_SESSION.name)
        val closedOpenRefs = closes
            .mapNotNull { OutboxPayloads.decodeCloseSession(moshi, it.payloadJson).openClientRef }
            .toSet()
        val open = opens.lastOrNull { it.clientRef !in closedOpenRefs } ?: return null
        val payload = OutboxPayloads.decodeOpenSession(moshi, open.payloadJson)
        return QueuedOpenSession(open.clientRef, payload.openingCashCents, payload.openedAt)
    }
}

/** A start-of-day open queued but not yet confirmed by the server. */
data class QueuedOpenSession(val clientRef: String, val openingCashCents: Long, val openedAtIso: String)
