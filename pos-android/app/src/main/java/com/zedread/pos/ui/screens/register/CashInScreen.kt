package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.repository.CASH_IN_MODE_DENOMINATION
import com.zedread.pos.ui.components.KeypadAmountDisplay
import com.zedread.pos.ui.components.NumericKeypad
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.components.RegisterPopupCard
import com.zedread.pos.ui.components.keypadAppendDigit
import com.zedread.pos.ui.components.keypadBackspace
import com.zedread.pos.ui.viewmodel.CashInState
import com.zedread.pos.ui.viewmodel.RegisterSessionViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel

/**
 * Start-of-day cash-in: bulk-total entry, or a per-denomination breakdown
 * grid when the site's cash_in_mode setting is "denomination" (Phase 2
 * settings framework — see SettingsRepository; now the out-of-box default
 * per user-testing feedback, see SettingsRepository.CASH_IN_MODE_DENOMINATION's
 * doc). Blocks Register access until a session is open
 * (POST /register-sessions/open). No back action — a session must be opened
 * before Register is usable, there's nowhere sensible to go back to short of
 * logging out entirely. Rendered as the same popup-card style as the
 * Register's modifier sheet — see [RegisterPopupCard]'s doc.
 */
@Composable
fun CashInScreen(
    onOpened: () -> Unit,
    viewModel: RegisterSessionViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
) {
    val state by viewModel.cashInState.collectAsState()
    val cashSettings by viewModel.cashSettings.collectAsState()
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()
    var amount by remember { mutableStateOf("") }
    var denominationTotalCents by remember { mutableStateOf(0L) }
    var printMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) { viewModel.loadCashSettings() }
    LaunchedEffect(Unit) { viewModel.printResult.collect { message -> printMessage = message } }

    LaunchedEffect(state) {
        // DoneOffline means the open was queued to the outbox rather than
        // confirmed by the server — no session to offer a print for, so this
        // still proceeds straight to Register (staff aren't blocked from
        // selling while offline — see RegisterSessionViewModel). Done stops
        // here instead, showing a "Print slip"/"Continue" step below.
        if (state is CashInState.DoneOffline) onOpened()
    }

    val isDenominationMode = cashSettings.cashInMode == CASH_IN_MODE_DENOMINATION
    val enteredCents = if (isDenominationMode) denominationTotalCents else dollarsToCents(amount)
    val hasEntry = if (isDenominationMode) denominationTotalCents > 0 else amount.isNotBlank()

    Column(modifier = Modifier.fillMaxSize()) {
        PosTopBar(
            title = deviceName ?: "Register",
            subtitle = "Start of Day",
            isOnline = isOnline,
            pendingCount = pendingCount,
            onSyncClick = {},
        )
        RegisterPopupCard(
            title = if (state is CashInState.Done) "Till Opened" else "Start of Day",
            subtitle = if (state !is CashInState.Done) "Count the cash in the till and enter the total to begin your shift." else null,
            // Wider for the denomination grid — see RegisterPopupCard's doc.
            maxWidth = if (isDenominationMode) 760.dp else 480.dp,
            footer = {
                val doneState = state as? CashInState.Done
                if (doneState != null) {
                    Column {
                        Button(
                            onClick = { viewModel.printCashInSlip(doneState.session) },
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("Print Slip") }
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = onOpened, modifier = Modifier.fillMaxWidth()) { Text("Continue") }
                    }
                } else {
                    Button(
                        onClick = {
                            val cents = enteredCents
                            if (cents != null) viewModel.openSession(cents)
                        },
                        enabled = hasEntry && state !is CashInState.Loading,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (state is CashInState.Loading) {
                            CircularProgressIndicator(modifier = Modifier.height(20.dp))
                        } else {
                            Text("Start Shift")
                        }
                    }
                }
            },
        ) {
            if (state is CashInState.Done) {
                Text(
                    "Opening cash counted: ${formatCentsCashIn(state.session.openingCashCents)}",
                    style = MaterialTheme.typography.bodyMedium,
                )
                printMessage?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else if (isDenominationMode) {
                DenominationGrid(
                    modifier = Modifier.fillMaxWidth(),
                    onTotalChanged = { denominationTotalCents = it },
                )
            } else {
                KeypadAmountDisplay(value = amount, placeholder = "0.00", label = "Opening cash ($)")
                Spacer(Modifier.height(14.dp))
                NumericKeypad(
                    onDigit = { digit -> amount = keypadAppendDigit(amount, digit) },
                    onBackspace = { amount = keypadBackspace(amount) },
                    modifier = Modifier.widthIn(max = 280.dp),
                )
            }

            if (state is CashInState.Error) {
                Spacer(Modifier.height(8.dp))
                Text(
                    (state as CashInState.Error).message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

private fun formatCentsCashIn(cents: Long): String {
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
