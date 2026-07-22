package com.zedread.pos.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/** Retrofit interface mapping every backend endpoint the POS terminal uses. */
interface PosApiService {

    // ── Auth ────────────────────────────────────────────────────────────────

    /** POST /auth/pos/login — token, or available_sites for a multi-site user. */
    @POST("auth/pos/login")
    suspend fun login(@Body body: LoginRequest): PosLoginResponseDto

    /** POST /auth/pos/site-token — finalizes a multi-site login for the chosen site. */
    @POST("auth/pos/site-token")
    suspend fun selectSite(@Body body: SiteTokenRequest): PosLoginResponseDto

    /** POST /auth/pos/pin/set — set or replace the caller's own PIN. */
    @POST("auth/pos/pin/set")
    suspend fun setPin(
        @Header("Authorization") bearer: String,
        @Body body: PinSetRequest,
    )

    /** POST /auth/pos/pin/verify — unauthenticated switch-user / re-auth check. */
    @POST("auth/pos/pin/verify")
    suspend fun verifyPin(@Body body: PinVerifyRequest): PinVerifyResponseDto

    /** POST /auth/pos/logout — revokes the presented access token. */
    @POST("auth/pos/logout")
    suspend fun logout(@Header("Authorization") bearer: String): LogoutResponseDto

    // ── Register (till) sessions ───────────────────────────────────────────

    /**
     * GET /register-sessions/current — the open session for this terminal, or null.
     *
     * Wrapped in Response<T> rather than declaring a nullable suspend return
     * type directly - Retrofit's suspend-fun nullable-body detection doesn't
     * reliably recognize a Kotlin `T?` return type from bytecode alone, and
     * throws "declared as non-null" even though the body is a legitimate
     * JSON `null` (this endpoint's contract when no session is open, not an
     * empty/204 response). Response<T>.body() sidesteps that entirely.
     */
    @GET("register-sessions/current")
    suspend fun getCurrentRegisterSession(
        @Header("Authorization") bearer: String,
    ): Response<RegisterSessionDto>

    /** POST /register-sessions/open — start-of-day cash-in. */
    @POST("register-sessions/open")
    suspend fun openRegisterSession(
        @Header("Authorization") bearer: String,
        @Body body: RegisterSessionOpenRequest,
    ): RegisterSessionDto

    /** POST /register-sessions/{id}/close — end-of-day cash-up. */
    @POST("register-sessions/{id}/close")
    suspend fun closeRegisterSession(
        @Header("Authorization") bearer: String,
        @Path("id") sessionId: String,
        @Body body: RegisterSessionCloseRequest,
    ): RegisterSessionDto

    // ── Catalog ─────────────────────────────────────────────────────────────

    /** GET /products?site_id= — site-resolved product catalog. */
    @GET("products")
    suspend fun getProducts(
        @Header("Authorization") bearer: String,
        @Query("site_id") siteId: String,
    ): List<ProductDto>

    /** GET /categories?site_id= — active categories for the site's brand. */
    @GET("categories")
    suspend fun getCategories(
        @Header("Authorization") bearer: String,
        @Query("site_id") siteId: String,
    ): List<CategoryDto>

    /** GET /products/{id}/modifiers/detailed — a product's attached modifier groups, fully nested. */
    @GET("products/{id}/modifiers/detailed")
    suspend fun getProductModifiersDetailed(
        @Header("Authorization") bearer: String,
        @Path("id") productId: String,
    ): List<ProductModifierGroupDto>

    /** GET /pos/menu-layout?site_id= — every currently-active published menu layout visible to the site. */
    @GET("pos/menu-layout")
    suspend fun getMenuLayouts(
        @Header("Authorization") bearer: String,
        @Query("site_id") siteId: String,
    ): List<PosMenuLayoutDto>

    // ── Invoices ─────────────────────────────────────────────────────────────

    /**
     * POST /invoices — open a new draft invoice. Site/brand/register-session
     * resolve server-side from the token; [body] only carries the optional
     * offline-sync idempotency key.
     */
    @POST("invoices")
    suspend fun createInvoice(
        @Header("Authorization") bearer: String,
        @Body body: InvoiceCreateBody,
    ): InvoiceDto

    /** GET /invoices — this site's invoice history, most recent first. Backfills the local search cache. */
    @GET("invoices")
    suspend fun listInvoices(
        @Header("Authorization") bearer: String,
        @Query("skip") skip: Int,
        @Query("limit") limit: Int,
    ): List<InvoiceDto>

    /** POST /invoices/{id}/line-items — append a product to the invoice. */
    @POST("invoices/{id}/line-items")
    suspend fun addLineItem(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Body body: AddLineItemRequest,
    ): LineItemDto

    /** PATCH /invoices/{id}/line-items/{lineItemId} — the Register screen's qty stepper. */
    @PATCH("invoices/{id}/line-items/{lineItemId}")
    suspend fun updateLineItemQuantity(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Path("lineItemId") lineItemId: String,
        @Body body: UpdateLineItemQuantityRequest,
    ): LineItemDto

    /** GET /invoices/{id}/line-items/{lineItemId} — a line item with its attached modifiers. */
    @GET("invoices/{id}/line-items/{lineItemId}")
    suspend fun getLineItem(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Path("lineItemId") lineItemId: String,
    ): LineItemDto

    /** POST /invoices/{id}/line-items/{lineItemId}/modifiers — attach a modifier option to a line. */
    @POST("invoices/{id}/line-items/{lineItemId}/modifiers")
    suspend fun addLineItemModifier(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Path("lineItemId") lineItemId: String,
        @Body body: AddModifierRequest,
    ): LineModifierDto

    /** DELETE /invoices/{id}/line-items/{lineItemId} — remove a line from the order. */
    @DELETE("invoices/{id}/line-items/{lineItemId}")
    suspend fun removeLineItem(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Path("lineItemId") lineItemId: String,
    ): Response<Unit>

    /** POST /invoices/{id}/pay — record a payment against the invoice. */
    @POST("invoices/{id}/pay")
    suspend fun pay(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Body body: PaymentRequest,
    ): InvoiceDto

    // ── Settings ────────────────────────────────────────────────────────────

    /** GET /pos/settings — every setting resolved for this terminal's own site, optionally search-filtered. */
    @GET("pos/settings")
    suspend fun getSettings(
        @Header("Authorization") bearer: String,
        @Query("search") search: String?,
    ): List<SettingDto>

    /**
     * PUT /settings/{key} — "Save as default": push a locally-edited setting
     * back to become this site's backend override. Server-gated to a
     * Manager-tier-or-above POS access profile (403 otherwise) — see
     * app/routes/settings.py's _POS_SETTINGS_WRITE_PROFILE_NAMES.
     */
    @PUT("settings/{key}")
    suspend fun updateSetting(
        @Header("Authorization") bearer: String,
        @Path("key") key: String,
        @Body body: SettingUpdateRequest,
    ): SettingDto
}
