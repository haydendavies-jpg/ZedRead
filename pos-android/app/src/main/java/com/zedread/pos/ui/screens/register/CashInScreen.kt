package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.CashInState
import com.zedread.pos.ui.viewmodel.RegisterSessionViewModel

/**
 * Start-of-day cash-in: bulk-value entry only for Phase 1 — the
 * denomination-breakdown variant is a Phase 2 setting. Blocks Register
 * access until a session is open (POST /register-sessions/open).
 */
@Composable
fun CashInScreen(
    onOpened: () -> Unit,
    viewModel: RegisterSessionViewModel = hiltViewModel(),
) {
    val state by viewModel.cashInState.collectAsState()
    var amount by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        if (state is CashInState.Done) onOpened()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Start of Day", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Count the cash in the till and enter the total to begin your shift.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = amount,
            onValueChange = { input -> if (input.matches(Regex("^\\d*\\.?\\d{0,2}$"))) amount = input },
            label = { Text("Opening cash ($)") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(8.dp))

        if (state is CashInState.Error) {
            Text(
                (state as CashInState.Error).message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = {
                val cents = dollarsToCents(amount)
                if (cents != null) viewModel.openSession(cents)
            },
            enabled = amount.isNotBlank() && state !is CashInState.Loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state is CashInState.Loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp))
            } else {
                Text("Start Shift")
            }
        }
    }
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
