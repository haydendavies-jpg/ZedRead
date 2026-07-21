package com.zedread.pos.data.repository

import com.zedread.pos.data.api.AddLineItemRequest
import com.zedread.pos.data.api.AddModifierRequest
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.LineModifierDto
import com.zedread.pos.data.api.PaymentRequest
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.UpdateLineItemQuantityRequest
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Manages invoice lifecycle: create, add items, attach modifiers, pay. */
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
    suspend fun pay(invoiceId: String, method: String, amountCents: Long, reference: String? = null): InvoiceDto =
        api.pay(requireBearer(), invoiceId, PaymentRequest(method, amountCents, reference))

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}
