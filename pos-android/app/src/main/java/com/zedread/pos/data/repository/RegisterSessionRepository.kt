package com.zedread.pos.data.repository

import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.RegisterSessionCloseRequest
import com.zedread.pos.data.api.RegisterSessionDto
import com.zedread.pos.data.api.RegisterSessionOpenRequest
import com.zedread.pos.data.local.TokenStore
import kotlinx.coroutines.flow.firstOrNull
import retrofit2.HttpException
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages this terminal's register (till) session — per-device, not per-user:
 * two terminals at one site run independent cash sessions, and switching the
 * active operator does not open or close one.
 */
@Singleton
class RegisterSessionRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
) {
    /** Fetch the open session for this terminal, or null if the till is closed. */
    suspend fun getCurrentSession(): RegisterSessionDto? {
        val response = api.getCurrentRegisterSession(requireBearer())
        if (!response.isSuccessful) throw HttpException(response)
        return response.body()
    }

    /** Open a new session (start-of-day cash-in) with the device-local time now. */
    suspend fun openSession(openingCashCents: Long, clientRef: String? = null): RegisterSessionDto =
        api.openRegisterSession(
            requireBearer(),
            RegisterSessionOpenRequest(
                openedAt = OffsetDateTime.now().toString(),
                openingCashCents = openingCashCents,
                clientRef = clientRef,
            ),
        )

    /** Open a session using an already-known device-local opened-at time — the outbox worker replaying a queued open. */
    suspend fun openSession(openedAtIso: String, openingCashCents: Long, clientRef: String?): RegisterSessionDto =
        api.openRegisterSession(
            requireBearer(),
            RegisterSessionOpenRequest(openedAt = openedAtIso, openingCashCents = openingCashCents, clientRef = clientRef),
        )

    /** Close a session (end-of-day cash-up) with the device-local time now. */
    suspend fun closeSession(sessionId: String, closingCashCents: Long, clientRef: String? = null): RegisterSessionDto =
        api.closeRegisterSession(
            requireBearer(),
            sessionId,
            RegisterSessionCloseRequest(
                closedAt = OffsetDateTime.now().toString(),
                closingCashCents = closingCashCents,
                clientRef = clientRef,
            ),
        )

    /** Close a session using an already-known device-local closed-at time — the outbox worker replaying a queued close. */
    suspend fun closeSession(sessionId: String, closedAtIso: String, closingCashCents: Long, clientRef: String?): RegisterSessionDto =
        api.closeRegisterSession(
            requireBearer(),
            sessionId,
            RegisterSessionCloseRequest(closedAt = closedAtIso, closingCashCents = closingCashCents, clientRef = clientRef),
        )

    private suspend fun requireBearer(): String {
        val token = tokenStore.accessToken.firstOrNull() ?: error("No access token")
        return "Bearer $token"
    }
}
