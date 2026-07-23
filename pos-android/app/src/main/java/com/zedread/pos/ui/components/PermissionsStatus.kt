package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zedread.pos.data.repository.permissionLabel
import com.zedread.pos.ui.theme.LocalZedReadColors

private val WarningColor = Color(0xFFFFC107)

/**
 * Compact icon badge shown in [PosTopBar] only when
 * [com.zedread.pos.ui.viewmodel.PermissionsViewModel.missingPermissions] is
 * non-empty — deliberately icon-only (not a text pill like
 * [SyncStatusBadge]) to sit alongside the other icon actions already
 * crowding some screens' top bars (e.g. Register's History/Settings/
 * Cash-up/Switch-operator row).
 */
@Composable
fun PermissionsWarningBadge(onClick: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(onClick = onClick, modifier = modifier) {
        Icon(Icons.Default.Warning, contentDescription = "Missing permissions", tint = WarningColor)
    }
}

/**
 * Lists what's missing in plain language (never a raw `android.permission.*`
 * string — see [permissionLabel]) with two ways to fix it: re-request
 * through the normal OS dialog (works unless the user picked "Don't ask
 * again"/denied twice, the one case Android requires going through system
 * Settings instead), or jump straight to this app's Settings page.
 * Same bottom-sheet-over-scrim treatment as [SyncPanel] for visual
 * consistency between the two persistent top-bar badges.
 */
@Composable
fun PermissionsPanel(
    missingPermissions: List<String>,
    onRequestAgain: () -> Unit,
    onOpenSettings: () -> Unit,
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
                .fillMaxHeight(0.5f)
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
                        "Permissions needed",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.text,
                    )
                    Text("✕", color = colors.muted, modifier = Modifier.clickable(onClick = onDismiss))
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "Printer discovery needs these to work on this device:",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.muted,
                )
                Spacer(Modifier.height(14.dp))
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(missingPermissions, key = { it }) { permission ->
                        Text(
                            "•  ${permissionLabel(permission)}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = colors.text,
                            modifier = Modifier.padding(vertical = 6.dp),
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(colors.accent)
                            .clickable(onClick = onRequestAgain),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("Grant permissions", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .border(width = 1.5.dp, color = colors.inputBorder, shape = RoundedCornerShape(10.dp))
                            .clickable(onClick = onOpenSettings),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("Open settings", color = colors.text, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}
