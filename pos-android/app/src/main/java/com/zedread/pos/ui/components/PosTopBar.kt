package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Fixed, theme-independent colours for this bar — per user-testing feedback
// the top bar always reads #332E29 (the portal's own dark-mode --zr-sidebar,
// pos-portal/src/index.css) with white content, in light AND dark app theme
// alike, unlike every other surface in the app which follows ZedReadColors'
// light/dark swap. Supersedes an earlier round's "always #FFFFFF" request.
private val TopBarBackground = Color(0xFF332E29)
private val TopBarText = Color.White
private val TopBarFaint = Color(0xFFD9D4CE) // muted near-white for the subtitle/tagline — full white would out-compete the title

/**
 * Persistent top navigation bar — per user-testing feedback, every screen
 * (including End of Day, which previously had no way back once entered)
 * must always show this bar, never a screen-specific one-off header with no
 * escape hatch. Leads with the [ZedReadWordmark] (moved here from the
 * trailing edge per user-testing feedback), then this terminal's own
 * configured name (PosDevice.device_name, via TokenStore — falls back to a
 * generic label before the first login populates it) instead of a generic
 * "Register" title, an optional subtitle (e.g. the selected category, or
 * the current screen's name — see the doc on [PosTopBar]'s `subtitle`
 * param for what it actually shows on the Register screen), a back
 * affordance where the screen has somewhere to go back to, screen-specific
 * actions in the middle (History/Settings/Cash-up/Switch operator icons on
 * Register; empty elsewhere), and the sync status badge on the trailing
 * edge — no longer a floating overlay icon.
 *
 * The background is always [TopBarBackground] (#332E29), never
 * ZedReadColors.surface — the design calls for this fixed dark bar in both
 * light and dark app mode, so its text/icon colours are pinned to fixed
 * white/near-white equivalents rather than the theme-aware
 * [LocalZedReadColors] the rest of this bar's content would otherwise use,
 * to stay legible against that fixed dark background regardless of the
 * app's own theme.
 */
/**
 * @param title This terminal's configured name (e.g. "POS #8" — see the
 * class doc). @param subtitle Context for the current screen — on
 * Register specifically, this is the name of whichever menu tab or
 * category is currently active (e.g. "TEST" is a Menu Studio tab named
 * "Test", not a build/debug label — see OrderEntryScreen's own subtitle
 * wiring), elsewhere it's a plain screen name like "Settings".
 */
@Composable
fun PosTopBar(
    title: String,
    subtitle: String? = null,
    onBack: (() -> Unit)? = null,
    isOnline: Boolean,
    pendingCount: Int,
    onSyncClick: () -> Unit,
    actions: @Composable RowScope.() -> Unit = {},
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(TopBarBackground)
            .border(width = 1.dp, color = Color(0x1FFFFFFF))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = TopBarText)
                }
            }
            ZedReadWordmark()
            Spacer(Modifier.width(10.dp))
            Column {
                // Sized down from titleLarge and set closer to the wordmark —
                // user-testing feedback that this terminal-name block read as
                // a second, competing logo rather than a small secondary
                // label sitting inline beside the real one.
                Text(title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = TopBarText)
                if (subtitle != null) {
                    Text(subtitle.uppercase(), style = MaterialTheme.typography.labelSmall, color = TopBarFaint)
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            actions()
            SyncStatusBadge(isOnline = isOnline, pendingCount = pendingCount, onClick = onSyncClick)
        }
    }
}

/**
 * The ZedRead wordmark — matches the portal's own sign-in page treatment
 * (serif "ZedRead" + a small uppercase tagline underneath, see
 * pos-portal's AuthPageShell.tsx) rather than the earlier single-letter "Z"
 * tile. Per user-testing feedback: moved from the bar's trailing edge
 * (where the terminal name now sits, shifted right to make room) to
 * leading, sized up, and set to plain white — it was previously the
 * portal's own brand taupe, which read as illegible dark-on-dark once the
 * bar's own background became the fixed dark #332E29.
 */
@Composable
private fun ZedReadWordmark() {
    Column(horizontalAlignment = Alignment.Start) {
        Text(
            "ZedRead",
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.Bold,
            fontSize = 22.sp,
            color = TopBarText,
        )
        Text(
            "POS YOU CAN COUNT ON",
            fontSize = 7.sp,
            letterSpacing = 0.8.sp,
            color = TopBarFaint,
        )
    }
}
