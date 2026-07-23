package com.zedread.pos.data.sync

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass
import com.squareup.moshi.Moshi

/**
 * What an [com.zedread.pos.data.local.entity.OutboxItemEntity] row does when drained.
 *
 * A whole sale is one [SYNC_SALE] row (not one row per API call) so the
 * worker can replay it as a single causally-ordered sequence — create, then
 * each line/modifier, then zero or more payment legs — within one
 * `doWork()` pass, using the real invoice id it just got back from `create`
 * for every call after it. That sidesteps needing a separate "local id ->
 * server id" mapping table for a not-yet-synced invoice, at the cost of the
 * sync panel showing one row per sale rather than one per tap — which reads
 * better to a cashier anyway ("Sale — pending" vs five rows per order).
 *
 * This is now the ONLY path a sale is ever created through — not just an
 * offline fallback. Every add-to-cart/Hold/Pay action builds the sale
 * entirely on-device (see SellViewModel); the outbox row is what turns it
 * into a real Invoice, whether that happens within milliseconds (online) or
 * after connectivity returns.
 */
enum class OutboxOperation {
    SYNC_SALE,
    OPEN_REGISTER_SESSION,
    CLOSE_REGISTER_SESSION,
}

/** PENDING rows are retried by [OutboxSyncWorker]; FAILED rows are a definitive rejection, kept for visibility. */
enum class OutboxStatus {
    PENDING,
    FAILED,
}

/** One product line within a queued sale — already resolved to real catalog ids at add-time. */
@JsonClass(generateAdapter = true)
data class OutboxSaleLine(
    @Json(name = "product_id") val productId: String,
    val quantity: Int,
    @Json(name = "modifier_option_ids") val modifierOptionIds: List<String> = emptyList(),
)

/**
 * One payment leg of a queued sale — a plain (non-split) sale has exactly
 * one; a split sale has one per tender the cashier confirmed before the
 * running total was fully covered (see SellViewModel.submitPayment, which
 * accumulates legs locally in [com.zedread.pos.ui.viewmodel.PaymentUiState]
 * and only enqueues the sale once `paidCents` reaches the total).
 */
@JsonClass(generateAdapter = true)
data class SyncPaymentLeg(
    val method: String,
    @Json(name = "amount_cents") val amountCents: Long,
    val reference: String?,
)

/**
 * Payload for a [OutboxOperation.SYNC_SALE] row.
 *
 * [payments] is empty for a **held** order — lines only, no payment yet;
 * the worker leaves the created invoice OPEN rather than calling `pay()` at
 * all (see OutboxSyncWorker.syncSale and SellViewModel.holdOrder). One or
 * more legs means a plain or split sale respectively.
 *
 * No checksum field: `pay_invoice()`'s checksum covers the invoice's
 * server-computed subtotal/tax/total — see app/utils/checksum.py's
 * `_build_invoice_checksum_payload`. This device computes its own running
 * total locally (see LocalTaxCalculator) to mirror the backend, but still
 * doesn't send it as a checksum — a mismatch here must never block a sale
 * from syncing, only be caught by other means (e.g. reconciliation
 * reporting), so `client_ref` alone (always sent) is what makes a retried
 * sync safe to replay; the checksum field is optional and skipped
 * server-side when absent, which is exactly the intended escape hatch.
 */
@JsonClass(generateAdapter = true)
data class SyncSalePayload(
    val lines: List<OutboxSaleLine>,
    val payments: List<SyncPaymentLeg> = emptyList(),
    // A manual discount applied at the Register before Hold/Pay (see
    // SellViewModel's Discount button) — applied server-side after the
    // lines are added and before any payment leg, so the payment total the
    // worker submits already reflects it.
    @Json(name = "discount_cents") val discountCents: Long = 0,
    @Json(name = "discount_reason") val discountReason: String? = null,
)

/**
 * Payload for a [OutboxOperation.OPEN_REGISTER_SESSION] row.
 *
 * Also checksum-less, for a different reason than the sale payload above:
 * the backend's open-session checksum is keyed in part by `device.id` —
 * the PosDevice's own server-side UUID — which is never returned to the
 * client (only the opaque `device_token` is). There is no way to source
 * that value on-device without a new backend field, which is out of scope
 * for this slice — flagged in ANDROID_POS_BUILD_PLAN.md rather than
 * guessed at.
 */
@JsonClass(generateAdapter = true)
data class OpenSessionPayload(
    @Json(name = "opened_at") val openedAt: String,
    @Json(name = "opening_cash_cents") val openingCashCents: Long,
)

/**
 * Payload for a [OutboxOperation.CLOSE_REGISTER_SESSION] row.
 *
 * [sessionId] is the real server id when the session that's being closed
 * was opened online; [openClientRef] is set instead when the open itself
 * is still queued (or was queued earlier in the same offline stretch) —
 * the worker resolves it to a real id from the OPEN row it processes
 * earlier in the same drain pass (rows are strictly FIFO), since the app
 * only ever enqueues a close after its matching open.
 */
@JsonClass(generateAdapter = true)
data class CloseSessionPayload(
    @Json(name = "session_id") val sessionId: String?,
    @Json(name = "open_client_ref") val openClientRef: String?,
    @Json(name = "closed_at") val closedAt: String,
    @Json(name = "closing_cash_cents") val closingCashCents: Long,
)

/** Moshi (de)serialization helpers for outbox payloads — kept in one place rather than repeated at each call site. */
object OutboxPayloads {
    fun encodeSale(moshi: Moshi, payload: SyncSalePayload): String =
        moshi.adapter(SyncSalePayload::class.java).toJson(payload)

    fun decodeSale(moshi: Moshi, json: String): SyncSalePayload =
        moshi.adapter(SyncSalePayload::class.java).fromJson(json)
            ?: error("Malformed SyncSalePayload in outbox")

    fun encodeOpenSession(moshi: Moshi, payload: OpenSessionPayload): String =
        moshi.adapter(OpenSessionPayload::class.java).toJson(payload)

    fun decodeOpenSession(moshi: Moshi, json: String): OpenSessionPayload =
        moshi.adapter(OpenSessionPayload::class.java).fromJson(json)
            ?: error("Malformed OpenSessionPayload in outbox")

    fun encodeCloseSession(moshi: Moshi, payload: CloseSessionPayload): String =
        moshi.adapter(CloseSessionPayload::class.java).toJson(payload)

    fun decodeCloseSession(moshi: Moshi, json: String): CloseSessionPayload =
        moshi.adapter(CloseSessionPayload::class.java).fromJson(json)
            ?: error("Malformed CloseSessionPayload in outbox")
}
