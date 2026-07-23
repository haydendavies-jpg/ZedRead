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

/**
 * POST /auth/pos/login request body.
 *
 * hardwareId is Settings.Secure.ANDROID_ID — a stable OS-level identifier
 * that survives an app reinstall, unlike deviceToken (which lives in this
 * app's own storage and is wiped with it). Sent alongside deviceToken so
 * the backend can recognise a returning physical device that lost its
 * token, instead of silently claiming a new license seat.
 */
@JsonClass(generateAdapter = true)
data class LoginRequest(
    val email: String,
    val password: String,
    // Null lets the backend auto-assign "POS #N" for a brand-new device claim.
    @Json(name = "device_name") val deviceName: String?,
    @Json(name = "device_token") val deviceToken: String?,
    @Json(name = "hardware_id") val hardwareId: String?,
)

/** POST /auth/pos/site-token request body — finalizes a multi-site login. */
@JsonClass(generateAdapter = true)
data class SiteTokenRequest(
    val email: String,
    val password: String,
    @Json(name = "device_name") val deviceName: String?,
    @Json(name = "device_token") val deviceToken: String?,
    @Json(name = "hardware_id") val hardwareId: String?,
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
    @Json(name = "device_name") val deviceName: String?,
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
    // Matches a menu_buttons.product_ref value (Menu Studio POS Layout) so
    // the Register screen can filter its grid down to a selected menu layout.
    val ref: String,
    @Json(name = "brand_id") val brandId: String,
    @Json(name = "category_id") val categoryId: String,
    val name: String,
    val description: String?,
    @Json(name = "base_price_cents") val basePriceCents: Long,
    // Cached so the Register can compute a line's tax on-device — see
    // ProductEntity.priceExCents/isTaxable's own doc.
    @Json(name = "price_ex_cents") val priceExCents: Long,
    @Json(name = "is_taxable") val isTaxable: Boolean,
    @Json(name = "photo_url") val photoUrl: String?,
    @Json(name = "display_order") val displayOrder: Int,
    @Json(name = "is_active") val isActive: Boolean,
    // Long-press product popup: greys the tile out with "SOLD OUT" written
    // over it and blocks adding it to an order until toggled off again.
    @Json(name = "is_sold_out") val isSoldOut: Boolean,
    // ProductListItem's joined fields — the Register screen's tile colour and
    // its "has modifiers" "+" badge (comma-joined active modifier group names;
    // null/blank means the product has none).
    @Json(name = "category_color") val categoryColor: String,
    @Json(name = "modifier_names") val modifierNames: String?,
)

/**
 * PATCH /products/{id} request — only the fields the Register app itself
 * ever writes (the long-press sold-out toggle). Mirrors ProductUpdate on the
 * backend, which accepts every product field, but this client only ever
 * sends is_sold_out — never null, Moshi would otherwise omit an unset
 * property entirely rather than send an explicit null, which is exactly
 * "leave everything else unchanged" here since every other field is absent.
 */
@JsonClass(generateAdapter = true)
data class ProductUpdateRequest(
    @Json(name = "is_sold_out") val isSoldOut: Boolean,
)

/**
 * PATCH /products/{id} response — deliberately NOT [ProductDto]. The
 * backend's plain `ProductResponse` (what this route returns) has no
 * `category_color`/`modifier_names` — those are joined-in fields only
 * `ProductListItem` (GET /products, the list route) carries. Moshi's
 * generated adapter requires every non-nullable constructor property to be
 * present in the JSON, so reusing [ProductDto] here threw
 * "Required value 'categoryColor' ... missing at $" on every sold-out
 * toggle — a real crash caught in testing, not just a lint concern.
 */
@JsonClass(generateAdapter = true)
data class ProductUpdateResponse(
    val id: String,
    @Json(name = "is_sold_out") val isSoldOut: Boolean,
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
    // "Comboing" — one level deep, mirrors LinkedGroupOut. Selecting this
    // option expands into each of these nested groups on the sheet.
    @Json(name = "linked_groups") val linkedGroups: List<LinkedGroupDto> = emptyList(),
)

/** One flat option belonging to a linked (combo) group — no further nesting. Mirrors LinkedGroupOptionOut. */
@JsonClass(generateAdapter = true)
data class LinkedGroupOptionDto(
    val id: String,
    val name: String,
    @Json(name = "price_delta_cents") val priceDeltaCents: Long,
)

/** A modifier group linked from an option ("comboing"), with its own active options. Mirrors LinkedGroupOut. */
@JsonClass(generateAdapter = true)
data class LinkedGroupDto(
    val id: String,
    val name: String,
    @Json(name = "min_selections") val minSelections: Int,
    @Json(name = "max_selections") val maxSelections: Int,
    // Per-group opt-in — see ProductModifierGroupDto.isFirstOptionDefaultSelected.
    @Json(name = "is_first_option_default_selected") val isFirstOptionDefaultSelected: Boolean = false,
    val options: List<LinkedGroupOptionDto>,
)

@JsonClass(generateAdapter = true)
data class ProductModifierGroupDto(
    val id: String,
    val name: String,
    @Json(name = "min_selections") val minSelections: Int,
    @Json(name = "max_selections") val maxSelections: Int,
    @Json(name = "has_quantity") val hasQuantity: Boolean,
    @Json(name = "display_order") val displayOrder: Int,
    // User-testing feedback: the sheet used to always pre-select a
    // single-select group's first option, which testers didn't want.
    // Nothing is pre-selected unless a manager explicitly opts this group
    // in from Menu Studio's Modifiers tab.
    @Json(name = "is_first_option_default_selected") val isFirstOptionDefaultSelected: Boolean = false,
    val options: List<ProductModifierOptionDto>,
)

@JsonClass(generateAdapter = true)
data class CategoryDto(
    val id: String,
    val name: String,
    @Json(name = "display_order") val displayOrder: Int,
    @Json(name = "default_color") val defaultColor: String,
)

// ── Menu layouts (Phase 3 — Menu Studio -> POS integration depth) ──────────
//
// Mirrors PosMenuLayoutDetail / MenuTabOut / MenuButtonOut in
// app/schemas/menu_layout.py — full enough to actually render the Register
// grid from the layout's own tabs/buttons (rail + dense 6-column tile grid,
// folder tiles opening a nested tab), matching the portal grid editor's own
// data model rather than only filtering the category-based grid by ref.
// grid_col/grid_row are null until a button has been explicitly dragged to
// a cell in the portal editor — MenuGridPacking.kt dense-packs the rest,
// mirroring the portal's own `grid-auto-flow: dense` CSS behaviour.

/** One button within a menu tab. */
@JsonClass(generateAdapter = true)
data class PosMenuButtonDto(
    val id: String,
    val kind: String,
    @Json(name = "product_ref") val productRef: String?,
    @Json(name = "child_tab_id") val childTabId: String?,
    val width: Int,
    val height: Int,
    val color: String?,
    @Json(name = "display_order") val displayOrder: Int,
    @Json(name = "grid_col") val gridCol: Int?,
    @Json(name = "grid_row") val gridRow: Int?,
    @Json(name = "product_name") val productName: String?,
    @Json(name = "price_cents") val priceCents: Long?,
    @Json(name = "is_active") val isActive: Boolean?,
    @Json(name = "is_sold_out") val isSoldOut: Boolean?,
    @Json(name = "category_color") val categoryColor: String?,
    @Json(name = "product_photo_url") val productPhotoUrl: String?,
    @Json(name = "child_tab_name") val childTabName: String?,
    @Json(name = "child_tab_button_count") val childTabButtonCount: Int?,
)

/** One tab within a menu layout, with its ordered buttons. Tabs are a flat list linked by parentTabId, not a nested tree. */
@JsonClass(generateAdapter = true)
data class PosMenuTabDto(
    val id: String,
    @Json(name = "parent_tab_id") val parentTabId: String?,
    val name: String,
    val color: String?,
    @Json(name = "display_order") val displayOrder: Int,
    val buttons: List<PosMenuButtonDto>,
)

/** GET /pos/menu-layout's per-layout response — one currently-active published layout for the site. */
@JsonClass(generateAdapter = true)
data class PosMenuLayoutDto(
    val id: String,
    val name: String,
    val color: String,
    @Json(name = "is_effective_default") val isEffectiveDefault: Boolean,
    val tabs: List<PosMenuTabDto>,
) {
    /** Every distinct product_ref referenced by a product button anywhere in this layout (any tab). */
    val productRefs: Set<String>
        get() = tabs.flatMap { it.buttons }
            .filter { it.kind == "product" }
            .mapNotNull { it.productRef }
            .toSet()

    /** The rail — every tab with no parent. */
    val topLevelTabs: List<PosMenuTabDto>
        get() = tabs.filter { it.parentTabId == null }.sortedBy { it.displayOrder }
}

// ── Invoices ──────────────────────────────────────────────────────────────
//
// Mirrors the inline request/response models in app/services/invoice_service.py
// (there is no separate schemas/invoice.py). POST /invoices takes no body at
// all — brand/site/register-session are all resolved server-side from the
// caller's POS access token, not supplied by the client.

@JsonClass(generateAdapter = true)
data class InvoiceDto(
    val id: String,
    val ref: String,
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

/** PUT /settings/{key} request body — see PosApiService.updateSetting. */
@JsonClass(generateAdapter = true)
data class SettingUpdateRequest(
    val value: Any?,
    @Json(name = "site_id") val siteId: String?,
)
