package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.local.TokenStore
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/** Feeds the persistent [com.zedread.pos.ui.components.PosTopBar] this terminal's own configured name, shared across every screen that renders it. */
@HiltViewModel
class TopBarViewModel @Inject constructor(
    tokenStore: TokenStore,
) : ViewModel() {

    val deviceName: StateFlow<String?> =
        tokenStore.deviceName.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)
}
