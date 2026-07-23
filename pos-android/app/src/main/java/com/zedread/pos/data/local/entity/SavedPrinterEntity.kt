package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * A printer this terminal has discovered and saved. Local to this device only
 * (not synced through the backend) — a multi-printer site may have different
 * registers seeing different printers on their own LAN segment, so pairing is
 * per-terminal, the same way [com.zedread.pos.data.local.TokenStore]'s device
 * pairing is.
 *
 * [macAddress] is the stable identifier a saved row is keyed on — the unique
 * index below is what makes re-discovering an already-saved printer a plain
 * IP-patching upsert rather than a duplicate row (see
 * [com.zedread.pos.data.repository.PrinterRepository.savePrinter]/
 * [com.zedread.pos.data.repository.PrinterRepository.rediscoverByMac]).
 * [lastKnownIp] is expected to drift under DHCP; [macAddress] is not.
 */
@Entity(tableName = "saved_printers", indices = [Index(value = ["mac_address"], unique = true)])
data class SavedPrinterEntity(
    @PrimaryKey val id: String,
    val name: String,
    // Matches a registered PrinterDriver.driverId — "epson_epos2" | "generic_network" | "generic_bluetooth".
    @ColumnInfo(name = "driver_id") val driverId: String,
    // "NETWORK" | "BLUETOOTH" — decides whether a failed send attempts a MAC-based IP re-discovery (network only).
    @ColumnInfo(name = "connection_type") val connectionType: String,
    @ColumnInfo(name = "mac_address") val macAddress: String,
    @ColumnInfo(name = "last_known_ip") val lastKnownIp: String?,
    val port: Int = 9100,
    @ColumnInfo(name = "is_enabled") val isEnabled: Boolean = true,
    @ColumnInfo(name = "last_seen_at_millis") val lastSeenAtMillis: Long? = null,
    @ColumnInfo(name = "last_connected_at_millis") val lastConnectedAtMillis: Long? = null,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
)
