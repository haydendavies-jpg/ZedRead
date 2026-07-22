package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.local.TokenStore
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/**
 * Backs the persistent top navigation bar (README-tables-floormap.md's "Top
 * Navigation Bar (persistent)" section, Android POS Phase 4) — currently
 * only the signed-in operator's name, for the avatar's initial letter.
 * Deliberately its own tiny ViewModel rather than reading [TokenStore]
 * directly from the composable: [MainScaffold] is instantiated once per tab
 * (Register, Tables), and routing it through `hiltViewModel()` keeps that
 * composable free of a manual DataStore/Flow wiring for a single field.
 */
@HiltViewModel
class TopNavViewModel @Inject constructor(
    tokenStore: TokenStore,
) : ViewModel() {

    /** Signed-in operator's display name, or null before it's loaded. */
    val userName: StateFlow<String?> =
        tokenStore.userName.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)
}
