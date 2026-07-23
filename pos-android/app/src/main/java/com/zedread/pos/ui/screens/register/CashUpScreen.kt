package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.repository.CASH_IN_MODE_DENOMINATION
import com.zedread.pos.ui.components.KeypadAmountDisplay
import com.zedread.pos.ui.components.NumericKeypad
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.components.RegisterPopupCard
import com.zedread.pos.ui.components.keypadAppendDigit
import com.zedread.pos.ui.components.keypadBackspace
import com.zedread.pos.ui.viewmodel.CashUpState
import com.zedread.pos.ui.viewmodel.RegisterSessionViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel

/**
 * End-of-day cash-up: bulk-total entry, or the same per-denomination
 * breakdown grid CashInScreen uses when cash_in_mode is "denomination" (now
 * the out-of-box default — see SettingsRepository.CASH_IN_MODE_DENOMINATION's
 * doc); the Expected/Variance comparison is hidden when
 * hide_variance_on_close is set (Phase 2 settings framework — see
 * SettingsRepository), showing only the counted total. Closes this
 * terminal's open till session (POST /register-sessions/{id}/close); the
 * operator stays logged in and the device stays paired for the next shift —
 * logging out is a separate, explicit action reserved for the Settings
 * screen, not something cash-up should force. Rendered as the same
 * popup-card style as the Register's modifier sheet — see
 * [RegisterPopupCard]'s doc.
 *
 * [onCancel] backs out to Register — only offered before the till is
 * actually closed (Ready/ReadyOffline/Error states). Previously there was no
 * way back at all once this screen was entered, even by mistake — flagged
 * in user testing.
 */
@Composable
fun CashUpScreen(
    onDone: () -> Unit,
    onCancel: () -> Unit,
    viewModel: RegisterSessionViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
) {
    val state by viewModel.cashUpState.collectAsState()
    val cashSettings by viewModel.cashSettings.collectAsState()
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()
    var amount by remember { mutableStateOf("") }
    var denominationTotalCents by remember { mutableStateOf(0L) }

    LaunchedEffect(Unit) {
        viewModel.loadForCashUp()
        viewModel.loadCashSettings()
    }

    val isDenominationMode = cashSettings.cashInMode == CASH_IN_MODE_DENOMINATION
    val enteredCents = if (isDenominationMode) denominationTotalCents else dollarsToCents(amount)
    val hasEntry = if (isDenominationMode) denominationTotalCents > 0 else amount.isNotBlank()

    // Backing out is only safe before the till is actually closed — once
    // Closed/ClosedPendingSync, the close already happened server-side.
    val canCancel = state is CashUpState.Ready || state is CashUpState.ReadyOffline || state is CashUpState.Error

    val title = when (state) {
        is CashUpState.ClosedPendingSync, is CashUpState.Closed -> "Till Closed"
        else -> "End of Day"
    }
    val subtitle = when (val current = state) {
        is CashUpState.Ready ->
            "Opened by ${current.session.openedByName} · opening cash ${formatCents(current.session.openingCashCents)}"
        is CashUpState.ReadyOffline -> "Offline · opening cash ${formatCents(current.openingCashCents)} — not yet synced"
        else -> null
    }

    Column(modifier = Modifier.fillMaxSize()) {
        PosTopBar(
            title = deviceName ?: "Register",
            subtitle = "End of Day",
            onBack = if (canCancel) onCancel else null,
            isOnline = isOnline,
            pendingCount = pendingCount,
            onSyncClick = {},
        )
        RegisterPopupCard(
            title = title,
            subtitle = subtitle,
            onClose = if (canCancel) onCancel else null,
            footer = {
                when (val current = state) {
                    is CashUpState.Ready -> Button(
                        onClick = {
                            val cents = enteredCents
                            if (cents != null) viewModel.closeSession(current.session.id, cents)
                        },
                        enabled = hasEntry,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Close Till") }

                    is CashUpState.ReadyOffline -> Button(
                        onClick = {
                            val cents = enteredCents
                            if (cents != null) viewModel.closeOfflineSession(current.openClientRef, cents)
                        },
                        enabled = hasEntry,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Close Till") }

                    is CashUpState.ClosedPendingSync, is CashUpState.Closed ->
                        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("Done") }

                    is CashUpState.Error ->
                        Button(onClick = { viewModel.loadForCashUp() }, modifier = Modifier.fillMaxWidth()) { Text("Retry") }

                    else -> Unit
                }
            },
        ) {
            when (val current = state) {
                is CashUpState.Ready -> {
                    Text(
                        "Count the cash in the till and enter the total to close your shift.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Spacer(Modifier.height(20.dp))
                    if (isDenominationMode) {
                        DenominationGrid(modifier = Modifier.fillMaxWidth(), onTotalChanged = { denominationTotalCents = it })
                    } else {
                        KeypadAmountDisplay(value = amount, placeholder = "0.00", label = "Closing cash ($)")
                        Spacer(Modifier.height(14.dp))
                        NumericKeypad(
                            onDigit = { digit -> amount = keypadAppendDigit(amount, digit) },
                            onBackspace = { amount = keypadBackspace(amount) },
                            modifier = Modifier.widthIn(max = 280.dp),
                        )
                    }
                }

                is CashUpState.ReadyOffline -> {
                    // This till's own opening hasn't synced yet — there's no real
                    // RegisterSessionDto to show expected-cash figures from, but
                    // the operator can still close out; the close is queued too
                    // and both replay together once reconnected.
                    Text(
                        "Count the cash in the till and enter the total to close your shift.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Spacer(Modifier.height(20.dp))
                    if (isDenominationMode) {
                        DenominationGrid(modifier = Modifier.fillMaxWidth(), onTotalChanged = { denominationTotalCents = it })
                    } else {
                        KeypadAmountDisplay(value = amount, placeholder = "0.00", label = "Closing cash ($)")
                        Spacer(Modifier.height(14.dp))
                        NumericKeypad(
                            onDigit = { digit -> amount = keypadAppendDigit(amount, digit) },
                            onBackspace = { amount = keypadBackspace(amount) },
                            modifier = Modifier.widthIn(max = 280.dp),
                        )
                    }
                }

                is CashUpState.ClosedPendingSync -> {
                    CashUpSummaryRow("Counted cash", current.closingCashCents, emphasize = true)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Offline — expected cash and variance will be confirmed once this syncs.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                is CashUpState.Closed -> {
                    if (cashSettings.hideVarianceOnClose) {
                        CashUpSummaryRow("Counted cash", current.session.closingCashCents, emphasize = true)
                    } else {
                        CashUpSummaryRow("Expected cash", current.session.expectedCashCents)
                        CashUpSummaryRow("Counted cash", current.session.closingCashCents)
                        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                        CashUpSummaryRow("Variance", current.session.varianceCents, emphasize = true)
                    }
                }

                is CashUpState.Error -> {
                    Text(
                        current.message,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }

                else -> CircularProgressIndicator()
            }
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
