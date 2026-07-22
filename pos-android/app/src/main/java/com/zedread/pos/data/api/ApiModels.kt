package com.zedread.pos.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

// ── Auth ──────────────────────────────────────────────────────────────────
//
// Mirrors app/schemas/pos_auth.py exactly (self-service license-seat device
// claiming — no site_id on the first call, no refresh-token endpoint).
// device_token identifies this physical terminal; unlike the old
// admin-pre-registration flow, it's never entered manually — the terminal
// sends whatever it has locally stored (null on first-ever login) and the
// backend claims or re-pairs a device automatically, returning the
// resulting token in PosLoginResponseDto.deviceToken for the client to
// persist. device_name is only used if a brand-new device is claimed.

/** POST /auth/pos/login request body. */
@JsonClass(generateAdapter = true)
data class LoginRequest(
    val email: String,
    val password: String,
    @Json(name = "device_name") val deviceName: String,
    @Json(name = "device_token") val deviceToken: String?,
)

/** POST /auth/pos/site-token request body — finalizes a multi-site login. */
@JsonClass(generateAdapter = true)
data class SiteTokenRequest(
    val email: String,
    val password: String,
    @Json(name = "device_name") val deviceName: String,
    @Json(name = "device_token") val deviceToken: String?,
    @Json(name = "site_id") val siteId: String,
)

/** One selectable site returned when a login can't resolve to a single site. */
@JsonClass(generateAdapter = true)
data class SiteOptionDto(
    @Json(name = "site_id") val siteId: String,
    @Json(name = "site_name") val siteName: String,
)

/**
 * Response shared by POST /auth/pos/login and POST /auth/pos/site-token.
 *
 * Exactly one of (accessToken, availableSites) is populated — never both.
 */
@JsonClass(generateAdapter = true)
data class PosLoginResponseDto(
    @Json(name = "access_token") val accessToken: String?,
    @Json(name = "token_type") val tokenType: String = "bearer",
    @Json(name = "user_id") val userId: String?,
    @Json(name = "user_name") val userName: String?,
    @Json(name = "site_id") val siteId: String?,
    @Json(name = "site_name") val siteName: String?,
    @Json(name = "access_profile_name") val accessProfileName: String?,
    @Json(name = "is_pin_reset_required") val isPinResetRequired: Boolean?,
    @Json(name = "available_sites") val availableSites: List<SiteOptionDto>?,
    @Json(name = "device_token") val deviceToken: String?,
)

/** POST /auth/pos/pin/set request — the caller's own new PIN (4-6 digits). */
@JsonClass(generateAdapter = true)
data class PinSetRequest(
    val pin: String,
)

/**
 * POST /auth/pos/pin/verify request — unauthenticated switch-user check.
 *
 * Verifies [pin] and issues a fresh session; used both to swap the active
 * operator on an already-unlocked terminal and to re-confirm the current
 * operator's identity. [email] is optional — the switch-operator flow asks
 * for a PIN only (matching real POS terminal conventions), which the
 * backend resolves against every active user granted at [siteId] instead of
 * one disambiguated account; supplying it keeps the cheaper single-account
 * check for callers that already know who's switching in (e.g. the inline
 * manager-authorisation prompt). deviceToken carries device context forward
 * so the switched-in session still gates on this terminal's register session.
 */
@JsonClass(generateAdapter = true)
data class PinVerifyRequest(
    val email: String?,
    val pin: String,
    @Json(name = "site_id") val siteId: String,
    @Json(name = "device_token") val deviceToken: String?,
)

/** Response on successful PIN verification — a fresh POS access token. */
@JsonClass(generateAdapter = true)
data class PinVerifyResponseDto(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "token_type") val tokenType: String = "bearer",
    @Json(name = "user_id") val userId: String,
    @Json(name = "user_name") val userName: String,
    val email: String?,
    @Json(name = "access_profile_name") val accessProfileName: String,
    @Json(name = "is_pin_reset_required") val isPinResetRequired: Boolean,
)

/** POST /auth/pos/logout response — the body is informational only. */
@JsonClass(generateAdapter = true)
data class LogoutResponseDto(
    val detail: String,
)

// ── Register (till) sessions ─────────────────────────────────────────────
//
// Mirrors app/schemas/register_session.py. Timestamps are device-local,
// ISO-8601 with offset (java.time.OffsetDateTime.toString()).

/**
 * POST /register-sessions/open request — start-of-day cash-in.
 *
 * [clientRef] dedupes a retried open (see RegisterSessionOpenRequest in
 * app/services/register_session_service.py). No [checksum] field — that
 * would need this terminal's own server-side `device.id`, which is never
 * returned to the client (only the opaque device_token is) — see
 * OutboxModels.kt's OpenSessionPayload doc for the full reasoning.
 * `client_ref` alone already makes a retried sync safe.
 */
@JsonClass(generateAdapter = true)
data class RegisterSessionOpenRequest(
    @Json(name = "opened_at") val openedAt: String,
    @Json(name = "opening_cash_cents") val openingCashCents: Long,
    @Json(name = "client_ref") val clientRef: String? = null,
)

/** POST /register-sessions/{id}/close request — end-of-day cash-up. [clientRef] dedupes a retried close. */
@JsonClass(generateAdapter = true)
data class RegisterSessionCloseRequest(
    @Json(name = "closed_at") val closedAt: String,
    @Json(name = "closing_cash_cents") val closingCashCents: Long,
    @Json(name = "client_ref") val clientRef: String? = null,
)

/** Full register session state, returned by every /register-sessions endpoint. */
@JsonClass(generateAdapter = true)
data class RegisterSessionDto(
    val id: String,
    @Json(name = "device_id") val deviceId: String,
    @Json(name = "site_id") val siteId: String,
    val status: String,
    @Json(name = "opened_at") val openedAt: String,
    @Json(name = "opening_cash_cents") val openingCashCents: Long,
    @Json(name = "opened_by_name") val openedByName: String,
    @Json(name = "closed_at") val closedAt: String?,
    @Json(name = "closing_cash_cents") val closingCashCents: Long?,
    @Json(name = "expected_cash_cents") val expectedCashCents: Long?,
    @Json(name = "variance_cents") val varianceCents: Long?,
    @Json(name = "closed_by_name") val closedByName: String?,
)

// ── Catalog ───────────────────────────────────────────────────────────────

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
    // ProductListItem's joined fields — the Register screen's tile colour and
    // its "has modifiers" "+" badge (comma-joined active modifier group names;
    // null/blank means the product has none).
    @Json(name = "category_color") val categoryColor: String,
    @Json(name = "modifier_names") val modifierNames: String?,
)

// ── Modifiers ─────────────────────────────────────────────────────────────
//
// Mirrors ProductModifierGroupDetailOut / ProductModifierOptionOut in
// app/services/modifier_service.py — a product's attached modifier groups,
// each fully nested with its active options. Powers the Register screen's
// modifier customise sheet (GET /products/{id}/modifiers/detailed).

@JsonClass(generateAdapter = true)
data class ProductModifierOptionDto(
    val id: String,
    val name: String,
    @Json(name = "price_delta_cents") val priceDeltaCents: Long,
    @Json(name = "display_order") val displayOrder: Int,
)

@JsonClass(generateAdapter = true)
data class ProductModifierGroupDto(
    val id: String,
    val name: String,
    @Json(name = "min_selections") val minSelections: Int,
    @Json(name = "max_selections") val maxSelections: Int,
    @Json(name = "has_quantity") val hasQuantity: Boolean,
    @Json(name = "display_order") val displayOrder: Int,
    val options: List<ProductModifierOptionDto>,
)

@JsonClass(generateAdapter = true)
data class CategoryDto(
    val id: String,
    val name: String,
    @Json(name = "display_order") val displayOrder: Int,
    @Json(name = "default_color") val defaultColor: String,
)

// ── Invoices ──────────────────────────────────────────────────────────────
//
// Mirrors the inline request/response models in app/services/invoice_service.py
// (there is no separate schemas/invoice.py). POST /invoices takes no body at
// all — brand/site/register-session are all resolved server-side from the
// caller's POS access token, not supplied by the client.

@JsonClass(generateAdapter = true)
data class InvoiceDto(
    val id: String,
    val status: String,
    @Json(name = "subtotal_cents") val subtotalCents: Long,
    @Json(name = "tax_cents") val taxCents: Long,
    @Json(name = "discount_cents") val discountCents: Long,
    @Json(name = "total_cents") val totalCents: Long,
    @Json(name = "is_refunded") val isRefunded: Boolean,
    // Only populated by GET /invoices (invoice history / search) — the
    // create/pay responses don't need it and older call sites ignore it.
    @Json(name = "created_at") val createdAt: String? = null,
)

/**
 * POST /invoices request. All fields optional — site/brand/register-session
 * resolve server-side from the caller's POS token (see InvoiceCreateRequest
 * in app/services/invoice_service.py); [clientRef] dedupes a retried create.
 */
@JsonClass(generateAdapter = true)
data class InvoiceCreateBody(
    @Json(name = "client_ref") val clientRef: String? = null,
)

/**
 * POST /invoices/{id}/line-items request.
 *
 * No modifier_ids field — AddLineItemRequest has none; a modifier is
 * attached afterward, one at a time, via
 * POST /invoices/{id}/line-items/{lineItemId}/modifiers (see
 * [AddModifierRequest] — wired by the modifier customise sheet).
 */
@JsonClass(generateAdapter = true)
data class AddLineItemRequest(
    @Json(name = "product_id") val productId: String,
    val quantity: Int,
)

/** PATCH /invoices/{id}/line-items/{lineItemId} request — the Register screen's qty stepper. */
@JsonClass(generateAdapter = true)
data class UpdateLineItemQuantityRequest(
    val quantity: Int,
)

/** POST /invoices/{id}/line-items/{lineItemId}/modifiers request. */
@JsonClass(generateAdapter = true)
data class AddModifierRequest(
    @Json(name = "modifier_option_id") val modifierOptionId: String,
)

/** A modifier attached to a line item — mirrors LineModifierResponse. */
@JsonClass(generateAdapter = true)
data class LineModifierDto(
    val id: String,
    @Json(name = "line_item_id") val lineItemId: String,
    @Json(name = "modifier_option_id") val modifierOptionId: String?,
    @Json(name = "modifier_name") val modifierName: String,
    @Json(name = "price_delta_cents") val priceDeltaCents: Long,
)

/**
 * A line item, optionally with its attached modifiers.
 *
 * [modifiers] is only populated by GET .../line-items/{id} (mirrors
 * LineItemDetailResponse) — the plain add/update line-item responses don't
 * include it (LineItemResponse has no such field), so it defaults to empty
 * for those.
 */
@JsonClass(generateAdapter = true)
data class LineItemDto(
    val id: String,
    @Json(name = "product_id") val productId: String?,
    @Json(name = "product_name") val productName: String,
    val quantity: Int,
    @Json(name = "unit_price_cents") val unitPriceCents: Long,
    @Json(name = "subtotal_cents") val subtotalCents: Long,
    @Json(name = "tax_cents") val taxCents: Long,
    val modifiers: List<LineModifierDto> = emptyList(),
)

/**
 * POST /invoices/{id}/pay request. [reference] carries a voucher's redemption
 * code; null for cash/card. [clientRef] dedupes a retried pay call. No
 * [checksum] field is populated by this client — see
 * OutboxModels.kt's SyncSalePayload doc for why.
 */
@JsonClass(generateAdapter = true)
data class PaymentRequest(
    val method: String,
    @Json(name = "amount_cents") val amountCents: Long,
    val reference: String? = null,
    @Json(name = "client_ref") val clientRef: String? = null,
)

// ── Settings (Android POS Phase 2) ───────────────────────────────────────────
//
// Mirrors SettingOut in app/schemas/setting.py. The value fields are
// polymorphic per catalog entry's type (Boolean for "boolean", String for
// "datetime"/"single_select", List<String> for "multi_select") — typed Any?
// here and narrowed by the caller (see SettingsRepository), which Moshi
// resolves via its built-in Any/Object adapter (the same mechanism backing
// Map<String, Any> parsing) rather than a registered custom adapter.

/** GET /pos/settings response row — one catalog entry resolved for the terminal's own site. */
@JsonClass(generateAdapter = true)
data class SettingDto(
    val key: String,
    val label: String,
    val category: String,
    val type: String,
    val options: List<String>?,
    @Json(name = "default_value") val defaultValue: Any?,
    @Json(name = "brand_value") val brandValue: Any?,
    @Json(name = "site_value") val siteValue: Any?,
    @Json(name = "effective_value") val effectiveValue: Any?,
)
