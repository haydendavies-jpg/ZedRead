package com.zedread.pos.printing.driver

import android.content.Context
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

/**
 * Scriptable [PrinterDriver] test double. [sendResults] is consumed in order
 * by successive [sendDocket] calls, repeating the last entry once exhausted
 * — so a test can script e.g. "fail once, then succeed" for a retry
 * scenario with exactly two calls expected.
 */
class FakePrinterDriver(
    override val driverId: String = "fake",
    override val displayName: String = "Fake driver",
    private val discoverFlow: Flow<DiscoveredPrinter> = emptyFlow(),
    sendResults: List<PrintResult> = listOf(PrintResult.Success),
) : PrinterDriver {

    private val pendingResults = ArrayDeque(sendResults)

    var sendCallCount: Int = 0
        private set
    var discoverCallCount: Int = 0
        private set

    override fun discover(context: Context): Flow<DiscoveredPrinter> {
        discoverCallCount++
        return discoverFlow
    }

    override suspend fun sendDocket(target: SavedPrinterEntity, docket: Docket): PrintResult {
        sendCallCount++
        return if (pendingResults.size > 1) pendingResults.removeFirst() else pendingResults.first()
    }

    var cashDrawerCallCount: Int = 0
        private set

    override suspend fun openCashDrawer(target: SavedPrinterEntity): PrintResult {
        cashDrawerCallCount++
        return PrintResult.Success
    }
}
