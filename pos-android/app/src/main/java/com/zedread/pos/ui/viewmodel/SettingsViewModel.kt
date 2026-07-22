package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.SettingDto
import com.zedread.pos.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Drives the Settings screen: a searchable list of every setting resolved
 * for this terminal's site (GET /pos/settings), editable locally at the
 * till without touching the backend, plus an explicit per-setting
 * "Save as default" action (PUT /settings/{key}) that pushes the local edit
 * back to become the site's own backend override — gated server-side to a
 * Manager-tier-or-above access profile. A local edit that's never saved as
 * default only affects this screen's display until the next full sync; it
 * does not persist anywhere and is lost on the next [load].
 */
@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SettingsUiState>(SettingsUiState.Loading)
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    private val _search = MutableStateFlow("")
    val search: StateFlow<String> = _search.asStateFlow()

    /** key -> locally-edited value not yet pushed to the backend. */
    private val _localEdits = MutableStateFlow<Map<String, Any?>>(emptyMap())
    val localEdits: StateFlow<Map<String, Any?>> = _localEdits.asStateFlow()

    private val _savingKeys = MutableStateFlow<Set<String>>(emptySet())
    val savingKeys: StateFlow<Set<String>> = _savingKeys.asStateFlow()

    private val _saveError = MutableStateFlow<String?>(null)
    val saveError: StateFlow<String?> = _saveError.asStateFlow()

    private val _canPushDefaults = MutableStateFlow(false)
    val canPushDefaults: StateFlow<Boolean> = _canPushDefaults.asStateFlow()

    init {
        load()
        viewModelScope.launch { _canPushDefaults.value = repo.canPushDefaults() }
    }

    /** [forceRefresh] bypasses SettingsRepository's session cache — the Settings screen's manual refresh action. */
    fun load(forceRefresh: Boolean = false) {
        _state.value = SettingsUiState.Loading
        _localEdits.value = emptyMap()
        viewModelScope.launch {
            runCatching { repo.getSettings(forceRefresh = forceRefresh) }
                .onSuccess { settings -> _state.value = SettingsUiState.Ready(settings) }
                .onFailure { e -> _state.value = SettingsUiState.Error(e.message ?: "Could not load settings") }
        }
    }

    /** Client-side filter as the operator types — the same list is re-searched server-side on next load(). */
    fun setSearch(value: String) {
        _search.value = value
    }

    /** Edit a setting's value locally — does not touch the backend until [saveAsDefault]. */
    fun setLocalValue(key: String, value: Any?) {
        _localEdits.value = _localEdits.value + (key to value)
    }

    /** The value to display for [setting] — the local edit if one exists, else its resolved effective value. */
    fun displayValue(setting: SettingDto): Any? = _localEdits.value.getOrElse(setting.key) { setting.effectiveValue }

    /** True if [setting] has an unsaved local edit differing from its last-loaded effective value. */
    fun isDirty(setting: SettingDto): Boolean =
        _localEdits.value.containsKey(setting.key) && _localEdits.value[setting.key] != setting.effectiveValue

    /** Push a local edit back to become the site's backend default. */
    fun saveAsDefault(key: String) {
        val value = _localEdits.value[key] ?: return
        _savingKeys.value = _savingKeys.value + key
        _saveError.value = null
        viewModelScope.launch {
            runCatching { repo.saveAsDefault(key, value) }
                .onSuccess { updated ->
                    val current = _state.value
                    if (current is SettingsUiState.Ready) {
                        _state.value = SettingsUiState.Ready(current.settings.map { if (it.key == key) updated else it })
                    }
                    _localEdits.value = _localEdits.value - key
                }
                .onFailure { e -> _saveError.value = e.message ?: "Could not save \"$key\" as default" }
            _savingKeys.value = _savingKeys.value - key
        }
    }
}

sealed class SettingsUiState {
    object Loading : SettingsUiState()
    data class Ready(val settings: List<SettingDto>) : SettingsUiState()
    data class Error(val message: String) : SettingsUiState()
}
