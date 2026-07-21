package com.zedread.pos.ui.screens.payment

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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.PaymentFlowState
import com.zedread.pos.ui.viewmodel.SellViewModel

/**
 * Dedicated payment screen supporting single payment (cash or card) and split payments.
 *
 * Split flow: operator enters a card amount, pays the first leg → screen refreshes
 * with remaining balance → operator pays second leg with cash. [viewModel] is
 * shared with Catalog/Cart (scoped to the "sell" nav sub-graph).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaymentScreen(
    onPaymentComplete: (invoiceId: String) -> Unit,
    viewModel: SellViewModel = hiltViewModel(),
) {
    val state by viewModel.paymentState.collectAsState()
    var splitMode by remember { mutableStateOf(false) }
    var splitAmountInput by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        if (state is PaymentFlowState.Complete) {
            onPaymentComplete((state as PaymentFlowState.Complete).invoiceId)
        }
    }

    val totalCents = viewModel.totalCents
    val remainingCents = when (state) {
        is PaymentFlowState.PartiallyPaid -> (state as PaymentFlowState.PartiallyPaid).remainingCents
        else -> totalCents
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Payment") }) },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .padding(24.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── Amount summary ───────────────────────────────────────────────
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Total", style = MaterialTheme.typography.titleMedium)
                Text(formatCents(totalCents), style = MaterialTheme.typography.titleMedium)
            }
            if (state is PaymentFlowState.PartiallyPaid) {
                val paid = (state as PaymentFlowState.PartiallyPaid).paidCents
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Paid", style = MaterialTheme.typography.bodyMedium)
                    Text(formatCents(paid), style = MaterialTheme.typography.bodyMedium)
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Remaining", style = MaterialTheme.typography.titleMedium,
                         color = MaterialTheme.colorScheme.error)
                    Text(formatCents(remainingCents), style = MaterialTheme.typography.titleMedium,
                         color = MaterialTheme.colorScheme.error)
                }
            }

            HorizontalDivider()

            if (state is PaymentFlowState.Error) {
                Text(
                    (state as PaymentFlowState.Error).message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            val isLoading = state is PaymentFlowState.Loading

            // ── Full payment buttons ──────────────────────────────────────────
            if (!splitMode) {
                Button(
                    onClick = { viewModel.pay("cash", remainingCents) },
                    enabled = !isLoading,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (isLoading) CircularProgressIndicator(modifier = Modifier.height(20.dp))
                    else Text("Pay ${formatCents(remainingCents)} — Cash")
                }

                OutlinedButton(
                    onClick = { viewModel.pay("card", remainingCents) },
                    enabled = !isLoading,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Pay ${formatCents(remainingCents)} — Card")
                }

                // Only offer split when there hasn't been a partial payment yet.
                if (state !is PaymentFlowState.PartiallyPaid) {
                    OutlinedButton(
                        onClick = { splitMode = true },
                        enabled = !isLoading,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("Split Payment")
                    }
                }
            } else {
                // ── Split payment: enter card amount, pay card first ──────────
                Text("Card amount:", style = MaterialTheme.typography.bodyLarge)
                OutlinedTextField(
                    value = splitAmountInput,
                    onValueChange = { splitAmountInput = it },
                    label = { Text("Amount (\$)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(4.dp))

                val cardCents = splitAmountInput.toDoubleOrNull()?.let { (it * 100).toLong() } ?: 0L
                val cashCents = remainingCents - cardCents

                if (cashCents >= 0 && cardCents > 0) {
                    Text(
                        "Cash portion: ${formatCents(cashCents)}",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }

                Button(
                    onClick = {
                        if (cardCents > 0) {
                            viewModel.pay("card", cardCents)
                            splitMode = false
                        }
                    },
                    enabled = !isLoading && cardCents > 0 && cardCents < remainingCents,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Pay ${formatCents(cardCents)} — Card")
                }

                OutlinedButton(
                    onClick = { splitMode = false },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Cancel Split")
                }
            }
        }
    }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
