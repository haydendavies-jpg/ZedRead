package com.zedread.pos.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * ZedRead Register design tokens — from design_handoff_zedread/README.md's
 * "Shared design system" section. Several of these (surface2, border,
 * accent-soft, green) have no direct Material3 colorScheme slot with
 * matching semantics, so they're exposed via [LocalZedReadColors] rather
 * than forced into ill-fitting MaterialTheme roles. Font swap (Public Sans /
 * IBM Plex Sans / IBM Plex Mono via the downloadable-fonts API) is a
 * separate, still-unbuilt follow-up — see ANDROID_POS_BUILD_PLAN.md.
 */
data class ZedReadColors(
    val bg: Color,
    val sidebar: Color,
    val surface: Color,
    val surface2: Color,
    val border: Color,
    val divider: Color,
    val inputBorder: Color,
    val text: Color,
    val muted: Color,
    val faint: Color,
    val accent: Color,
    val accentText: Color,
    val accentSoft: Color,
    val accentSoft2: Color,
    val green: Color,
    val greenSoft: Color,
)

private val LightZedReadColors = ZedReadColors(
    bg = Color(0xFFFAF7F2),
    sidebar = Color(0xFF554C44),
    surface = Color(0xFFFFFFFF),
    surface2 = Color(0xFFF0ECE3),
    border = Color(0x14241F1A),
    divider = Color(0x0F241F1A),
    inputBorder = Color(0x29241F1A),
    text = Color(0xFF241F1A),
    muted = Color(0xFF6B6259),
    faint = Color(0xFFA39A8C),
    accent = Color(0xFFA82040),
    accentText = Color(0xFFA82040),
    accentSoft = Color(0x1AA82040),
    accentSoft2 = Color(0x29A82040),
    green = Color(0xFF2F4034),
    greenSoft = Color(0x242F4034),
)

private val DarkZedReadColors = ZedReadColors(
    bg = Color(0xFF201A15),
    sidebar = Color(0xFF1B1611),
    surface = Color(0xFF2A2119),
    surface2 = Color(0xFF33291F),
    border = Color(0x14FFFFFF),
    divider = Color(0x0FFFFFFF),
    inputBorder = Color(0x26FFFFFF),
    text = Color(0xFFEFE9E0),
    muted = Color(0xFFA89F92),
    faint = Color(0xFF6F685E),
    accent = Color(0xFFA82040),
    accentText = Color(0xFFE58BA0),
    accentSoft = Color(0x33A82040),
    accentSoft2 = Color(0x4DA82040),
    green = Color(0xFF8FBF9C),
    greenSoft = Color(0x298FBF9C),
)

val LocalZedReadColors = staticCompositionLocalOf { LightZedReadColors }

private val LightMaterialColors = lightColorScheme(
    primary = LightZedReadColors.accent,
    onPrimary = Color.White,
    background = LightZedReadColors.bg,
    onBackground = LightZedReadColors.text,
    surface = LightZedReadColors.surface,
    onSurface = LightZedReadColors.text,
    surfaceVariant = LightZedReadColors.surface2,
    onSurfaceVariant = LightZedReadColors.muted,
    outline = LightZedReadColors.inputBorder,
    error = Color(0xFFA82040),
)

private val DarkMaterialColors = darkColorScheme(
    primary = DarkZedReadColors.accentText,
    onPrimary = Color.White,
    background = DarkZedReadColors.bg,
    onBackground = DarkZedReadColors.text,
    surface = DarkZedReadColors.surface,
    onSurface = DarkZedReadColors.text,
    surfaceVariant = DarkZedReadColors.surface2,
    onSurfaceVariant = DarkZedReadColors.muted,
    outline = DarkZedReadColors.inputBorder,
    error = Color(0xFFE58BA0),
)

/**
 * Picks readable text (the design system's near-black `--text` or white)
 * against an arbitrary category/tile fill color, per the design bundle's
 * "luminance test" rule. [hex] is `#RRGGBB`; malformed input falls back to
 * white (the safer default against an unknown-brightness fill).
 */
fun contrastTextColor(hex: String, onLight: Color = Color(0xFF241F1A), onDark: Color = Color.White): Color {
    val clean = hex.removePrefix("#")
    if (clean.length != 6) return onDark
    return runCatching {
        val r = clean.substring(0, 2).toInt(16)
        val g = clean.substring(2, 4).toInt(16)
        val b = clean.substring(4, 6).toInt(16)
        val luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        if (luminance > 0.55) onLight else onDark
    }.getOrDefault(onDark)
}

/** Parses a `#RRGGBB` category/tile fill color; malformed input falls back to a neutral gray. */
fun parseHexColor(hex: String): Color {
    val clean = hex.removePrefix("#")
    if (clean.length != 6) return Color(0xFF5A5550)
    return runCatching { Color(0xFF000000 or clean.toLong(16)) }.getOrDefault(Color(0xFF5A5550))
}

@Composable
fun ZedReadTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val zedColors = if (dark) DarkZedReadColors else LightZedReadColors
    CompositionLocalProvider(LocalZedReadColors provides zedColors) {
        MaterialTheme(
            colorScheme = if (dark) DarkMaterialColors else LightMaterialColors,
            content = content,
        )
    }
}
