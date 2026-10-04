package com.liberivixer.youtubeharvester.model

import org.junit.Assert.assertEquals
import org.junit.Test

class AppSettingsMigrationTest {
    @Test
    fun languageAcceptsStableTagsAndLegacyDisplayNames() {
        assertEquals(AppLanguage.English, AppLanguage.fromStored(null))
        assertEquals(AppLanguage.Russian, AppLanguage.fromStored("Русский"))
        assertEquals(AppLanguage.Ukrainian, AppLanguage.fromStored("Українська"))
        assertEquals(AppLanguage.Belarusian, AppLanguage.fromStored("Белорусский"))
        assertEquals(AppLanguage.Chinese, AppLanguage.fromStored("zh-CN"))
        assertEquals(AppLanguage.Arabic, AppLanguage.fromStored("العربية"))
    }

    @Test
    fun androidOnlySettingsUseSafeTelegramDefaults() {
        val settings = AppSettings()

        assertEquals(false, settings.telegramEnabled)
        assertEquals("", settings.telegramBotToken)
        assertEquals("", settings.telegramChannelId)
        assertEquals("", settings.telegramProxyUrl)
        assertEquals(3, settings.logRetentionDays)
    }
}
