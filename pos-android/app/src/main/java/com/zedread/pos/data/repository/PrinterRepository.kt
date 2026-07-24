package com.zedread.pos.data.repository

import android.content.Context
import com.zedread.pos.data.local.dao.PrinterLocationDao
import com.zedread.pos.data.local.dao.SavedPrinterDao
import com.zedread.pos.data.local.dao.SavedPrinterLocationDao
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.printing.driver.PrinterDriverRegistry
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.withTimeoutOrNull
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

private const val REDISCOVER_TIMEOUT_MS = 8_000L

/**
 * Owns this terminal's saved printers: discovery, saving, enable/disable,
 * and sending a completed sale's docket to every enabled one — the "not
 * just Epson" brand-agnostic entry point, dispatching to whichever
 * [com.zedread.pos.printing.driver.PrinterDriver] a saved row's
 * [SavedPrinterEntity.driverId] resolves to.
 *
 * Local to this device only — see [SavedPrinterEntity]'s own doc for why
 * this isn't backend-synced.
 */
@Singleton
class PrinterRepository @Inject constructor(
    private val dao: SavedPrinterDao,
    private val locationDao: PrinterLocationDao,
    private val printerLocationDao: SavedPrinterLocationDao,
    private val driverRegistry: PrinterDriverRegistry,
    @ApplicationContext private val context: Context,
) {
    fun observeSavedPrinters(): Flow<List<SavedPrinterEntity>> = dao.observeAll()

    fun observeEnabledPrinters(): Flow<List<SavedPrinterEntity>> = dao.observeEnabled()

    /**
     * Scan for printers. Merges every registered driver's own discovery
     * flow, or just [driverId]'s if given (e.g. "Add another Epson printer"
     * without re-scanning Bluetooth too).
     *
     * Each driver's flow is individually wrapped in [catch] — a permission
     * denial, a missing native library, or any other driver-specific failure
     * (e.g. Epson's SDK or a raw `BluetoothAdapter` call throwing a
     * `SecurityException`) must not silently take down every other driver's
     * scan by cancelling the shared [merge]d flow, and must never propagate
     * as an uncaught exception out of [PrintersViewModel]'s collecting
     * coroutine — that's a hard app crash, not a graceful "printer not
     * found." A driver that fails this way simply contributes nothing to
     * this scan.
     */
    fun discover(driverId: String? = null): Flow<DiscoveredPrinter> {
        val drivers = driverId?.let { id -> listOfNotNull(driverRegistry.get(id)) } ?: driverRegistry.all()
        return drivers.map { driver -> driver.discover(context).catch { } }.merge()
    }

    /**
     * Save a printer found by [discover]. Upserts by MAC — re-adding an
     * already-saved printer (e.g. after it moved IP) patches the existing
     * row's IP/name instead of creating a duplicate, since
     * [SavedPrinterEntity.macAddress] carries a unique index.
     */
    suspend fun savePrinter(discovered: DiscoveredPrinter, name: String): SavedPrinterEntity {
        val existing = dao.findByMac(discovered.macAddress)
        val now = System.currentTimeMillis()
        val entity = SavedPrinterEntity(
            id = existing?.id ?: UUID.randomUUID().toString(),
            name = name,
            driverId = discovered.driverId,
            connectionType = if (discovered.ipAddress != null) "NETWORK" else "BLUETOOTH",
            macAddress = discovered.macAddress,
            lastKnownIp = discovered.ipAddress ?: existing?.lastKnownIp,
            port = existing?.port ?: 9100,
            isEnabled = existing?.isEnabled ?: true,
            lastSeenAtMillis = now,
            lastConnectedAtMillis = existing?.lastConnectedAtMillis,
            createdAtMillis = existing?.createdAtMillis ?: now,
        )
        dao.upsert(entity)
        return entity
    }

    suspend fun setEnabled(id: String, isEnabled: Boolean) = dao.setEnabled(id, isEnabled)

    suspend fun removePrinter(id: String) = dao.delete(id)

    /**
     * Re-locate [printer] on the network by MAC via its own driver's
     * discovery, patching [SavedPrinterEntity.lastKnownIp] in Room when
     * found within [timeoutMillis]. This is the literal "if we can't poll
     * it, discover it and get the new IP" behavior — a DHCP-assigned IP can
     * move; the MAC does not.
     */
    suspend fun rediscoverByMac(printer: SavedPrinterEntity, timeoutMillis: Long = REDISCOVER_TIMEOUT_MS): SavedPrinterEntity {
        val driver = driverRegistry.get(printer.driverId) ?: return printer
        val found = withTimeoutOrNull(timeoutMillis) {
            driver.discover(context).firstOrNull { it.macAddress.equals(printer.macAddress, ignoreCase = true) }
        }
        val ip = found?.ipAddress ?: return printer
        dao.updateIpByMac(printer.macAddress, ip, System.currentTimeMillis())
        return dao.findById(printer.id) ?: printer
    }

    /**
     * Send [docket] to one saved printer. On a first-attempt failure for a
     * NETWORK-connection printer, retries once after [rediscoverByMac] —
     * a Bluetooth-addressed printer has nothing to re-resolve, since its
     * MAC *is* its connection address, so that leg is skipped for it.
     * Never throws — printing must never block or roll back a completed
     * sale (see [com.zedread.pos.printing.PrintService]'s own doc).
     */
    suspend fun sendToPrinter(printer: SavedPrinterEntity, docket: Docket): PrintResult {
        val driver = driverRegistry.get(printer.driverId)
            ?: return PrintResult.Failure("Unknown printer driver: ${printer.driverId}")

        val first = driver.sendDocket(printer, docket)
        if (first is PrintResult.Success) {
            dao.markConnected(printer.id, System.currentTimeMillis())
            return first
        }
        if (printer.connectionType != "NETWORK") return first

        val refreshed = rediscoverByMac(printer)
        if (refreshed.lastKnownIp == printer.lastKnownIp) return first

        val retry = driver.sendDocket(refreshed, docket)
        if (retry is PrintResult.Success) dao.markConnected(refreshed.id, System.currentTimeMillis())
        return retry
    }

    /** Fan [docket] out to every currently-enabled saved printer, concurrently. */
    suspend fun sendToAllEnabled(docket: Docket): Map<SavedPrinterEntity, PrintResult> = coroutineScope {
        dao.observeEnabled().first()
            .map { printer -> async { printer to sendToPrinter(printer, docket) } }
            .awaitAll()
            .toMap()
    }

    // ── Printer-to-location assignment (local-only — see SavedPrinterLocationEntity's own doc) ──

    fun observeLocationIdsForPrinter(printerId: String): Flow<List<String>> =
        printerLocationDao.observeLocationIdsForPrinter(printerId)

    /** Replace [printerId]'s complete set of assigned printer locations — the Printers screen's chip-toggle save action. */
    suspend fun setPrinterLocations(printerId: String, locationIds: List<String>) =
        printerLocationDao.setForPrinter(printerId, locationIds)

    /**
     * Send [docket] to every enabled printer assigned to [printerLocationId],
     * [copyCount][com.zedread.pos.data.local.entity.PrinterLocationEntity.copyCount]
     * times each — the order-docket auto-print coordinator's fan-out target
     * (see SellViewModel), reusing [sendToPrinter]'s own retry/rediscover path
     * for every copy.
     */
    suspend fun sendToLocation(printerLocationId: String, docket: Docket): Map<SavedPrinterEntity, List<PrintResult>> = coroutineScope {
        val copyCount = locationDao.getAll().firstOrNull { it.id == printerLocationId }?.copyCount ?: 1
        printerLocationDao.getEnabledPrintersForLocation(printerLocationId)
            .map { printer ->
                async {
                    printer to (1..copyCount).map { sendToPrinter(printer, docket) }
                }
            }
            .awaitAll()
            .toMap()
    }

    /** Fire the cash-drawer kick pulse on every currently-enabled saved printer, concurrently — see PrinterDriver.openCashDrawer's own doc. */
    suspend fun kickDrawerOnAllEnabled(): Map<SavedPrinterEntity, PrintResult> = coroutineScope {
        dao.observeEnabled().first()
            .map { printer ->
                async {
                    val driver = driverRegistry.get(printer.driverId)
                    printer to (driver?.openCashDrawer(printer) ?: PrintResult.Failure("Unknown printer driver: ${printer.driverId}"))
                }
            }
            .awaitAll()
            .toMap()
    }
}
