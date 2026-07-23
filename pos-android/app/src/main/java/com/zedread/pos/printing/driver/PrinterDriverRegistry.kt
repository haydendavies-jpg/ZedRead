package com.zedread.pos.printing.driver

import javax.inject.Inject
import javax.inject.Singleton

/**
 * Resolves a [com.zedread.pos.data.local.entity.SavedPrinterEntity.driverId]
 * (or a brand picked in the discovery UI) back to its [PrinterDriver].
 *
 * [drivers] is a Hilt multibinding — the first `Set<PrinterDriver>` used
 * anywhere in this codebase (everywhere else uses plain constructor
 * injection), wired up in [com.zedread.pos.di.PrinterModule]. That's what
 * lets a future brand register itself with no change to this class.
 */
@Singleton
class PrinterDriverRegistry @Inject constructor(
    private val drivers: Set<@JvmSuppressWildcards PrinterDriver>,
) {
    fun get(driverId: String): PrinterDriver? = drivers.firstOrNull { it.driverId == driverId }

    fun all(): List<PrinterDriver> = drivers.toList()
}
