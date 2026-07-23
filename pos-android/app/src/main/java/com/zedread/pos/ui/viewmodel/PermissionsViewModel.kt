package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import com.zedread.pos.data.repository.PermissionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

/**
 * Thin per-screen wrapper around [PermissionsRepository] — like
 * [TopBarViewModel]/[SyncViewModel], every instance (one per nav
 * destination, via the default `hiltViewModel()` scoping) reads the same
 * `@Singleton` repository, so state stays consistent across screens without
 * threading it through navigation. Backs the warning badge baked into
 * [com.zedread.pos.ui.components.PosTopBar] and the app-open request in
 * [com.zedread.pos.ui.PosNavHost].
 */
@HiltViewModel
class PermissionsViewModel @Inject constructor(
    private val permissionsRepo: PermissionsRepository,
) : ViewModel() {

    val missingPermissions: StateFlow<List<String>> = permissionsRepo.missingPermissions

    fun requiredPermissions(): Array<String> = permissionsRepo.requiredPermissions()

    fun refresh() = permissionsRepo.refresh()
}
