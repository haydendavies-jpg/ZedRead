package com.zedread.pos.ui.screens.payment

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zedread.pos.ui.components.KeypadAmountDisplay
import com.zedread.pos.ui.components.NumericKeypad
import com.zedread.pos.ui.components.keypadAppendDigit
import com.zedread.pos.ui.components.keypadBackspace
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.PaymentMethod
import com.zedread.pos.ui.viewmodel.PaymentStage
import com.zedread.pos.ui.viewmodel.PaymentUiState

/**
 * Payment modal — exact-match to design_handoff_zedread/README.md's
 * "Component: Payment flow": a centered modal over a dimming overlay with
 * Choosing/Done states, Card/Cash method tabs (dashed terminal placeholder /
 * tender-preset grid respectively), plus the two flagged additions the
 * mockup predates the backend capability for — a Voucher tab (reference-code
 * input, Card's visual language) and a Split toggle on Cash/Card (partial
 * amount + "Add another payment", keeping the modal open with a running
 * remaining-due).
 *
 * Rendered as an overlay on the Register screen itself (not a nav
 * destination) — see SellViewModel's class doc for why. Unlike the modifier
 * sheet, the scrim here has no click-to-dismiss — matches the mockup (the ✕
 * is the only close affordance) and avoids an accidental mid-payment loss.
 */
@Composable
fun PaymentModal(
    state: PaymentUiState,
    totalCents: Long,
    remainingCents: Long,
    isOnline: Boolean,
    onClose: () -> Unit,
    onSelectMethod: (PaymentMethod) -> Unit,
    onToggleSplit: (Boolean) -> Unit,
    onSplitAmountChange: (Long) -> Unit,
    onPickTender: (Long) -> Unit,
    onVoucherReferenceChange: (String) -> Unit,
    onConfirmCard: () -> Unit,
    onConfirmCash: () -> Unit,
    onConfirmVoucher: () -> Unit,
    onNewOrder: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.5f))
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 560.dp)
                .fillMaxWidth(0.9f)
                .clip(RoundedCornerShape(18.dp))
                .background(colors.surface),
        ) {
            if (state.stage == PaymentStage.DONE) {
                PaymentDoneContent(state = state, isOnline = isOnline, onNewOrder = onNewOrder)
            } else {
                PaymentChoosingContent(
                    state = state,
                    totalCents = totalCents,
                    remainingCents = remainingCents,
                    onClose = onClose,
                    onSelectMethod = onSelectMethod,
                    onToggleSplit = onToggleSplit,
                    onSplitAmountChange = onSplitAmountChange,
                    onPickTender = onPickTender,
                    onVoucherReferenceChange = onVoucherReferenceChange,
                    onConfirmCard = onConfirmCard,
                    onConfirmCash = onConfirmCash,
                    onConfirmVoucher = onConfirmVoucher,
                )
            }
        }
    }
}

@Composable
private fun PaymentChoosingContent(
    state: PaymentUiState,
    totalCents: Long,
    remainingCents: Long,
    onClose: () -> Unit,
    onSelectMethod: (PaymentMethod) -> Unit,
    onToggleSplit: (Boolean) -> Unit,
    onSplitAmountChange: (Long) -> Unit,
    onPickTender: (Long) -> Unit,
    onVoucherReferenceChange: (String) -> Unit,
    onConfirmCard: () -> Unit,
    onConfirmCash: () -> Unit,
    onConfirmVoucher: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column {
        // ── Header: "Amount due" + close ──────────────────────────────────
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .border(width = 1.dp, color = colors.border)
                .padding(horizontal = 30.dp, vertical = 24.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    "AMOUNT DUE",
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.faint,
                )
                Text(
                    formatCents(remainingCents),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 32.sp,
                    color = colors.text,
                )
            }
            Spacer(Modifier.weight(1f))
            Box(
                modifier = Modifier
                    .size(38.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .clickable(onClick = onClose),
                contentAlignment = Alignment.Center,
            ) {
                Text("✕", color = colors.muted, style = MaterialTheme.typography.titleMedium)
            }
        }

        Column(modifier = Modifier.padding(30.dp)) {
            if (state.paidCents > 0) {
                Text(
                    "${formatCents(state.paidCents)} paid so far · ${formatCents(totalCents)} total",
                    style = MaterialTheme.typography.labelMedium,
                    color = colors.muted,
                    modifier = Modifier.padding(bottom = 14.dp),
                )
            }

            // ── Method tabs ─────────────────────────────────────────────────
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                MethodTab("💳 Card", state.method == PaymentMethod.CARD, Modifier.weight(1f)) {
                    onSelectMethod(PaymentMethod.CARD)
                }
                MethodTab("💵 Cash", state.method == PaymentMethod.CASH, Modifier.weight(1f)) {
                    onSelectMethod(PaymentMethod.CASH)
                }
                MethodTab("🎫 Voucher", state.method == PaymentMethod.VOUCHER, Modifier.weight(1f)) {
                    onSelectMethod(PaymentMethod.VOUCHER)
                }
            }

            // ── Split toggle (Card/Cash only, matches the task's spec) ───────
            if (state.method != PaymentMethod.VOUCHER) {
                Spacer(Modifier.height(18.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Split payment", color = colors.text, style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.weight(1f))
                    Switch(
                        checked = state.splitMode,
                        onCheckedChange = onToggleSplit,
                        colors = SwitchDefaults.colors(checkedTrackColor = colors.accent),
                    )
                }
            }

            Spacer(Modifier.height(18.dp))

            when {
                state.splitMode && state.method != PaymentMethod.VOUCHER -> {
                    SplitAmountEntry(
                        state = state,
                        remainingCents = remainingCents,
                        onSplitAmountChange = onSplitAmountChange,
                        onConfirm = if (state.method == PaymentMethod.CASH) onConfirmCash else onConfirmCard,
                    )
                }
                state.method == PaymentMethod.CARD -> CardTabContent(remainingCents, onConfirmCard, state.isSubmitting)
                state.method == PaymentMethod.CASH -> CashTabContent(
                    state = state,
                    remainingCents = remainingCents,
                    onPickTender = onPickTender,
                    onConfirm = onConfirmCash,
                )
                state.method == PaymentMethod.VOUCHER -> VoucherTabContent(
                    state = state,
                    remainingCents = remainingCents,
                    onVoucherReferenceChange = onVoucherReferenceChange,
                    onConfirm = onConfirmVoucher,
                )
            }

            if (state.errorMessage != null) {
                Spacer(Modifier.height(12.dp))
                Text(
                    state.errorMessage,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun MethodTab(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = modifier
            .height(56.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (selected) colors.accentSoft else colors.surface)
            .border(
                width = if (selected) 2.dp else 1.5.dp,
                color = if (selected) colors.accent else colors.inputBorder,
                shape = RoundedCornerShape(12.dp),
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (selected) colors.accentText else colors.muted,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.SemiBold,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun CardTabContent(remainingCents: Long, onConfirm: () -> Unit, isSubmitting: Boolean) {
    val colors = LocalZedReadColors.current
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(8.dp))
        Box(
            modifier = Modifier
                .size(130.dp)
                .clip(RoundedCornerShape(18.dp))
                .border(width = 2.dp, color = colors.inputBorder, shape = RoundedCornerShape(18.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text("📟", fontSize = 52.sp)
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "Present card or device to the terminal",
            color = colors.muted,
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(20.dp))
        PrimaryActionButton(
            label = "Charge ${formatCents(remainingCents)}",
            enabled = !isSubmitting && remainingCents > 0,
            isLoading = isSubmitting,
            onClick = onConfirm,
        )
    }
}

@Composable
private fun CashTabContent(
    state: PaymentUiState,
    remainingCents: Long,
    onPickTender: (Long) -> Unit,
    onConfirm: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    val presets = remember(remainingCents) { tenderPresetsCents(remainingCents) }
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            presets.take(3).forEach { preset -> TenderPresetTile(preset, state.tendered == preset, Modifier.weight(1f)) { onPickTender(preset) } }
        }
        if (presets.size > 3) {
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                presets.drop(3).forEach { preset -> TenderPresetTile(preset, state.tendered == preset, Modifier.weight(1f)) { onPickTender(preset) } }
            }
        }
        Spacer(Modifier.height(20.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bg)
                .padding(16.dp),
        ) {
            Column {
                Text("TENDERED", style = MaterialTheme.typography.labelSmall, color = colors.faint)
                Text(
                    if (state.tendered > 0) formatCents(state.tendered) else "—",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 22.sp,
                    color = colors.text,
                )
            }
            Spacer(Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.End) {
                Text("CHANGE", style = MaterialTheme.typography.labelSmall, color = colors.faint)
                val change = (state.tendered - remainingCents).coerceAtLeast(0)
                Text(
                    if (state.tendered > 0) formatCents(change) else "—",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 22.sp,
                    color = if (state.tendered > 0 && state.tendered >= remainingCents) colors.green else colors.faint,
                )
            }
        }
        Spacer(Modifier.height(16.dp))
        PrimaryActionButton(
            label = "Complete payment",
            enabled = !state.isSubmitting && state.tendered >= remainingCents && remainingCents > 0,
            isLoading = state.isSubmitting,
            onClick = onConfirm,
        )
    }
}

@Composable
private fun TenderPresetTile(amountCents: Long, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = modifier
            .height(52.dp)
            .clip(RoundedCornerShape(11.dp))
            .background(if (selected) colors.accentSoft else colors.surface)
            .border(
                width = 1.5.dp,
                color = if (selected) colors.accent else colors.inputBorder,
                shape = RoundedCornerShape(11.dp),
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            formatCents(amountCents),
            color = if (selected) colors.accentText else colors.text,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun VoucherTabContent(
    state: PaymentUiState,
    remainingCents: Long,
    onVoucherReferenceChange: (String) -> Unit,
    onConfirm: () -> Unit,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = state.voucherReference,
            onValueChange = onVoucherReferenceChange,
            label = { Text("Voucher reference code") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(20.dp))
        PrimaryActionButton(
            label = "Redeem ${formatCents(remainingCents)}",
            enabled = !state.isSubmitting && state.voucherReference.isNotBlank() && remainingCents > 0,
            isLoading = state.isSubmitting,
            onClick = onConfirm,
        )
    }
}

@Composable
private fun SplitAmountEntry(
    state: PaymentUiState,
    remainingCents: Long,
    onSplitAmountChange: (Long) -> Unit,
    onConfirm: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    var amountText by remember(state.method, state.paidCents) { mutableStateOf("") }

    fun applyDigit(digit: Char) {
        amountText = keypadAppendDigit(amountText, digit)
        onSplitAmountChange(dollarsToCents(amountText))
    }

    fun applyBackspace() {
        amountText = keypadBackspace(amountText)
        onSplitAmountChange(dollarsToCents(amountText))
    }

    Column {
        Text(
            "Partial amount",
            style = MaterialTheme.typography.labelSmall,
            color = colors.faint,
        )
        Spacer(Modifier.height(6.dp))
        KeypadAmountDisplay(value = amountText, placeholder = "0.00")
        Spacer(Modifier.height(10.dp))
        NumericKeypad(
            onDigit = ::applyDigit,
            onBackspace = ::applyBackspace,
            modifier = Modifier.widthIn(max = 260.dp),
        )
        Spacer(Modifier.height(8.dp))
        val after = (remainingCents - state.splitAmountCents).coerceAtLeast(0)
        Text(
            "Remaining after this payment: ${formatCents(after)}",
            style = MaterialTheme.typography.bodySmall,
            color = colors.muted,
        )
        Spacer(Modifier.height(16.dp))
        PrimaryActionButton(
            label = "Add payment${if (state.splitAmountCents > 0) " " + formatCents(state.splitAmountCents) else ""}",
            enabled = !state.isSubmitting && state.splitAmountCents > 0,
            isLoading = state.isSubmitting,
            onClick = onConfirm,
        )
    }
}

@Composable
private fun PrimaryActionButton(label: String, enabled: Boolean, isLoading: Boolean, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (enabled) colors.accent else colors.surface2)
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (isLoading) {
            CircularProgressIndicator(modifier = Modifier.size(22.dp), color = Color.White)
        } else {
            Text(
                label,
                color = if (enabled) Color.White else colors.faint,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun PaymentDoneContent(state: PaymentUiState, isOnline: Boolean, onNewOrder: () -> Unit) {
    val colors = LocalZedReadColors.current
    Column(
        modifier = Modifier.padding(40.dp).fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier
                .size(76.dp)
                .clip(CircleShape)
                .background(colors.greenSoft),
            contentAlignment = Alignment.Center,
        ) {
            Text("✓", color = colors.green, fontSize = 38.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(20.dp))
        Text(
            "Payment complete",
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.headlineSmall,
            color = colors.text,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "${state.doneMethodLabel} · ${formatCents(state.doneAmountCents)}",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
        if (!isOnline) {
            // Every sale is queued through the same sync mechanism now (see
            // SellViewModel's class doc), so this is worth surfacing only
            // when the device is genuinely offline right now — otherwise
            // it's redundant with the persistent top-bar sync badge.
            Spacer(Modifier.height(4.dp))
            Text(
                "Offline — queued, will sync automatically once back online",
                style = MaterialTheme.typography.labelSmall,
                color = colors.muted,
            )
        }
        if (state.doneChangeCents > 0) {
            Spacer(Modifier.height(22.dp))
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(colors.bg)
                    .padding(18.dp),
            ) {
                Text("CHANGE DUE", style = MaterialTheme.typography.labelSmall, color = colors.faint)
                Text(
                    formatCents(state.doneChangeCents),
                    color = colors.green,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 34.sp,
                )
            }
        }
        Spacer(Modifier.height(26.dp))
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(colors.accent)
                .clickable(onClick = onNewOrder),
            contentAlignment = Alignment.Center,
        ) {
            Text("New order", color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

/**
 * Cash tender presets, mirroring the design bundle's own computation:
 * the exact remaining amount, the next whole dollar up, then $20/$50/$100/
 * $200 — deduped and filtered to amounts that actually cover what's due,
 * capped at 6.
 */
private fun tenderPresetsCents(remainingCents: Long): List<Long> {
    if (remainingCents <= 0) return emptyList()
    val ceilDollar = ((remainingCents + 99) / 100) * 100
    val candidates = listOf(remainingCents, ceilDollar, 2000L, 5000L, 10000L, 20000L)
    val seen = LinkedHashSet<Long>()
    candidates.forEach { amount -> if (amount >= remainingCents) seen.add(amount) }
    return seen.take(6).toList()
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
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
