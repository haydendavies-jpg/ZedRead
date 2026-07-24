package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.RegisterSessionDto
import com.zedread.pos.data.local.TokenStore
import com.zedread.pos.data.repository.AuthRepository
import com.zedread.pos.data.repository.CASH_IN_MODE_DENOMINATION
import com.zedread.pos.data.repository.CashSettings
import com.zedread.pos.data.repository.OutboxRepository
import com.zedread.pos.data.repository.PrintConfigRepository
import com.zedread.pos.data.repository.PrinterRepository
import com.zedread.pos.data.repository.RegisterSessionRepository
import com.zedread.pos.data.repository.SettingsRepository
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.DocketRenderContext
import com.zedread.pos.printing.RenderedLine
import com.zedread.pos.printing.TemplateDocketRenderer
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject

/**
 * Gates entry to the Register screen on this terminal having an open
 * register (till) session, and drives the start-of-day cash-in form that
 * opens one. POST /invoices rejects with 400 until a session is open, so
 * this check runs on every app launch/resume before a sale can start.
 *
 * Offline write-queue: a network failure on open/close queues the event to
 * [OutboxRepository] instead (see [openSession]/[closeSession]) and
 * proceeds optimistically — the operator isn't blocked from starting or
 * ending a shift just because the device is offline. A queued close can't
 * show a real expected-cash/variance figure (that's computed server-side
 * from committed cash payments, some of which may themselves still be
 * queued) — the cash-up screen shows "pending sync" instead, see
 * [CashUpState.ClosedPendingSync].
 */
@HiltViewModel
class RegisterSessionViewModel @Inject constructor(
    private val repo: RegisterSessionRepository,
    private val authRepository: AuthRepository,
    private val settingsRepository: SettingsRepository,
    private val outboxRepo: OutboxRepository,
    private val printerRepo: PrinterRepository,
    private val printConfigRepo: PrintConfigRepository,
    private val templateRenderer: TemplateDocketRenderer,
    private val tokenStore: TokenStore,
) : ViewModel() {

    // One-shot print-result events for a snackbar — same pattern as PrintersViewModel.actionResult.
    private val _printResult = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val printResult: SharedFlow<String> = _printResult

    /**
     * Print the start-of-day cash-in slip ('cash_in_slip' template) to every
     * enabled saved printer — manual action, staff-initiated shift boundary,
     * matching "Print receipt"'s own manual/unsplit convention rather than
     * the order-docket auto-print's per-location behaviour.
     */
    fun printCashInSlip(session: RegisterSessionDto) {
        viewModelScope.launch {
            val ctx = DocketRenderContext(
                companyProfile = printConfigRepo.getCompanyProfile(),
                openingCashCents = session.openingCashCents,
                countedBy = session.openedByName,
                dateTime = registerPrintDateTimeNow(),
            )
            val renderedLines = templateRenderer.renderByType("cash_in_slip", ctx)
            if (renderedLines == null) {
                _printResult.tryEmit("No cash-in slip template found")
                return@launch
            }
            sendRegisterDocketToAllEnabled(renderedLines)
        }
    }

    /** Print the end-of-day register summary ('register_summary' template) to every enabled saved printer. */
    fun printRegisterSummary(session: RegisterSessionDto) {
        viewModelScope.launch {
            val ctx = DocketRenderContext(
                companyProfile = printConfigRepo.getCompanyProfile(),
                openingCashCents = session.openingCashCents,
                closingCashCents = session.closingCashCents,
                varianceCents = session.varianceCents,
                paymentBreakdownCents = session.paymentBreakdownCents ?: emptyMap(),
                countedBy = session.closedByName ?: "",
                dateTime = registerPrintDateTimeNow(),
            )
            val renderedLines = templateRenderer.renderByType("register_summary", ctx)
            if (renderedLines == null) {
                _printResult.tryEmit("No register summary template found")
                return@launch
            }
            sendRegisterDocketToAllEnabled(renderedLines)
        }
    }

    private suspend fun sendRegisterDocketToAllEnabled(renderedLines: List<RenderedLine>) {
        val docket = Docket(
            invoiceId = "",
            siteName = tokenStore.siteName.firstOrNull() ?: "",
            lineItems = emptyList(),
            totalCents = 0,
            paymentMethod = "",
            renderedLines = renderedLines,
        )
        val results = printerRepo.sendToAllEnabled(docket)
        _printResult.tryEmit(if (results.isEmpty()) "No enabled printers" else "Printed to ${results.size} printer(s)")
    }

    private val _gateState = MutableStateFlow<RegisterGateState>(RegisterGateState.Checking)
    val gateState: StateFlow<RegisterGateState> = _gateState.asStateFlow()

    // Defaults (full denomination count, variance shown) match the settings
    // catalog's own defaults in app/constants/settings.py — used until
    // loadCashSettings() resolves, and if that call fails, so a settings
    // outage never blocks opening or closing the till.
    private val _cashSettings = MutableStateFlow(CashSettings(cashInMode = CASH_IN_MODE_DENOMINATION, hideVarianceOnClose = false))
    val cashSettings: StateFlow<CashSettings> = _cashSettings.asStateFlow()

    /** Resolve the cash-in-mode / hide-variance-on-close settings for this site. */
    fun loadCashSettings() {
        viewModelScope.launch {
            _cashSettings.value = settingsRepository.getCashSettings()
        }
    }

    fun checkCurrentSession() {
        _gateState.value = RegisterGateState.Checking
        viewModelScope.launch {
            runCatching { repo.getCurrentSession() }
                .onSuccess { session ->
                    _gateState.value = when {
                        session != null -> RegisterGateState.Open(session.id)
                        else -> offlineOpenGateStateOrNeedsCashIn()
                    }
                }
                .onFailure { e ->
                    // A 401 here means the terminal's session was revoked server-side
                    // (logout elsewhere, device unpaired, license lapsed) — the POS
                    // access token itself no longer expires on its own, so retrying
                    // the same call would just 401 forever. Clear local credentials
                    // and send the operator back to login instead.
                    if (e is HttpException && e.code() == 401) {
                        authRepository.logout()
                        _gateState.value = RegisterGateState.SessionExpired
                    } else if (e is IOException) {
                        // Can't even reach the server to check — if a start-of-day
                        // open is queued from earlier in this offline stretch, don't
                        // block selling on a round trip that isn't happening yet.
                        _gateState.value = offlineOpenGateStateOrNeedsCashIn()
                    } else {
                        _gateState.value = RegisterGateState.Error(e.message ?: "Could not check register session")
                    }
                }
        }
    }

    private suspend fun offlineOpenGateStateOrNeedsCashIn(): RegisterGateState {
        val queued = outboxRepo.latestQueuedOpenSessionWithoutClose()
        return if (queued != null) RegisterGateState.Open(OFFLINE_SESSION_ID_PREFIX + queued.clientRef) else RegisterGateState.NeedsCashIn
    }

    private val _cashInState = MutableStateFlow<CashInState>(CashInState.Idle)
    val cashInState: StateFlow<CashInState> = _cashInState.asStateFlow()

    /** Open the till with [openingCashCents] counted in at the start of the shift. */
    fun openSession(openingCashCents: Long) {
        _cashInState.value = CashInState.Loading
        val openedAtIso = OffsetDateTime.now().toString()
        viewModelScope.launch {
            runCatching { repo.openSession(openedAtIso, openingCashCents, clientRef = null) }
                .onSuccess { session -> _cashInState.value = CashInState.Done(session) }
                .onFailure { e ->
                    if (e is IOException) {
                        outboxRepo.enqueueOpenSession(openedAtIso, openingCashCents)
                        _cashInState.value = CashInState.DoneOffline
                    } else {
                        _cashInState.value = CashInState.Error(e.message ?: "Failed to open the till")
                    }
                }
        }
    }

    private val _cashUpState = MutableStateFlow<CashUpState>(CashUpState.Loading)
    val cashUpState: StateFlow<CashUpState> = _cashUpState.asStateFlow()

    /** Load this terminal's open session so end-of-day cash-up has something to close. */
    fun loadForCashUp() {
        _cashUpState.value = CashUpState.Loading
        viewModelScope.launch {
            runCatching { repo.getCurrentSession() }
                .onSuccess { session ->
                    _cashUpState.value = if (session != null) CashUpState.Ready(session) else offlineCashUpStateOrError()
                }
                .onFailure { e ->
                    _cashUpState.value = if (e is IOException) {
                        offlineCashUpStateOrError()
                    } else {
                        CashUpState.Error(e.message ?: "Could not load the till session")
                    }
                }
        }
    }

    private suspend fun offlineCashUpStateOrError(): CashUpState {
        val queued = outboxRepo.latestQueuedOpenSessionWithoutClose()
            ?: return CashUpState.Error("No open till session to close")
        return CashUpState.ReadyOffline(queued.clientRef, queued.openingCashCents, queued.openedAtIso)
    }

    /** Close the till with [closingCashCents] counted in at the end of the shift. [sessionId] is the real server id. */
    fun closeSession(sessionId: String, closingCashCents: Long) {
        _cashUpState.value = CashUpState.Submitting
        val closedAtIso = OffsetDateTime.now().toString()
        viewModelScope.launch {
            runCatching { repo.closeSession(sessionId, closedAtIso, closingCashCents, clientRef = null) }
                .onSuccess { result -> _cashUpState.value = CashUpState.Closed(result) }
                .onFailure { e ->
                    if (e is IOException) {
                        outboxRepo.enqueueCloseSession(
                            sessionId = sessionId,
                            openClientRef = null,
                            closedAtIso = closedAtIso,
                            closingCashCents = closingCashCents,
                        )
                        _cashUpState.value = CashUpState.ClosedPendingSync(closingCashCents)
                    } else {
                        _cashUpState.value = CashUpState.Error(e.message ?: "Failed to close the till")
                    }
                }
        }
    }

    /**
     * Close a till whose own opening never synced ([CashUpState.ReadyOffline]) — there's no real
     * session id to call the online close endpoint with, so this queues directly rather than
     * attempting (and failing) an online call first.
     */
    fun closeOfflineSession(openClientRef: String, closingCashCents: Long) {
        _cashUpState.value = CashUpState.Submitting
        val closedAtIso = OffsetDateTime.now().toString()
        viewModelScope.launch {
            outboxRepo.enqueueCloseSession(
                sessionId = null,
                openClientRef = openClientRef,
                closedAtIso = closedAtIso,
                closingCashCents = closingCashCents,
            )
            _cashUpState.value = CashUpState.ClosedPendingSync(closingCashCents)
        }
    }
}

/** Prefix marking a [RegisterGateState.Open.sessionId] as a not-yet-synced offline open's client_ref, not a real server id. */
const val OFFLINE_SESSION_ID_PREFIX = "offline:"

/** Device-local date/time formatted for a print template's DATE_TIME field — mirrors SellViewModel's own printDateTimeNow(). */
private fun registerPrintDateTimeNow(): String =
    DateTimeFormatter.ofPattern("d MMM yyyy, h:mm a").format(java.time.LocalDateTime.now())

sealed class RegisterGateState {
    object Checking : RegisterGateState()
    object NeedsCashIn : RegisterGateState()
    data class Open(val sessionId: String) : RegisterGateState()
    data class Error(val message: String) : RegisterGateState()
    /** The terminal's session was revoked server-side — credentials are already cleared. */
    object SessionExpired : RegisterGateState()
}

sealed class CashInState {
    object Idle : CashInState()
    object Loading : CashInState()
    /** Opened successfully — carries the session so the screen can offer a "Print slip" action before continuing to Register. */
    data class Done(val session: RegisterSessionDto) : CashInState()
    /** Opened successfully, but only locally — queued to the outbox because the device is offline, so there's no session to print from. */
    object DoneOffline : CashInState()
    data class Error(val message: String) : CashInState()
}

sealed class CashUpState {
    object Loading : CashUpState()
    data class Ready(val session: RegisterSessionDto) : CashUpState()
    /** The till's own opening hasn't synced yet — no real [RegisterSessionDto] exists to show. */
    data class ReadyOffline(val openClientRef: String, val openingCashCents: Long, val openedAtIso: String) : CashUpState()
    object Submitting : CashUpState()
    data class Closed(val session: RegisterSessionDto) : CashUpState()
    /** Closed locally and queued — no server-computed expected-cash/variance figures exist yet. */
    data class ClosedPendingSync(val closingCashCents: Long) : CashUpState()
    data class Error(val message: String) : CashUpState()
}
