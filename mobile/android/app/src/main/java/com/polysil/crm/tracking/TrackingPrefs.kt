package com.polysil.crm.tracking

import android.content.Context
import android.content.SharedPreferences
import com.polysil.crm.tracking.core.InFlight
import com.polysil.crm.tracking.core.UploadLedger
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.contentOrNull
import java.util.UUID

/** The duty as the service runs it: kept on disk, so a restart or a reboot picks it up again. */
internal data class DutyConfig(
    val dutyId: String,
    /** When the duty started, ISO 8601 as the server answered it. */
    val since: String,
    val intervalSeconds: Int,
    val distanceFilterM: Int,
    val maxBatchPoints: Int,
    /** The API's origin and prefix, "https://…/api/v1". */
    val apiBaseUrl: String,
)

/**
 * TRK-008 · What the tracking module keeps between runs: the install's device id, the open duty,
 * the last upload and error, and the upload ledger (the batch in flight and the used keys).
 */
internal class TrackingPrefs(context: Context) : UploadLedger {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("polysil_tracking", Context.MODE_PRIVATE)

    /** A uuid made on first use and kept for the life of the install. */
    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(KEY_DEVICE_ID, it).apply()
        }

    var duty: DutyConfig?
        get() {
            val id = prefs.getString(KEY_DUTY_ID, null) ?: return null
            return DutyConfig(
                dutyId = id,
                since = prefs.getString(KEY_SINCE, null) ?: "",
                intervalSeconds = prefs.getInt(KEY_INTERVAL, DEFAULT_INTERVAL_SECONDS),
                distanceFilterM = prefs.getInt(KEY_DISTANCE, 0),
                maxBatchPoints = prefs.getInt(KEY_MAX_BATCH, DEFAULT_MAX_BATCH),
                apiBaseUrl = prefs.getString(KEY_API, null) ?: return null,
            )
        }
        set(value) {
            val edit = prefs.edit()
            if (value == null) {
                listOf(KEY_DUTY_ID, KEY_SINCE, KEY_INTERVAL, KEY_DISTANCE, KEY_MAX_BATCH).forEach(edit::remove)
            } else {
                edit.putString(KEY_DUTY_ID, value.dutyId)
                    .putString(KEY_SINCE, value.since)
                    .putInt(KEY_INTERVAL, value.intervalSeconds)
                    .putInt(KEY_DISTANCE, value.distanceFilterM)
                    .putInt(KEY_MAX_BATCH, value.maxBatchPoints)
                    .putString(KEY_API, value.apiBaseUrl)
            }
            edit.apply()
        }

    var lastUploadAt: String?
        get() = prefs.getString(KEY_LAST_UPLOAD, null)
        set(value) = prefs.edit().putString(KEY_LAST_UPLOAD, value).apply()

    var lastError: String?
        get() = prefs.getString(KEY_LAST_ERROR, null)
        set(value) = prefs.edit().putString(KEY_LAST_ERROR, value).apply()

    /** The last API base URL the web app gave, so uploads work after the duty has ended too. */
    var apiBaseUrl: String?
        get() = prefs.getString(KEY_API, null)
        set(value) = prefs.edit().putString(KEY_API, value).apply()

    // ── UploadLedger ───────────────────────────────────────────────────────────────

    override fun inFlight(): InFlight? {
        val key = prefs.getString(KEY_FLIGHT_KEY, null) ?: return null
        val body = prefs.getString(KEY_FLIGHT_BODY, null) ?: return null
        val ids = prefs.getString(KEY_FLIGHT_IDS, null)?.let(::decodeIds) ?: return null
        return InFlight(key, body, ids)
    }

    override fun setInFlight(batch: InFlight?) {
        val edit = prefs.edit()
        if (batch == null) {
            edit.remove(KEY_FLIGHT_KEY).remove(KEY_FLIGHT_BODY).remove(KEY_FLIGHT_IDS)
        } else {
            edit.putString(KEY_FLIGHT_KEY, batch.key)
                .putString(KEY_FLIGHT_BODY, batch.body)
                .putString(KEY_FLIGHT_IDS, encodeIds(batch.ids))
        }
        // Written before the request goes, so a crash mid-send still resends the same body.
        edit.commit()
    }

    override fun isBurned(key: String): Boolean = burned().contains(key)

    override fun burn(key: String) {
        val keys = (burned() + key).takeLast(MAX_BURNED)
        prefs.edit().putString(KEY_BURNED, encodeIds(keys)).apply()
    }

    private fun burned(): List<String> = prefs.getString(KEY_BURNED, null)?.let(::decodeIds).orEmpty()

    private fun encodeIds(ids: List<String>): String =
        buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } }.toString()

    private fun decodeIds(text: String): List<String> =
        runCatching { Json.parseToJsonElement(text) as? JsonArray }.getOrNull().orEmpty()
            .mapNotNull { (it as? JsonPrimitive)?.contentOrNull }

    private companion object {
        const val DEFAULT_INTERVAL_SECONDS = 120
        const val DEFAULT_MAX_BATCH = 500
        /** Enough to cover every batch a duty could have refused; older ones can't recur. */
        const val MAX_BURNED = 500
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_DUTY_ID = "duty_id"
        const val KEY_SINCE = "duty_since"
        const val KEY_INTERVAL = "interval_seconds"
        const val KEY_DISTANCE = "distance_filter_m"
        const val KEY_MAX_BATCH = "max_batch_points"
        const val KEY_API = "api_base_url"
        const val KEY_LAST_UPLOAD = "last_upload_at"
        const val KEY_LAST_ERROR = "last_error"
        const val KEY_FLIGHT_KEY = "in_flight_key"
        const val KEY_FLIGHT_BODY = "in_flight_body"
        const val KEY_FLIGHT_IDS = "in_flight_ids"
        const val KEY_BURNED = "burned_keys"
    }
}
