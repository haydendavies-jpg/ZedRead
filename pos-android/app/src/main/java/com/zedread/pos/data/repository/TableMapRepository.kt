package com.zedread.pos.data.repository

import com.zedread.pos.data.api.MergeTableRequestBody
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosTableMapDetailDto
import com.zedread.pos.data.api.ReserveTableRequestBody
import com.zedread.pos.data.api.SeatTableRequestBody
import com.zedread.pos.data.api.TableActionRequestBody
import com.zedread.pos.data.api.TableSessionDto
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Live floor-status reads and table/session mutations for the Tables screen
 * (Android POS Phase 4). Not cached in Room like the product catalog — the
 * floor map is a live-status view by nature (TablesViewModel polls it on an
 * interval), so a local cache would just be a second source of staleness to
 * reconcile, mirroring [MenuLayoutRepository]'s same reasoning.
 */
@Singleton
class TableMapRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /** Every published floor map for this terminal's site, with live table status. */
    suspend fun getTableMap(): List<PosTableMapDetailDto> {
        val siteId = tokenStore.siteId.firstOrNull()
            ?: error("No site ID — cannot fetch table map")
        return api.getTableMap(requireBearer(), siteId)
    }

    /** Seat a table — opens a new occupancy session. */
    suspend fun seatTable(diningTableId: String, covers: Int, serverUserId: String? = null): TableSessionDto =
        api.seatDiningTable(requireBearer(), diningTableId, SeatTableRequestBody(covers, serverUserId))

    /** Record a future reservation on a currently-open table. */
    suspend fun reserveTable(diningTableId: String, reservationLabel: String, reservedAtIso: String) {
        api.reserveDiningTable(requireBearer(), diningTableId, ReserveTableRequestBody(reservationLabel, reservedAtIso))
    }

    /** Mark a seated table's session as ordered. */
    suspend fun markOrdered(sessionId: String): TableSessionDto =
        api.markTableOrdered(requireBearer(), sessionId, TableActionRequestBody())

    /** Mark a table's session as needing its bill. */
    suspend fun markBill(sessionId: String): TableSessionDto =
        api.markTableBill(requireBearer(), sessionId, TableActionRequestBody())

    /** Bidirectionally merge two open table sessions. */
    suspend fun mergeSessions(sessionId: String, partnerSessionId: String): TableSessionDto =
        api.mergeTableSessions(requireBearer(), sessionId, MergeTableRequestBody(partnerSessionId))

    /** Clear a table — closes its session and returns it to 'open'. */
    suspend fun clearSession(sessionId: String): TableSessionDto =
        api.clearTableSession(requireBearer(), sessionId, TableActionRequestBody())

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}
