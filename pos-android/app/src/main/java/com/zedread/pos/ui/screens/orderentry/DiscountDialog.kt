package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.components.KeypadAmountDisplay
import com.zedread.pos.ui.components.NumericKeypad
import com.zedread.pos.ui.components.keypadAppendDigit
import com.zedread.pos.ui.components.keypadBackspace
import com.zedread.pos.ui.theme.LocalZedReadColors

/** Which unit the discount pinpad is entering — $ off, or % off. */
enum class DiscountMode { DOLLAR, PERCENT }

/**
 * Discount pinpad popup — the Register's "Discount" button above Hold/Pay.
 * Enter either a flat dollar amount or a percentage of the order's
 * (pre-discount) subtotal+tax; either way the result is clamped so a
 * discount can never exceed the order total, matching the backend's own
 * "discount cannot exceed total" invariant (see
 * SellViewModel.setDiscount/invoice_service.apply_discount).
 *
 * Same centered-overlay chrome as [com.zedread.pos.ui.screens.payment.PaymentModal]/
 * [ModifierSheetOverlay] — a dimming scrim, no click-to-dismiss (an
 * accidental mid-entry loss here is just as unwelcome as mid-payment).
 */
@Composable
fun DiscountDialog(
    baseCents: Long,
    currentDiscountCents: Long,
    onDismiss: () -> Unit,
    onApply: (Long) -> Unit,
    onRemove: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    var mode by remember { mutableStateOf(DiscountMode.DOLLAR) }
    var amountText by remember { mutableStateOf("") }

    fun previewCents(): Long = when (mode) {
        DiscountMode.DOLLAR -> dollarsToCents(amountText).coerceIn(0L, baseCents)
        DiscountMode.PERCENT -> discountCentsFromPercent(baseCents, percentStringToBasisPoints(amountText))
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.5f))
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 420.dp)
                .fillMaxWidth(0.88f)
                .clip(RoundedCornerShape(18.dp))
                .background(colors.surface)
                .padding(26.dp),
        ) {
            Column {
                Text("Discount", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Order total before discount: ${formatCentsLocal(baseCents)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.muted,
                )
                Spacer(Modifier.height(16.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    ModeTab("$ off", mode == DiscountMode.DOLLAR, Modifier.weight(1f)) {
                        mode = DiscountMode.DOLLAR
                        amountText = ""
                    }
                    ModeTab("% off", mode == DiscountMode.PERCENT, Modifier.weight(1f)) {
                        mode = DiscountMode.PERCENT
                        amountText = ""
                    }
                }

                Spacer(Modifier.height(16.dp))
                KeypadAmountDisplay(
                    value = amountText,
                    placeholder = if (mode == DiscountMode.DOLLAR) "0.00" else "0",
                    label = if (mode == DiscountMode.DOLLAR) "Dollars off" else "Percent off (max 100)",
                )
                Spacer(Modifier.height(10.dp))
                NumericKeypad(
                    showDecimal = true,
                    onDigit = { digit -> amountText = keypadAppendDigit(amountText, digit) },
                    onBackspace = { amountText = keypadBackspace(amountText) },
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    "Discount: ${formatCentsLocal(previewCents())}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.accent,
                )

                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp)
                            .clip(RoundedCornerShape(11.dp))
                            .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(11.dp))
                            .clickable(onClick = onDismiss),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("Cancel", color = colors.text, fontWeight = FontWeight.SemiBold)
                    }
                    if (currentDiscountCents > 0) {
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .height(48.dp)
                                .clip(RoundedCornerShape(11.dp))
                                .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(11.dp))
                                .clickable(onClick = onRemove),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("Remove", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp)
                            .clip(RoundedCornerShape(11.dp))
                            .background(if (previewCents() > 0) colors.accent else colors.surface2)
                            .clickable(enabled = previewCents() > 0, onClick = { onApply(previewCents()) }),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("Apply", color = if (previewCents() > 0) Color.White else colors.faint, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun ModeTab(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = modifier
            .height(44.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(if (selected) colors.accentSoft else colors.surface)
            .border(
                width = if (selected) 2.dp else 1.dp,
                color = if (selected) colors.accent else colors.inputBorder,
                shape = RoundedCornerShape(10.dp),
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (selected) colors.accentText else colors.muted, fontWeight = FontWeight.SemiBold)
    }
}

/** Parse a keypad-built "$" amount string into integer cents — never float arithmetic on money. */
private fun dollarsToCents(input: String): Long {
    if (input.isBlank()) return 0L
    val parts = input.split(".")
    val dollars = parts.getOrNull(0)?.toLongOrNull() ?: 0L
    val centsPart = parts.getOrNull(1).orEmpty().padEnd(2, '0').take(2)
    val cents = centsPart.toLongOrNull() ?: 0L
    return dollars * 100 + cents
}

/** Parse a keypad-built percent string into basis points (percent × 100), capped at 10000 (100.00%) — never exceeds the order total. */
internal fun percentStringToBasisPoints(input: String): Long {
    if (input.isBlank()) return 0L
    val parts = input.split(".")
    val whole = parts.getOrNull(0)?.toLongOrNull() ?: 0L
    val frac = parts.getOrNull(1).orEmpty().padEnd(2, '0').take(2).toLongOrNull() ?: 0L
    return (whole * 100 + frac).coerceIn(0L, 10000L)
}

/** Integer-only percent-of-amount, never float — mirrors the backend's Decimal-based money math in spirit. */
internal fun discountCentsFromPercent(baseCents: Long, basisPoints: Long): Long =
    (baseCents * basisPoints) / 10000L

private fun formatCentsLocal(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
