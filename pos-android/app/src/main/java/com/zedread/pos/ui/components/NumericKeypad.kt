package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.theme.LocalZedReadColors

/**
 * In-app numeric keypad — user-testing feedback: cash-in/cash-up and the
 * payment screen's amount fields should never open the Android soft
 * keyboard; a persistent on-screen pinpad should sit under the amount
 * display at all times instead, matching a dedicated POS terminal's usual
 * hardware/software split (staff shouldn't need a full QWERTY layout to key
 * in a dollar figure). Callers pair this with a **read-only** amount display
 * (see e.g. [KeypadAmountDisplay]) rather than a focusable [androidx.compose.material3.OutlinedTextField]
 * — the latter would still summon the IME on tap regardless of what other
 * input methods are offered alongside it.
 *
 * Stateless by design: the caller owns the current string value and applies
 * [keypadAppendDigit]/[keypadBackspace] to it, the same convention every
 * other screen in this app already uses for its own local editable state.
 */
@Composable
fun NumericKeypad(
    onDigit: (Char) -> Unit,
    onBackspace: () -> Unit,
    modifier: Modifier = Modifier,
    showDecimal: Boolean = true,
) {
    val rows = listOf(
        listOf('1', '2', '3'),
        listOf('4', '5', '6'),
        listOf('7', '8', '9'),
    )
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        rows.forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { digit -> KeypadButton(digit.toString(), Modifier.weight(1f)) { onDigit(digit) } }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            if (showDecimal) {
                KeypadButton(".", Modifier.weight(1f)) { onDigit('.') }
            } else {
                Box(Modifier.weight(1f))
            }
            KeypadButton("0", Modifier.weight(1f)) { onDigit('0') }
            KeypadButton("⌫", Modifier.weight(1f), onClick = onBackspace)
        }
    }
}

@Composable
private fun KeypadButton(label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = modifier
            .height(52.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(colors.surface)
            .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(10.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = colors.text, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
    }
}

/**
 * A non-focusable stand-in for an amount [androidx.compose.material3.OutlinedTextField] —
 * shows the current typed value (or [placeholder] when empty) with the same
 * bordered-box visual language as a real text field, but never opens the IME
 * since it isn't a text field at all. Pairs with [NumericKeypad], which is
 * the only way this value ever changes.
 */
@Composable
fun KeypadAmountDisplay(value: String, placeholder: String, modifier: Modifier = Modifier, label: String? = null) {
    val colors = LocalZedReadColors.current
    Column(modifier = modifier) {
        if (label != null) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = colors.faint)
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(colors.bg)
                .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(8.dp))
                .padding(horizontal = 14.dp),
            contentAlignment = Alignment.CenterStart,
        ) {
            Text(
                value.ifEmpty { placeholder },
                color = if (value.isEmpty()) colors.faint else colors.text,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

/**
 * Appends [digit] ('0'-'9' or '.') to a dollar-amount string, e.g. building
 * "12.34" one keypress at a time. A leading "0" is replaced rather than
 * accumulated ("0" + '5' -> "5", not "05"); a second '.' is ignored; digits
 * typed past [maxDecimals] places after the point are ignored, matching the
 * existing `^\d*\.?\d{0,2}$` typed-input validation this keypad replaces.
 */
fun keypadAppendDigit(current: String, digit: Char, maxDecimals: Int = 2): String {
    if (digit == '.') {
        return if (current.contains('.')) current else if (current.isEmpty()) "0." else "$current."
    }
    val decimalIndex = current.indexOf('.')
    if (decimalIndex >= 0 && current.length - decimalIndex - 1 >= maxDecimals) return current
    if (current == "0") return digit.toString()
    return current + digit
}

/**
 * Appends [digit] ('0'-'9') to a whole-number count string (denomination
 * counts — no decimal point), capped at [maxDigits] to match the prior
 * `^\d{0,4}$` typed-input validation.
 */
fun keypadAppendCountDigit(current: String, digit: Char, maxDigits: Int = 4): String {
    if (current.length >= maxDigits) return current
    if (current == "0") return digit.toString()
    return current + digit
}

/** Removes the last character, or leaves an already-empty value untouched. */
fun keypadBackspace(current: String): String = if (current.isEmpty()) current else current.dropLast(1)
