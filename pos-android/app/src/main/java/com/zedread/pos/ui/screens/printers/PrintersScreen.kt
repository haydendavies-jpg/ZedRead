package com.zedread.pos.ui.screens.printers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Print
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.PrintersViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel

/**
 * Saved-printer management: enable/disable each printer independently, run a
 * network/Bluetooth discovery scan to add new ones, reconnect (re-discover
 * by MAC to recover a moved IP) or test-print an existing one, and forget a
 * printer no longer in use.
 */
@Composable
fun PrintersScreen(
    onBack: () -> Unit,
    viewModel: PrintersViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
) {
    val printers by viewModel.savedPrinters.collectAsState()
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()

    var showDiscoverDialog by remember { mutableStateOf(false) }
    var pendingRemoval by remember { mutableStateOf<SavedPrinterEntity?>(null) }
    var actionMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        viewModel.actionResult.collect { message -> actionMessage = message }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        PosTopBar(
            title = deviceName ?: "Register",
            subtitle = "Printers",
            onBack = onBack,
            isOnline = isOnline,
            pendingCount = pendingCount,
            onSyncClick = {},
        ) {
            IconButton(onClick = { showDiscoverDialog = true }) {
                Icon(Icons.Default.Add, contentDescription = "Discover printers", tint = Color.White)
            }
        }

        if (actionMessage != null) {
            Text(
                actionMessage.orEmpty(),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
        }

        if (printers.isEmpty()) {
            Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    "No printers saved yet — tap + to discover one on the network.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(32.dp),
                )
            }
        } else {
            LazyColumn(contentPadding = PaddingValues(bottom = 24.dp)) {
                items(printers, key = { it.id }) { printer ->
                    PrinterRow(
                        printer = printer,
                        onToggle = { enabled -> viewModel.setEnabled(printer.id, enabled) },
                        onReconnect = { viewModel.reconnect(printer) },
                        onTestPrint = { viewModel.testPrint(printer) },
                        onRemove = { pendingRemoval = printer },
                    )
                    HorizontalDivider()
                }
            }
        }
    }

    if (showDiscoverDialog) {
        DiscoverPrintersDialog(
            viewModel = viewModel,
            onDismiss = { showDiscoverDialog = false },
        )
    }

    val toRemove = pendingRemoval
    if (toRemove != null) {
        AlertDialog(
            onDismissRequest = { pendingRemoval = null },
            title = { Text("Remove ${toRemove.name}?") },
            text = { Text("This terminal will forget this printer. You can re-add it later via discovery.") },
            confirmButton = {
                TextButton(onClick = { viewModel.remove(toRemove.id); pendingRemoval = null }) {
                    Text("Remove")
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingRemoval = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun PrinterRow(
    printer: SavedPrinterEntity,
    onToggle: (Boolean) -> Unit,
    onReconnect: () -> Unit,
    onTestPrint: () -> Unit,
    onRemove: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(printer.name, fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodyLarge)
                Text(
                    printerSubtitle(printer),
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.muted,
                )
            }
            Switch(checked = printer.isEnabled, onCheckedChange = onToggle)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onReconnect) {
                Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.padding(end = 4.dp))
                Text("Reconnect")
            }
            TextButton(onClick = onTestPrint) {
                Icon(Icons.Default.Print, contentDescription = null, modifier = Modifier.padding(end = 4.dp))
                Text("Test print")
            }
            IconButton(onClick = onRemove) {
                Icon(Icons.Default.Delete, contentDescription = "Remove printer")
            }
        }
    }
}

private fun printerSubtitle(printer: SavedPrinterEntity): String {
    val address = printer.lastKnownIp ?: printer.macAddress
    return "${printer.driverId} · $address"
}
