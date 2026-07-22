package com.zedread.pos.data.repository

import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosMenuLayoutDto
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Fetches the site's currently-active published menu layouts (Phase 3 —
 * Menu Studio -> POS integration depth) for the Register header's menu
 * selector. Not cached in Room like the product catalog — a terminal
 * offline for an entire daypart window has bigger problems than a stale
 * menu-selector list, and re-fetching on every Register screen load keeps
 * "which layout is the current schedule default" accurate without a cache
 * invalidation story of its own.
 */
@Singleton
class MenuLayoutRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /**
     * Fetch every currently-active published layout visible to this terminal's site.
     *
     * Throws on network error — callers fall back to showing no menu
     * selector (the full, unfiltered catalog) rather than blocking the sale.
     */
    suspend fun getMenuLayouts(): List<PosMenuLayoutDto> {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot fetch menu layouts")
        val siteId = tokenStore.siteId.firstOrNull()
            ?: error("No site ID — cannot fetch menu layouts")
        return api.getMenuLayouts("Bearer $token", siteId)
    }
}
