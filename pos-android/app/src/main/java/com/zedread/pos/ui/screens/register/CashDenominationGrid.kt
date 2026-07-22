package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/** One AUD cash denomination: its value in cents and a short display label. */
private data class Denomination(val cents: Long, val label: String)

/** Standard AUD notes and coins, largest first. */
private val AUD_DENOMINATIONS = listOf(
    Denomination(10000, "$100"),
    Denomination(5000, "$50"),
    Denomination(2000, "$20"),
    Denomination(1000, "$10"),
    Denomination(500, "$5"),
    Denomination(200, "$2"),
    Denomination(100, "$1"),
    Denomination(50, "50c"),
    Denomination(20, "20c"),
    Denomination(10, "10c"),
    Denomination(5, "5c"),
)

/**
 * Per-denomination count entry grid — the "denomination" cash_in_mode
 * variant, an alternative to a single bulk-total field. Each row starts
 * blank (not zero) so an untouched row doesn't imply a counted-and-confirmed
 * zero. Reports the running total in cents via [onTotalChanged] on every
 * keystroke, so the caller's submit button stays wired to a single Long
 * exactly like the bulk-entry field's dollarsToCents() result.
 */
@Composable
fun DenominationGrid(
    modifier: Modifier = Modifier,
    onTotalChanged: (Long) -> Unit,
) {
    val counts = remember { mutableStateMapOf<Long, String>() }

    fun reportTotal() {
        val total = AUD_DENOMINATIONS.sumOf { d -> (counts[d.cents]?.toLongOrNull() ?: 0L) * d.cents }
        onTotalChanged(total)
    }

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Denomination", style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(72.dp))
            Text("Count", style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(96.dp))
            Text("Subtotal", style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(80.dp))
        }
        AUD_DENOMINATIONS.forEach { d ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(d.label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.width(72.dp))
                OutlinedTextField(
                    value = counts[d.cents] ?: "",
                    onValueChange = { input ->
                        if (input.isEmpty() || input.matches(Regex("^\\d{0,4}$"))) {
                            counts[d.cents] = input
                            reportTotal()
                        }
                    },
                    placeholder = { Text("0") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.width(96.dp),
                )
                Text(
                    formatCentsCompact((counts[d.cents]?.toLongOrNull() ?: 0L) * d.cents),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(80.dp),
                )
            }
        }
    }
}

private fun formatCentsCompact(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
