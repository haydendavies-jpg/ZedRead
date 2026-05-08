package com.zedread.pos.printing

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.zedread.pos.data.api.LineItemDto
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Configuration controlling which printer transport is used. */
data class PrinterConfig(
    val type: PrinterType,
    /** MAC address for Bluetooth; IP address for Network. */
    val address: String,
    val networkPort: Int = 9100,
)

enum class PrinterType { BLUETOOTH, NETWORK }

/**
 * Unified print service — delegates to [BluetoothPrintService] or [NetworkPrintService]
 * based on [PrinterConfig]. Failure does NOT affect the invoice.
 */
@Singleton
class PrintService @Inject constructor(
    @ApplicationContext private val context: Context,
    private val bluetoothPrint: BluetoothPrintService,
    private val networkPrint: NetworkPrintService,
) {
    /**
     * Format and send a docket for the completed invoice.
     *
     * On Android 12+ (API 31), the caller must have requested BLUETOOTH_CONNECT at runtime
     * before calling this with a Bluetooth printer. If permission is missing the function
     * returns [PrintResult.Failure] rather than crashing.
     */
    suspend fun printDocket(
        config: PrinterConfig,
        invoiceId: String,
        siteName: String,
        lineItems: List<LineItemDto>,
        totalCents: Long,
        paymentMethod: String,
    ): PrintResult {
        if (config.type == PrinterType.BLUETOOTH && !hasBluetoothPermission()) {
            return PrintResult.Failure("BLUETOOTH_CONNECT permission not granted")
        }

        val docket = DocketFormatter.format(invoiceId, siteName, lineItems, totalCents, paymentMethod)

        return when (config.type) {
            PrinterType.BLUETOOTH -> bluetoothPrint.print(config.address, docket)
            PrinterType.NETWORK -> networkPrint.print(config.address, config.networkPort, docket)
        }
    }

    /** Check runtime Bluetooth permission on API 31+ (Android 12+). */
    private fun hasBluetoothPermission(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.BLUETOOTH_CONNECT,
            ) == PackageManager.PERMISSION_GRANTED
        } else {
            // Legacy permission is granted at install time on API < 31.
            true
        }
}
