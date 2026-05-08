package com.zedread.pos.data.repository

import com.zedread.pos.data.api.AddLineItemRequest
import com.zedread.pos.data.api.CreateInvoiceRequest
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.PaymentRequest
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Manages invoice lifecycle: create, add items, pay. */
@Singleton
class InvoiceRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /** Open a new draft invoice for the active site. */
    suspend fun createInvoice(): InvoiceDto {
        val (bearer, siteId) = requireAuth()
        return api.createInvoice(bearer, CreateInvoiceRequest(siteId = siteId))
    }

    /** Append a product (with optional modifiers) to an open invoice. */
    suspend fun addLineItem(
        invoiceId: String,
        productId: String,
        quantity: Int,
        modifierIds: List<String> = emptyList(),
    ): LineItemDto {
        val (bearer) = requireAuth()
        return api.addLineItem(
            bearer,
            invoiceId,
            AddLineItemRequest(productId, quantity, modifierIds),
        )
    }

    /** Record a payment. For split payments, call this twice with different methods. */
    suspend fun pay(invoiceId: String, method: String, amountCents: Long): InvoiceDto {
        val (bearer) = requireAuth()
        return api.pay(bearer, invoiceId, PaymentRequest(method, amountCents))
    }

    /** Destructure bearer + siteId from DataStore, throwing if either is missing. */
    private suspend fun requireAuth(): Pair<String, String> {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token")
        val siteId = tokenStore.siteId.firstOrNull()
            ?: error("No site ID")
        return "Bearer $token" to siteId
    }
}
