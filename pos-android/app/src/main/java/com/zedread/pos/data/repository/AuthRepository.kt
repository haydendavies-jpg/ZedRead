package com.zedread.pos.data.repository

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.zedread.pos.data.api.LoginRequest
import com.zedread.pos.data.api.PinSetRequest
import com.zedread.pos.data.api.PinVerifyRequest
import com.zedread.pos.data.api.PinVerifyResponseDto
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosLoginResponseDto
import com.zedread.pos.data.api.SiteOptionDto
import com.zedread.pos.data.api.SiteTokenRequest
import com.zedread.pos.data.local.TokenStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Handles all authentication operations: self-service device claiming, login, PIN, logout. */
@Singleton
class AuthRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
    @ApplicationContext private val context: Context,
) {
    /** Outcome of a login()/selectSite() call — exactly one branch applies. */
    sealed class LoginOutcome {
        /** Token issued. [needsPinSetup] mirrors POSLoginResponse.is_pin_reset_required. */
        data class Authenticated(val needsPinSetup: Boolean) : LoginOutcome()

        /** The user has grants on more than one site — must call selectSite() next. */
        data class NeedsSiteSelection(val sites: List<SiteOptionDto>) : LoginOutcome()
    }

    // ── Login ────────────────────────────────────────────────────────────────

    /** True once an operator session is persisted (survives app relaunch). */
    suspend fun hasActiveSession(): Boolean = tokenStore.accessToken.firstOrNull() != null

    /**
     * Step 1: authenticate with email/password.
     *
     * No device setup required — this terminal sends its own previously
     * claimed device_token (null on first-ever login) and a device_name
     * fallback, and the backend claims or re-pairs a device seat inline.
     */
    suspend fun login(email: String, password: String): LoginOutcome {
        val deviceToken = tokenStore.deviceToken.firstOrNull()
        val response = api.login(LoginRequest(email, password, deviceName(), deviceToken, hardwareId()))
        return handleLoginResponse(response, email)
    }

    /** Step 2 (multi-site only): finalize login by choosing one of the offered sites. */
    suspend fun selectSite(email: String, password: String, siteId: String): LoginOutcome {
        val deviceToken = tokenStore.deviceToken.firstOrNull()
        val response = api.selectSite(
            SiteTokenRequest(email, password, deviceName(), deviceToken, hardwareId(), siteId)
        )
        return handleLoginResponse(response, email)
    }

    /** Human-readable fallback name for a brand-new device claim — the model name is good enough. */
    private fun deviceName(): String = Build.MODEL ?: "Android Terminal"

    /**
     * This terminal's stable OS-level identifier, read fresh from the OS each call rather than
     * cached locally — it survives an app reinstall (unlike deviceToken), so the backend can
     * recognise this physical device even after its stored device_token was wiped. Deliberately
     * not the device's MAC address: modern Android randomizes the Wi-Fi MAC per network for
     * privacy and blocks apps from reading the real hardware MAC without root, so it would never
     * reliably match across reinstalls. Null only on the (extremely rare) device/OS combination
     * where ANDROID_ID itself is unavailable — the backend already treats a missing hardware_id
     * as "can't fall back, use device_token alone".
     */
    private fun hardwareId(): String? =
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)

    private suspend fun handleLoginResponse(
        response: PosLoginResponseDto,
        email: String,
    ): LoginOutcome {
        val availableSites = response.availableSites
        if (availableSites != null) return LoginOutcome.NeedsSiteSelection(availableSites)

        val accessToken = response.accessToken
            ?: error("Login response carried neither a token nor available_sites")
        response.deviceToken?.let { tokenStore.saveDeviceToken(it) }
        tokenStore.saveSession(
            accessToken = accessToken,
            siteId = response.siteId ?: error("Login response missing site_id"),
            siteName = response.siteName.orEmpty(),
            userId = response.userId ?: error("Login response missing user_id"),
            userName = response.userName.orEmpty(),
            email = email,
            accessProfileName = response.accessProfileName.orEmpty(),
            deviceName = response.deviceName,
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
     * Verify [pin] and adopt the returned session as the active one — used
     * for switch-user, where a different operator takes over the terminal
     * with a PIN alone (no email prompt) or the currently signed-in operator
     * re-confirms their own identity. The backend resolves the account by
     * checking every active user granted at this site against the PIN.
     */
    suspend fun verifyPinAndSwitch(pin: String): PinVerifyResponseDto {
        val response = callVerifyPin(email = null, pin = pin)
        val siteId = tokenStore.siteId.firstOrNull() ?: error("No active site")
        tokenStore.saveSession(
            accessToken = response.accessToken,
            siteId = siteId,
            siteName = tokenStore.siteName.firstOrNull().orEmpty(),
            userId = response.userId,
            userName = response.userName,
            email = response.email.orEmpty(),
            accessProfileName = response.accessProfileName,
        )
        return response
    }

    /**
     * Verify a specific [email]'s PIN without changing the terminal's active
     * session — used by the inline manager-authorisation prompt (approve
     * void/refund/discount), which only needs a yes/no on "did a manager
     * approve this", not to log that manager in as the active operator.
     */
    suspend fun verifyPinOnly(email: String, pin: String): PinVerifyResponseDto =
        callVerifyPin(email = email, pin = pin)

    private suspend fun callVerifyPin(email: String?, pin: String): PinVerifyResponseDto {
        val siteId = tokenStore.siteId.firstOrNull() ?: error("No active site")
        val deviceToken = tokenStore.deviceToken.firstOrNull()
        return api.verifyPin(PinVerifyRequest(email, pin, siteId, deviceToken))
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

    private suspend fun requireAccessToken(): String =
        tokenStore.accessToken.firstOrNull() ?: error("No access token — user is not authenticated")
}
