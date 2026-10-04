package com.liberivixer.youtubeharvester.ui

import android.app.Activity
import android.app.LocaleManager
import android.os.Build
import android.os.LocaleList
import android.content.Context
import android.content.res.Configuration
import androidx.core.content.edit
import com.liberivixer.youtubeharvester.model.AppLanguage
import java.util.Locale

object LocaleController {
    private const val PREFERENCES = "yth_locale"
    private const val LANGUAGE_TAG = "language_tag"

    fun wrap(context: Context): Context {
        val tag = currentTag(context)
        val locale = Locale.forLanguageTag(tag)
        Locale.setDefault(locale)
        val configuration = Configuration(context.resources.configuration).apply {
            setLocale(locale)
            setLayoutDirection(locale)
        }
        return context.createConfigurationContext(configuration)
    }

    fun currentTag(context: Context): String {
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        if (Build.VERSION.SDK_INT >= 33) {
            val manager = context.getSystemService(LocaleManager::class.java)
            if (!preferences.getBoolean("framework_migrated", false)) {
                if (manager.applicationLocales.isEmpty) {
                    manager.applicationLocales = LocaleList.forLanguageTags(preferences.getString(LANGUAGE_TAG, AppLanguage.English.tag))
                }
                preferences.edit { putBoolean("framework_migrated", true) }
            }
            val selected = manager.applicationLocales.get(0) ?: manager.systemLocales.get(0)
            return AppLanguage.entries.firstOrNull {
                Locale.forLanguageTag(it.tag).language == selected?.language
            }?.tag ?: AppLanguage.English.tag
        }
        return preferences.getString(LANGUAGE_TAG, AppLanguage.English.tag) ?: AppLanguage.English.tag
    }

    fun setLanguage(context: Context, tag: String) {
        if (Build.VERSION.SDK_INT >= 33) {
            context.getSystemService(LocaleManager::class.java).applicationLocales = LocaleList.forLanguageTags(tag)
        }
    }

    fun apply(activity: Activity, storedLanguage: String) {
        if (Build.VERSION.SDK_INT >= 33) return
        val tag = AppLanguage.fromStored(storedLanguage).tag
        if (currentTag(activity) == tag) return
        activity.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit {
            putString(LANGUAGE_TAG, tag)
        }
        activity.recreate()
    }
}
