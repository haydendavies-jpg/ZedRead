package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.repository.RegisterSessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
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
) : ViewModel() {

    private val _gateState = MutableStateFlow<RegisterGateState>(RegisterGateState.Checking)
    val gateState: StateFlow<RegisterGateState> = _gateState.asStateFlow()

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
                    _gateState.value = RegisterGateState.Error(e.message ?: "Could not check register session")
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
}

sealed class RegisterGateState {
    object Checking : RegisterGateState()
    object NeedsCashIn : RegisterGateState()
    data class Open(val sessionId: String) : RegisterGateState()
    data class Error(val message: String) : RegisterGateState()
}

sealed class CashInState {
    object Idle : CashInState()
    object Loading : CashInState()
    object Done : CashInState()
    data class Error(val message: String) : CashInState()
}
