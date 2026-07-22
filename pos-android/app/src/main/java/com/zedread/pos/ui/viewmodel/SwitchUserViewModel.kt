package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException
import javax.inject.Inject

/**
 * Drives the switch-user flow (change cashier without full device logout)
 * and the inline manager auth prompt (approve void/refund actions).
 *
 * Both call POST /auth/pos/pin/verify, but differently: switch-user asks for
 * a PIN alone (the backend checks it against every active user granted at
 * this site — real POS terminals don't make staff re-type an email each
 * time) and adopts the result as the terminal's active session; manager
 * auth still supplies a specific email (it's authorising a particular
 * manager, not "any staff") and never changes the active session.
 */
@HiltViewModel
class SwitchUserViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    // ── Currently signed-in operator (context shown while switching) ────────

    private val _currentUserName = MutableStateFlow<String?>(null)
    val currentUserName: StateFlow<String?> = _currentUserName.asStateFlow()

    init {
        viewModelScope.launch { _currentUserName.value = authRepo.getUserName() }
    }

    // ── Switch user state ────────────────────────────────────────────────────

    private val _switchState = MutableStateFlow<SwitchUserState>(SwitchUserState.Idle)
    val switchState: StateFlow<SwitchUserState> = _switchState.asStateFlow()

    /**
     * Verify [pin] against every active user granted at this site and adopt
     * whichever one matches as the terminal's active session.
     * [needsPinSetup] on success mirrors PinVerifyResponse.is_pin_reset_required.
     */
    fun switchOperator(pin: String) {
        _switchState.value = SwitchUserState.Loading
        viewModelScope.launch {
            runCatching { authRepo.verifyPinAndSwitch(pin) }
                .onSuccess { resp -> _switchState.value = SwitchUserState.Switched(resp.isPinResetRequired) }
                .onFailure { e -> _switchState.value = pinFailureToSwitchState(e) }
        }
    }

    fun resetSwitchState() { _switchState.value = SwitchUserState.Idle }

    // ── Inline manager auth state ─────────────────────────────────────────────

    private val _inlineAuthState = MutableStateFlow<InlineAuthState>(InlineAuthState.Idle)
    val inlineAuthState: StateFlow<InlineAuthState> = _inlineAuthState.asStateFlow()

    /**
     * Verify the manager's PIN for elevated-privilege actions (void, refund, discount).
     * Does not change the active cashier session — only confirms the manager approved.
     */
    fun authorizeManager(managerEmail: String, managerPin: String) {
        _inlineAuthState.value = InlineAuthState.Loading
        viewModelScope.launch {
            runCatching { authRepo.verifyPinOnly(managerEmail, managerPin) }
                .onSuccess { _inlineAuthState.value = InlineAuthState.Authorised }
                .onFailure { e ->
                    _inlineAuthState.value = if (e is HttpException && e.code() == 401) {
                        InlineAuthState.Denied
                    } else {
                        InlineAuthState.Error(e.message ?: "Authorisation failed")
                    }
                }
        }
    }

    fun resetInlineAuth() { _inlineAuthState.value = InlineAuthState.Idle }

    private fun pinFailureToSwitchState(e: Throwable): SwitchUserState = when {
        e is HttpException && e.code() == 401 -> SwitchUserState.InvalidPin
        e is HttpException && e.code() == 403 -> SwitchUserState.Error("No active access at this site")
        else -> SwitchUserState.Error(e.message ?: "Switch failed")
    }
}

sealed class SwitchUserState {
    object Idle : SwitchUserState()
    object Loading : SwitchUserState()
    data class Switched(val needsPinSetup: Boolean) : SwitchUserState()
    object InvalidPin : SwitchUserState()
    data class Error(val message: String) : SwitchUserState()
}

sealed class InlineAuthState {
    object Idle : InlineAuthState()
    object Loading : InlineAuthState()
    object Authorised : InlineAuthState()
    object Denied : InlineAuthState()
    data class Error(val message: String) : InlineAuthState()
}
