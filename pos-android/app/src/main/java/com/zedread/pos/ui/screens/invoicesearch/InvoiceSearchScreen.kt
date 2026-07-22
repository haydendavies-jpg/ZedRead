package com.zedread.pos.ui.screens.invoicesearch

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.DateRangeFilter
import com.zedread.pos.ui.viewmodel.InvoiceSearchViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Invoice search/history — filterable (date range, status, payment method)
 * list reading the local Room cache, so it works offline. Each row shows
 * synced/pending state. Entry point: the History icon on the Register
 * header, alongside Cash Up/Settings.
 */
@Composable
fun InvoiceSearchScreen(
    onBack: () -> Unit,
    viewModel: InvoiceSearchViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val results by viewModel.results.collectAsState()
    val statusFilter by viewModel.statusFilter.collectAsState()
    val paymentMethodFilter by viewModel.paymentMethodFilter.collectAsState()
    val dateRangeFilter by viewModel.dateRangeFilter.collectAsState()

    Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = colors.text)
            }
            Text("Invoice Search", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
        }

        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            FilterChipRow(
                label = "Status",
                options = listOf(null to "All", "draft" to "Draft", "open" to "Open", "paid" to "Paid", "voided" to "Voided"),
                selected = statusFilter,
                onSelect = viewModel::setStatusFilter,
            )
            Spacer(Modifier.height(8.dp))
            FilterChipRow(
                label = "Payment",
                options = listOf(null to "All", "cash" to "Cash", "card" to "Card", "voucher" to "Voucher"),
                selected = paymentMethodFilter,
                onSelect = viewModel::setPaymentMethodFilter,
            )
            Spacer(Modifier.height(8.dp))
            DateRangeChipRow(selected = dateRangeFilter, onSelect = viewModel::setDateRangeFilter)
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

@Composable
private fun FilterChipRow(
    label: String,
    options: List<Pair<String?, String>>,
    selected: String?,
    onSelect: (String?) -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column {
        Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = colors.faint)
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            options.forEach { (value, text) ->
                val isSelected = value == selected
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(16.dp))
                        .background(if (isSelected) colors.accent else colors.surface)
                        .clickable { onSelect(value) }
                        .padding(horizontal = 14.dp, vertical = 6.dp),
                ) {
                    Text(
                        text,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (isSelected) androidx.compose.ui.graphics.Color.White else colors.text,
                    )
                }
            }
        }
    }
}

@Composable
private fun DateRangeChipRow(selected: DateRangeFilter, onSelect: (DateRangeFilter) -> Unit) {
    val colors = LocalZedReadColors.current
    Column {
        Text("DATE RANGE", style = MaterialTheme.typography.labelSmall, color = colors.faint)
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DateRangeFilter.entries.forEach { range ->
                val isSelected = range == selected
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(16.dp))
                        .background(if (isSelected) colors.accent else colors.surface)
                        .clickable { onSelect(range) }
                        .padding(horizontal = 14.dp, vertical = 6.dp),
                ) {
                    Text(
                        range.label,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (isSelected) androidx.compose.ui.graphics.Color.White else colors.text,
                    )
                }
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
                formatInvoiceDate(invoice.createdAtMillis),
                style = MaterialTheme.typography.bodyLarge,
                color = colors.text,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                listOfNotNull(invoice.status.replaceFirstChar { it.uppercase() }, invoice.paymentMethod?.replaceFirstChar { it.uppercase() })
                    .joinToString(" · "),
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
