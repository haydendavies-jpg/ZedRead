package com.zedread.pos.data.repository

import com.zedread.pos.data.api.AddLineItemRequest
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.PaymentRequest
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.UpdateLineItemQuantityRequest
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
    /** Open a new draft invoice — site/brand/register-session resolve server-side from the token. */
    suspend fun createInvoice(): InvoiceDto = api.createInvoice(requireBearer())

    /** Append a product to an open invoice. */
    suspend fun addLineItem(invoiceId: String, productId: String, quantity: Int): LineItemDto =
        api.addLineItem(requireBearer(), invoiceId, AddLineItemRequest(productId, quantity))

    /** Change a line item's quantity — the Register screen's qty stepper. */
    suspend fun updateLineItemQuantity(invoiceId: String, lineItemId: String, quantity: Int): LineItemDto =
        api.updateLineItemQuantity(requireBearer(), invoiceId, lineItemId, UpdateLineItemQuantityRequest(quantity))

    /** Remove a line item from the order. */
    suspend fun removeLineItem(invoiceId: String, lineItemId: String) {
        api.removeLineItem(requireBearer(), invoiceId, lineItemId)
    }

    /** Record a payment. For split payments, call this twice with different methods. */
    suspend fun pay(invoiceId: String, method: String, amountCents: Long): InvoiceDto =
        api.pay(requireBearer(), invoiceId, PaymentRequest(method, amountCents))

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}
