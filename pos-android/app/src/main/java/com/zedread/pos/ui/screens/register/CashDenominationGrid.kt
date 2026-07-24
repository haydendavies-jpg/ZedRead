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

// Column widths for the single-column denomination list — sized generously
// (not the previous two-column split's cramped widths) now that the popup
// card hosting this is wide enough to give every column room without
// truncating any label.
private val LABEL_COLUMN_WIDTH = 92.dp
private val COUNT_COLUMN_WIDTH = 96.dp
private val SUBTOTAL_COLUMN_WIDTH = 100.dp

// Row height/gap for the 11-row denomination list — tight enough that the
// full list fits within RegisterPopupCard's content area without scrolling
// (user-testing feedback) on anything down to a compact phone screen; still
// tall enough to stay comfortably tappable.
private val ROW_HEIGHT = 34.dp
private val ROW_GAP = 3.dp

/**
 * Per-denomination count entry — the "denomination" cash_in_mode variant, an
 * alternative to a single bulk-total field. Each row starts blank (not
 * zero) so an untouched row doesn't imply a counted-and-confirmed zero.
 * Reports the running total in cents via [onTotalChanged] on every
 * keystroke, so the caller's submit button stays wired to a single Long
 * exactly like the bulk-entry field's dollarsToCents() result.
 *
 * Laid out as ONE full-width column of all 11 rows with the [NumericKeypad]
 * to its right (not below) — per user-testing feedback that the earlier
 * two-column notes/coins split, with the keypad underneath, made the popup
 * feel cramped and forced truncated labels; the popup card hosting this is
 * now wide enough (see RegisterPopupCard's `maxWidth`) that a single column
 * plus a side-by-side keypad fits without ever needing to scroll.
 *
 * Count entry is tap-to-select-then-type rather than 11 individually
 * focusable text fields: tapping a row makes it the active one (highlighted
 * border), and the persistent [NumericKeypad] types into whichever row is
 * currently active. User-testing feedback that cash entry should never open
 * the Android soft keyboard; the first (largest) denomination starts active
 * so the keypad is immediately usable without an extra tap.
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

    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(20.dp)) {
        DenominationColumn(
            denominations = AUD_DENOMINATIONS,
            counts = counts,
            activeCents = activeCents,
            onSelect = { activeCents = it },
            modifier = Modifier.weight(1f),
        )
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
            modifier = Modifier.widthIn(max = 260.dp),
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
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(ROW_GAP)) {
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
                Text(
                    d.label,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Visible,
                    modifier = Modifier.width(LABEL_COLUMN_WIDTH),
                )
                Box(
                    modifier = Modifier
                        .width(COUNT_COLUMN_WIDTH)
                        .height(ROW_HEIGHT)
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
                    maxLines = 1,
                    overflow = TextOverflow.Visible,
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
