package com.zedread.pos.data.repository

import com.zedread.pos.data.api.LoginRequest
import com.zedread.pos.data.api.PinSetRequest
import com.zedread.pos.data.api.PinVerifyRequest
import com.zedread.pos.data.api.PinVerifyResponseDto
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosLoginResponseDto
import com.zedread.pos.data.api.SiteOptionDto
import com.zedread.pos.data.api.SiteTokenRequest
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Handles all authentication operations: device pairing, login, PIN, logout. */
@Singleton
class AuthRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /** Outcome of a login()/selectSite() call — exactly one branch applies. */
    sealed class LoginOutcome {
        /** Token issued. [needsPinSetup] mirrors POSLoginResponse.is_pin_reset_required. */
        data class Authenticated(val needsPinSetup: Boolean) : LoginOutcome()

        /** The user has grants on more than one site — must call selectSite() next. */
        data class NeedsSiteSelection(val sites: List<SiteOptionDto>) : LoginOutcome()
    }

    // ── Device pairing ──────────────────────────────────────────────────────

    /** True once this terminal has been paired with a device_token. */
    suspend fun hasPairedDevice(): Boolean = tokenStore.deviceToken.firstOrNull() != null

    /** Persist the device_token issued by a portal admin for this terminal. */
    suspend fun pairDevice(deviceToken: String) = tokenStore.pairDevice(deviceToken)

    // ── Login ────────────────────────────────────────────────────────────────

    /** True once an operator session is persisted (survives app relaunch). */
    suspend fun hasActiveSession(): Boolean = tokenStore.accessToken.firstOrNull() != null

    /** Step 1: authenticate with email/password against this terminal's paired device. */
    suspend fun login(email: String, password: String): LoginOutcome {
        val deviceToken = requireDeviceToken()
        val response = api.login(LoginRequest(email, password, deviceToken))
        return handleLoginResponse(response, email)
    }

    /** Step 2 (multi-site only): finalize login by choosing one of the offered sites. */
    suspend fun selectSite(email: String, password: String, siteId: String): LoginOutcome {
        val deviceToken = requireDeviceToken()
        val response = api.selectSite(SiteTokenRequest(email, password, deviceToken, siteId))
        return handleLoginResponse(response, email)
    }

    private suspend fun handleLoginResponse(
        response: PosLoginResponseDto,
        email: String,
    ): LoginOutcome {
        val availableSites = response.availableSites
        if (availableSites != null) return LoginOutcome.NeedsSiteSelection(availableSites)

        val accessToken = response.accessToken
            ?: error("Login response carried neither a token nor available_sites")
        tokenStore.saveSession(
            accessToken = accessToken,
            siteId = response.siteId ?: error("Login response missing site_id"),
            siteName = response.siteName.orEmpty(),
            userId = response.userId ?: error("Login response missing user_id"),
            userName = response.userName.orEmpty(),
            email = email,
            accessProfileName = response.accessProfileName.orEmpty(),
        )
        return LoginOutcome.Authenticated(needsPinSetup = response.isPinResetRequired ?: true)
    }

    // ── PIN ─────────────────────────────────────────────────────────────────

    /** Set or change the currently authenticated operator's own PIN. */
    suspend fun setPin(pin: String) {
        val token = requireAccessToken()
        api.setPin("Bearer $token", PinSetRequest(pin))
    }

    /**
     * Verify [email]'s PIN and adopt the returned session as the active one —
     * used for switch-user (a different operator takes over) and for
     * re-confirming the currently signed-in operator's identity.
     */
    suspend fun verifyPin(email: String, pin: String): PinVerifyResponseDto {
        val siteId = tokenStore.siteId.firstOrNull() ?: error("No active site")
        val deviceToken = tokenStore.deviceToken.firstOrNull()
        val response = api.verifyPin(PinVerifyRequest(email, pin, siteId, deviceToken))
        tokenStore.saveSession(
            accessToken = response.accessToken,
            siteId = siteId,
            siteName = tokenStore.siteName.firstOrNull().orEmpty(),
            userId = response.userId,
            userName = response.userName,
            email = email,
            accessProfileName = response.accessProfileName,
        )
        return response
    }

    // ── Session state / logout ──────────────────────────────────────────────

    suspend fun getAccessToken(): String? = tokenStore.accessToken.firstOrNull()
    suspend fun getSiteId(): String? = tokenStore.siteId.firstOrNull()
    suspend fun getSiteName(): String? = tokenStore.siteName.firstOrNull()
    suspend fun getUserName(): String? = tokenStore.userName.firstOrNull()
    suspend fun getEmail(): String? = tokenStore.email.firstOrNull()

    /** End the session server-side and clear local credentials. The device stays paired. */
    suspend fun logout() {
        val token = tokenStore.accessToken.firstOrNull()
        if (token != null) {
            runCatching { api.logout("Bearer $token") }
        }
        tokenStore.clearSession()
    }

    private suspend fun requireDeviceToken(): String =
        tokenStore.deviceToken.firstOrNull() ?: error("This terminal is not paired — set up its device token first")

    private suspend fun requireAccessToken(): String =
        tokenStore.accessToken.firstOrNull() ?: error("No access token — user is not authenticated")
}
