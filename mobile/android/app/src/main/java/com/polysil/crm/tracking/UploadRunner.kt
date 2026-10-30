package com.polysil.crm.tracking

import android.content.Context
import com.polysil.crm.tracking.core.DeviceToken
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

    /**
     * TRK-009 · Keeps the device token the screens handed over (an empty one forgets it). Under the
     * run's lock, so a run that ends on a `401` for the old token can't forget the new one.
     */
    fun acceptToken(context: Context, token: DeviceToken?): Boolean = synchronized(lock) {
        val tokens = DeviceTokenStore(context)
        if (token == null || token.token.isBlank()) {
            tokens.clear()
            return true
        }
        val kept = tokens.save(token)
        TrackingPrefs(context).lastError = if (kept) null else "token_not_kept"
        return kept
    }

    fun run(context: Context): FlushOutcome = synchronized(lock) {
        val prefs = TrackingPrefs(context)
        val tokens = DeviceTokenStore(context)
        val held = tokens.load()
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
            token = { held?.usable(System.currentTimeMillis()) },
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
            UploadResult.WaitingForToken -> {
                // No token, an expired one, or a `401`: it is dead either way. Forgetting it stops
                // the timer's runs from sending until the screens hand over a new one.
                tokens.clear()
                prefs.lastError = "waiting_for_sign_in"
            }
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
                // Contract §1 step 9: stop and keep the points; a new token comes on the next launch.
                tokens.clear()
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
