package com.zedread.pos.printing.driver

import android.content.Context
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import kotlinx.coroutines.flow.Flow

/**
 * One printer brand's implementation of discovery + sending a docket.
 *
 * Adding a new brand later is exactly one new class implementing this
 * interface plus one `@Binds @IntoSet` line in
 * [com.zedread.pos.di.PrinterModule] — nothing else in the app changes.
 * [com.zedread.pos.printing.driver.PrinterDriverRegistry] is how callers
 * resolve a [SavedPrinterEntity.driverId] back to the driver that saved it.
 */
interface PrinterDriver {

    /** Stable id stored on [SavedPrinterEntity.driverId] — e.g. "epson_epos2". */
    val driverId: String

    /** Human-readable label for the discovery/saved-printer UI. */
    val displayName: String

    /**
     * Scan for this brand's printers on the network/Bluetooth radio,
     * emitting one [DiscoveredPrinter] per device found. Implementations
     * wrap their vendor SDK's async discovery callback in a `callbackFlow`,
     * stopping the underlying scan in `awaitClose {}` when the flow is
     * cancelled (e.g. the discovery dialog is dismissed).
     */
    fun discover(context: Context): Flow<DiscoveredPrinter>

    /** Send [docket] to [target] using this brand's own printing protocol. */
    suspend fun sendDocket(target: SavedPrinterEntity, docket: Docket): PrintResult
}
