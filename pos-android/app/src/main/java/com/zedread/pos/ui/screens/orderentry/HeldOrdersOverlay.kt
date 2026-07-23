package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.HeldOrdersUiState
import com.zedread.pos.ui.viewmodel.HeldOrdersViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Held Orders tab — a list of this site's currently-open (held, unpaid)
 * invoices, tap to recall onto the Register's cart (see
 * [com.zedread.pos.ui.viewmodel.SellViewModel.recallHeldOrder]).
 *
 * An overlay on the Register screen, same convention as the modifier sheet
 * and payment modal (see SellViewModel's class doc for why) rather than a
 * separate nav destination — recalling needs to mutate the SAME
 * SellViewModel instance the Register screen already holds, which a nav
 * destination's own default-scoped ViewModel wouldn't share.
 */
@Composable
fun HeldOrdersOverlay(
    viewModel: HeldOrdersViewModel,
    onDismiss: () -> Unit,
    onRecall: (invoiceId: String) -> Unit,
) {
    val colors = LocalZedReadColors.current
    val state by viewModel.state.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.5f))
            .clickable(onClick = onDismiss),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 480.dp)
                .fillMaxWidth(0.9f)
                .fillMaxHeight(0.8f)
                .clip(RoundedCornerShape(18.dp))
                .clickable(enabled = false) {}
                .background(colors.surface),
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(20.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Held Orders", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
                            Text("Tap an order to recall it to the current sale", style = MaterialTheme.typography.bodySmall, color = colors.faint)
                        }
                        Box(
                            modifier = Modifier
                                .size(34.dp)
                                .clip(RoundedCornerShape(9.dp))
                                .clickable(onClick = onDismiss),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("✕", color = colors.muted, style = MaterialTheme.typography.titleMedium)
                        }
                    }
                    HorizontalDivider(color = colors.border)
                }

                when (val current = state) {
                    is HeldOrdersUiState.Loading -> {
                        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                    is HeldOrdersUiState.Error -> {
                        Box(Modifier.weight(1f).fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                            Text(current.message, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center)
                        }
                    }
                    is HeldOrdersUiState.Ready -> {
                        if (current.orders.isEmpty()) {
                            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                                Text("No held orders right now.", color = colors.muted)
                            }
                        } else {
                            LazyColumn(modifier = Modifier.weight(1f).fillMaxWidth()) {
                                items(current.orders, key = { it.id }) { order ->
                                    HeldOrderRow(order = order, onClick = { onRecall(order.id) })
                                    HorizontalDivider(color = colors.border)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun HeldOrderRow(order: InvoiceDto, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(order.ref, style = MaterialTheme.typography.bodyLarge, color = colors.text, fontWeight = FontWeight.SemiBold)
            order.createdAt?.let { createdAt ->
                Text(formatHeldOrderDate(createdAt), style = MaterialTheme.typography.labelSmall, color = colors.faint)
            }
        }
        Text(formatCentsHeld(order.totalCents), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold, color = colors.text)
    }
}

private fun formatCentsHeld(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}

/** [createdAtIso] is an ISO-8601 timestamp; falls back to the raw string if it doesn't parse cleanly (unexpected server format, not worth crashing over). */
private fun formatHeldOrderDate(createdAtIso: String): String =
    runCatching {
        val parsed = java.time.OffsetDateTime.parse(createdAtIso)
        SimpleDateFormat("d MMM, h:mm a", Locale.getDefault()).format(Date(parsed.toInstant().toEpochMilli()))
    }.getOrDefault(createdAtIso)
