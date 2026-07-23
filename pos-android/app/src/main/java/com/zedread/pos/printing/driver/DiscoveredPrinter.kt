package com.zedread.pos.printing.driver

/**
 * One printer found by a [PrinterDriver]'s network/Bluetooth scan, before
 * it's been saved. [macAddress] is what a save keys on — see
 * [com.zedread.pos.data.local.entity.SavedPrinterEntity]'s doc.
 */
data class DiscoveredPrinter(
    val macAddress: String,
    val ipAddress: String?,
    val bluetoothAddress: String?,
    val name: String,
    val driverId: String,
    val deviceType: String? = null,
)
