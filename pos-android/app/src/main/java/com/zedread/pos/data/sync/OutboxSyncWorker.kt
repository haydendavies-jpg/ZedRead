package com.zedread.pos.data.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ListenableWorker.Result
import androidx.work.WorkerParameters
import com.squareup.moshi.Moshi
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.dao.OutboxDao
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.data.local.entity.OutboxItemEntity
import com.zedread.pos.data.repository.InvoiceRepository
import com.zedread.pos.data.repository.RegisterSessionRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import retrofit2.HttpException
import java.io.IOException

/**
 * Drains the offline write-queue: replays each PENDING [OutboxItemEntity]
 * as real API calls, oldest first (see the ordering guarantee this relies
 * on in [OutboxOperation]'s doc).
 *
 * Failure handling is split by kind, per ANDROID_POS_BUILD_PLAN.md's "never
 * expiring or discarding an item" requirement:
 *  - A network/IO failure is transient — the row is left PENDING (its
 *    attempt count bumped) and the whole pass stops there, since later rows
 *    may depend on this one having synced. [androidx.work.Result.retry]
 *    lets WorkManager's own backoff schedule the next attempt.
 *  - An HTTP error response is a definitive rejection from the server — the
 *    row is marked FAILED with a plain-language reason and kept (not
 *    deleted) for the sync panel, and the drain continues past it; only
 *    rows that causally depend on it (e.g. a close whose matching open just
 *    failed) fail in turn, each with their own reason.
 */
@HiltWorker
class OutboxSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val outboxDao: OutboxDao,
    private val invoiceCacheDao: InvoiceCacheDao,
    private val invoiceRepo: InvoiceRepository,
    private val registerSessionRepo: RegisterSessionRepository,
    private val moshi: Moshi,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val pending = outboxDao.getPending()
        if (pending.isEmpty()) return Result.success()

        // Resolves an OPEN_REGISTER_SESSION row's own client_ref to the real
        // session id it was just assigned, for a CLOSE row processed later
        // in this same pass (see CloseSessionPayload's doc).
        val openedSessionIds = mutableMapOf<String, String>()
        var hadTransientFailure = false

        for (item in pending) {
            try {
                when (OutboxOperation.valueOf(item.operation)) {
                    OutboxOperation.SYNC_SALE -> syncSale(item)
                    OutboxOperation.OPEN_REGISTER_SESSION -> openedSessionIds[item.clientRef] = syncOpenSession(item)
                    OutboxOperation.CLOSE_REGISTER_SESSION -> syncCloseSession(item, openedSessionIds)
                }
                outboxDao.deleteById(item.id)
            } catch (e: IOException) {
                outboxDao.recordRetry(item.id)
                hadTransientFailure = true
                break
            } catch (e: HttpException) {
                outboxDao.markFailed(item.id, plainLanguageReason(e))
            } catch (e: Exception) {
                outboxDao.markFailed(item.id, e.message ?: "This couldn't be synced for an unknown reason.")
            }
        }

        return if (hadTransientFailure) Result.retry() else Result.success()
    }

    /**
     * Replays a queued sale: create -> each line (+ its modifiers) -> each
     * payment leg in order (zero for a held order, one for a plain sale,
     * two-plus for a split payment), all with the real invoice id from
     * create.
     */
    private suspend fun syncSale(item: OutboxItemEntity) {
        val payload = OutboxPayloads.decodeSale(moshi, item.payloadJson)
        val invoice = invoiceRepo.createInvoice(item.clientRef)
        for (line in payload.lines) {
            val lineItem = invoiceRepo.addLineItem(invoice.id, line.productId, line.quantity)
            for (modifierOptionId in line.modifierOptionIds) {
                invoiceRepo.addLineModifier(invoice.id, lineItem.id, modifierOptionId)
            }
        }
        // Applied after every line lands (so the discount doesn't clamp
        // against an incomplete subtotal) and before any payment leg, so
        // the invoice's server-computed total already reflects it once a
        // payment is recorded against it.
        if (payload.discountCents > 0) {
            invoiceRepo.applyDiscount(invoice.id, payload.discountCents, payload.discountReason)
        }
        // Each leg needs its own idempotency key — payments.client_ref is
        // unique server-side, so reusing item.clientRef across legs of the
        // same sale would collide on the second call. Deterministic (not
        // freshly minted here) so a retried worker pass after a partial
        // failure doesn't double-pay a leg that already landed.
        var current = invoice
        payload.payments.forEachIndexed { index, leg ->
            current = invoiceRepo.pay(invoice.id, leg.method, leg.amountCents, leg.reference, "${item.clientRef}-$index")
        }

        // Re-key the invoice-history cache from the client_ref placeholder to the real synced id.
        invoiceCacheDao.deleteById(item.clientRef)
        invoiceCacheDao.upsert(
            InvoiceCacheEntity(
                id = current.id,
                ref = current.ref,
                status = current.status,
                totalCents = current.totalCents,
                createdAtMillis = System.currentTimeMillis(),
                paymentMethod = payload.payments.lastOrNull()?.method,
                isSynced = true,
            )
        )
    }

    /** Returns the real server session id, for [openedSessionIds]. */
    private suspend fun syncOpenSession(item: OutboxItemEntity): String {
        val payload = OutboxPayloads.decodeOpenSession(moshi, item.payloadJson)
        return registerSessionRepo.openSession(payload.openedAt, payload.openingCashCents, item.clientRef).id
    }

    private suspend fun syncCloseSession(item: OutboxItemEntity, openedSessionIds: Map<String, String>) {
        val payload = OutboxPayloads.decodeCloseSession(moshi, item.payloadJson)
        val sessionId = payload.sessionId
            ?: payload.openClientRef?.let { openedSessionIds[it] }
            ?: error("This till's opening hasn't synced yet — it will retry once that does.")
        registerSessionRepo.closeSession(sessionId, payload.closedAt, payload.closingCashCents, item.clientRef)
    }

    /** Non-technical wording for the sync panel — a cashier reads this, not a developer. */
    private fun plainLanguageReason(e: HttpException): String = when (e.code()) {
        422 -> "The server couldn't confirm this matches what's on file — it may need to be re-entered."
        400 -> "This couldn't be completed — something about it is no longer valid (e.g. the till was already closed)."
        403 -> "This account no longer has permission to complete this action."
        404 -> "The related record could no longer be found."
        409 -> "This conflicts with something already recorded on the server."
        else -> "The server rejected this (error ${e.code()})."
    }
}
