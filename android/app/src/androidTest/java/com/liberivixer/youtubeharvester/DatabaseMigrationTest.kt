package com.liberivixer.youtubeharvester

import androidx.room.testing.MigrationTestHelper
import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.json.JSONObject

class DatabaseMigrationTest {
    @get:Rule val helper = MigrationTestHelper(InstrumentationRegistry.getInstrumentation(), HarvesterDatabase::class.java)

    @Test fun allHistoricalSchemasMigrateWithoutDestructiveFallback() {
        val migrations = with(HarvesterDatabase) {
            arrayOf(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5,
                MIGRATION_5_6, MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9, MIGRATION_9_10, MIGRATION_10_11)
        }
        for (version in 1..10) {
            val name = "migration-from-$version"
            val expected = linkedMapOf<String, Map<String, String?>>()
            helper.createDatabase(name, version).use { db ->
                val assets = InstrumentationRegistry.getInstrumentation().context.assets
                val schema = assets.open("${HarvesterDatabase::class.java.canonicalName}/$version.json")
                    .bufferedReader().use { JSONObject(it.readText()) }
                val entities = schema.getJSONObject("database").getJSONArray("entities")
                for (i in 0 until entities.length()) {
                    val entity = entities.getJSONObject(i)
                    val table = entity.getString("tableName")
                    val fields = entity.getJSONArray("fields")
                    val values = ContentValues()
                    val row = linkedMapOf<String, String?>()
                    for (j in 0 until fields.length()) {
                        val field = fields.getJSONObject(j)
                        val column = field.getString("columnName")
                        val value = when {
                            !field.optBoolean("notNull", false) -> null
                            field.getString("affinity") == "INTEGER" -> "1"
                            column.endsWith("_json") -> "[\"preserved\"]"
                            else -> "saved-$column"
                        }
                        if (value == null) values.putNull(column) else values.put(column, value)
                        row[column] = value
                    }
                    db.insert(table, SQLiteDatabase.CONFLICT_ABORT, values)
                    expected[table] = row
                }
            }
            helper.runMigrationsAndValidate(name, 11, true, *migrations).use { db ->
                expected.forEach { (table, row) ->
                    db.query("SELECT * FROM `$table`").use { cursor ->
                        assertTrue("v$version $table", cursor.moveToFirst())
                        row.forEach { (column, value) ->
                            assertEquals("v$version $table.$column", value,
                                cursor.getString(cursor.getColumnIndexOrThrow(column)))
                        }
                        assertEquals("v$version $table row count", 1, cursor.count)
                    }
                }
            }
        }
    }
}
