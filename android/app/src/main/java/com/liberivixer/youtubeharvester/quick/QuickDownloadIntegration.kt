package com.liberivixer.youtubeharvester.quick

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon
import com.liberivixer.youtubeharvester.MainActivity
import com.liberivixer.youtubeharvester.R

object QuickDownloadIntegration {
    const val ACTION_QUICK_DOWNLOAD = "com.liberivixer.youtubeharvester.action.QUICK_DOWNLOAD"

    fun clipboardText(context: Context): String? {
        val clipboard = context.getSystemService(ClipboardManager::class.java)
        val clip = clipboard.primaryClip ?: return null
        if (clip.itemCount == 0) return null
        return clip.getItemAt(0).coerceToText(context)?.toString()?.trim()?.takeIf(String::isNotBlank)
    }

    fun clipboardSignature(context: Context, text: String): String {
        val timestamp = context.getSystemService(ClipboardManager::class.java)
            .primaryClipDescription
            ?.timestamp
            ?: 0L
        return "$timestamp:${text.hashCode()}"
    }

    fun requestPinnedShortcut(context: Context): ShortcutRequestResult {
        val manager = context.getSystemService(ShortcutManager::class.java)
        if (!manager.isRequestPinShortcutSupported) return ShortcutRequestResult.Unsupported
        val launchIntent = Intent(context, MainActivity::class.java).apply {
            action = ACTION_QUICK_DOWNLOAD
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val shortcut = ShortcutInfo.Builder(context, SHORTCUT_ID)
            .setShortLabel(context.getString(R.string.quick_download))
            .setLongLabel(context.getString(R.string.app_shortcut_hint))
            .setIcon(Icon.createWithResource(context, R.mipmap.ic_launcher))
            .setIntent(launchIntent)
            .build()
        return if (manager.requestPinShortcut(shortcut, null)) {
            ShortcutRequestResult.Requested
        } else {
            ShortcutRequestResult.Rejected
        }
    }

    private const val SHORTCUT_ID = "quick-download"
}

enum class ShortcutRequestResult {
    Requested,
    Unsupported,
    Rejected,
}
