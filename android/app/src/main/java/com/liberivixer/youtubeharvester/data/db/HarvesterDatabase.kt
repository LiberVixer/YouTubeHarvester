package com.liberivixer.youtubeharvester.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [QueueEntity::class, ArchiveEntity::class, DownloadJobEntity::class, ChannelEntity::class, ScheduleEntity::class, MarkedMediaEntity::class, PendingTransferEntity::class, ArchiveRelinkEntity::class],
    version = 11,
    exportSchema = true,
)
abstract class HarvesterDatabase : RoomDatabase() {
    abstract fun queueDao(): QueueDao
    abstract fun archiveDao(): ArchiveDao
    abstract fun downloadJobDao(): DownloadJobDao
    abstract fun channelDao(): ChannelDao
    abstract fun scheduleDao(): ScheduleDao
    abstract fun markedMediaDao(): MarkedMediaDao
    abstract fun pendingTransferDao(): PendingTransferDao
    abstract fun archiveRelinkDao(): ArchiveRelinkDao

    companion object {
        @Volatile
        private var instance: HarvesterDatabase? = null

        fun getInstance(context: Context): HarvesterDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    HarvesterDatabase::class.java,
                    "youtube_harvester.db",
                ).addMigrations(
                    MIGRATION_1_2,
                    MIGRATION_2_3,
                    MIGRATION_3_4,
                    MIGRATION_4_5,
                    MIGRATION_5_6,
                    MIGRATION_6_7,
                    MIGRATION_7_8,
                    MIGRATION_8_9,
                    MIGRATION_9_10,
                    MIGRATION_10_11,
                ).build().also { instance = it }
            }

        val MIGRATION_10_11 = object : Migration(10, 11) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("CREATE TABLE IF NOT EXISTS `pending_transfer` (`id` INTEGER NOT NULL, `encryptedSettings` TEXT NOT NULL, PRIMARY KEY(`id`))")
                db.execSQL("CREATE TABLE IF NOT EXISTS `archive_relinks` (`source` TEXT NOT NULL, `media_id` TEXT NOT NULL, `resolution` TEXT NOT NULL, `variant_key` TEXT NOT NULL, `file_name` TEXT NOT NULL, `file_size` INTEGER NOT NULL, `sha256` TEXT NOT NULL, PRIMARY KEY(`source`, `media_id`, `resolution`, `variant_key`))")
            }
        }

        val MIGRATION_9_10 = object : Migration(9, 10) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `download_jobs` ADD COLUMN `retry_count` INTEGER NOT NULL DEFAULT 0")
            }
        }

        val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `archive_items` ADD COLUMN `thumbnail_url` TEXT")
                db.execSQL(
                    """
                    UPDATE `archive_items`
                    SET `thumbnail_url` = (
                        SELECT `thumbnail_url`
                        FROM `download_jobs`
                        WHERE `download_jobs`.`source` = `archive_items`.`source`
                            AND `download_jobs`.`media_id` = `archive_items`.`media_id`
                            AND `download_jobs`.`thumbnail_url` IS NOT NULL
                        ORDER BY `download_jobs`.`updated_at_epoch_ms` DESC
                        LIMIT 1
                    )
                    WHERE `thumbnail_url` IS NULL
                    """.trimIndent(),
                )
            }
        }

        val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("CREATE TABLE IF NOT EXISTS `marked_media` (`source` TEXT NOT NULL, `media_id` TEXT NOT NULL, `marked_at_epoch_ms` INTEGER NOT NULL, PRIMARY KEY(`source`, `media_id`))")
            }
        }

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `download_jobs` (
                        `job_id` TEXT NOT NULL,
                        `source` TEXT NOT NULL,
                        `media_id` TEXT NOT NULL,
                        `url` TEXT NOT NULL,
                        `title` TEXT NOT NULL,
                        `channel` TEXT NOT NULL,
                        `thumbnail_url` TEXT,
                        `resolution` TEXT NOT NULL,
                        `status` TEXT NOT NULL,
                        `progress` INTEGER NOT NULL,
                        `eta_seconds` INTEGER,
                        `message` TEXT NOT NULL,
                        `created_at_epoch_ms` INTEGER NOT NULL,
                        `updated_at_epoch_ms` INTEGER NOT NULL,
                        `file_uri` TEXT,
                        `error_message` TEXT,
                        `from_queue` INTEGER NOT NULL,
                        PRIMARY KEY(`job_id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_download_jobs_status_created_at_epoch_ms` ON `download_jobs` (`status`, `created_at_epoch_ms`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_download_jobs_source_media_id` ON `download_jobs` (`source`, `media_id`)")
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `queue_items` ADD COLUMN `audio_json` TEXT NOT NULL DEFAULT '[]'")
                db.execSQL("ALTER TABLE `queue_items` ADD COLUMN `subtitles_json` TEXT NOT NULL DEFAULT '[]'")
                db.execSQL("ALTER TABLE `download_jobs` ADD COLUMN `audio_json` TEXT NOT NULL DEFAULT '[]'")
                db.execSQL("ALTER TABLE `download_jobs` ADD COLUMN `subtitles_json` TEXT NOT NULL DEFAULT '[]'")
            }
        }

        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Fresh v3 databases lacked the defaults added by the v2 migration.
                // Rebuild both tables so either installation history reaches the same schema.
                db.execSQL("""
                    CREATE TABLE `queue_items_v4` (
                        `source` TEXT NOT NULL, `media_id` TEXT NOT NULL,
                        `url` TEXT NOT NULL, `title` TEXT NOT NULL, `channel` TEXT NOT NULL,
                        `thumbnail_url` TEXT, `resolution` TEXT NOT NULL,
                        `selected` INTEGER NOT NULL, `status` TEXT NOT NULL,
                        `audio_json` TEXT NOT NULL DEFAULT '[]',
                        `subtitles_json` TEXT NOT NULL DEFAULT '[]', `sort_order` INTEGER NOT NULL,
                        PRIMARY KEY(`source`, `media_id`))
                """.trimIndent())
                db.execSQL("""
                    INSERT INTO `queue_items_v4`
                    SELECT `source`, `media_id`, `url`, `title`, `channel`, `thumbnail_url`,
                        `resolution`, `selected`, `status`, `audio_json`, `subtitles_json`, `sort_order`
                    FROM `queue_items`
                """.trimIndent())
                db.execSQL("DROP TABLE `queue_items`")
                db.execSQL("ALTER TABLE `queue_items_v4` RENAME TO `queue_items`")
                db.execSQL("CREATE INDEX `index_queue_items_sort_order` ON `queue_items` (`sort_order`)")
                db.execSQL("""
                    CREATE TABLE `download_jobs_v4` (
                        `job_id` TEXT NOT NULL, `source` TEXT NOT NULL, `media_id` TEXT NOT NULL,
                        `url` TEXT NOT NULL, `title` TEXT NOT NULL, `channel` TEXT NOT NULL,
                        `thumbnail_url` TEXT, `resolution` TEXT NOT NULL, `status` TEXT NOT NULL,
                        `progress` INTEGER NOT NULL, `eta_seconds` INTEGER, `message` TEXT NOT NULL,
                        `created_at_epoch_ms` INTEGER NOT NULL, `updated_at_epoch_ms` INTEGER NOT NULL,
                        `file_uri` TEXT, `error_message` TEXT, `from_queue` INTEGER NOT NULL,
                        `audio_json` TEXT NOT NULL DEFAULT '[]',
                        `subtitles_json` TEXT NOT NULL DEFAULT '[]', PRIMARY KEY(`job_id`))
                """.trimIndent())
                db.execSQL("""
                    INSERT INTO `download_jobs_v4`
                    SELECT `job_id`, `source`, `media_id`, `url`, `title`, `channel`, `thumbnail_url`,
                        `resolution`, `status`, `progress`, `eta_seconds`, `message`,
                        `created_at_epoch_ms`, `updated_at_epoch_ms`, `file_uri`, `error_message`,
                        `from_queue`, `audio_json`, `subtitles_json`
                    FROM `download_jobs`
                """.trimIndent())
                db.execSQL("DROP TABLE `download_jobs`")
                db.execSQL("ALTER TABLE `download_jobs_v4` RENAME TO `download_jobs`")
                db.execSQL("CREATE INDEX `index_download_jobs_status_created_at_epoch_ms` ON `download_jobs` (`status`, `created_at_epoch_ms`)")
                db.execSQL("CREATE INDEX `index_download_jobs_source_media_id` ON `download_jobs` (`source`, `media_id`)")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `archive_items_new` (
                        `source` TEXT NOT NULL,
                        `media_id` TEXT NOT NULL,
                        `title` TEXT NOT NULL,
                        `channel` TEXT NOT NULL,
                        `content_type` TEXT NOT NULL,
                        `resolution` TEXT NOT NULL,
                        `variant_key` TEXT NOT NULL DEFAULT 'default',
                        `downloaded_at` TEXT NOT NULL,
                        `downloaded_at_epoch_ms` INTEGER NOT NULL,
                        `file_exists` INTEGER NOT NULL,
                        `file_uri` TEXT,
                        `audio_json` TEXT NOT NULL,
                        `subtitles_json` TEXT NOT NULL,
                        PRIMARY KEY(`source`, `media_id`, `resolution`, `variant_key`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    INSERT INTO `archive_items_new` (
                        `source`, `media_id`, `title`, `channel`, `content_type`, `resolution`,
                        `variant_key`, `downloaded_at`, `downloaded_at_epoch_ms`, `file_exists`,
                        `file_uri`, `audio_json`, `subtitles_json`
                    )
                    SELECT `source`, `media_id`, `title`, `channel`, `content_type`, `resolution`,
                        'default', `downloaded_at`, `downloaded_at_epoch_ms`, `file_exists`,
                        `file_uri`, `audio_json`, `subtitles_json`
                    FROM `archive_items`
                    """.trimIndent(),
                )
                db.execSQL("DROP TABLE `archive_items`")
                db.execSQL("ALTER TABLE `archive_items_new` RENAME TO `archive_items`")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_archive_items_downloaded_at_epoch_ms` ON `archive_items` (`downloaded_at_epoch_ms`)")
            }
        }

        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `channels` (
                        `id` TEXT NOT NULL,
                        `url` TEXT NOT NULL,
                        `name` TEXT NOT NULL,
                        `handle` TEXT NOT NULL,
                        `thumbnail_url` TEXT,
                        `videos_enabled` INTEGER NOT NULL,
                        `shorts_enabled` INTEGER NOT NULL,
                        `streams_enabled` INTEGER NOT NULL,
                        `paid_content` TEXT NOT NULL,
                        `status` TEXT NOT NULL,
                        `last_checked_epoch_ms` INTEGER,
                        `sort_order` INTEGER NOT NULL,
                        PRIMARY KEY(`id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_channels_sort_order` ON `channels` (`sort_order`)")
            }
        }

        val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `queue_items` ADD COLUMN `content_type` TEXT NOT NULL DEFAULT 'Video'")
                db.execSQL("ALTER TABLE `queue_items` ADD COLUMN `origin_channel_id` TEXT")
                db.execSQL("ALTER TABLE `download_jobs` ADD COLUMN `content_type` TEXT NOT NULL DEFAULT 'Video'")
                db.execSQL("ALTER TABLE `download_jobs` ADD COLUMN `origin_channel_id` TEXT")
            }
        }

        val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `check_schedules` (
                        `id` TEXT NOT NULL,
                        `hour` INTEGER NOT NULL,
                        `minute` INTEGER NOT NULL,
                        `enabled` INTEGER NOT NULL,
                        `last_run_epoch_ms` INTEGER,
                        `created_at_epoch_ms` INTEGER NOT NULL,
                        PRIMARY KEY(`id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_check_schedules_hour_minute` ON `check_schedules` (`hour`, `minute`)")
            }
        }
    }
}
