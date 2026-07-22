package com.zedread.pos.data.repository

import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.SettingDto
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Setting keys — must match app/constants/settings.py's catalog exactly. */
object SettingKeys {
    const val CASH_IN_MODE = "cash_in_mode"
    const val HIDE_VARIANCE_ON_CLOSE = "hide_variance_on_close"
}

/** Value the cash_in_mode setting resolves to when the denomination-grid variant is selected. */
const val CASH_IN_MODE_DENOMINATION = "denomination"

/**
 * Reads the POS settings catalog resolved for this terminal's own site
 * (GET /pos/settings — read-only; overrides are managed from the portal's
 * Settings page, not this app). No local cache: unlike the product catalog,
 * settings are small and read on-demand each time a screen needs them
 * (Settings screen open, CashIn/CashUp screen mount) rather than kept warm
 * for offline browsing.
 */
@Singleton
class SettingsRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /** Fetch every setting, optionally filtered server-side by [search] (key/label/category substring). */
    suspend fun getSettings(search: String? = null): List<SettingDto> =
        api.getSettings(requireBearer(), search)

    /**
     * Fetch the two settings the cash-in/cash-up screens need, returning
     * sensible defaults (bulk entry, variance shown) if the call fails —
     * a settings-fetch error should never block a cashier from opening or
     * closing the till.
     */
    suspend fun getCashSettings(): CashSettings {
        val settings = runCatching { getSettings() }.getOrDefault(emptyList())
        val cashInMode = settings.firstOrNull { it.key == SettingKeys.CASH_IN_MODE }
            ?.effectiveValue as? String ?: "bulk"
        val hideVariance = settings.firstOrNull { it.key == SettingKeys.HIDE_VARIANCE_ON_CLOSE }
            ?.effectiveValue as? Boolean ?: false
        return CashSettings(cashInMode = cashInMode, hideVarianceOnClose = hideVariance)
    }

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}

/** The two Register-relevant settings, resolved together for CashIn/CashUp screens. */
data class CashSettings(
    val cashInMode: String,
    val hideVarianceOnClose: Boolean,
)
