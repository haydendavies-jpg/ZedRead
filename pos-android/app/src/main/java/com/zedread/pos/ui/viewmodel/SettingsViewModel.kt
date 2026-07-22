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
 * Drives the read-only Settings screen: a searchable list of every setting
 * resolved for this terminal's site (GET /pos/settings). Overrides are
 * managed from the management portal's Settings page, not this app — the
 * POS side only ever reads.
 */
@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SettingsUiState>(SettingsUiState.Loading)
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    private val _search = MutableStateFlow("")
    val search: StateFlow<String> = _search.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.value = SettingsUiState.Loading
        viewModelScope.launch {
            runCatching { repo.getSettings() }
                .onSuccess { settings -> _state.value = SettingsUiState.Ready(settings) }
                .onFailure { e -> _state.value = SettingsUiState.Error(e.message ?: "Could not load settings") }
        }
    }

    /** Client-side filter as the operator types — the same list is re-searched server-side on next load(). */
    fun setSearch(value: String) {
        _search.value = value
    }
}

sealed class SettingsUiState {
    object Loading : SettingsUiState()
    data class Ready(val settings: List<SettingDto>) : SettingsUiState()
    data class Error(val message: String) : SettingsUiState()
}
