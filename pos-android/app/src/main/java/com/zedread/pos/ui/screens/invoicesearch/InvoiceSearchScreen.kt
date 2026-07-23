package com.zedread.pos.ui.screens.invoicesearch

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.DateRangeFilter
import com.zedread.pos.ui.viewmodel.InvoiceSearchViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Invoice search/history — a text search box (matches an invoice's
 * INV-000001-style ref) plus dropdown filters (status, payment method,
 * date range — converted from the earlier pill-button row per user-testing
 * feedback that the pills didn't read as filters), reading the local Room
 * cache so it works offline. Rendered as a table: a fixed column-header row
 * (Invoice #/Payment/Date & Status/Total), rows that expand in place on tap
 * to show their line items (GET /invoices/{id}/line-items, fetched once and
 * cached — see InvoiceSearchViewModel.toggleExpand), a per-row Refund action
 * for a paid-and-not-already-refunded invoice, and a totals row pinned below
 * the (scrollable) list rather than inside it, so it's always visible.
 * Entry point: the History icon on the Register header, alongside Cash Up/
 * Settings.
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
    val expandedInvoiceId by viewModel.expandedInvoiceId.collectAsState()
    val lineItemsByInvoice by viewModel.lineItemsByInvoice.collectAsState()
    val lineItemsLoading by viewModel.lineItemsLoading.collectAsState()
    val refundTarget by viewModel.refundTarget.collectAsState()
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
            // A sale syncs within milliseconds under normal conditions (the
            // outbox requests an immediate drain the moment it's queued —
            // see OutboxRepository.enqueueSale) — a brand-new unsynced row
            // is the ordinary in-flight case, not a problem, so it shouldn't
            // read as one. "Pending sync" only appears once a row has stayed
            // unsynced for PENDING_GRACE_MILLIS; [nowMillis] ticks on a timer
            // so a row already on screen flips over on its own once that
            // threshold passes, without needing a fresh DB emission.
            var nowMillis by remember { mutableLongStateOf(System.currentTimeMillis()) }
            LaunchedEffect(Unit) {
                while (true) {
                    delay(30_000)
                    nowMillis = System.currentTimeMillis()
                }
            }
            InvoiceTableHeader()
            HorizontalDivider(color = colors.border)
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(results, key = { it.id }) { invoice ->
                    InvoiceRow(
                        invoice = invoice,
                        nowMillis = nowMillis,
                        expanded = invoice.id == expandedInvoiceId,
                        lineItems = lineItemsByInvoice[invoice.id],
                        isLoadingLineItems = invoice.id in lineItemsLoading,
                        onToggleExpand = { viewModel.toggleExpand(invoice.id) },
                        onRefund = { viewModel.openRefundDialog(invoice) },
                    )
                    HorizontalDivider(color = colors.border)
                }
            }
            // Frozen totals row — outside the LazyColumn (not one of its
            // items), so it never scrolls out of view, per user-testing
            // feedback that the invoice table should always show a total.
            InvoiceTableFooter(totalCents = results.sumOf { it.totalCents })
        }
    }

    val target = refundTarget
    if (target != null) {
        val isRefunding by viewModel.isRefunding.collectAsState()
        val refundError by viewModel.refundError.collectAsState()
        RefundDialog(
            invoice = target,
            lineItems = lineItemsByInvoice[target.id],
            isLoadingLineItems = target.id in lineItemsLoading,
            isSubmitting = isRefunding,
            errorMessage = refundError,
            onDismiss = viewModel::dismissRefundDialog,
            onConfirm = { lineItemIds -> viewModel.submitRefund(lineItemIds) },
        )
    }
}

/** How long an unsynced invoice is treated as "still syncing" before the list flags it as genuinely pending. */
private const val PENDING_GRACE_MILLIS = 5 * 60 * 1000L

// Column widths shared between InvoiceTableHeader and each InvoiceRow so
// headers line up with their data exactly.
private val REF_COLUMN_WEIGHT = 1.3f
private val PAYMENT_COLUMN_WEIGHT = 1f
private val DATE_COLUMN_WEIGHT = 1.4f
private val TOTAL_COLUMN_WIDTH = 90.dp
private val ACTIONS_COLUMN_WIDTH = 84.dp

@Composable
private fun InvoiceTableHeader() {
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            "Invoice #",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = colors.muted,
            modifier = Modifier.weight(REF_COLUMN_WEIGHT),
        )
        Text(
            "Payment",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = colors.muted,
            modifier = Modifier.weight(PAYMENT_COLUMN_WEIGHT),
        )
        Text(
            "Date & status",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = colors.muted,
            modifier = Modifier.weight(DATE_COLUMN_WEIGHT),
        )
        Text(
            "Total",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = colors.muted,
            textAlign = TextAlign.End,
            modifier = Modifier.width(TOTAL_COLUMN_WIDTH),
        )
        Spacer(Modifier.width(ACTIONS_COLUMN_WIDTH))
    }
}

/** Pinned below the (scrollable) invoice list — sums every currently-filtered row's total, not just what's on screen. */
@Composable
private fun InvoiceTableFooter(totalCents: Long) {
    val colors = LocalZedReadColors.current
    HorizontalDivider(color = colors.border)
    Row(
        modifier = Modifier.fillMaxWidth().background(colors.surface).padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Total", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge, color = colors.text)
        Text(formatCentsDollars(totalCents), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge, color = colors.text)
    }
}

/**
 * A labelled dropdown select — replaces the earlier horizontally-scrolling
 * pill row for each filter. A plain [DropdownMenu] anchored to a clickable
 * bordered row, not [androidx.compose.material3.ExposedDropdownMenuBox] —
 * that component's own `ExposedDropdownMenu` doesn't resolve against this
 * project's pinned Compose BOM (2024.12.01 / Material3 1.3.1), confirmed by
 * a real CI compile failure; this is the same proven pattern already used
 * by MenuSelectorRow/SettingsScreen's SingleSelectEditor elsewhere in the app.
 */
@Composable
private fun <T> FilterDropdown(
    modifier: Modifier = Modifier,
    label: String,
    options: List<Pair<T, String>>,
    selected: T,
    onSelect: (T) -> Unit,
) {
    val colors = LocalZedReadColors.current
    var expanded by remember { mutableStateOf(false) }
    val selectedText = options.firstOrNull { it.first == selected }?.second.orEmpty()

    Column(modifier = modifier) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = colors.faint)
        Box {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(8.dp))
                    .clickable { expanded = true }
                    .padding(horizontal = 12.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(selectedText, style = MaterialTheme.typography.bodyMedium, color = colors.text)
                Text("▾", color = colors.muted)
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { (value, text) ->
                    DropdownMenuItem(text = { Text(text) }, onClick = { onSelect(value); expanded = false })
                }
            }
        }
    }
}

@Composable
private fun InvoiceRow(
    invoice: InvoiceCacheEntity,
    nowMillis: Long,
    expanded: Boolean,
    lineItems: List<LineItemDto>?,
    isLoadingLineItems: Boolean,
    onToggleExpand: () -> Unit,
    onRefund: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    // A paid invoice not already refunded is the only kind eligible — mirrors
    // create_refund()'s own 409 rules (must be paid, must not already be
    // refunded) so the button is never offered only to fail server-side.
    val canRefund = invoice.status == "paid" && !invoice.isRefunded

    Column(modifier = Modifier.fillMaxWidth().clickable(onClick = onToggleExpand)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                invoice.ref,
                style = MaterialTheme.typography.bodyLarge,
                color = colors.text,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(REF_COLUMN_WEIGHT),
            )
            Text(
                invoice.paymentMethod?.replaceFirstChar { it.uppercase() } ?: "—",
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(PAYMENT_COLUMN_WEIGHT),
            )
            Column(modifier = Modifier.weight(DATE_COLUMN_WEIGHT)) {
                Text(formatInvoiceDate(invoice.createdAtMillis), style = MaterialTheme.typography.bodySmall, color = colors.muted)
                Text(
                    invoice.status.replaceFirstChar { it.uppercase() } + if (invoice.isRefunded) " · Refunded" else "",
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.muted,
                )
                // A fresh unsynced row (still within the grace window) is the
                // ordinary in-flight case — see the LazyColumn's own doc — so
                // it reads as "Syncing…", not an alarming "Pending sync";
                // that label is reserved for a row that's genuinely stuck.
                val isStale = !invoice.isSynced && (nowMillis - invoice.createdAtMillis) >= PENDING_GRACE_MILLIS
                when {
                    invoice.isSynced -> {}
                    isStale -> Text("Pending sync", style = MaterialTheme.typography.labelSmall, color = colors.accent)
                    else -> Text("Syncing…", style = MaterialTheme.typography.labelSmall, color = colors.muted)
                }
            }
            Text(
                formatCentsDollars(invoice.totalCents),
                style = MaterialTheme.typography.bodyLarge,
                color = colors.text,
                textAlign = TextAlign.End,
                modifier = Modifier.width(TOTAL_COLUMN_WIDTH),
            )
            Row(
                modifier = Modifier.width(ACTIONS_COLUMN_WIDTH),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (canRefund) {
                    TextButton(onClick = onRefund, contentPadding = PaddingValues(horizontal = 4.dp)) {
                        Text("Refund", style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text(if (expanded) "▾" else "▸", color = colors.muted)
            }
        }

        if (expanded) {
            InvoiceLineItemsPanel(lineItems = lineItems, isLoading = isLoadingLineItems)
        }
    }
}

/** The line-item breakdown shown below a tapped-open InvoiceRow. */
@Composable
private fun InvoiceLineItemsPanel(lineItems: List<LineItemDto>?, isLoading: Boolean) {
    val colors = LocalZedReadColors.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.bg)
            .padding(horizontal = 16.dp, vertical = 10.dp),
    ) {
        when {
            isLoading -> Box(Modifier.fillMaxWidth().padding(12.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp))
            }
            lineItems.isNullOrEmpty() -> Text(
                "No line items on this invoice.",
                style = MaterialTheme.typography.bodySmall,
                color = colors.muted,
            )
            else -> lineItems.forEach { line -> LineItemRow(line) }
        }
    }
}

@Composable
private fun LineItemRow(line: LineItemDto) {
    val colors = LocalZedReadColors.current
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "${line.quantity} × ${line.productName}",
                style = MaterialTheme.typography.bodyMedium,
                color = colors.text,
                modifier = Modifier.weight(1f),
            )
            Text(
                formatCentsDollars(line.subtotalCents + line.taxCents),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.text,
            )
        }
        if (line.modifiers.isNotEmpty()) {
            Text(
                line.modifiers.joinToString(", ") { it.modifierName },
                style = MaterialTheme.typography.labelSmall,
                color = colors.muted,
                modifier = Modifier.padding(start = 12.dp),
            )
        }
    }
}

/**
 * Full-or-partial refund confirmation — Full is the default (matches the
 * server's own default when line_item_ids is omitted); switching to Partial
 * reveals a checkbox per line item, and Confirm is disabled until at least
 * one is checked (an empty list would read server-side as a full refund,
 * which isn't what a cashier who chose "Partial" and checked nothing meant).
 */
@Composable
private fun RefundDialog(
    invoice: InvoiceCacheEntity,
    lineItems: List<LineItemDto>?,
    isLoadingLineItems: Boolean,
    isSubmitting: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onConfirm: (lineItemIds: List<String>?) -> Unit,
) {
    val colors = LocalZedReadColors.current
    var isPartial by remember(invoice.id) { mutableStateOf(false) }
    val selectedIds = remember(invoice.id) { mutableStateOf(setOf<String>()) }

    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .widthIn(max = 420.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(colors.surface)
                .padding(20.dp),
        ) {
            Text("Refund ${invoice.ref}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = colors.text)
            Spacer(Modifier.height(4.dp))
            Text(
                "Total paid: ${formatCentsDollars(invoice.totalCents)}",
                style = MaterialTheme.typography.bodySmall,
                color = colors.muted,
            )
            Spacer(Modifier.height(16.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = !isPartial, onClick = { isPartial = false })
                Text("Full refund", modifier = Modifier.clickable { isPartial = false })
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = isPartial, onClick = { isPartial = true })
                Text("Partial refund (choose items)", modifier = Modifier.clickable { isPartial = true })
            }

            if (isPartial) {
                Spacer(Modifier.height(8.dp))
                when {
                    isLoadingLineItems -> Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    }
                    lineItems.isNullOrEmpty() -> Text(
                        "No line items to select.",
                        style = MaterialTheme.typography.bodySmall,
                        color = colors.muted,
                    )
                    else -> Column {
                        lineItems.forEach { line ->
                            val checked = line.id in selectedIds.value
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        selectedIds.value = if (checked) selectedIds.value - line.id else selectedIds.value + line.id
                                    },
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Checkbox(checked = checked, onCheckedChange = { on ->
                                    selectedIds.value = if (on) selectedIds.value + line.id else selectedIds.value - line.id
                                })
                                Text(
                                    "${line.quantity} × ${line.productName} — ${formatCentsDollars(line.subtotalCents + line.taxCents)}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = colors.text,
                                    modifier = Modifier.weight(1f),
                                )
                            }
                        }
                    }
                }
            }

            if (errorMessage != null) {
                Spacer(Modifier.height(8.dp))
                Text(errorMessage, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(16.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onDismiss, enabled = !isSubmitting) { Text("Cancel") }
                Spacer(Modifier.width(8.dp))
                TextButton(
                    onClick = { onConfirm(if (isPartial) selectedIds.value.toList() else null) },
                    enabled = !isSubmitting && (!isPartial || selectedIds.value.isNotEmpty()),
                ) {
                    Text(if (isSubmitting) "Refunding…" else "Confirm refund")
                }
            }
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
