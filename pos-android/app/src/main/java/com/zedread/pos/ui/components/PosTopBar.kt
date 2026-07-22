package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
 * Persistent top navigation bar — per user-testing feedback, every screen
 * (including End of Day, which previously had no way back once entered)
 * must always show this bar, never a screen-specific one-off header with no
 * escape hatch. Shows this terminal's own configured name (PosDevice.
 * device_name, via TokenStore — falls back to a generic label before the
 * first login populates it) instead of a generic "Register" title, an
 * optional subtitle (e.g. the selected category, or the current screen's
 * name), a back affordance where the screen has somewhere to go back to,
 * screen-specific actions in the middle (History/Settings/Cash-up/Switch
 * operator icons on Register; empty elsewhere), and the sync status badge +
 * ZedRead wordmark pinned to the trailing edge on every screen — the sync
 * badge is no longer a floating overlay icon.
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
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .border(width = 1.dp, color = colors.border)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = colors.text)
                }
            }
            Column {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
                if (subtitle != null) {
                    Text(subtitle.uppercase(), style = MaterialTheme.typography.labelSmall, color = colors.faint)
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            actions()
            SyncStatusBadge(isOnline = isOnline, pendingCount = pendingCount, onClick = onSyncClick)
            ZedReadBadge()
        }
    }
}

/** Small "Z" wordmark badge — the ZedRead identity every top bar carries in its trailing corner. */
@Composable
private fun ZedReadBadge() {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .padding(start = 8.dp)
            .size(28.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(colors.accent),
        contentAlignment = Alignment.Center,
    ) {
        Text("Z", color = androidx.compose.ui.graphics.Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
    }
}
