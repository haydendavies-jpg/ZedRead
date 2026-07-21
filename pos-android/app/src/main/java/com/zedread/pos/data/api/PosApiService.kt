package com.zedread.pos.data.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
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

    /** GET /register-sessions/current — the open session for this terminal, or null. */
    @GET("register-sessions/current")
    suspend fun getCurrentRegisterSession(
        @Header("Authorization") bearer: String,
    ): RegisterSessionDto?

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

    // ── Invoices ─────────────────────────────────────────────────────────────

    /** POST /invoices — open a new draft invoice. No body: site/brand/register-session resolve from the token. */
    @POST("invoices")
    suspend fun createInvoice(
        @Header("Authorization") bearer: String,
    ): InvoiceDto

    /** POST /invoices/{id}/line-items — append a product to the invoice. */
    @POST("invoices/{id}/line-items")
    suspend fun addLineItem(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Body body: AddLineItemRequest,
    ): LineItemDto

    /** POST /invoices/{id}/pay — record a payment against the invoice. */
    @POST("invoices/{id}/pay")
    suspend fun pay(
        @Header("Authorization") bearer: String,
        @Path("id") invoiceId: String,
        @Body body: PaymentRequest,
    ): InvoiceDto
}
