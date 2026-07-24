package com.zedread.pos.printing.driver

import android.content.Context
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.CASH_DRAWER_KICK_BYTES
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.DocketFormatter
import com.zedread.pos.printing.NetworkPrintService
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.renderedLinesToEscPosBytes
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Wraps the pre-existing raw-socket [NetworkPrintService] (any ESC/POS
 * thermal printer listening on a raw TCP port, not brand-specific) as a
 * [PrinterDriver] — the "not just Epson" leg of discovery/saving/printing.
 *
 * [discover] returns nothing today: unlike Epson's own SDK, a raw ESC/POS
 * printer has no discovery protocol this app can piggyback on without
 * implementing its own subnet sweep (open gap — see the plan/PR notes). A
 * printer of this driver therefore can't be added via the Discover flow yet;
 * only re-discovery-by-MAC for an *already-saved* row is unaffected by this,
 * since it's this same `discover()` — a printer saved under this driver id
 * simply won't recover a moved IP automatically until that gap is closed.
 */
@Singleton
class GenericNetworkPrinterDriver @Inject constructor(
    private val networkPrint: NetworkPrintService,
) : PrinterDriver {

    override val driverId = "generic_network"
    override val displayName = "Network printer (generic ESC/POS)"

    override fun discover(context: Context): Flow<DiscoveredPrinter> = emptyFlow()

    override suspend fun sendDocket(target: SavedPrinterEntity, docket: Docket): PrintResult {
        val ip = target.lastKnownIp ?: return PrintResult.Failure("No known IP address for this printer")
        // renderedLines (from TemplateDocketRenderer) is the template-driven
        // path every real print goes through; a null falls back to
        // DocketFormatter's fixed layout, used only by the "Test print" action.
        val bytes = docket.renderedLines?.let { renderedLinesToEscPosBytes(it) }
            ?: DocketFormatter.format(docket.invoiceId, docket.siteName, docket.lineItems, docket.totalCents, docket.paymentMethod)
        return networkPrint.print(ip, target.port, bytes)
    }

    override suspend fun openCashDrawer(target: SavedPrinterEntity): PrintResult {
        val ip = target.lastKnownIp ?: return PrintResult.Failure("No known IP address for this printer")
        return networkPrint.print(ip, target.port, CASH_DRAWER_KICK_BYTES)
    }
}
