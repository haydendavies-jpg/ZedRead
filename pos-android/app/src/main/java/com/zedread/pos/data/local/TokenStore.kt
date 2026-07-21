package com.zedread.pos.data.local

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * DataStore-backed storage for this terminal's device pairing and the active
 * operator session.
 *
 * Device pairing (deviceToken) and the operator session are separate
 * lifecycles: [clearSession] runs on logout and leaves deviceToken alone —
 * the physical terminal stays paired to its site even when nobody is
 * signed in, matching the "device stays pinned unless explicitly re-paired"
 * architecture decision in ANDROID_POS_BUILD_PLAN.md.
 */
private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "pos_auth")

@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        private val KEY_DEVICE_TOKEN = stringPreferencesKey("device_token")
        private val KEY_ACCESS = stringPreferencesKey("access_token")
        private val KEY_SITE_ID = stringPreferencesKey("site_id")
        private val KEY_SITE_NAME = stringPreferencesKey("site_name")
        private val KEY_USER_ID = stringPreferencesKey("user_id")
        private val KEY_USER_NAME = stringPreferencesKey("user_name")
        private val KEY_EMAIL = stringPreferencesKey("email")
        private val KEY_ACCESS_PROFILE_NAME = stringPreferencesKey("access_profile_name")
    }

    /** Emit this terminal's paired device token, or null if never paired. */
    val deviceToken: Flow<String?> = context.dataStore.data.map { it[KEY_DEVICE_TOKEN] }

    /** Emit the current access token whenever it changes. */
    val accessToken: Flow<String?> = context.dataStore.data.map { it[KEY_ACCESS] }

    /** Emit the active site ID whenever it changes. */
    val siteId: Flow<String?> = context.dataStore.data.map { it[KEY_SITE_ID] }

    /** Emit the active site's display name. */
    val siteName: Flow<String?> = context.dataStore.data.map { it[KEY_SITE_NAME] }

    /** Emit the signed-in operator's display name. */
    val userName: Flow<String?> = context.dataStore.data.map { it[KEY_USER_NAME] }

    /** Emit the signed-in operator's email — needed to re-verify their PIN. */
    val email: Flow<String?> = context.dataStore.data.map { it[KEY_EMAIL] }

    /** Persist the device pairing. Independent of any operator session. */
    suspend fun pairDevice(deviceToken: String) {
        context.dataStore.edit { prefs -> prefs[KEY_DEVICE_TOKEN] = deviceToken }
    }

    /** Persist a freshly issued operator session after login/site-select/switch. */
    suspend fun saveSession(
        accessToken: String,
        siteId: String,
        siteName: String,
        userId: String,
        userName: String,
        email: String,
        accessProfileName: String,
    ) {
        context.dataStore.edit { prefs ->
            prefs[KEY_ACCESS] = accessToken
            prefs[KEY_SITE_ID] = siteId
            prefs[KEY_SITE_NAME] = siteName
            prefs[KEY_USER_ID] = userId
            prefs[KEY_USER_NAME] = userName
            prefs[KEY_EMAIL] = email
            prefs[KEY_ACCESS_PROFILE_NAME] = accessProfileName
        }
    }

    /** Clear the operator session on logout — keeps the device pairing intact. */
    suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(KEY_ACCESS)
            prefs.remove(KEY_SITE_ID)
            prefs.remove(KEY_SITE_NAME)
            prefs.remove(KEY_USER_ID)
            prefs.remove(KEY_USER_NAME)
            prefs.remove(KEY_EMAIL)
            prefs.remove(KEY_ACCESS_PROFILE_NAME)
        }
    }
}
