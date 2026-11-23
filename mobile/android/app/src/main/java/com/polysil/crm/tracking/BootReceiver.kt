package com.polysil.crm.tracking

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * TRK-008 · A duty still open when the phone restarts carries on. Android lets a location service
 * start from here only with background location, which Duty asks for before it starts.
 */
internal class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (TrackingPrefs(context).duty == null) return
        if (!Permissions.backgroundGranted(context)) return
        TrackingService.start(context)
    }
}
