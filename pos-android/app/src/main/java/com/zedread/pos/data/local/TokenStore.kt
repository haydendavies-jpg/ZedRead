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

/** DataStore-backed storage for POS JWT tokens and active site. */
private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "pos_auth")

@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        private val KEY_ACCESS = stringPreferencesKey("access_token")
        private val KEY_REFRESH = stringPreferencesKey("refresh_token")
        private val KEY_SITE_ID = stringPreferencesKey("site_id")
    }

    /** Emit the current access token whenever it changes. */
    val accessToken: Flow<String?> = context.dataStore.data.map { it[KEY_ACCESS] }

    /** Emit the current refresh token whenever it changes. */
    val refreshToken: Flow<String?> = context.dataStore.data.map { it[KEY_REFRESH] }

    /** Emit the active site ID whenever it changes. */
    val siteId: Flow<String?> = context.dataStore.data.map { it[KEY_SITE_ID] }

    /** Persist all three values atomically after successful POS token exchange. */
    suspend fun save(accessToken: String, refreshToken: String, siteId: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_ACCESS] = accessToken
            prefs[KEY_REFRESH] = refreshToken
            prefs[KEY_SITE_ID] = siteId
        }
    }

    /** Wipe all stored credentials on logout or auth failure. */
    suspend fun clear() {
        context.dataStore.edit { it.clear() }
    }
}
