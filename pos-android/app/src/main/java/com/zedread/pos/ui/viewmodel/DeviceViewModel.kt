package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Drives one-time device setup: entering the device_token a portal admin
 * issued via POST /pos-devices when they registered this physical terminal.
 * Pairing is local-only (no network call) — the token is verified by the
 * backend on the next login attempt.
 */
@HiltViewModel
class DeviceViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<DevicePairState>(DevicePairState.Idle)
    val state: StateFlow<DevicePairState> = _state.asStateFlow()

    fun pair(deviceToken: String) {
        val trimmed = deviceToken.trim()
        if (trimmed.isEmpty()) {
            _state.value = DevicePairState.Error("Enter this terminal's device token")
            return
        }
        _state.value = DevicePairState.Loading
        viewModelScope.launch {
            authRepo.pairDevice(trimmed)
            _state.value = DevicePairState.Done
        }
    }
}

sealed class DevicePairState {
    object Idle : DevicePairState()
    object Loading : DevicePairState()
    object Done : DevicePairState()
    data class Error(val message: String) : DevicePairState()
}
