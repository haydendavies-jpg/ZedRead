package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.SyncItemUi

/**
 * Persistent, unobtrusive offline/pending-sync status — "Offline · N
 * pending" while there's queued work and no network, "N pending" once back
 * online (a drain is imminent/in progress), or "Synced" once the queue is
 * empty. Never a blocking modal — tapping it opens [SyncPanel] as a
 * dismissible overlay, staff keep selling underneath it either way.
 */
@Composable
fun SyncStatusBadge(
    isOnline: Boolean,
    pendingCount: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    val label = when {
        !isOnline && pendingCount > 0 -> "Offline · $pendingCount pending"
        !isOnline -> "Offline"
        pendingCount > 0 -> "$pendingCount pending"
        else -> "Synced"
    }
    val dotColor = if (!isOnline || pendingCount > 0) colors.accent else colors.green

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(20.dp))
            .background(colors.surface)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(dotColor))
        Text(label, style = MaterialTheme.typography.labelMedium, color = colors.text)
    }
}

/**
 * The offline/pending-sync detail panel: per-item status (a plain-language
 * failure reason for anything that genuinely failed — not an error code)
 * and the manual "Sync now" action.
 */
@Composable
fun SyncPanel(
    isOnline: Boolean,
    items: List<SyncItemUi>,
    onSyncNow: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.42f))
            .clickable(onClick = onDismiss),
    ) {
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .heightFraction(0.6f)
                .clickable(enabled = false) {}
                .background(colors.surface),
        ) {
            Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        if (isOnline) "Sync status" else "Offline — will sync automatically",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.text,
                    )
                    Text("✕", color = colors.muted, modifier = Modifier.clickable(onClick = onDismiss))
                }
                Spacer(Modifier.height(12.dp))

                if (items.isEmpty()) {
                    Box(Modifier.fillMaxWidth().height(80.dp), contentAlignment = Alignment.Center) {
                        Text("Everything is synced.", color = colors.muted)
                    }
                } else {
                    LazyColumn(modifier = Modifier.weight(1f)) {
                        items(items, key = { it.id }) { item ->
                            SyncItemRow(item)
                            HorizontalDivider(color = colors.border)
                        }
                    }
                }

                Spacer(Modifier.height(16.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(colors.accent)
                        .clickable(onClick = onSyncNow),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Sync now", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun SyncItemRow(item: SyncItemUi) {
    val colors = LocalZedReadColors.current
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Text(item.title, style = MaterialTheme.typography.bodyLarge, color = colors.text, fontWeight = FontWeight.SemiBold)
        Text(
            item.subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = if (item.isFailed) MaterialTheme.colorScheme.error else colors.muted,
        )
    }
}

/** Small helper so the panel takes a fraction of screen height rather than the whole thing, like a bottom sheet. */
private fun Modifier.heightFraction(fraction: Float): Modifier = this.then(Modifier.fillMaxHeight(fraction))
