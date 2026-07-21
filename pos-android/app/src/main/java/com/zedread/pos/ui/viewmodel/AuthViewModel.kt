package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.SiteOptionDto
import com.zedread.pos.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException
import javax.inject.Inject

/** Manages auth state across Login, SiteSelector, and PinSet screens. */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    // ── Login / site selection state ────────────────────────────────────────
    //
    // A single state machine covers both screens since selectSite() returns
    // the exact same outcome shape as login() — the backend's site-token step
    // is just login() finalized with a chosen site.

    private val _loginUiState = MutableStateFlow<LoginUiState>(LoginUiState.Idle)
    val loginUiState: StateFlow<LoginUiState> = _loginUiState.asStateFlow()

    /** Cached credentials, re-sent by selectSite() — the backend issues no interim token. */
    private var pendingEmail: String = ""
    private var pendingPassword: String = ""

    fun login(email: String, password: String) {
        pendingEmail = email
        pendingPassword = password
        _loginUiState.value = LoginUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.login(email, password) }
                .onSuccess { outcome -> _loginUiState.value = outcome.toUiState() }
                .onFailure { e -> _loginUiState.value = LoginUiState.Error(loginErrorMessage(e)) }
        }
    }

    fun selectSite(siteId: String) {
        _loginUiState.value = LoginUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.selectSite(pendingEmail, pendingPassword, siteId) }
                .onSuccess { outcome -> _loginUiState.value = outcome.toUiState() }
                .onFailure { e -> _loginUiState.value = LoginUiState.Error(loginErrorMessage(e)) }
        }
    }

    private fun AuthRepository.LoginOutcome.toUiState(): LoginUiState = when (this) {
        is AuthRepository.LoginOutcome.NeedsSiteSelection -> LoginUiState.NeedsSiteSelection(sites)
        is AuthRepository.LoginOutcome.Authenticated -> LoginUiState.Authenticated(needsPinSetup)
    }

    fun resetLoginState() { _loginUiState.value = LoginUiState.Idle }

    // ── First-time / forced PIN set state ───────────────────────────────────

    private val _pinSetUiState = MutableStateFlow<PinSetUiState>(PinSetUiState.Idle)
    val pinSetUiState: StateFlow<PinSetUiState> = _pinSetUiState.asStateFlow()

    fun setPin(pin: String) {
        _pinSetUiState.value = PinSetUiState.Loading
        viewModelScope.launch {
            runCatching { authRepo.setPin(pin) }
                .onSuccess { _pinSetUiState.value = PinSetUiState.Done }
                .onFailure { e -> _pinSetUiState.value = PinSetUiState.Error(e.message ?: "Could not save PIN") }
        }
    }
}

// ── UI state sealed classes ──────────────────────────────────────────────────

sealed class LoginUiState {
    object Idle : LoginUiState()
    object Loading : LoginUiState()
    data class NeedsSiteSelection(val sites: List<SiteOptionDto>) : LoginUiState()
    data class Authenticated(val needsPinSetup: Boolean) : LoginUiState()
    data class Error(val message: String) : LoginUiState()
}

sealed class PinSetUiState {
    object Idle : PinSetUiState()
    object Loading : PinSetUiState()
    object Done : PinSetUiState()
    data class Error(val message: String) : PinSetUiState()
}

/** Maps common login failure codes to operator-facing copy. */
internal fun loginErrorMessage(e: Throwable): String = when {
    e is HttpException && e.code() == 401 -> "Incorrect email or password"
    e is HttpException && e.code() == 403 && e.isNoAvailableSeats() ->
        "No available license seats for this site — ask an admin to release one, or purchase more"
    e is HttpException && e.code() == 403 -> "This account has no active access at this site"
    else -> e.message ?: "Something went wrong. Please try again."
}

/**
 * True when a 403's response body mentions "seat" — distinguishes the
 * license-seat-exhausted case from a plain no-access-grant 403, both of
 * which share the same HTTP status code.
 */
private fun HttpException.isNoAvailableSeats(): Boolean =
    runCatching { response()?.errorBody()?.string() }
        .getOrNull()
        ?.contains("seat", ignoreCase = true) == true
