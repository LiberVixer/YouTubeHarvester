package com.liberivixer.youtubeharvester.data

import android.content.Context
import android.content.SharedPreferences
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.AppLanguage
import com.liberivixer.youtubeharvester.model.AppThemeMode
import com.liberivixer.youtubeharvester.model.CheckReport
import com.liberivixer.youtubeharvester.model.CheckOutcome
import com.liberivixer.youtubeharvester.model.SectionResult
import com.liberivixer.youtubeharvester.model.SectionStatus
import com.liberivixer.youtubeharvester.model.overviewContentTypes
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.Dispatchers

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "yth_settings")

class SettingsDataStore(context: Context, private val dataStore: DataStore<Preferences> = context.applicationContext.settingsDataStore) {
    private val secretCipher = SecretCipher()

    val settings: Flow<AppSettings> = dataStore.data
        .catch { error ->
            if (error is IOException) emit(emptyPreferences()) else throw error
        }
        .map(::preferencesToSettings)
        .distinctUntilChanged()
        .flowOn(Dispatchers.IO)

    val lastCheck: Flow<CheckReport?> = dataStore.data
        .catch { if (it is IOException) emit(emptyPreferences()) else throw it }
        .map { p ->
            val finished = p[longPreferencesKey("check_finished")] ?: return@map null
            CheckReport(finished,
                CheckOutcome.entries.firstOrNull { it.name == p[stringPreferencesKey("check_outcome")] } ?: CheckOutcome.FAILED,
                p[intPreferencesKey("check_checked")] ?: 0,
                p[intPreferencesKey("check_total")] ?: 0,
                p[intPreferencesKey("check_errors")] ?: 0,
                p[intPreferencesKey("check_downloaded")] ?: 0,
                overviewContentTypes.associateWith { type ->
                    SectionResult(p[intPreferencesKey("check_count_${type.name}")] ?: 0,
                        SectionStatus.entries.firstOrNull { it.name == p[stringPreferencesKey("check_status_${type.name}")] } ?: SectionStatus.WAITING)
                }, p[intPreferencesKey("check_attempted")] ?: 0)
        }

    suspend fun saveCheckReport(report: CheckReport) {
        dataStore.edit { p ->
            p[longPreferencesKey("check_finished")] = report.finishedAt
            p[stringPreferencesKey("check_outcome")] = report.outcome.name
            p[intPreferencesKey("check_checked")] = report.checkedChannels
            p[intPreferencesKey("check_total")] = report.totalChannels
            p[intPreferencesKey("check_errors")] = report.errors
            p[intPreferencesKey("check_downloaded")] = report.downloaded
            p[intPreferencesKey("check_attempted")] = report.attempted
            overviewContentTypes.forEach { type ->
                val section = report.sections[type] ?: SectionResult()
                p[intPreferencesKey("check_count_${type.name}")] = section.count
                p[stringPreferencesKey("check_status_${type.name}")] = section.status.name
            }
        }
    }

    suspend fun migrateLegacy(legacy: SharedPreferences) {
        dataStore.edit { target ->
            if (target[Keys.legacyMigrated] != true && legacy.all.isNotEmpty()) {
                val settings = legacyToSettings(legacy)
                writeSettings(target, settings)
            }
            target[Keys.legacyMigrated] = true
            listOf(Keys.telegramBotToken, Keys.telegramChannelId, Keys.telegramProxyUrl).forEach { key ->
                val value = target[key].orEmpty()
                if (value.isNotEmpty() && !value.startsWith(SecretCipher.PREFIX)) {
                    target[key] = secretCipher.encrypt(value, key.name)
                }
            }
        }
        check(legacy.edit().remove("bot_token").remove("channel_id").remove("proxy_url").commit()) {
            "Could not remove migrated legacy secrets"
        }
    }

    suspend fun save(settings: AppSettings, replaceSecrets: Boolean = false) {
        dataStore.edit { preferences ->
            writeSettings(preferences, settings, replaceSecrets)
            preferences[Keys.legacyMigrated] = true
        }
    }

    private fun preferencesToSettings(preferences: Preferences): AppSettings {
        val defaults = AppSettings()
        val telegramBotToken = readSecret(preferences, Keys.telegramBotToken)
        val telegramChannelId = readSecret(preferences, Keys.telegramChannelId)
        val telegramProxyUrl = readSecret(preferences, Keys.telegramProxyUrl)
        val credentialError = listOf(Pair(Keys.telegramBotToken, telegramBotToken), Pair(Keys.telegramChannelId, telegramChannelId),
            Pair(Keys.telegramProxyUrl, telegramProxyUrl)).any { (key, value) ->
                preferences[key].orEmpty().startsWith(SecretCipher.PREFIX) && value.isEmpty()
            }
        return AppSettings(
            downloadDirectory = preferences[Keys.downloadDirectory] ?: defaults.downloadDirectory,
            downloadDirectoryUri = preferences[Keys.downloadDirectoryUri],
            tempDirectory = normalizeTempDirectory(preferences[Keys.tempDirectory] ?: defaults.tempDirectory),
            maxResolution = normalizeResolution(preferences[Keys.maxResolution] ?: defaults.maxResolution),
            videoLimit = normalizeLimit(preferences[Keys.videoLimit] ?: defaults.videoLimit),
            shortsLimit = normalizeLimit(preferences[Keys.shortsLimit] ?: defaults.shortsLimit),
            streamsLimit = normalizeLimit(preferences[Keys.streamsLimit] ?: defaults.streamsLimit),
            language = AppLanguage.fromStored(preferences[Keys.language]).tag,
            themeMode = enumValueOrDefault(preferences[Keys.themeMode], defaults.themeMode),
            watchClipboard = preferences[Keys.watchClipboard] ?: defaults.watchClipboard,
            systemNotifications = preferences[Keys.systemNotifications] ?: defaults.systemNotifications,
            telegramEnabled = (preferences[Keys.telegramEnabled] ?: defaults.telegramEnabled) &&
                telegramBotToken.isNotBlank() && telegramChannelId.isNotBlank() && !credentialError,
            telegramBotToken = telegramBotToken,
            telegramChannelId = telegramChannelId,
            telegramProxyUrl = telegramProxyUrl,
            telegramCredentialError = credentialError,
            logRetentionDays = (preferences[Keys.logRetentionDays] ?: defaults.logRetentionDays).coerceIn(1, 30),
        )
    }

    private fun legacyToSettings(preferences: SharedPreferences): AppSettings {
        val defaults = AppSettings()
        return AppSettings(
            downloadDirectory = preferences.getString("download_directory", defaults.downloadDirectory) ?: defaults.downloadDirectory,
            downloadDirectoryUri = null,
            tempDirectory = normalizeTempDirectory(preferences.getString("temp_directory", defaults.tempDirectory) ?: defaults.tempDirectory),
            maxResolution = normalizeResolution(preferences.getString("max_resolution", defaults.maxResolution) ?: defaults.maxResolution),
            videoLimit = normalizeLimit(preferences.getInt("video_limit", defaults.videoLimit)),
            shortsLimit = normalizeLimit(preferences.getInt("shorts_limit", defaults.shortsLimit)),
            streamsLimit = normalizeLimit(preferences.getInt("streams_limit", defaults.streamsLimit)),
            language = AppLanguage.fromStored(preferences.getString("language", defaults.language)).tag,
            themeMode = enumValueOrDefault(preferences.getString("theme_mode", null), defaults.themeMode),
            watchClipboard = preferences.getBoolean("watch_clipboard", defaults.watchClipboard),
            systemNotifications = preferences.getBoolean("system_notifications", defaults.systemNotifications),
            telegramEnabled = preferences.getBoolean("telegram_enabled", defaults.telegramEnabled),
            telegramBotToken = preferences.getString("bot_token", "").orEmpty(),
            telegramChannelId = preferences.getString("channel_id", "").orEmpty(),
            telegramProxyUrl = preferences.getString("proxy_url", "").orEmpty(),
            logRetentionDays = preferences.getInt("log_retention_days", defaults.logRetentionDays).coerceIn(1, 30),
        )
    }

    private fun writeSettings(preferences: androidx.datastore.preferences.core.MutablePreferences, settings: AppSettings,
        replaceSecrets: Boolean = false) {
        preferences[Keys.downloadDirectory] = settings.downloadDirectory
        settings.downloadDirectoryUri?.takeIf(String::isNotBlank)?.let {
            preferences[Keys.downloadDirectoryUri] = it
        } ?: preferences.remove(Keys.downloadDirectoryUri)
        preferences[Keys.tempDirectory] = settings.tempDirectory
        preferences[Keys.maxResolution] = settings.maxResolution
        preferences[Keys.videoLimit] = normalizeLimit(settings.videoLimit)
        preferences[Keys.shortsLimit] = normalizeLimit(settings.shortsLimit)
        preferences[Keys.streamsLimit] = normalizeLimit(settings.streamsLimit)
        preferences[Keys.language] = settings.language
        preferences[Keys.themeMode] = settings.themeMode.name
        preferences[Keys.watchClipboard] = settings.watchClipboard
        preferences[Keys.systemNotifications] = settings.systemNotifications
        preferences[Keys.telegramEnabled] = settings.telegramEnabled
        writeSecret(preferences, Keys.telegramBotToken, settings.telegramBotToken, replaceSecrets)
        writeSecret(preferences, Keys.telegramChannelId, settings.telegramChannelId, replaceSecrets)
        writeSecret(preferences, Keys.telegramProxyUrl, settings.telegramProxyUrl, replaceSecrets)
        preferences[Keys.logRetentionDays] = settings.logRetentionDays.coerceIn(1, 30)
    }

    private fun enumValueOrDefault(value: String?, fallback: AppThemeMode): AppThemeMode =
        AppThemeMode.entries.firstOrNull { it.name == value } ?: fallback

    private fun readSecret(preferences: Preferences, key: Preferences.Key<String>): String =
        recoverSecret { secretCipher.decrypt(preferences[key].orEmpty(), key.name) }

    private fun writeSecret(preferences: androidx.datastore.preferences.core.MutablePreferences, key: Preferences.Key<String>,
        value: String, replace: Boolean) {
        val previous = preferences[key].orEmpty()
        val decoded = readSecret(preferences, key)
        // Do not erase a temporarily unreadable credential when saving unrelated settings.
        if (!replace && previous.startsWith(SecretCipher.PREFIX) && value == decoded) return
        preferences[key] = secretCipher.encrypt(value, key.name)
    }

    private fun normalizeResolution(value: String): String = when (value.lowercase()) {
        "лучшее", "best", "max", "mejor", "meilleur" -> "best"
        else -> value
    }

    private fun normalizeTempDirectory(value: String): String = when (value.trim().lowercase()) {
        "внутренний кэш приложения", "internal app cache", "internal-cache" -> "internal-cache"
        else -> value
    }

    private fun normalizeLimit(value: Int): Int = value.coerceIn(1, 99)

    private object Keys {
        val downloadDirectory = stringPreferencesKey("download_directory")
        val downloadDirectoryUri = stringPreferencesKey("download_directory_uri")
        val tempDirectory = stringPreferencesKey("temp_directory")
        val maxResolution = stringPreferencesKey("max_resolution")
        val videoLimit = intPreferencesKey("video_limit")
        val shortsLimit = intPreferencesKey("shorts_limit")
        val streamsLimit = intPreferencesKey("streams_limit")
        val language = stringPreferencesKey("language")
        val themeMode = stringPreferencesKey("theme_mode")
        val watchClipboard = booleanPreferencesKey("watch_clipboard")
        val systemNotifications = booleanPreferencesKey("system_notifications")
        val telegramEnabled = booleanPreferencesKey("telegram_enabled")
        val telegramBotToken = stringPreferencesKey("telegram_bot_token")
        val telegramChannelId = stringPreferencesKey("telegram_channel_id")
        val telegramProxyUrl = stringPreferencesKey("telegram_proxy_url")
        val logRetentionDays = intPreferencesKey("log_retention_days")
        val legacyMigrated = booleanPreferencesKey("legacy_migrated")
    }
}
