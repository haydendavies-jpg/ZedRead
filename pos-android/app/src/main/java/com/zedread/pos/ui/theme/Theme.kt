package com.zedread.pos.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** ZedRead brand: crimson #7B1D2A as primary. */
private val Crimson = Color(0xFF7B1D2A)
private val CrimsonContainer = Color(0xFFFFDAD6)

private val LightColors = lightColorScheme(
    primary = Crimson,
    onPrimary = Color.White,
    primaryContainer = CrimsonContainer,
    surface = Color(0xFFFFFBFE),
    background = Color(0xFFF5F5F5),
)

@Composable
fun ZedReadTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        content = content,
    )
}
