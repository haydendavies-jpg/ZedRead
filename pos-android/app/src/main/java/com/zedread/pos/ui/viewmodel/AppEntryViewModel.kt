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
 * Resolves which screen the nav graph should start on, so a relaunch skips
 * straight back past setup/login instead of always starting cold.
 *
 * [startDestination] is null while resolving — PosNavHost waits for a value
 * before composing the NavHost, since Compose Navigation doesn't support
 * changing startDestination after the graph is created.
 */
@HiltViewModel
class AppEntryViewModel @Inject constructor(
    private val authRepo: AuthRepository,
) : ViewModel() {

    private val _startDestination = MutableStateFlow<StartDestination?>(null)
    val startDestination: StateFlow<StartDestination?> = _startDestination.asStateFlow()

    init {
        viewModelScope.launch {
            _startDestination.value = when {
                !authRepo.hasPairedDevice() -> StartDestination.DeviceSetup
                !authRepo.hasActiveSession() -> StartDestination.Login
                else -> StartDestination.RegisterGate
            }
        }
    }
}

enum class StartDestination {
    DeviceSetup,
    Login,
    RegisterGate,
}
