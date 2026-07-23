package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateMap
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.components.NumericKeypad
import com.zedread.pos.ui.components.keypadAppendCountDigit
import com.zedread.pos.ui.components.keypadBackspace
import com.zedread.pos.ui.theme.LocalZedReadColors

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

// Column widths shared between the header row and every data row within one
// half of the two-column split below, so everything lines up. "Denomination"
// (12 characters) needs more room than any actual label ("$100"/"50c") ever
// does — previously the header wrapped to two lines because it shared the
// data rows' narrower 72.dp width; kept the header and label columns
// separately sized here instead of forcing them to match.
private val LABEL_COLUMN_WIDTH = 78.dp
private val COUNT_COLUMN_WIDTH = 72.dp
private val SUBTOTAL_COLUMN_WIDTH = 64.dp

/**
 * Per-denomination count entry grid — the "denomination" cash_in_mode
 * variant, an alternative to a single bulk-total field. Each row starts
 * blank (not zero) so an untouched row doesn't imply a counted-and-confirmed
 * zero. Reports the running total in cents via [onTotalChanged] on every
 * keystroke, so the caller's submit button stays wired to a single Long
 * exactly like the bulk-entry field's dollarsToCents() result.
 *
 * Laid out as two side-by-side columns (6 notes, 5 coins) rather than one
 * long list of 11 rows — user-testing feedback that the single-column
 * version forced scrolling to reach the smaller coin denominations inside
 * the popup card's fixed height. Each half gets its own compact header.
 *
 * Count entry is tap-to-select-then-type rather than 11 individually
 * focusable text fields: tapping a row makes it the active one (highlighted
 * border), and a single persistent [NumericKeypad] below both columns —
 * shared across every row — types into whichever row is currently active.
 * User-testing feedback that cash entry should never open the Android soft
 * keyboard; the first (largest) denomination starts active so the keypad is
 * immediately usable without an extra tap.
 */
@Composable
fun DenominationGrid(
    modifier: Modifier = Modifier,
    onTotalChanged: (Long) -> Unit,
) {
    val counts = remember { mutableStateMapOf<Long, String>() }
    var activeCents by remember { mutableStateOf(AUD_DENOMINATIONS.first().cents) }

    fun reportTotal() {
        val total = AUD_DENOMINATIONS.sumOf { d -> (counts[d.cents]?.toLongOrNull() ?: 0L) * d.cents }
        onTotalChanged(total)
    }

    val half = (AUD_DENOMINATIONS.size + 1) / 2
    val notes = AUD_DENOMINATIONS.subList(0, half)
    val coins = AUD_DENOMINATIONS.subList(half, AUD_DENOMINATIONS.size)

    Column(modifier = modifier) {
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            DenominationColumn(notes, counts, activeCents, onSelect = { activeCents = it }, modifier = Modifier.weight(1f))
            DenominationColumn(coins, counts, activeCents, onSelect = { activeCents = it }, modifier = Modifier.weight(1f))
        }
        Spacer(Modifier.height(14.dp))
        NumericKeypad(
            showDecimal = false,
            onDigit = { digit ->
                counts[activeCents] = keypadAppendCountDigit(counts[activeCents] ?: "", digit)
                reportTotal()
            },
            onBackspace = {
                counts[activeCents] = keypadBackspace(counts[activeCents] ?: "")
                reportTotal()
            },
            modifier = Modifier.widthIn(max = 280.dp),
        )
    }
}

@Composable
private fun DenominationColumn(
    denominations: List<Denomination>,
    counts: SnapshotStateMap<Long, String>,
    activeCents: Long,
    onSelect: (Long) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "Denomination",
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.width(LABEL_COLUMN_WIDTH),
            )
            Text("Count", style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(COUNT_COLUMN_WIDTH))
            Text("Subtotal", style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(SUBTOTAL_COLUMN_WIDTH))
        }
        denominations.forEach { d ->
            val isActive = d.cents == activeCents
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(d.label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.width(LABEL_COLUMN_WIDTH))
                Box(
                    modifier = Modifier
                        .width(COUNT_COLUMN_WIDTH)
                        .height(44.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(if (isActive) colors.accentSoft else colors.bg)
                        .border(
                            width = if (isActive) 2.dp else 1.dp,
                            color = if (isActive) colors.accent else colors.inputBorder,
                            shape = RoundedCornerShape(8.dp),
                        )
                        .clickable { onSelect(d.cents) },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(counts[d.cents]?.ifEmpty { "0" } ?: "0", color = colors.text)
                }
                Text(
                    formatCentsCompact((counts[d.cents]?.toLongOrNull() ?: 0L) * d.cents),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(SUBTOTAL_COLUMN_WIDTH),
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
