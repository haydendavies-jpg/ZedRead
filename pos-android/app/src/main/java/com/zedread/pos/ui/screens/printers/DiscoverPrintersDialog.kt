package com.zedread.pos.ui.screens.printers

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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.ui.viewmodel.DiscoveryUiState
import com.zedread.pos.ui.viewmodel.PermissionsViewModel
import com.zedread.pos.ui.viewmodel.PrintersViewModel

/**
 * Live-updating discovery scan — requires the same runtime permissions
 * [com.zedread.pos.ui.components.PosTopBar]'s warning badge already tracks
 * (see [PermissionsViewModel]/[com.zedread.pos.data.repository.PermissionsRepository]
 * for the full per-API-level rationale: `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`
 * on API 31+, `ACCESS_FINE_LOCATION` below). The app already asks for these
 * once on launch (see [com.zedread.pos.ui.PosNavHost]'s doc) — this is the
 * contextual fallback for a cashier who denied that, or whose grant was
 * later revoked, without making them go find the top-bar badge first.
 * Starts the scan once permission is settled, and always stops it
 * ([PrintersViewModel.stopDiscovery]) when the dialog leaves composition —
 * a discovery scan left running in the background would drain battery/radio
 * for no reason once the user has navigated away.
 */
@Composable
fun DiscoverPrintersDialog(
    viewModel: PrintersViewModel,
    onDismiss: () -> Unit,
    permissionsViewModel: PermissionsViewModel = hiltViewModel(),
) {
    val discoveryState by viewModel.discoveryState.collectAsState()
    var permissionDenied by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        permissionsViewModel.refresh()
        if (granted.values.all { it }) viewModel.startDiscovery() else permissionDenied = true
    }

    LaunchedEffect(Unit) {
        permissionsViewModel.refresh()
        val missing = permissionsViewModel.missingPermissions.value
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
