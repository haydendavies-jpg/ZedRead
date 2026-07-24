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
 * till without touching the backend at all — every edit stays purely local
 * (see [SettingsRepository.applyLocalOverride]) until the operator taps the
 * single "Push changes" bar (see [pushAllDefaults]), which sends every
 * outstanding edit back to become the site's own backend default in one
 * action (PUT /settings/{key} per edit) — gated server-side to a
 * Manager-tier-or-above access profile. Previously each row carried its own
 * "Save as default" button; per user-testing feedback that's now a single
 * explicit push covering every unsaved change at once, so it's unambiguous
 * that nothing reaches the backend/other devices until that's tapped. A
 * local edit that's never pushed only affects this screen's display until
 * the next full sync; it does not persist anywhere and is lost on the next
 * [load].
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

    /** True while [pushAllDefaults] is in flight — disables the push bar's button and every row's editor. */
    private val _isPushing = MutableStateFlow(false)
    val isPushing: StateFlow<Boolean> = _isPushing.asStateFlow()

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

    /**
     * Edit a setting's value — takes effect on this device immediately (see
     * [SettingsRepository.applyLocalOverride]) regardless of the operator's
     * role; does not touch the backend/other devices until [pushAllDefaults],
     * which remains role-gated.
     */
    fun setLocalValue(key: String, value: Any?) {
        _localEdits.value = _localEdits.value + (key to value)
        repo.applyLocalOverride(key, value)
    }

    /** The value to display for [setting] — the local edit if one exists, else its resolved effective value. */
    fun displayValue(setting: SettingDto): Any? = _localEdits.value.getOrElse(setting.key) { setting.effectiveValue }

    /** True if [setting] has an unsaved local edit differing from its last-loaded effective value. */
    fun isDirty(setting: SettingDto): Boolean =
        _localEdits.value.containsKey(setting.key) && _localEdits.value[setting.key] != setting.effectiveValue

    /**
     * Push every outstanding local edit back to become the site's backend
     * default, one PUT /settings/{key} call per edit. All-or-nothing isn't
     * enforced server-side (each key is its own independent row) — a
     * mid-batch failure leaves the earlier pushes applied and reports the
     * first error; the still-unpushed keys stay in [localEdits] so the
     * operator can retry just by tapping the bar again.
     */
    fun pushAllDefaults() {
        val current = _state.value
        if (current !is SettingsUiState.Ready) return
        val pending = _localEdits.value.filterKeys { key -> current.settings.any { it.key == key } }
        if (pending.isEmpty()) return
        _isPushing.value = true
        _saveError.value = null
        viewModelScope.launch {
            var settings = current.settings
            for ((key, value) in pending) {
                val result = runCatching { repo.saveAsDefault(key, value) }
                result
                    .onSuccess { updated ->
                        settings = settings.map { if (it.key == key) updated else it }
                        _localEdits.value = _localEdits.value - key
                    }
                    .onFailure { e ->
                        if (_saveError.value == null) _saveError.value = e.message ?: "Could not push \"$key\""
                    }
            }
            _state.value = SettingsUiState.Ready(settings)
            _isPushing.value = false
        }
    }
}

sealed class SettingsUiState {
    object Loading : SettingsUiState()
    data class Ready(val settings: List<SettingDto>) : SettingsUiState()
    data class Error(val message: String) : SettingsUiState()
}
