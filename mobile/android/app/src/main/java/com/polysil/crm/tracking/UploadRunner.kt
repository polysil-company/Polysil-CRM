package com.polysil.crm.tracking

import android.content.Context
import com.polysil.crm.tracking.core.UploadResult
import com.polysil.crm.tracking.core.Uploader
import com.polysil.crm.tracking.data.RoomPointStore
import com.polysil.crm.tracking.data.TrackingDatabase

/** What a flush reports to the web app. */
internal data class FlushOutcome(val accepted: Int, val duplicates: Int, val rejected: Int, val pending: Int)

/**
 * TRK-008 · One upload run, for the service's timer, the network coming back, the backup worker
 * and `flush()`. Runs one at a time; the caller is never the main thread.
 */
internal object UploadRunner {
    private val lock = Any()

    fun run(context: Context): FlushOutcome = synchronized(lock) {
        val prefs = TrackingPrefs(context)
        val store = RoomPointStore(TrackingDatabase.get(context).points())
        val apiBaseUrl = prefs.apiBaseUrl
        if (apiBaseUrl == null) {
            return FlushOutcome(0, 0, 0, store.count())
        }
        val uploader = Uploader(
            store = store,
            ledger = prefs,
            transport = OkHttpTransport(apiBaseUrl),
            deviceId = prefs.deviceId,
            sentAt = { isoTime(System.currentTimeMillis()) },
            accessToken = { AccessTokenHolder.valid() },
        )
        val maxBatch = prefs.duty?.maxBatchPoints ?: DEFAULT_MAX_BATCH
        val result = uploader.uploadAll(maxBatch)
        var outcome = FlushOutcome(0, 0, 0, store.count())
        when (result) {
            is UploadResult.Done -> {
                prefs.lastUploadAt = isoTime(System.currentTimeMillis())
                prefs.lastError = null
                outcome = FlushOutcome(result.accepted, result.duplicates, result.rejected, store.count())
            }
            UploadResult.WaitingForToken -> prefs.lastError = "waiting_for_sign_in"
            is UploadResult.RetryLater -> {
                prefs.lastError = "offline"
                UploadWorker.enqueue(context)
            }
            is UploadResult.ServerEndedDuty -> {
                prefs.lastUploadAt = isoTime(System.currentTimeMillis())
                prefs.lastError = null
                prefs.duty = null
                TrackingService.stop(context)
                TrackingEvents.serverEnded(statusOf(context), result.endReason)
            }
            UploadResult.Forbidden -> {
                prefs.lastError = "forbidden"
                prefs.duty = null
                TrackingService.stop(context)
            }
            UploadResult.BadClock -> prefs.lastError = "bad_clock"
            is UploadResult.Refused -> prefs.lastError = "refused:${result.code ?: result.status}"
        }
        TrackingEvents.status(statusOf(context))
        return outcome
    }

    fun statusOf(context: Context): TrackingStatus {
        val prefs = TrackingPrefs(context)
        val duty = prefs.duty
        return TrackingStatus(
            onDuty = duty != null,
            dutyId = duty?.dutyId,
            since = duty?.since,
            lastUploadAt = prefs.lastUploadAt,
            pendingPoints = TrackingDatabase.get(context).points().count(),
            lastError = prefs.lastError,
        )
    }

    private const val DEFAULT_MAX_BATCH = 500
}
