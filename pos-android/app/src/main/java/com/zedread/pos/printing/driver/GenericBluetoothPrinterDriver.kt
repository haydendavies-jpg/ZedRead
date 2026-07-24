package com.zedread.pos.printing.driver

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.BluetoothPrintService
import com.zedread.pos.printing.CASH_DRAWER_KICK_BYTES
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.DocketFormatter
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.renderedLinesToEscPosBytes
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Wraps the pre-existing raw-socket [BluetoothPrintService] (SPP-profile
 * ESC/POS printers, not brand-specific) as a [PrinterDriver] — the classic
 * Bluetooth leg of "not just Epson".
 *
 * [discover] emits this terminal's already-bonded (paired) devices
 * immediately, then whatever [BluetoothDevice.ACTION_FOUND] reports as
 * `adapter.startDiscovery()` runs — callers must already hold
 * `BLUETOOTH_SCAN` (API 31+) or `ACCESS_FINE_LOCATION` (below API 31) before
 * calling this, same runtime-permission contract [PrintersScreen] already
 * has to satisfy to reach here.
 */
@Singleton
class GenericBluetoothPrinterDriver @Inject constructor(
    private val bluetoothPrint: BluetoothPrintService,
) : PrinterDriver {

    override val driverId = "generic_bluetooth"
    override val displayName = "Bluetooth printer (generic ESC/POS)"

    @SuppressLint("MissingPermission")
    override fun discover(context: Context): Flow<DiscoveredPrinter> = callbackFlow {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter: BluetoothAdapter? = bluetoothManager.adapter
        if (adapter == null) {
            close()
            return@callbackFlow
        }

        adapter.bondedDevices?.forEach { device -> trySend(device.toDiscoveredPrinter()) }

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                if (intent.action != BluetoothDevice.ACTION_FOUND) return
                val device = intent.getBluetoothDeviceExtra() ?: return
                trySend(device.toDiscoveredPrinter())
            }
        }
        // ContextCompat.registerReceiver (not the plain 2-arg Context.registerReceiver) —
        // API 33+ requires RECEIVER_EXPORTED/RECEIVER_NOT_EXPORTED to be specified or
        // registration itself throws a SecurityException; this compat call handles that
        // (and is a no-op flag pre-33) so this driver works across the whole minSdk range.
        ContextCompat.registerReceiver(context, receiver, IntentFilter(BluetoothDevice.ACTION_FOUND), ContextCompat.RECEIVER_NOT_EXPORTED)
        adapter.startDiscovery()

        awaitClose {
            runCatching { adapter.cancelDiscovery() }
            runCatching { context.unregisterReceiver(receiver) }
        }
    }

    override suspend fun sendDocket(target: SavedPrinterEntity, docket: Docket): PrintResult {
        val bytes = docket.renderedLines?.let { renderedLinesToEscPosBytes(it) }
            ?: DocketFormatter.format(docket.invoiceId, docket.siteName, docket.lineItems, docket.totalCents, docket.paymentMethod)
        return bluetoothPrint.print(target.macAddress, bytes)
    }

    override suspend fun openCashDrawer(target: SavedPrinterEntity): PrintResult =
        bluetoothPrint.print(target.macAddress, CASH_DRAWER_KICK_BYTES)
}

@SuppressLint("MissingPermission")
private fun BluetoothDevice.toDiscoveredPrinter(): DiscoveredPrinter =
    DiscoveredPrinter(
        macAddress = address,
        ipAddress = null,
        bluetoothAddress = address,
        name = name ?: address,
        driverId = "generic_bluetooth",
        deviceType = null,
    )

@Suppress("DEPRECATION")
private fun Intent.getBluetoothDeviceExtra(): BluetoothDevice? =
    getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
