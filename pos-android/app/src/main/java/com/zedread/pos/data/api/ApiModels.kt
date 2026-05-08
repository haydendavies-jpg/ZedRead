package com.zedread.pos.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/** POST /auth/pos/login request body. */
@JsonClass(generateAdapter = true)
data class LoginRequest(
    val email: String,
    val password: String,
)

/** POST /auth/pos/login response — site list included for site selection. */
@JsonClass(generateAdapter = true)
data class LoginResponse(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "refresh_token") val refreshToken: String,
    val sites: List<SiteDto>,
)

@JsonClass(generateAdapter = true)
data class SiteDto(
    val id: String,
    val name: String,
    @Json(name = "brand_id") val brandId: String,
    @Json(name = "is_active") val isActive: Boolean,
)

/** POST /auth/pos/token request — exchange credentials for a site-scoped POS JWT. */
@JsonClass(generateAdapter = true)
data class PosTokenRequest(
    val email: String,
    val password: String,
    @Json(name = "site_id") val siteId: String,
)

@JsonClass(generateAdapter = true)
data class PosTokenResponse(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "refresh_token") val refreshToken: String,
    @Json(name = "site_id") val siteId: String,
)

/** POST /auth/pos/pin/verify request. */
@JsonClass(generateAdapter = true)
data class PinVerifyRequest(
    val pin: String,
)

@JsonClass(generateAdapter = true)
data class PinVerifyResponse(
    val valid: Boolean,
    @Json(name = "must_reset") val mustReset: Boolean = false,
)

/** POST /auth/pos/pin/set request. */
@JsonClass(generateAdapter = true)
data class PinSetRequest(
    @Json(name = "current_pin") val currentPin: String? = null,
    @Json(name = "new_pin") val newPin: String,
)

/** Resolved product — returned by GET /products (site-resolved catalog). */
@JsonClass(generateAdapter = true)
data class ProductDto(
    val id: String,
    @Json(name = "brand_id") val brandId: String,
    @Json(name = "category_id") val categoryId: String,
    val name: String,
    val description: String?,
    @Json(name = "base_price_cents") val basePriceCents: Long,
    @Json(name = "photo_url") val photoUrl: String?,
    @Json(name = "display_order") val displayOrder: Int,
    @Json(name = "is_active") val isActive: Boolean,
)

@JsonClass(generateAdapter = true)
data class CategoryDto(
    val id: String,
    val name: String,
    @Json(name = "display_order") val displayOrder: Int,
)

/** POST /invoices request. */
@JsonClass(generateAdapter = true)
data class CreateInvoiceRequest(
    @Json(name = "site_id") val siteId: String,
    @Json(name = "invoice_type") val invoiceType: String = "sale",
)

@JsonClass(generateAdapter = true)
data class InvoiceDto(
    val id: String,
    val status: String,
    @Json(name = "subtotal_cents") val subtotalCents: Long,
    @Json(name = "tax_cents") val taxCents: Long,
    @Json(name = "discount_cents") val discountCents: Long,
    @Json(name = "total_cents") val totalCents: Long,
    @Json(name = "is_refunded") val isRefunded: Boolean,
)

/** POST /invoices/{id}/line-items request. */
@JsonClass(generateAdapter = true)
data class AddLineItemRequest(
    @Json(name = "product_id") val productId: String,
    val quantity: Int,
    @Json(name = "modifier_ids") val modifierIds: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class LineItemDto(
    val id: String,
    @Json(name = "product_name") val productName: String,
    val quantity: Int,
    @Json(name = "unit_price_cents") val unitPriceCents: Long,
    @Json(name = "subtotal_cents") val subtotalCents: Long,
    @Json(name = "tax_cents") val taxCents: Long,
)

/** POST /invoices/{id}/pay request. */
@JsonClass(generateAdapter = true)
data class PaymentRequest(
    val method: String,
    @Json(name = "amount_cents") val amountCents: Long,
)
