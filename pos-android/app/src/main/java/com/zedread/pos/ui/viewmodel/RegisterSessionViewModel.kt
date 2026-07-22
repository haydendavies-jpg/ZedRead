package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.RegisterSessionDto
import com.zedread.pos.data.repository.AuthRepository
import com.zedread.pos.data.repository.CashSettings
import com.zedread.pos.data.repository.RegisterSessionRepository
import com.zedread.pos.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException
import javax.inject.Inject

/**
 * Gates entry to the Register screen on this terminal having an open
 * register (till) session, and drives the start-of-day cash-in form that
 * opens one. POST /invoices rejects with 400 until a session is open, so
 * this check runs on every app launch/resume before a sale can start.
 */
@HiltViewModel
class RegisterSessionViewModel @Inject constructor(
    private val repo: RegisterSessionRepository,
    private val authRepository: AuthRepository,
    private val settingsRepository: SettingsRepository,
) : ViewModel() {

    private val _gateState = MutableStateFlow<RegisterGateState>(RegisterGateState.Checking)
    val gateState: StateFlow<RegisterGateState> = _gateState.asStateFlow()

    // Defaults (bulk entry, variance shown) match the settings catalog's own
    // defaults in app/constants/settings.py — used until loadCashSettings()
    // resolves, and if that call fails, so a settings outage never blocks
    // opening or closing the till.
    private val _cashSettings = MutableStateFlow(CashSettings(cashInMode = "bulk", hideVarianceOnClose = false))
    val cashSettings: StateFlow<CashSettings> = _cashSettings.asStateFlow()

    /** Resolve the cash-in-mode / hide-variance-on-close settings for this site. */
    fun loadCashSettings() {
        viewModelScope.launch {
            _cashSettings.value = settingsRepository.getCashSettings()
        }
    }

    fun checkCurrentSession() {
        _gateState.value = RegisterGateState.Checking
        viewModelScope.launch {
            runCatching { repo.getCurrentSession() }
                .onSuccess { session ->
                    _gateState.value = if (session != null) {
                        RegisterGateState.Open(session.id)
                    } else {
                        RegisterGateState.NeedsCashIn
                    }
                }
                .onFailure { e ->
                    // A 401 here means the terminal's session was revoked server-side
                    // (logout elsewhere, device unpaired, license lapsed) — the POS
                    // access token itself no longer expires on its own, so retrying
                    // the same call would just 401 forever. Clear local credentials
                    // and send the operator back to login instead.
                    if (e is HttpException && e.code() == 401) {
                        authRepository.logout()
                        _gateState.value = RegisterGateState.SessionExpired
                    } else {
                        _gateState.value = RegisterGateState.Error(e.message ?: "Could not check register session")
                    }
                }
        }
    }

    private val _cashInState = MutableStateFlow<CashInState>(CashInState.Idle)
    val cashInState: StateFlow<CashInState> = _cashInState.asStateFlow()

    /** Open the till with [openingCashCents] counted in at the start of the shift. */
    fun openSession(openingCashCents: Long) {
        _cashInState.value = CashInState.Loading
        viewModelScope.launch {
            runCatching { repo.openSession(openingCashCents) }
                .onSuccess { _cashInState.value = CashInState.Done }
                .onFailure { e -> _cashInState.value = CashInState.Error(e.message ?: "Failed to open the till") }
        }
    }

    private val _cashUpState = MutableStateFlow<CashUpState>(CashUpState.Loading)
    val cashUpState: StateFlow<CashUpState> = _cashUpState.asStateFlow()

    /** Load this terminal's open session so end-of-day cash-up has something to close. */
    fun loadForCashUp() {
        _cashUpState.value = CashUpState.Loading
        viewModelScope.launch {
            runCatching { repo.getCurrentSession() }
                .onSuccess { session ->
                    _cashUpState.value = if (session != null) {
                        CashUpState.Ready(session)
                    } else {
                        CashUpState.Error("No open till session to close")
                    }
                }
                .onFailure { e -> _cashUpState.value = CashUpState.Error(e.message ?: "Could not load the till session") }
        }
    }

    /** Close the till with [closingCashCents] counted in at the end of the shift. */
    fun closeSession(sessionId: String, closingCashCents: Long) {
        _cashUpState.value = CashUpState.Submitting
        viewModelScope.launch {
            runCatching { repo.closeSession(sessionId, closingCashCents) }
                .onSuccess { result -> _cashUpState.value = CashUpState.Closed(result) }
                .onFailure { e -> _cashUpState.value = CashUpState.Error(e.message ?: "Failed to close the till") }
        }
    }
}

sealed class RegisterGateState {
    object Checking : RegisterGateState()
    object NeedsCashIn : RegisterGateState()
    data class Open(val sessionId: String) : RegisterGateState()
    data class Error(val message: String) : RegisterGateState()
    /** The terminal's session was revoked server-side — credentials are already cleared. */
    object SessionExpired : RegisterGateState()
}

sealed class CashInState {
    object Idle : CashInState()
    object Loading : CashInState()
    object Done : CashInState()
    data class Error(val message: String) : CashInState()
}

sealed class CashUpState {
    object Loading : CashUpState()
    data class Ready(val session: RegisterSessionDto) : CashUpState()
    object Submitting : CashUpState()
    data class Closed(val session: RegisterSessionDto) : CashUpState()
    data class Error(val message: String) : CashUpState()
}
