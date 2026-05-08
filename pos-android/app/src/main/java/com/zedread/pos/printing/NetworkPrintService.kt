package com.zedread.pos.printing

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.Socket
import javax.inject.Inject
import javax.inject.Singleton

/** Sends ESC/POS docket bytes to a network-connected (Wi-Fi) thermal printer via raw TCP. */
@Singleton
class NetworkPrintService @Inject constructor() {

    /**
     * Print [data] to the printer at [host]:[port].
     * Standard port for raw ESC/POS over TCP is 9100.
     *
     * The invoice is NOT affected if printing fails; [PrintResult.Failure] is returned
     * so the UI can offer a retry.
     */
    suspend fun print(host: String, port: Int = 9100, data: ByteArray): PrintResult =
        withContext(Dispatchers.IO) {
            var socket: Socket? = null
            try {
                socket = Socket(host, port)
                socket.getOutputStream().apply {
                    write(data)
                    flush()
                }
                PrintResult.Success
            } catch (e: IOException) {
                PrintResult.Failure(e.message ?: "Network print failed")
            } finally {
                runCatching { socket?.close() }
            }
        }
}
