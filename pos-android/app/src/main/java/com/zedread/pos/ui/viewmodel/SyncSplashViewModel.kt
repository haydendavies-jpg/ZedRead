package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.repository.CatalogRepository
import com.zedread.pos.data.repository.MenuLayoutRepository
import com.zedread.pos.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Blocking (but bounded) pre-Register sync — user-testing feedback: show a
 * "syncing" status on login instead of silently warming the catalog cache
 * the first time the Register screen itself mounts (SellViewModel.init's
 * own refresh()/refreshMenuLayouts()/refreshAutoMenuSetting() calls, which
 * still run there too — this splash's own fetches just mean that first
 * mount already has a warm cache instead of a cold one, so there's no
 * double-loading UI, just a harmless redundant network refresh).
 *
 * Each step is best-effort: a failed step (e.g. no connectivity) doesn't
 * block the sync from finishing — the terminal is meant to run fully
 * offline off whatever catalog is already cached from a previous sync (see
 * ANDROID_POS_BUILD_PLAN.md's offline-first principle). [state.hadError]
 * only changes the final status line's wording, never whether [onDone]
 * eventually fires.
 */
@HiltViewModel
class SyncSplashViewModel @Inject constructor(
    private val catalogRepo: CatalogRepository,
    private val menuLayoutRepo: MenuLayoutRepository,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SyncSplashState())
    val state: StateFlow<SyncSplashState> = _state.asStateFlow()

    init { runSync() }

    private fun runSync() {
        viewModelScope.launch {
            val steps: List<Pair<String, suspend () -> Unit>> = listOf(
                "Syncing catalog…" to { catalogRepo.refresh() },
                "Syncing menu layouts…" to { menuLayoutRepo.getMenuLayouts() },
                "Syncing settings…" to { settingsRepo.getSettings() },
            )
            var hadError = false
            steps.forEachIndexed { index, (label, action) ->
                _state.value = _state.value.copy(currentLabel = label, progress = index / steps.size.toFloat())
                runCatching { action() }.onFailure { hadError = true }
            }
            _state.value = SyncSplashState(
                currentLabel = if (hadError) "Offline — continuing with cached data" else "Ready",
                progress = 1f,
                isDone = true,
                hadError = hadError,
            )
        }
    }
}

/** Splash UI state — [progress] is 0f..1f across the sync steps, driving the status bar. */
data class SyncSplashState(
    val currentLabel: String = "Starting sync…",
    val progress: Float = 0f,
    val isDone: Boolean = false,
    val hadError: Boolean = false,
)
