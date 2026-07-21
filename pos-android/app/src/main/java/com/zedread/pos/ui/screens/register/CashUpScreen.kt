package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.CashUpState
import com.zedread.pos.ui.viewmodel.RegisterSessionViewModel

/**
 * End-of-day cash-up: bulk-value entry only for Phase 1 — the
 * denomination-breakdown variant and the hide-variance option are both
 * Phase 2 settings. Closes this terminal's open till session and logs the
 * operator out (POST /register-sessions/{id}/close); the device stays
 * paired for the next shift.
 */
@Composable
fun CashUpScreen(
    onDone: () -> Unit,
    viewModel: RegisterSessionViewModel = hiltViewModel(),
) {
    val state by viewModel.cashUpState.collectAsState()
    val loggedOut by viewModel.loggedOut.collectAsState()
    var amount by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { viewModel.loadForCashUp() }
    LaunchedEffect(loggedOut) { if (loggedOut) onDone() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        when (val current = state) {
            is CashUpState.Ready -> {
                Text("End of Day", style = MaterialTheme.typography.headlineMedium)
                Text(
                    "Opened by ${current.session.openedByName} · opening cash ${formatCents(current.session.openingCashCents)}",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    "Count the cash in the till and enter the total to close your shift.",
                    style = MaterialTheme.typography.bodyMedium,
                )

                Spacer(Modifier.height(32.dp))

                OutlinedTextField(
                    value = amount,
                    onValueChange = { input -> if (input.matches(Regex("^\\d*\\.?\\d{0,2}$"))) amount = input },
                    label = { Text("Closing cash ($)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(24.dp))

                Button(
                    onClick = {
                        val cents = dollarsToCents(amount)
                        if (cents != null) viewModel.closeSession(current.session.id, cents)
                    },
                    enabled = amount.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Close Till") }
            }

            is CashUpState.Closed -> {
                Text("Till Closed", style = MaterialTheme.typography.headlineMedium)

                Spacer(Modifier.height(24.dp))

                CashUpSummaryRow("Expected cash", current.session.expectedCashCents)
                CashUpSummaryRow("Counted cash", current.session.closingCashCents)
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                CashUpSummaryRow("Variance", current.session.varianceCents, emphasize = true)

                Spacer(Modifier.height(32.dp))

                Button(onClick = { viewModel.logout() }, modifier = Modifier.fillMaxWidth()) {
                    Text("Log Out")
                }
            }

            is CashUpState.Error -> {
                Text(
                    current.message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(16.dp))
                Button(onClick = { viewModel.loadForCashUp() }, modifier = Modifier.fillMaxWidth()) {
                    Text("Retry")
                }
            }

            else -> CircularProgressIndicator()
        }
    }
}

@Composable
private fun CashUpSummaryRow(label: String, cents: Long?, emphasize: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = if (emphasize) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge,
            fontWeight = if (emphasize) FontWeight.Bold else FontWeight.Normal,
        )
        Text(
            if (cents != null) formatCents(cents) else "—",
            style = if (emphasize) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge,
            fontWeight = if (emphasize) FontWeight.Bold else FontWeight.Normal,
        )
    }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}

/** Parse a "$" input field into integer cents — never float arithmetic on money. */
private fun dollarsToCents(input: String): Long? {
    val normalized = input.ifBlank { return null }
    val parts = normalized.split(".")
    val dollars = parts.getOrNull(0)?.toLongOrNull() ?: return null
    val centsPart = parts.getOrNull(1).orEmpty().padEnd(2, '0').take(2)
    val cents = if (centsPart.isEmpty()) 0L else centsPart.toLongOrNull() ?: return null
    return dollars * 100 + cents
}
