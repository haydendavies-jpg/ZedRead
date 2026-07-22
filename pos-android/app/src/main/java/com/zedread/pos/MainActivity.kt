package com.zedread.pos

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import dagger.hilt.android.AndroidEntryPoint
import com.zedread.pos.ui.PosNavHost
import com.zedread.pos.ui.theme.ZedReadTheme

/**
 * Single-activity host. Navigation handled entirely by Compose NavHost.
 *
 * Runs immersive/kiosk-style: the system status bar and navigation bar are
 * hidden while the terminal is in use (a POS register has no business
 * showing the clock, notifications, or a back/home/recents bar) — a swipe
 * from either edge reveals them transiently without dismissing the hide.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        hideSystemBars()
        setContent {
            ZedReadTheme {
                PosNavHost()
            }
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        // Re-hide on every focus regain — a transient reveal (edge swipe) or
        // returning from another app/the recents screen both clear the
        // hidden state otherwise.
        if (hasFocus) hideSystemBars()
    }

    private fun hideSystemBars() {
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }
}
