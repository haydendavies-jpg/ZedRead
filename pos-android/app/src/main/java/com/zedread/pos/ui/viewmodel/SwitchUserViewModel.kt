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

/**
 * Drives the switch-user flow (change cashier without full device logout)
 * and the inline manager auth prompt (approve void/refund actions).
 *
 * Switch user keeps the device logged in to the same site. Only the active
 * operator changes — the site-scoped JWT is NOT replaced.
 */
@HiltViewModel
class SwitchUserViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    // ── Switch user state ────────────────────────────────────────────────────

    private val _switchState = MutableStateFlow<SwitchUserState>(SwitchUserState.Idle)
    val switchState: StateFlow<SwitchUserState> = _switchState.asStateFlow()

    /**
     * Verify the new operator's PIN to switch the active cashier.
     * On success the caller should update any displayed "current user" label.
     * The JWT and site selection are not changed.
     */
    fun switchOperator(pin: String) {
        _switchState.value = SwitchUserState.Loading
        viewModelScope.launch {
            runCatching { authRepo.verifyPin(pin) }
                .onSuccess { resp ->
                    _switchState.value = when {
                        !resp.valid -> SwitchUserState.InvalidPin
                        resp.mustReset -> SwitchUserState.MustResetPin
                        else -> SwitchUserState.Switched
                    }
                }
                .onFailure { e -> _switchState.value = SwitchUserState.Error(e.message ?: "Switch failed") }
        }
    }

    fun resetSwitchState() { _switchState.value = SwitchUserState.Idle }

    // ── Inline manager auth state ─────────────────────────────────────────────

    private val _inlineAuthState = MutableStateFlow<InlineAuthState>(InlineAuthState.Idle)
    val inlineAuthState: StateFlow<InlineAuthState> = _inlineAuthState.asStateFlow()

    /**
     * Verify the manager's PIN for elevated-privilege actions (void, refund, discount).
     * Does not switch the active cashier — only confirms the manager approved the action.
     */
    fun authorizeManager(managerPin: String) {
        _inlineAuthState.value = InlineAuthState.Loading
        viewModelScope.launch {
            runCatching { authRepo.verifyPin(managerPin) }
                .onSuccess { resp ->
                    _inlineAuthState.value = if (resp.valid) InlineAuthState.Authorised
                                             else InlineAuthState.Denied
                }
                .onFailure { e -> _inlineAuthState.value = InlineAuthState.Error(e.message ?: "Auth failed") }
        }
    }

    fun resetInlineAuth() { _inlineAuthState.value = InlineAuthState.Idle }
}

sealed class SwitchUserState {
    object Idle : SwitchUserState()
    object Loading : SwitchUserState()
    object Switched : SwitchUserState()
    object InvalidPin : SwitchUserState()
    object MustResetPin : SwitchUserState()
    data class Error(val message: String) : SwitchUserState()
}

sealed class InlineAuthState {
    object Idle : InlineAuthState()
    object Loading : InlineAuthState()
    object Authorised : InlineAuthState()
    object Denied : InlineAuthState()
    data class Error(val message: String) : InlineAuthState()
}
