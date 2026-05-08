package com.zedread.pos.data.repository

import com.zedread.pos.data.api.LoginRequest
import com.zedread.pos.data.api.PinSetRequest
import com.zedread.pos.data.api.PinVerifyRequest
import com.zedread.pos.data.api.PinVerifyResponse
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosTokenRequest
import com.zedread.pos.data.api.SiteDto
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Handles all authentication operations: login, site selection, PIN, logout. */
@Singleton
class AuthRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /**
     * Step 1 of login: authenticate with email/password, return list of sites.
     * Does NOT persist any tokens — site selection happens in [selectSite].
     */
    suspend fun login(email: String, password: String): List<SiteDto> {
        val response = api.login(LoginRequest(email, password))
        return response.sites
    }

    /**
     * Step 2 of login: exchange credentials + chosen site for a site-scoped POS JWT.
     * Persists the tokens and site ID to DataStore.
     */
    suspend fun selectSite(email: String, password: String, siteId: String) {
        val response = api.getPosToken(PosTokenRequest(email, password, siteId))
        tokenStore.save(response.accessToken, response.refreshToken, response.siteId)
    }

    /** Return the stored access token, or null if not logged in. */
    suspend fun getAccessToken(): String? = tokenStore.accessToken.firstOrNull()

    /** Return the stored site ID, or null if not logged in. */
    suspend fun getSiteId(): String? = tokenStore.siteId.firstOrNull()

    /**
     * Verify the operator's PIN. Returns [PinVerifyResponse] which includes
     * [PinVerifyResponse.mustReset] when a forced PIN change is required.
     */
    suspend fun verifyPin(pin: String): PinVerifyResponse {
        val token = requireToken()
        return api.verifyPin("Bearer $token", PinVerifyRequest(pin))
    }

    /**
     * Set or change the operator's PIN.
     * Pass [currentPin] = null only when the user has no PIN yet.
     */
    suspend fun setPin(currentPin: String?, newPin: String) {
        val token = requireToken()
        api.setPin("Bearer $token", PinSetRequest(currentPin, newPin))
    }

    /** Clear all stored credentials — the user must log in again. */
    suspend fun logout() {
        tokenStore.clear()
    }

    /** Throw [IllegalStateException] if no access token is stored. */
    private suspend fun requireToken(): String =
        tokenStore.accessToken.firstOrNull()
            ?: error("No access token — user is not authenticated")
}
