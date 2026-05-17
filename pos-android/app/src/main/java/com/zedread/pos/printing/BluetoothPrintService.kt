package com.zedread.pos.printing

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/** Sends ESC/POS docket bytes to a paired Bluetooth printer. */
@Singleton
class BluetoothPrintService @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        // Standard SPP UUID accepted by virtually all Bluetooth thermal printers.
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }

    /**
     * Print [data] to the printer with the given MAC address.
     *
     * Requires BLUETOOTH_CONNECT permission on Android 12+ — callers must check
     * before invoking this function.
     *
     * The invoice is NOT affected if printing fails; [PrintResult.Failure] is returned
     * so the UI can offer a retry.
     */
    @SuppressLint("MissingPermission")
    suspend fun print(printerMacAddress: String, data: ByteArray): PrintResult =
        withContext(Dispatchers.IO) {
            var socket: BluetoothSocket? = null
            try {
                val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
                val adapter: BluetoothAdapter = bluetoothManager.adapter
                    ?: return@withContext PrintResult.Failure("Bluetooth not available")

                val device = adapter.getRemoteDevice(printerMacAddress)
                socket = device.createRfcommSocketToServiceRecord(SPP_UUID)

                // Cancel discovery before connecting — it significantly slows down the connection.
                adapter.cancelDiscovery()
                socket.connect()

                socket.outputStream.write(data)
                socket.outputStream.flush()

                PrintResult.Success
            } catch (e: IOException) {
                PrintResult.Failure(e.message ?: "Bluetooth print failed")
            } finally {
                runCatching { socket?.close() }
            }
        }
}
