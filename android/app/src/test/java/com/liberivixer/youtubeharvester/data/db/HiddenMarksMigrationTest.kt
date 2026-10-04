package com.liberivixer.youtubeharvester.data.db

import androidx.sqlite.db.SupportSQLiteDatabase
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.lang.reflect.Proxy

class HiddenMarksMigrationTest {
    @Test
    fun archiveThumbnailMigrationAddsAndBackfillsTheColumn() {
        val statements = migrationStatements(HarvesterDatabase.MIGRATION_8_9)

        assertEquals(8, HarvesterDatabase.MIGRATION_8_9.startVersion)
        assertEquals(9, HarvesterDatabase.MIGRATION_8_9.endVersion)
        assertEquals("ALTER TABLE `archive_items` ADD COLUMN `thumbnail_url` TEXT", statements.first())
        assertTrue(statements.last().contains("FROM `download_jobs`"))
        assertTrue(statements.last().contains("`download_jobs`.`media_id` = `archive_items`.`media_id`"))
    }

    @Test
    fun archiveThumbnailSchemaOnlyChangesArchiveItems() {
        val before = entities(8)
        val after = entities(9)
        assertEquals(before.size, after.size)
        for (table in before.filterNot { it.getString("tableName") == "archive_items" }) {
            val migrated = after.single { it.getString("tableName") == table.getString("tableName") }
            assertEquals("Changed ${table.getString("tableName")}", table.toString(), migrated.toString())
        }
        val oldArchive = entities(8).single { it.getString("tableName") == "archive_items" }
        val newArchive = entities(9).single { it.getString("tableName") == "archive_items" }
        val oldColumns = fields(oldArchive)
        val newColumns = fields(newArchive)
        assertEquals(
            oldColumns.mapValues { it.value.toString() },
            newColumns.filterKeys { it != "thumbnail_url" }.mapValues { it.value.toString() },
        )
        assertEquals("TEXT", newColumns.getValue("thumbnail_url").getString("affinity"))
        assertEquals(false, newColumns.getValue("thumbnail_url").optBoolean("notNull", false))
    }

    @Test
    fun migrationOnlyAddsTheHiddenMarksTable() {
        val migration = HarvesterDatabase.MIGRATION_7_8
        assertEquals(7, migration.startVersion)
        assertEquals(8, migration.endVersion)
        val statements = migrationStatements(migration)

        val marks = entities(8).single { it.getString("tableName") == "marked_media" }
        val expected = marks.getString("createSql").replace("\${TABLE_NAME}", "marked_media")
        assertEquals(listOf(expected), statements)
    }

    @Test
    fun allExistingTablesAndIndicesStayUnchanged() {
        val before = entities(7)
        val after = entities(8)
        assertEquals(before.size + 1, after.size)
        for (table in before) {
            val migrated = after.single { it.getString("tableName") == table.getString("tableName") }
            assertEquals("Changed ${table.getString("tableName")}", table.toString(), migrated.toString())
        }
        val marks = after.single { it.getString("tableName") == "marked_media" }
        val primaryKey = marks.getJSONObject("primaryKey").getJSONArray("columnNames")
        assertEquals(listOf("source", "media_id"), (0 until primaryKey.length()).map(primaryKey::getString))
    }

    private fun entities(version: Int): List<JSONObject> {
        val schema = File("schemas/com.liberivixer.youtubeharvester.data.db.HarvesterDatabase/$version.json")
        val entities = JSONObject(schema.readText()).getJSONObject("database").getJSONArray("entities")
        return (0 until entities.length()).map(entities::getJSONObject)
    }

    private fun fields(entity: JSONObject): Map<String, JSONObject> {
        val fields = entity.getJSONArray("fields")
        return (0 until fields.length()).associate { index ->
            fields.getJSONObject(index).let { it.getString("columnName") to it }
        }
    }

    private fun migrationStatements(migration: androidx.room.migration.Migration): List<String> {
        val statements = mutableListOf<String>()
        val database = Proxy.newProxyInstance(
            SupportSQLiteDatabase::class.java.classLoader,
            arrayOf(SupportSQLiteDatabase::class.java),
        ) { _, method, arguments ->
            check(method.name == "execSQL") { "Unexpected migration operation: ${method.name}" }
            statements += arguments!![0] as String
            null
        } as SupportSQLiteDatabase
        migration.migrate(database)
        return statements
    }
}
