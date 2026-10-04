package com.liberivixer.youtubeharvester.data

import android.content.Context
import android.database.Cursor
import androidx.room.withTransaction
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.data.db.PendingTransferEntity
import com.liberivixer.youtubeharvester.download.HarvestSessionStore
import com.liberivixer.youtubeharvester.ui.LocaleController
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject

class DataTransferNotEmptyException : IllegalStateException()
class DataTransferBusyException : IllegalStateException()
class DataTransferCredentialsException : IllegalStateException()
class DataTransferArchiveException : IllegalStateException()
class DataTransferPendingException : IllegalStateException()

class DataTransferStore(
    context: Context,
    private val database: HarvesterDatabase = HarvesterDatabase.getInstance(context),
    private val settingsStore: SettingsDataStore = SettingsDataStore(context),
) {
    private val appContext = context.applicationContext
    private val secretCipher = SecretCipher()

    suspend fun export(password: CharArray): ByteArray = withContext(Dispatchers.IO) { transferLock.withLock {
        if (HarvestSessionStore(appContext).current() != null) throw DataTransferBusyException()
        val settings = settingsStore.settings.first().copy(language = LocaleController.currentTag(appContext))
        if (settings.telegramCredentialError) throw DataTransferCredentialsException()
        val data = database.withTransaction {
            if (database.downloadJobDao().pendingCount() != 0 || database.pendingTransferDao().get() != null) {
                throw DataTransferBusyException()
            }
            val sqlite = database.openHelper.writableDatabase
            var total = 0
            val tables = TransferSnapshot.schema.associate { table ->
                val rows = mutableListOf<JSONObject>()
                val columns = table.columns.joinToString { "`$it`" }
                val order = if ("sort_order" in table.columns) "`sort_order`, " else ""
                val keys = table.primaryKey.joinToString { "`$it`" }
                sqlite.query("SELECT $columns FROM `${table.name}` ORDER BY $order$keys").use { cursor ->
                    while (cursor.moveToNext()) {
                        check(++total <= TransferSnapshot.MAX_ROWS)
                        val row = JSONObject()
                        table.columns.forEachIndexed { index, name ->
                            row.put(name, when (cursor.getType(index)) {
                                Cursor.FIELD_TYPE_NULL -> JSONObject.NULL
                                Cursor.FIELD_TYPE_INTEGER -> cursor.getLong(index)
                                Cursor.FIELD_TYPE_STRING -> cursor.getString(index)
                                else -> error("Unsupported transfer column")
                            })
                        }
                        rows.add(row)
                    }
                }
                table.name to rows
            }
            TransferSnapshot(settings, tables)
        }
        val archiveFiles = ArchiveTransferFiles(appContext)
        val existingHints = data.tables.getValue("archive_relinks").associateBy { hint ->
            listOf("source", "media_id", "resolution", "variant_key").map(hint::getString)
        }
        val hints = data.tables.getValue("archive_items").mapNotNull { archive ->
            val hint = archiveFiles.capture(archive) ?: existingHints[listOf("source", "media_id", "resolution", "variant_key").map(archive::getString)]
            if (hint == null && archive.getInt("file_exists") != 0) throw DataTransferArchiveException()
            hint
        }
        val snapshot = data.copy(tables = data.tables + ("archive_relinks" to hints)).encode()
        try {
            // Validate our own output before offering a backup which cannot be restored.
            TransferSnapshot.decode(snapshot)
            TransferEncryption.encrypt(snapshot, password)
        } finally { snapshot.fill(0) }
    } }

    suspend fun import(file: ByteArray, password: CharArray) = withContext(Dispatchers.IO) { transferLock.withLock {
        if (HarvestSessionStore(appContext).current() != null) throw DataTransferBusyException()
        val plain = TransferEncryption.decrypt(file, password)
        val snapshot = try { TransferSnapshot.decode(plain) } finally { plain.fill(0) }
        val settings = TransferSettings.forImport(snapshot.settings)
        val encryptedSettings = secretCipher.encrypt(TransferSettings.encode(settings).toString(), SETTINGS_AAD)
        database.withTransaction {
            val sqlite = database.openHelper.writableDatabase
            if (database.pendingTransferDao().get() != null) throw DataTransferBusyException()
            for (table in TransferSnapshot.schema) {
                sqlite.query("SELECT EXISTS(SELECT 1 FROM `${table.name}`)").use { cursor ->
                    check(cursor.moveToFirst())
                    if (cursor.getInt(0) != 0) throw DataTransferNotEmptyException()
                }
            }
            for (table in TransferSnapshot.schema) {
                val columns = table.columns.joinToString { "`$it`" }
                val placeholders = table.columns.joinToString { "?" }
                sqlite.compileStatement("INSERT INTO `${table.name}` ($columns) VALUES ($placeholders)").use { statement ->
                    for (original in snapshot.tables.getValue(table.name)) {
                        val row = TransferSnapshot.importedRow(table, original)
                        statement.clearBindings()
                        table.columns.forEachIndexed { index, column ->
                            when (val value = row.get(column)) {
                                JSONObject.NULL -> statement.bindNull(index + 1)
                                is Number -> statement.bindLong(index + 1, value.toLong())
                                is String -> statement.bindString(index + 1, value)
                                else -> error("Unsupported transfer value")
                            }
                        }
                        statement.executeInsert()
                    }
                }
            }
            // Room and DataStore do not share a transaction. This Keystore-encrypted
            // journal is committed with the rows and completed idempotently after a crash.
            database.pendingTransferDao().insert(PendingTransferEntity(encryptedSettings = encryptedSettings))
        }
        try { finishPendingImportLocked() }
        catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (_: Exception) { throw DataTransferPendingException() }
    } }

    suspend fun finishPendingImport() = withContext(Dispatchers.IO) { transferLock.withLock { finishPendingImportLocked() } }

    private suspend fun finishPendingImportLocked() {
        val pending = database.pendingTransferDao().get() ?: return
        val settings = TransferSettings.decode(JSONObject(secretCipher.decrypt(pending.encryptedSettings, SETTINGS_AAD)))
        settingsStore.save(settings, replaceSecrets = true)
        LocaleController.setLanguage(appContext, settings.language)
        database.pendingTransferDao().clear()
    }

    private companion object {
        const val SETTINGS_AAD = "data-transfer-settings-v1"
        val transferLock = Mutex()
    }
}
