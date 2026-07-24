package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.local.entity.PrinterLocationEntity
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.data.repository.PrintConfigRepository
import com.zedread.pos.data.repository.PrinterRepository
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.driver.DiscoveredPrinter
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Live results of an in-progress [PrinterRepository.discover] scan, deduped by MAC as callbacks stream in. */
sealed class DiscoveryUiState {
    object Idle : DiscoveryUiState()
    data class Scanning(val found: List<DiscoveredPrinter>) : DiscoveryUiState()
}

/** Backs [com.zedread.pos.ui.screens.printers.PrintersScreen] — saved-printer list, discovery, and per-row actions. */
@HiltViewModel
class PrintersViewModel @Inject constructor(
    private val printerRepo: PrinterRepository,
    private val printConfigRepo: PrintConfigRepository,
) : ViewModel() {

    val savedPrinters: StateFlow<List<SavedPrinterEntity>> =
        printerRepo.observeSavedPrinters().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Every printer location synced from GET /pos/print-config — the chip options each saved printer can be assigned to. */
    val printerLocations: StateFlow<List<PrinterLocationEntity>> =
        printConfigRepo.observePrinterLocations().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Which printer location ids [printerId] is currently assigned to — for the row's chip toggles. */
    fun locationIdsForPrinter(printerId: String): StateFlow<List<String>> =
        printerRepo.observeLocationIdsForPrinter(printerId)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Toggle [locationId] on/off for [printerId] — the chip row's tap handler. */
    fun toggleLocationForPrinter(printerId: String, locationId: String, currentIds: List<String>) {
        val next = if (locationId in currentIds) currentIds - locationId else currentIds + locationId
        viewModelScope.launch { printerRepo.setPrinterLocations(printerId, next) }
    }

    private val _discoveryState = MutableStateFlow<DiscoveryUiState>(DiscoveryUiState.Idle)
    val discoveryState: StateFlow<DiscoveryUiState> = _discoveryState.asStateFlow()
    private var discoveryJob: Job? = null

    // One-shot events (test print / reconnect results) — a snackbar, not persisted state.
    private val _actionResult = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val actionResult: SharedFlow<String> = _actionResult

    fun startDiscovery() {
        discoveryJob?.cancel()
        _discoveryState.value = DiscoveryUiState.Scanning(emptyList())
        discoveryJob = viewModelScope.launch {
            // Individual drivers already swallow their own failures (see
            // PrinterRepository.discover's doc) — this is a last-resort
            // backstop so a scan can never crash the app outright, only
            // ever end early with nothing further found.
            runCatching {
                printerRepo.discover().collect { found ->
                    val current = _discoveryState.value as? DiscoveryUiState.Scanning ?: return@collect
                    if (current.found.none { it.macAddress.equals(found.macAddress, ignoreCase = true) }) {
                        _discoveryState.value = current.copy(found = current.found + found)
                    }
                }
            }.onFailure { e -> _actionResult.tryEmit("Discovery stopped: ${e.message ?: "unknown error"}") }
        }
    }

    fun stopDiscovery() {
        discoveryJob?.cancel()
        discoveryJob = null
        _discoveryState.value = DiscoveryUiState.Idle
    }

    fun addDiscovered(printer: DiscoveredPrinter) {
        viewModelScope.launch {
            printerRepo.savePrinter(printer, printer.name)
            _actionResult.tryEmit("Saved ${printer.name}")
        }
    }

    fun setEnabled(id: String, enabled: Boolean) {
        viewModelScope.launch { printerRepo.setEnabled(id, enabled) }
    }

    fun remove(id: String) {
        viewModelScope.launch { printerRepo.removePrinter(id) }
    }

    fun reconnect(printer: SavedPrinterEntity) {
        viewModelScope.launch {
            val refreshed = printerRepo.rediscoverByMac(printer)
            _actionResult.tryEmit(
                if (refreshed.lastKnownIp != printer.lastKnownIp) "Found ${printer.name} at ${refreshed.lastKnownIp}"
                else "Couldn't find ${printer.name} on the network",
            )
        }
    }

    fun testPrint(printer: SavedPrinterEntity) {
        viewModelScope.launch {
            val result = printerRepo.sendToPrinter(printer, testDocket(printer))
            _actionResult.tryEmit(
                when (result) {
                    is PrintResult.Success -> "Test print sent to ${printer.name}"
                    is PrintResult.Failure -> "Test print failed: ${result.reason}"
                },
            )
        }
    }
}

/** A single fixed line item so "Test print" doesn't depend on an in-progress sale. */
private fun testDocket(printer: SavedPrinterEntity): Docket = Docket(
    invoiceId = "TEST",
    siteName = "ZedRead",
    lineItems = listOf(
        LineItemDto(
            id = "test",
            productId = null,
            productName = "Test print — ${printer.name}",
            quantity = 1,
            unitPriceCents = 0L,
            subtotalCents = 0L,
            taxCents = 0L,
        ),
    ),
    totalCents = 0L,
    paymentMethod = "n/a",
)
