package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.theme.LocalZedReadColors

/**
 * Shared "popup card" chrome for the Register's start/end-of-day flows —
 * user-testing feedback that cash-in/cash-up should read as the same style
 * of popup as [com.zedread.pos.ui.screens.orderentry.ModifierSheetOverlay]
 * instead of a plain full-bleed form. Unlike the modifier sheet, cash-in/
 * cash-up are real nav destinations (not an overlay on top of another
 * screen — [onClose] is optional and absent entirely on CashInScreen, which
 * has nowhere to back out to), so this renders as a centered rounded card
 * over the page's own [LocalZedReadColors.bg] canvas rather than a dimming
 * scrim over live content underneath — same visual language (rounded
 * corners, header/divider/footer), different context.
 */
@Composable
fun RegisterPopupCard(
    title: String,
    subtitle: String? = null,
    onClose: (() -> Unit)? = null,
    // Wider for the denomination-grid cash entry variant (see
    // CashDenominationGrid's doc) — its single-column list of 11
    // denominations plus a side-by-side keypad needs more room than the
    // plain bulk-total entry's single field+keypad ever did. Default
    // unchanged from before this parameter existed.
    maxWidth: Dp = 480.dp,
    footer: @Composable () -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bg)
            .padding(20.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = maxWidth)
                .fillMaxWidth(0.92f)
                // Denomination-grid variant gets nearly the full height budget —
                // its 11-row list is the tallest content this card ever hosts, and
                // the previous 0.85f cap forced it to scroll on anything short of
                // a large tablet (user-testing feedback: cash-in/cash-up should
                // never need to scroll). Bulk-total entry doesn't need the extra
                // room but fitting it inside a taller card is harmless.
                .fillMaxHeight(if (maxWidth > 480.dp) 0.96f else 0.85f)
                .clip(RoundedCornerShape(18.dp))
                .background(colors.surface),
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                title,
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleLarge,
                                color = colors.text,
                            )
                            if (subtitle != null) {
                                Spacer(Modifier.height(2.dp))
                                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = colors.faint)
                            }
                        }
                        if (onClose != null) {
                            Box(
                                modifier = Modifier
                                    .size(34.dp)
                                    .clip(RoundedCornerShape(9.dp))
                                    .clickable(onClick = onClose),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text("✕", color = colors.muted, style = MaterialTheme.typography.titleMedium)
                            }
                        }
                    }
                    HorizontalDivider(color = colors.border)
                }
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .imePadding()
                        .verticalScroll(rememberScrollState())
                        .padding(PaddingValues(horizontal = 22.dp, vertical = 10.dp)),
                    content = content,
                )
                Column {
                    HorizontalDivider(color = colors.border)
                    Box(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) { footer() }
                }
            }
        }
    }
}
