package com.polysil.crm.tracking

import java.util.concurrent.CopyOnWriteArraySet

/** The status the plugin reports, and emits as `status` when it changes. */
internal data class TrackingStatus(
    val onDuty: Boolean,
    val dutyId: String?,
    val since: String?,
    val lastUploadAt: String?,
    val pendingPoints: Int,
    val lastError: String?,
)

/** What the service and the uploader tell the plugin, while the app's screens are open. */
internal object TrackingEvents {
    interface Listener {
        fun onStatus(status: TrackingStatus)
        fun onServerEndedDuty(status: TrackingStatus, endReason: String?)
    }

    private val listeners = CopyOnWriteArraySet<Listener>()

    fun add(listener: Listener) {
        listeners += listener
    }

    fun remove(listener: Listener) {
        listeners -= listener
    }

    fun status(status: TrackingStatus) = listeners.forEach { it.onStatus(status) }

    fun serverEnded(status: TrackingStatus, endReason: String?) =
        listeners.forEach { it.onServerEndedDuty(status, endReason) }
}
