package com.zedread.pos.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.LightMode
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.TableBar
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.ThemeState
import com.zedread.pos.ui.viewmodel.TopNavViewModel

/**
 * Which persistent top-nav tab is active. `ONLINE` is a disabled placeholder
 * — see [TopNavBar]'s doc — so it deliberately has no destination route of
 * its own to navigate to.
 */
enum class TopNavTab { REGISTER, TABLES, ONLINE }

/**
 * Wraps a screen with the persistent top navigation bar
 * (README-tables-floormap.md's "Top Navigation Bar (persistent)" section,
 * Android POS Phase 4) — the shared chrome for the Register and Tables
 * routes. [content] fills the remaining space below the 64dp bar.
 */
@Composable
fun MainScaffold(
    activeTab: TopNavTab,
    onSelectRegister: () -> Unit,
    onSelectTables: () -> Unit,
    content: @Composable () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
        TopNavBar(activeTab = activeTab, onSelectRegister = onSelectRegister, onSelectTables = onSelectTables)
        Box(modifier = Modifier.fillMaxSize()) { content() }
    }
}

/**
 * The persistent top nav bar itself: logo tile, Register/Tables/Online nav
 * items, a theme toggle, and a static avatar.
 *
 * **Online tab**: per ANDROID_POS_BUILD_PLAN.md's Phase 4 scope, this is a
 * disabled placeholder — non-clickable, dimmed, and carries no order-count
 * badge, since fabricating one would need a real online-orders feature this
 * phase explicitly excludes.
 *
 * **Avatar**: a static circle showing the signed-in operator's first
 * initial ([TopNavViewModel.userName]) — the design bundle's own avatar is
 * likewise just a static "M" glyph, not a real profile picture, and no
 * profile-photo concept exists anywhere else in this app yet.
 */
@Composable
private fun TopNavBar(
    activeTab: TopNavTab,
    onSelectRegister: () -> Unit,
    onSelectTables: () -> Unit,
    viewModel: TopNavViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val userName by viewModel.userName.collectAsState()
    val isDark = ThemeState.darkOverride ?: isSystemInDarkTheme()

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(64.dp)
            .background(colors.sidebar)
            .padding(horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Logo tile.
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(Color.White.copy(alpha = 0.14f)),
            contentAlignment = Alignment.Center,
        ) {
            Text("Z", fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold, fontSize = 21.sp, color = Color.White)
        }

        Row(modifier = Modifier.padding(start = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            NavItem(
                label = "Register",
                icon = Icons.Default.Receipt,
                active = activeTab == TopNavTab.REGISTER,
                onClick = onSelectRegister,
            )
            Spacer(Modifier.width(5.dp))
            NavItem(
                label = "Tables",
                icon = Icons.Default.TableBar,
                active = activeTab == TopNavTab.TABLES,
                onClick = onSelectTables,
            )
            Spacer(Modifier.width(5.dp))
            NavItem(
                label = "Online",
                icon = Icons.Default.Public,
                active = false,
                enabled = false,
                onClick = {},
            )
        }

        Spacer(Modifier.weight(1f))

        IconButton(onClick = { ThemeState.darkOverride = !isDark }) {
            Icon(
                if (isDark) Icons.Default.LightMode else Icons.Default.DarkMode,
                contentDescription = "Toggle theme",
                tint = Color.White,
            )
        }

        Box(
            modifier = Modifier
                .padding(start = 4.dp)
                .size(32.dp)
                .clip(CircleShape)
                .background(colors.accentSoft2),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                (userName?.trim()?.firstOrNull()?.uppercaseChar() ?: '?').toString(),
                fontWeight = FontWeight.Bold,
                fontSize = 13.sp,
                color = Color.White,
            )
        }
    }
}

@Composable
private fun NavItem(
    label: String,
    icon: ImageVector,
    active: Boolean,
    onClick: () -> Unit,
    enabled: Boolean = true,
) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(if (active) Color.White.copy(alpha = 0.14f) else Color.Transparent)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 10.dp)
            .alpha(if (enabled) 1f else 0.45f),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = label, tint = Color.White, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(9.dp))
        Text(label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = Color.White)
    }
}
