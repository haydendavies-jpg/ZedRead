package com.zedread.pos.printing.epson

import android.content.Context
import com.epson.epos2.Epos2Exception
import com.epson.epos2.discovery.Discovery
import com.epson.epos2.discovery.DiscoveryListener
import com.epson.epos2.discovery.FilterOption
import com.epson.epos2.printer.Printer
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.printing.driver.PrinterDriver
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * [PrinterDriver] for Epson thermal printers via Epson's own ePOS2 Android
 * SDK (`com.epson.epos2.*`) — proprietary, not on Maven Central. This file
 * will not compile until the real SDK AAR is added to `app/libs/`; see
 * `pos-android/PRINTER_SDK_SETUP.md`. This is expected and deliberate, not a
 * bug — isolating all `com.epson.epos2` imports to this one file/package is
 * what keeps that gap from blocking every other driver/screen in this
 * feature from compiling and being tested in the meantime.
 *
 * Epson's `Printer` class is a command *builder* — it flushes its own
 * internal buffer via `sendData()` — so unlike the generic drivers, this
 * class does not go through [com.zedread.pos.printing.DocketFormatter]'s raw
 * ESC/POS bytes at all; it reads [Docket]'s fields directly into `addText`/
 * `addFeedLine`/`addCut` calls.
 *
 * The series constant passed to the `Printer` constructor
 * ([Printer.TM_M30] below) is a placeholder — Epson receipt printers span
 * several series with different constants, and this driver has no
 * per-printer "model" field yet to pick the right one. Flagged as an open
 * follow-up once real hardware is available to test against; every printer
 * saved under this driver is currently assumed to be series-compatible with
 * [Printer.TM_M30].
 */
@Singleton
class EpsonPrinterDriver @Inject constructor(
    @ApplicationContext private val context: Context,
) : PrinterDriver {

    override val driverId = "epson_epos2"
    override val displayName = "Epson (ePOS2)"

    override fun discover(context: Context): Flow<DiscoveredPrinter> = callbackFlow {
        val filterOption = FilterOption().apply {
            deviceType = Discovery.TYPE_PRINTER
            portType = Discovery.PORTTYPE_ALL
        }
        val listener = DiscoveryListener { deviceInfo ->
            trySend(
                DiscoveredPrinter(
                    macAddress = deviceInfo.macAddress,
                    ipAddress = deviceInfo.ipAddress,
                    bluetoothAddress = deviceInfo.bdAddress,
                    name = deviceInfo.deviceName,
                    driverId = driverId,
                    deviceType = deviceInfo.deviceType.toString(),
                )
            )
        }
        try {
            Discovery.start(context, filterOption, listener)
        } catch (e: Epos2Exception) {
            close(e)
            return@callbackFlow
        }
        awaitClose { runCatching { Discovery.stop() } }
    }

    override suspend fun sendDocket(target: SavedPrinterEntity, docket: Docket): PrintResult =
        withContext(Dispatchers.IO) {
            val ip = target.lastKnownIp ?: return@withContext PrintResult.Failure("No known IP address for this printer")
            var printer: Printer? = null
            try {
                val p = Printer(Printer.TM_M30, Printer.MODEL_ANK, context)
                printer = p
                p.connect("TCP:$ip", Printer.PARAM_DEFAULT)
                p.addTextAlign(Printer.ALIGN_CENTER)
                p.addText("${docket.siteName}\n")
                p.addText("RECEIPT\n")
                p.addTextAlign(Printer.ALIGN_LEFT)
                docket.lineItems.forEach { item ->
                    p.addText("${item.quantity}x ${item.productName} — ${formatCents(item.subtotalCents)}\n")
                }
                p.addTextAlign(Printer.ALIGN_RIGHT)
                p.addText("TOTAL: ${formatCents(docket.totalCents)}\n")
                p.addText("PAID (${docket.paymentMethod.uppercase()})\n")
                p.addFeedLine(3)
                p.addCut(Printer.CUT_FEED)
                p.sendData(Printer.PARAM_DEFAULT)
                PrintResult.Success
            } catch (e: Epos2Exception) {
                PrintResult.Failure("Epson error ${e.errorStatus}")
            } finally {
                runCatching { printer?.disconnect() }
                printer?.clearCommandBuffer()
            }
        }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
