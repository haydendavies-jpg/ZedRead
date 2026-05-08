package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.SiteDto
import com.zedread.pos.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Manages auth state across Login, SiteSelector, PinEntry, and PinSet screens. */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    // ── Login state ─────────────────────────────────────────────────────────

    private val _loginUiState = MutableStateFlow<LoginUiState>(LoginUiState.Idle)
    val loginUiState: StateFlow<LoginUiState> = _loginUiState.asStateFlow()

    /** Cached email used in [selectSite] (avoids re-entering on site selector screen). */
    private var pendingEmail: String = ""
    private var pendingPassword: String = ""

    /** Call on login form submission. On success, [loginUiState] emits [LoginUiState.Sites]. */
    fun login(email: String, password: String) {
        pendingEmail = email
        pendingPassword = password
        _loginUiState.value = LoginUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.login(email, password) }
                .onSuccess { sites -> _loginUiState.value = LoginUiState.Sites(sites) }
                .onFailure { e -> _loginUiState.value = LoginUiState.Error(e.message ?: "Login failed") }
        }
    }

    // ── Site selection state ─────────────────────────────────────────────────

    private val _siteUiState = MutableStateFlow<SiteUiState>(SiteUiState.Idle)
    val siteUiState: StateFlow<SiteUiState> = _siteUiState.asStateFlow()

    /** Expose the sites list from the last successful login. */
    fun sitesFromLogin(): List<SiteDto> =
        (loginUiState.value as? LoginUiState.Sites)?.sites ?: emptyList()

    /** Exchange credentials + chosen site for a site-scoped JWT and persist it. */
    fun selectSite(siteId: String) {
        _siteUiState.value = SiteUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.selectSite(pendingEmail, pendingPassword, siteId) }
                .onSuccess { _siteUiState.value = SiteUiState.Done }
                .onFailure { e -> _siteUiState.value = SiteUiState.Error(e.message ?: "Site selection failed") }
        }
    }

    // ── PIN state ────────────────────────────────────────────────────────────

    private val _pinUiState = MutableStateFlow<PinUiState>(PinUiState.Idle)
    val pinUiState: StateFlow<PinUiState> = _pinUiState.asStateFlow()

    /** Verify the entered PIN. Emits [PinUiState.MustReset] when a change is required. */
    fun verifyPin(pin: String) {
        _pinUiState.value = PinUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.verifyPin(pin) }
                .onSuccess { resp ->
                    _pinUiState.value = when {
                        !resp.valid -> PinUiState.Invalid
                        resp.mustReset -> PinUiState.MustReset
                        else -> PinUiState.Verified
                    }
                }
                .onFailure { e -> _pinUiState.value = PinUiState.Error(e.message ?: "PIN check failed") }
        }
    }

    /** Set or change the operator's PIN. */
    fun setPin(currentPin: String?, newPin: String) {
        _pinUiState.value = PinUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.setPin(currentPin, newPin) }
                .onSuccess { _pinUiState.value = PinUiState.Set }
                .onFailure { e -> _pinUiState.value = PinUiState.Error(e.message ?: "PIN set failed") }
        }
    }

    /** Reset PIN state so the screen can react to a fresh attempt. */
    fun resetPinState() { _pinUiState.value = PinUiState.Idle }
}

// ── UI state sealed classes ──────────────────────────────────────────────────

sealed class LoginUiState {
    object Idle : LoginUiState()
    object Loading : LoginUiState()
    data class Sites(val sites: List<SiteDto>) : LoginUiState()
    data class Error(val message: String) : LoginUiState()
}

sealed class SiteUiState {
    object Idle : SiteUiState()
    object Loading : SiteUiState()
    object Done : SiteUiState()
    data class Error(val message: String) : SiteUiState()
}

sealed class PinUiState {
    object Idle : PinUiState()
    object Loading : PinUiState()
    object Verified : PinUiState()
    object Invalid : PinUiState()
    object MustReset : PinUiState()
    object Set : PinUiState()
    data class Error(val message: String) : PinUiState()
}
