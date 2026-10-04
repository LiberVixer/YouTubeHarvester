package com.liberivixer.youtubeharvester.download

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.liberivixer.youtubeharvester.model.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

private val Context.harvestDataStore by preferencesDataStore(name = "harvest_session")

data class HarvestSession(
    val id: String = UUID.randomUUID().toString(),
    val channels: List<ChannelItem>,
    val settings: AppSettings,
    val checkpoint: HarvestCheckpoint = HarvestCheckpoint(),
    val stopRequested: Boolean = false,
)

class HarvestSessionStore(context: Context) {
    private val store = context.applicationContext.harvestDataStore
    private val key = stringPreferencesKey("session")
    val sessions = store.data.map { it[key]?.let(HarvestSessionCodec::decode) }.distinctUntilChanged()
    suspend fun current() = sessions.first()
    suspend fun begin(session: HarvestSession): Boolean {
        var created = false
        store.edit { p -> if (p[key] == null) { p[key] = HarvestSessionCodec.encode(session); created = true } }
        return created
    }
    suspend fun checkpoint(id: String, checkpoint: HarvestCheckpoint) {
        store.edit { p ->
            p[key]?.let(HarvestSessionCodec::decode)?.takeIf { it.id == id }?.let {
                p[key] = HarvestSessionCodec.encode(it.copy(checkpoint = checkpoint))
            }
        }
    }
    suspend fun stop() {
        store.edit { p -> p[key]?.let(HarvestSessionCodec::decode)?.let {
            p[key] = HarvestSessionCodec.encode(it.copy(stopRequested = true))
        } }
    }
    suspend fun clear(id: String) {
        store.edit { p -> if (p[key]?.let(HarvestSessionCodec::decode)?.id == id) p.remove(key) }
    }
}

internal object HarvestSessionCodec {
    fun encode(session: HarvestSession): String {
        val c = session.checkpoint
        return JSONObject().put("id", session.id).put("stop", session.stopRequested)
            .put("channels", JSONArray(session.channels.map { channel -> JSONObject()
                .put("id", channel.id).put("url", channel.url).put("name", channel.name).put("handle", channel.handle)
                .put("thumbnail", channel.thumbnailUrl).put("videos", channel.videosEnabled)
                .put("shorts", channel.shortsEnabled).put("streams", channel.streamsEnabled)
                .put("paid", channel.paidContent.name) }))
            .put("resolution", session.settings.maxResolution).put("videos", session.settings.videoLimit)
            .put("shorts", session.settings.shortsLimit).put("streams", session.settings.streamsLimit)
            .put("phase", c.phase.name).put("checked", c.completedChannels)
            .put("scanErrors", c.scanErrors).put("downloadErrors", c.downloadErrors)
            .put("downloaded", JSONObject(c.downloaded.mapKeys { it.key.name }))
            .put("attempted", JSONArray(c.attempted.toList()))
            .put("pending", c.pending?.let { JSONObject().put("key", it.key).put("id", it.jobId).put("type", it.type.name) })
            .put("sections", JSONObject(c.sections.mapKeys { it.key.name }.mapValues {
                JSONObject().put("count", it.value.count).put("status", it.value.status.name)
            })).toString()
    }

    fun decode(raw: String): HarvestSession {
        val j = JSONObject(raw)
        val channels = j.getJSONArray("channels")
        val downloaded = j.getJSONObject("downloaded")
        val sections = j.getJSONObject("sections")
        val attempted = j.getJSONArray("attempted")
        return HarvestSession(j.getString("id"), (0 until channels.length()).map { n ->
            val ch = channels.getJSONObject(n)
            ChannelItem(ch.getString("id"), ch.getString("url"), ch.getString("name"), ch.getString("handle"),
                ch.optString("thumbnail").takeIf { it.isNotBlank() }, ch.getBoolean("videos"), ch.getBoolean("shorts"),
                ch.getBoolean("streams"), PaidContentStatus.valueOf(ch.getString("paid")))
        }, AppSettings(maxResolution = j.getString("resolution"), videoLimit = j.getInt("videos"),
            shortsLimit = j.getInt("shorts"), streamsLimit = j.getInt("streams")),
            HarvestCheckpoint(HarvestPhase.valueOf(j.getString("phase")), j.getInt("checked"), j.getInt("scanErrors"),
                j.getInt("downloadErrors"), downloaded.keys().asSequence().associate { ContentType.valueOf(it) to downloaded.getInt(it) },
                (0 until attempted.length()).map { attempted.getString(it) }.toSet(),
                j.optJSONObject("pending")?.let { PendingHarvestDownload(it.getString("key"), it.getString("id"), ContentType.valueOf(it.getString("type"))) },
                sections.keys().asSequence().associate { name -> val s = sections.getJSONObject(name)
                    ContentType.valueOf(name) to SectionResult(s.getInt("count"), SectionStatus.valueOf(s.getString("status"))) }),
            j.optBoolean("stop"))
    }
}
