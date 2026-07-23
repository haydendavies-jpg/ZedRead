package com.zedread.pos.data.repository

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Single source of truth for this app's runtime-dangerous permissions.
 * `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT` (API 31+) or `ACCESS_FINE_LOCATION`
 * (below API 31) are what printer discovery needs — see
 * [com.zedread.pos.printing.driver.GenericBluetoothPrinterDriver]'s doc for
 * why each is required at the OS level regardless of the manifest's
 * `neverForLocation` flag.
 *
 * OS-level grant state has no Flow API of its own, so [missingPermissions]
 * is a plain [MutableStateFlow] that only changes when [refresh] is called —
 * callers must call it after a permission-request result and on app
 * resume (the user may have granted/revoked it from system Settings while
 * away), not just once at construction.
 */
@Singleton
class PermissionsRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    /** This app's required runtime-dangerous permissions, given the device's own API level. */
    fun requiredPermissions(): Array<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }

    private val _missingPermissions = MutableStateFlow(computeMissing())
    val missingPermissions: StateFlow<List<String>> = _missingPermissions.asStateFlow()

    /** Re-check current grant status against the OS. Call after a permission-request result and on app resume. */
    fun refresh() {
        _missingPermissions.value = computeMissing()
    }

    private fun computeMissing(): List<String> =
        requiredPermissions().filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
}

/** Plain-language label for a permission constant — never show a raw `android.permission.*` string to a cashier. */
fun permissionLabel(permission: String): String = when (permission) {
    Manifest.permission.BLUETOOTH_SCAN -> "Bluetooth — scan for printers"
    Manifest.permission.BLUETOOTH_CONNECT -> "Bluetooth — connect to printers"
    Manifest.permission.ACCESS_FINE_LOCATION -> "Location — required for Bluetooth scanning on this Android version"
    else -> permission.substringAfterLast('.')
}
