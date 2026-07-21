package com.zedread.pos.ui.screens.cart

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.ui.viewmodel.SellViewModel

/**
 * Invoice builder screen — displays line items already added from the
 * catalog and the running total, then hands off to payment. [viewModel] is
 * shared with CatalogScreen/PaymentScreen (scoped to the "sell" nav
 * sub-graph), so the cart it shows is the one the operator was just building.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CartScreen(
    onProceedToPayment: () -> Unit,
    viewModel: SellViewModel = hiltViewModel(),
) {
    val lineItems by viewModel.lineItems.collectAsState()

    Scaffold(
        topBar = { TopAppBar(title = { Text("Current Order") }) },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize(),
        ) {
            LazyColumn(modifier = Modifier.weight(1f)) {
                if (lineItems.isEmpty()) {
                    item {
                        Text(
                            "No items yet — go back to add products.",
                            modifier = Modifier.padding(24.dp),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
                items(lineItems) { item -> LineItemRow(item) }
            }

            HorizontalDivider()

            Column(Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text("Total", style = MaterialTheme.typography.titleMedium)
                    Text(
                        formatCents(viewModel.totalCents),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }

                Spacer(Modifier.height(12.dp))

                Button(
                    onClick = onProceedToPayment,
                    enabled = lineItems.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Proceed to Payment")
                }
            }
        }
    }
}

@Composable
private fun LineItemRow(item: LineItemDto) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(item.productName, style = MaterialTheme.typography.bodyLarge)
            Text(
                "Qty: ${item.quantity}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(formatCents(item.subtotalCents + item.taxCents), style = MaterialTheme.typography.bodyLarge)
    }
    HorizontalDivider()
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
