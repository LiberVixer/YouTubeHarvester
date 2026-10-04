package com.liberivixer.youtubeharvester

import android.app.Notification
import android.app.NotificationManager
import androidx.test.core.app.ApplicationProvider
import com.liberivixer.youtubeharvester.download.DownloadBootNotification
import com.liberivixer.youtubeharvester.ui.LocaleController
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

class DownloadBootNotificationTest {
    @Test fun recoveryNotificationOffersForegroundResumeWithoutOpeningActivity() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val manager = context.getSystemService(NotificationManager::class.java)
        assumeTrue(manager.areNotificationsEnabled())
        try {
            DownloadBootNotification.show(context)
            val notification = manager.activeNotifications.single { it.id == 25002 }.notification
            val action = notification.actions.single()
            assertTrue(action.actionIntent.isForegroundService)
            assertFalse(action.actionIntent.isActivity)
            assertEquals(context.packageName, action.actionIntent.creatorPackage)
            assertEquals(action.actionIntent, notification.contentIntent)
            assertEquals(LocaleController.wrap(context).getString(R.string.download_recovery_title),
                notification.extras.getCharSequence(Notification.EXTRA_TITLE).toString())
            DownloadBootNotification.clear(context)
            assertFalse(manager.activeNotifications.any { it.id == 25002 })
        } finally { DownloadBootNotification.clear(context) }
    }
}
