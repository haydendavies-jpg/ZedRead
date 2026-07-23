package com.zedread.pos.data.repository

import com.zedread.pos.data.api.AddLineItemRequest
import com.zedread.pos.data.api.AddModifierRequest
import com.zedread.pos.data.api.ApplyDiscountRequest
import com.zedread.pos.data.api.InvoiceCreateBody
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.LineModifierDto
import com.zedread.pos.data.api.PaymentRequest
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.UpdateLineItemQuantityRequest
import com.zedread.pos.data.local.TokenStore
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

/** Manages invoice lifecycle: create, add items, attach modifiers, pay. */
@Singleton
class InvoiceRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
    private val invoiceCacheDao: InvoiceCacheDao,
) {
    /**
     * Open a new draft invoice — site/brand/register-session resolve
     * server-side from the token. [clientRef], when supplied, dedupes a
     * retried create against the outbox sync worker's own idempotency key.
     */
    suspend fun createInvoice(clientRef: String? = null): InvoiceDto =
        api.createInvoice(requireBearer(), InvoiceCreateBody(clientRef))

    /** This site's invoice history, most recent first — backfills the local search cache. [status], when supplied, filters (e.g. "open" for Held Orders). */
    suspend fun listInvoices(skip: Int = 0, limit: Int = 200, status: String? = null): List<InvoiceDto> =
        api.listInvoices(requireBearer(), skip, limit, status)

    /** Every line item on an invoice, with modifiers — reconstructs a held order's cart on recall. */
    suspend fun getLineItems(invoiceId: String): List<LineItemDto> =
        api.getInvoiceLineItems(requireBearer(), invoiceId)

    /** A single invoice's header — used alongside [getLineItems] on Held Orders recall to restore any discount already applied before the order was held. */
    suspend fun getInvoice(invoiceId: String): InvoiceDto =
        api.getInvoice(requireBearer(), invoiceId)

    /** Append a product to an open invoice. */
    suspend fun addLineItem(invoiceId: String, productId: String, quantity: Int): LineItemDto =
        api.addLineItem(requireBearer(), invoiceId, AddLineItemRequest(productId, quantity))

    /** Change a line item's quantity — the Register screen's qty stepper. */
    suspend fun updateLineItemQuantity(invoiceId: String, lineItemId: String, quantity: Int): LineItemDto =
        api.updateLineItemQuantity(requireBearer(), invoiceId, lineItemId, UpdateLineItemQuantityRequest(quantity))

    /** Fetch a line item with its attached modifiers — refreshes display state after [addLineModifier] calls. */
    suspend fun getLineItem(invoiceId: String, lineItemId: String): LineItemDto =
        api.getLineItem(requireBearer(), invoiceId, lineItemId)

    /** Attach a modifier option to a line item — the modifier customise sheet's per-selection call. */
    suspend fun addLineModifier(invoiceId: String, lineItemId: String, modifierOptionId: String): LineModifierDto =
        api.addLineItemModifier(requireBearer(), invoiceId, lineItemId, AddModifierRequest(modifierOptionId))

    /** Remove a line item from the order. */
    suspend fun removeLineItem(invoiceId: String, lineItemId: String) {
        api.removeLineItem(requireBearer(), invoiceId, lineItemId)
    }

    /**
     * Record a payment or one leg of a split payment.
     *
     * [reference] carries a voucher's redemption code (voucher method only —
     * null for cash/card). The response's status is only "paid" once the sum
     * of all payments recorded against the invoice covers its total — see
     * pay_invoice()'s split-payment handling.
     */
    suspend fun pay(
        invoiceId: String,
        method: String,
        amountCents: Long,
        reference: String? = null,
        clientRef: String? = null,
    ): InvoiceDto =
        api.pay(requireBearer(), invoiceId, PaymentRequest(method, amountCents, reference, clientRef))

    /** Apply a manual discount to an invoice before it's paid — the Register's Discount button. */
    suspend fun applyDiscount(invoiceId: String, discountCents: Long, reason: String? = null): InvoiceDto =
        api.applyDiscount(requireBearer(), invoiceId, ApplyDiscountRequest(discountCents, reason))

    // ── Invoice search cache (Android POS Phase 2) ──────────────────────────

    /** Filtered, most-recent-first search over the local invoice-history cache — works fully offline. */
    fun searchCache(
        status: String?,
        paymentMethod: String?,
        fromMillis: Long?,
        toMillis: Long?,
        refQuery: String?,
    ): Flow<List<InvoiceCacheEntity>> = invoiceCacheDao.search(status, paymentMethod, fromMillis, toMillis, refQuery)

    /**
     * Backfill the local cache from `GET /invoices` — other devices' sales,
     * and this device's own sales made before this cache existed. Silently
     * a no-op offline (caller decides whether to surface the failure);
     * doesn't touch rows still pending in the outbox (a different id space
     * — the client_ref placeholder — so there's no collision to worry about).
     */
    suspend fun refreshCacheFromServer() {
        val remote = listInvoices()
        invoiceCacheDao.upsertAll(
            remote.map { dto ->
                InvoiceCacheEntity(
                    id = dto.id,
                    ref = dto.ref,
                    status = dto.status,
                    totalCents = dto.totalCents,
                    createdAtMillis = dto.createdAt?.let { OffsetDateTime.parse(it).toInstant().toEpochMilli() }
                        ?: System.currentTimeMillis(),
                    // Payment method isn't returned by GET /invoices (per-invoice, not
                    // per-payment) — only known for sales rung up on this device, see
                    // InvoiceCacheEntity's doc.
                    paymentMethod = null,
                    isSynced = true,
                )
            }
        )
    }

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}
