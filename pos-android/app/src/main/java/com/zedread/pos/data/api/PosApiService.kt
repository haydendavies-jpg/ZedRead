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

    /** POST /auth/pos/login — returns list of sites for the operator to pick from. */
    @POST("auth/pos/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    /** POST /auth/pos/token — exchange credentials + site selection for a site-scoped JWT. */
    @POST("auth/pos/token")
    suspend fun getPosToken(@Body body: PosTokenRequest): PosTokenResponse

    /** POST /auth/pos/refresh — exchange a refresh token for a new access token. */
    @POST("auth/pos/refresh")
    suspend fun refresh(@Body body: Map<String, String>): PosTokenResponse

    // ── PIN ─────────────────────────────────────────────────────────────────

    /** POST /auth/pos/pin/verify — verify the operator's PIN. */
    @POST("auth/pos/pin/verify")
    suspend fun verifyPin(
        @Header("Authorization") bearer: String,
        @Body body: PinVerifyRequest,
    ): PinVerifyResponse

    /** POST /auth/pos/pin/set — set or change the operator's PIN. */
    @POST("auth/pos/pin/set")
    suspend fun setPin(
        @Header("Authorization") bearer: String,
        @Body body: PinSetRequest,
    ): Unit

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

    /** POST /invoices — open a new draft invoice. */
    @POST("invoices")
    suspend fun createInvoice(
        @Header("Authorization") bearer: String,
        @Body body: CreateInvoiceRequest,
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
