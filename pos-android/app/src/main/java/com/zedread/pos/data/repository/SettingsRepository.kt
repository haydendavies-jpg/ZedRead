package com.zedread.pos.data.repository

import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.SettingDto
import com.zedread.pos.data.api.SettingUpdateRequest
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Setting keys — must match app/constants/settings.py's catalog exactly. */
object SettingKeys {
    const val CASH_IN_MODE = "cash_in_mode"
    const val HIDE_VARIANCE_ON_CLOSE = "hide_variance_on_close"
    const val AUTO_MENU_ENABLED = "auto_menu_enabled"
}

/**
 * POS access profile names allowed to push a "Save as default" settings
 * override — mirrors app/routes/settings.py's
 * _POS_SETTINGS_WRITE_PROFILE_NAMES exactly. Purely a UI nicety (hide/show
 * the button); the backend is the real gate and re-checks this on every
 * PUT /settings/{key} call regardless of what the client shows.
 */
private val POS_SETTINGS_WRITE_PROFILES = setOf("Master User", "Admin", "Manager")

/** Value the cash_in_mode setting resolves to when the denomination-grid variant is selected. */
const val CASH_IN_MODE_DENOMINATION = "denomination"

/**
 * Reads the POS settings catalog resolved for this terminal's own site
 * (GET /pos/settings — read-only; overrides are managed from the portal's
 * Settings page, not this app).
 *
 * Cached in-memory after the first fetch (this session) — per user-testing
 * feedback that the app was re-hitting the server on essentially every
 * screen open, settings now sync once and serve from that cache thereafter,
 * same as the product catalog's own Room cache. [getSettings]'s
 * [forceRefresh] is the escape hatch (a manual refresh action on the
 * Settings screen); [saveAsDefault] patches the cache in place from its own
 * response so a save is reflected immediately without a second round trip.
 * The cache is keyed on "no search term" only — a server-side search
 * query always bypasses it, though no current caller actually passes one
 * (SettingsViewModel filters client-side against the unfiltered load).
 */
@Singleton
class SettingsRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    @Volatile
    private var cachedSettings: List<SettingDto>? = null

    /** Fetch every setting, optionally filtered server-side by [search] (key/label/category substring). */
    suspend fun getSettings(search: String? = null, forceRefresh: Boolean = false): List<SettingDto> {
        if (search == null && !forceRefresh) {
            cachedSettings?.let { return it }
        }
        val fetched = api.getSettings(requireBearer(), search)
        if (search == null) cachedSettings = fetched
        return fetched
    }

    /**
     * Push a locally-edited setting back to become this site's backend
     * override ("Save as default"). The backend re-verifies the operator's
     * access profile itself — [canPushDefaults] only decides whether to
     * offer the button. Patches the in-memory cache from the response so
     * the next [getSettings] call (e.g. a later Settings screen open, or
     * CashIn/CashUp reading cash_in_mode) sees the saved value without
     * re-fetching.
     */
    suspend fun saveAsDefault(key: String, value: Any?): SettingDto {
        val siteId = tokenStore.siteId.firstOrNull() ?: error("No site ID — cannot save setting")
        val updated = api.updateSetting(requireBearer(), key, SettingUpdateRequest(value = value, siteId = siteId))
        cachedSettings = cachedSettings?.map { if (it.key == key) updated else it }
        return updated
    }

    /**
     * Apply an edit to THIS device only, immediately — patches the
     * in-memory cache's effectiveValue without touching the backend at all.
     *
     * Previously a setting edited from the Settings screen only ever
     * affected that screen's own display: [setLocalValue]-style edits lived
     * entirely in SettingsViewModel's local state, so a Staff-tier operator
     * (who can't [saveAsDefault] — see canPushDefaults) had no way to
     * actually change how the till behaved this shift, even though the
     * toggle visibly flipped. Every other reader of [getSettings] (this
     * cache) — CashIn/CashUp's cash_in_mode, the Register's auto_menu_enabled
     * check — now sees this change immediately, same as a pushed default
     * would look locally, just without persisting past this session/until
     * overwritten by the next non-forced [getSettings] call after a real sync.
     */
    fun applyLocalOverride(key: String, value: Any?) {
        cachedSettings = cachedSettings?.map { if (it.key == key) it.copy(effectiveValue = value) else it }
    }

    /** True if the signed-in operator's POS access profile may push settings back to the backend. */
    suspend fun canPushDefaults(): Boolean =
        tokenStore.accessProfileName.firstOrNull() in POS_SETTINGS_WRITE_PROFILES

    /**
     * Fetch the two settings the cash-in/cash-up screens need, returning
     * sensible defaults (full denomination count, variance shown) if the
     * call fails — a settings-fetch error should never block a cashier from
     * opening or closing the till.
     */
    suspend fun getCashSettings(): CashSettings {
        val settings = runCatching { getSettings() }.getOrDefault(emptyList())
        val cashInMode = settings.firstOrNull { it.key == SettingKeys.CASH_IN_MODE }
            ?.effectiveValue as? String ?: CASH_IN_MODE_DENOMINATION
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
