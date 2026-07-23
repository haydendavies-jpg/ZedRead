package com.zedread.pos.ui.screens.sync

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.SyncSplashViewModel

/**
 * Post-login sync splash — ZedRead wordmark over a status line + progress
 * bar (see [SyncSplashViewModel]'s doc for why this blocks briefly instead
 * of syncing silently like everything else in the app), then hands off to
 * [onDone] once every step has settled (success or not — offline devices
 * must still be able to reach the Register).
 */
@Composable
fun SyncSplashScreen(
    onDone: () -> Unit,
    viewModel: SyncSplashViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val state by viewModel.state.collectAsState()

    LaunchedEffect(state.isDone) {
        if (state.isDone) onDone()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bg),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "ZedRead",
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.Bold,
            fontSize = 30.sp,
            color = colors.accentText,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "POS YOU CAN COUNT ON",
            style = MaterialTheme.typography.labelSmall,
            letterSpacing = 2.sp,
            color = colors.faint,
        )
        Spacer(Modifier.height(40.dp))
        LinearProgressIndicator(
            progress = { state.progress },
            modifier = Modifier
                .widthIn(max = 280.dp)
                .fillMaxWidth(0.7f)
                .height(6.dp)
                .clip(RoundedCornerShape(3.dp)),
            color = colors.accent,
            trackColor = colors.border,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            state.currentLabel,
            style = MaterialTheme.typography.bodySmall,
            color = if (state.hadError) MaterialTheme.colorScheme.error else colors.faint,
        )
    }
}
