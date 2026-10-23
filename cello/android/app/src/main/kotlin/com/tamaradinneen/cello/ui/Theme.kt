package com.tamaradinneen.cello.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// The host site's palette: Prussian blue, warm ivory, champagne gold,
// charcoal body text. Gold is a seasoning, never a fill.
object Brand {
    val Prussian = Color(0xFF003152)
    val PrussianDeep = Color(0xFF002238)
    val Ivory = Color(0xFFFAF7F0)
    val IvoryDim = Color(0xFFF1ECE1)
    val Gold = Color(0xFFC2A96A)
    val GoldDeep = Color(0xFF9C7E3B)
    val Charcoal = Color(0xFF2A2A2A)
    val CharcoalSoft = Color(0xFF5C5C5C)
    val Rule = Color(0xFFDDD5C4)

    val Good = Color(0xFF2F6B4F)
    val GoodBright = Color(0xFF6FC79A)
    val Warn = Color(0xFF8A6D1F)
    val WarnBright = Color(0xFFE0BF5E)
    val Off = Color(0xFF8C3A2B)
    val OffBright = Color(0xFFE49585)
}

private val scheme = lightColorScheme(
    primary = Brand.Prussian,
    onPrimary = Brand.Ivory,
    secondary = Brand.GoldDeep,
    onSecondary = Brand.Ivory,
    background = Brand.Ivory,
    onBackground = Brand.Charcoal,
    surface = Color.White,
    onSurface = Brand.Charcoal,
    surfaceVariant = Brand.IvoryDim,
    onSurfaceVariant = Brand.CharcoalSoft,
    outline = Brand.Rule,
    error = Brand.Off,
)

val Caps = TextStyle(
    fontSize = 11.sp,
    fontWeight = FontWeight.SemiBold,
    letterSpacing = 1.4.sp,
)

@Composable
fun CelloTheme(content: @Composable () -> kotlin.Unit) {
    // Deliberately light in both system modes: the stage panels are already
    // dark, and a full dark theme would put dark text on dark panels.
    @Suppress("UNUSED_EXPRESSION") isSystemInDarkTheme()
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
}
