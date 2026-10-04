package com.liberivixer.youtubeharvester.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import com.liberivixer.youtubeharvester.model.AppThemeMode

val AccentBlue = Color(0xFF278CE8)
val DeepBackground = Color(0xFF0B1117)
val PanelBackground = Color(0xFF111820)
val RaisedBackground = Color(0xFF18212B)
val BorderColor = Color(0xFF2A3540)
val SecondaryText = Color(0xFFAAB4C0)
val SuccessGreen = Color(0xFF4CAF50)
val ErrorRed = Color(0xFFE94A4A)

private val DarkColors = darkColorScheme(
    primary = AccentBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF163C60),
    onPrimaryContainer = Color(0xFFDCEEFF),
    secondary = SecondaryText,
    onSecondary = DeepBackground,
    secondaryContainer = RaisedBackground,
    onSecondaryContainer = Color(0xFFF0F3F7),
    tertiary = Color(0xFF7D8B99),
    onTertiary = DeepBackground,
    tertiaryContainer = Color(0xFF202A34),
    onTertiaryContainer = Color(0xFFE4E9EE),
    background = DeepBackground,
    onBackground = Color(0xFFF0F3F7),
    surface = PanelBackground,
    onSurface = Color(0xFFF0F3F7),
    surfaceVariant = RaisedBackground,
    onSurfaceVariant = SecondaryText,
    outline = BorderColor,
    error = ErrorRed,
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF176FB5),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD7EAFA),
    onPrimaryContainer = Color(0xFF082E4D),
    secondary = Color(0xFF53616E),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE1E7EC),
    onSecondaryContainer = Color(0xFF1D2831),
    tertiary = Color(0xFF66737F),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFE5EAF0),
    onTertiaryContainer = Color(0xFF212B35),
    background = Color(0xFFF4F6F8),
    onBackground = Color(0xFF17202A),
    surface = Color.White,
    onSurface = Color(0xFF17202A),
    surfaceVariant = Color(0xFFE8EDF2),
    onSurfaceVariant = Color(0xFF4E5B68),
    outline = Color(0xFFBCC6D0),
    error = Color(0xFFBA1A1A),
)

@Composable
fun YouTubeHarvesterTheme(
    mode: AppThemeMode,
    content: @Composable () -> Unit,
) {
    val dark = when (mode) {
        AppThemeMode.System -> isSystemInDarkTheme()
        AppThemeMode.Light -> false
        AppThemeMode.Dark -> true
    }
    val view = LocalView.current
    if (!view.isInEditMode) {
        val window = (view.context as Activity).window
        WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !dark
        WindowCompat.getInsetsController(window, view).isAppearanceLightNavigationBars = !dark
    }
    MaterialTheme(
        colorScheme = if (dark) DarkColors else LightColors,
        content = content,
    )
}
