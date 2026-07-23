package com.zedread.pos.ui.screens.printers

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.ui.viewmodel.DiscoveryUiState
import com.zedread.pos.ui.viewmodel.PrintersViewModel

/**
 * Live-updating discovery scan — first runtime permission request in this
 * app. On API 31+ (Android 12+), `BLUETOOTH_SCAN` and `BLUETOOTH_CONNECT`
 * are both runtime-dangerous permissions regardless of the `neverForLocation`
 * manifest flag — [GenericBluetoothPrinterDriver.discover] calls
 * `adapter.startDiscovery()` (needs SCAN) and reads `adapter.bondedDevices`
 * (needs CONNECT), and Epson's own SDK makes the same OS-level calls
 * internally. Below API 31, `ACCESS_FINE_LOCATION` is what classic Bluetooth
 * discovery (and Epson's SDK on those levels) needs instead; see
 * AndroidManifest.xml and PRINTER_SDK_SETUP.md for the full rationale.
 * Starts the scan once permission is settled, and always stops it
 * ([PrintersViewModel.stopDiscovery]) when the dialog leaves composition —
 * a discovery scan left running in the background would drain battery/radio
 * for no reason once the user has navigated away.
 */
@Composable
fun DiscoverPrintersDialog(
    viewModel: PrintersViewModel,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val discoveryState by viewModel.discoveryState.collectAsState()
    var permissionDenied by remember { mutableStateOf(false) }

    val requiredPermissions = remember {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (granted.values.all { it }) viewModel.startDiscovery() else permissionDenied = true
    }

    LaunchedEffect(Unit) {
        val missing = requiredPermissions.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        } else {
            viewModel.startDiscovery()
        }
    }

    DisposableEffect(Unit) {
        onDispose { viewModel.stopDiscovery() }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Discover printers") },
        text = {
            when {
                permissionDenied -> Text(
                    "Bluetooth permission is needed to scan for printers on this device. " +
                        "You can still add network printers once permission is granted.",
                )
                else -> {
                    val found = (discoveryState as? DiscoveryUiState.Scanning)?.found.orEmpty()
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(modifier = Modifier.height(18.dp))
                            Text(
                                "Scanning…",
                                style = MaterialTheme.typography.labelMedium,
                                modifier = Modifier.padding(start = 10.dp),
                            )
                        }
                        if (found.isEmpty()) {
                            Text(
                                "No printers found yet.",
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(top = 12.dp),
                            )
                        } else {
                            LazyColumn(modifier = Modifier.height(280.dp).padding(top = 8.dp)) {
                                items(found, key = { it.macAddress }) { device ->
                                    DiscoveredPrinterRow(
                                        device = device,
                                        onAdd = { viewModel.addDiscovered(device) },
                                    )
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Done") }
        },
    )
}

@Composable
private fun DiscoveredPrinterRow(device: DiscoveredPrinter, onAdd: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(device.name, style = MaterialTheme.typography.bodyMedium)
            Text(
                device.ipAddress ?: device.bluetoothAddress ?: device.macAddress,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        TextButton(onClick = onAdd) { Text("Add") }
    }
}
