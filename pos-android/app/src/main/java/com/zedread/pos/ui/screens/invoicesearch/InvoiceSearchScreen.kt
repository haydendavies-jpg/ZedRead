package com.zedread.pos.ui.screens.invoicesearch

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.DateRangeFilter
import com.zedread.pos.ui.viewmodel.InvoiceSearchViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Invoice search/history — a text search box (matches an invoice's
 * INV-000001-style ref) plus dropdown filters (status, payment method,
 * date range — converted from the earlier pill-button row per user-testing
 * feedback that the pills didn't read as filters), reading the local Room
 * cache so it works offline. Each row shows the invoice's ref and its
 * synced/pending state. Entry point: the History icon on the Register
 * header, alongside Cash Up/Settings.
 */
@Composable
fun InvoiceSearchScreen(
    onBack: () -> Unit,
    viewModel: InvoiceSearchViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val results by viewModel.results.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()
    val statusFilter by viewModel.statusFilter.collectAsState()
    val paymentMethodFilter by viewModel.paymentMethodFilter.collectAsState()
    val dateRangeFilter by viewModel.dateRangeFilter.collectAsState()
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()

    Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
        PosTopBar(
            title = deviceName ?: "Register",
            subtitle = "Invoice Search",
            onBack = onBack,
            isOnline = isOnline,
            pendingCount = pendingCount,
            onSyncClick = {},
        )

        Column(modifier = Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = viewModel::setSearchQuery,
                label = { Text("Search invoice number") },
                placeholder = { Text("INV-000123") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilterDropdown(
                    modifier = Modifier.weight(1f),
                    label = "Status",
                    options = listOf(null to "All", "draft" to "Draft", "open" to "Open", "paid" to "Paid", "voided" to "Voided"),
                    selected = statusFilter,
                    onSelect = viewModel::setStatusFilter,
                )
                FilterDropdown(
                    modifier = Modifier.weight(1f),
                    label = "Payment",
                    options = listOf(null to "All", "cash" to "Cash", "card" to "Card", "voucher" to "Voucher"),
                    selected = paymentMethodFilter,
                    onSelect = viewModel::setPaymentMethodFilter,
                )
                FilterDropdown(
                    modifier = Modifier.weight(1f),
                    label = "Date range",
                    options = DateRangeFilter.entries.map { it to it.label },
                    selected = dateRangeFilter,
                    onSelect = viewModel::setDateRangeFilter,
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        HorizontalDivider(color = colors.border)

        if (results.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No invoices match these filters.", color = colors.muted)
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(results, key = { it.id }) { invoice ->
                    InvoiceRow(invoice)
                    HorizontalDivider(color = colors.border)
                }
            }
        }
    }
}

/** A labelled dropdown select — replaces the earlier horizontally-scrolling pill row for each filter. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> FilterDropdown(
    modifier: Modifier = Modifier,
    label: String,
    options: List<Pair<T, String>>,
    selected: T,
    onSelect: (T) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedText = options.firstOrNull { it.first == selected }?.second.orEmpty()

    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }, modifier = modifier) {
        OutlinedTextField(
            value = selectedText,
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (value, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { onSelect(value); expanded = false })
            }
        }
    }
}

@Composable
private fun InvoiceRow(invoice: InvoiceCacheEntity) {
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(
                invoice.ref,
                style = MaterialTheme.typography.bodyLarge,
                color = colors.text,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                listOfNotNull(
                    formatInvoiceDate(invoice.createdAtMillis),
                    invoice.status.replaceFirstChar { it.uppercase() },
                    invoice.paymentMethod?.replaceFirstChar { it.uppercase() },
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = colors.muted,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(formatCentsDollars(invoice.totalCents), style = MaterialTheme.typography.bodyLarge, color = colors.text)
            Text(
                if (invoice.isSynced) "Synced" else "Pending sync",
                style = MaterialTheme.typography.labelSmall,
                color = if (invoice.isSynced) colors.green else colors.accent,
            )
        }
    }
}

private fun formatCentsDollars(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}

private fun formatInvoiceDate(millis: Long): String =
    SimpleDateFormat("d MMM yyyy, h:mm a", Locale.getDefault()).format(Date(millis))
