package com.polysil.crm.tracking

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import java.util.concurrent.Executors

/**
 * TRK-008 · The web app's handle on duty tracking (`Frontend/src/features/tracking/native/`). The
 * web side calls the API for duty start and end; this keeps the fixes, uploads them natively, and
 * reports back. Events: `status`, and `serverEndedDuty` when a batch answer ends the duty.
 */
@CapacitorPlugin(
    name = "PolysilTracking",
    permissions = [
        Permission(
            alias = TrackingPlugin.LOCATION,
            strings = [Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION],
        ),
        Permission(alias = TrackingPlugin.BACKGROUND, strings = [Manifest.permission.ACCESS_BACKGROUND_LOCATION]),
        Permission(alias = TrackingPlugin.NOTIFICATIONS, strings = [Manifest.permission.POST_NOTIFICATIONS]),
    ],
)
class TrackingPlugin : Plugin() {
    private val worker = Executors.newSingleThreadExecutor()

    private val listener = object : TrackingEvents.Listener {
        override fun onStatus(status: TrackingStatus) {
            notifyListeners("status", status.toJs())
        }

        override fun onServerEndedDuty(status: TrackingStatus, endReason: String?) {
            notifyListeners("serverEndedDuty", status.toJs().put("endReason", endReason))
        }
    }

    override fun load() {
        TrackingEvents.add(listener)
    }

    override fun handleOnDestroy() {
        TrackingEvents.remove(listener)
        worker.shutdown()
    }

    /** The install's uuid, and the phone's maker for the autostart advice. */
    @PluginMethod
    fun getDeviceId(call: PluginCall) {
        call.resolve(
            JSObject()
                .put("deviceId", TrackingPrefs(context).deviceId)
                .put("manufacturer", Build.MANUFACTURER.orEmpty()),
        )
    }

    @PluginMethod
    override fun checkPermissions(call: PluginCall) {
        call.resolve(permissionsJs())
    }

    /** Fine location first, then "Allow all the time", then notifications on Android 13 and up. */
    @PluginMethod
    override fun requestPermissions(call: PluginCall) {
        when {
            !Permissions.fineGranted(context) -> requestPermissionForAlias(LOCATION, call, "afterPermission")
            !Permissions.backgroundGranted(context) -> requestPermissionForAlias(BACKGROUND, call, "afterPermission")
            !Permissions.notificationsGranted(context) ->
                requestPermissionForAlias(NOTIFICATIONS, call, "afterPermission")
            else -> call.resolve(permissionsJs())
        }
    }

    @PermissionCallback
    private fun afterPermission(call: PluginCall) {
        val next = when {
            !Permissions.fineGranted(context) -> null
            !Permissions.backgroundGranted(context) && getPermissionState(BACKGROUND) == PermissionState.PROMPT -> BACKGROUND
            !Permissions.notificationsGranted(context) && getPermissionState(NOTIFICATIONS) == PermissionState.PROMPT ->
                NOTIFICATIONS
            else -> null
        }
        if (next == null) call.resolve(permissionsJs()) else requestPermissionForAlias(next, call, "afterPermission")
    }

    /** Asks to ignore battery optimisation (`ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`). */
    @PluginMethod
    fun openBatterySettings(call: PluginCall) {
        val ask = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
        val list = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
        startSettings(call, ask, list)
    }

    /** The app's own settings (a permission denied for good), or the phone's location switch. */
    @PluginMethod
    fun openSettings(call: PluginCall) {
        val target = if (call.getString("which") == "location") {
            Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))
        }
        startSettings(call, target, Intent(Settings.ACTION_SETTINGS))
    }

    /** The web app's access token and when it expires; empty to forget it (signed out). */
    @PluginMethod
    fun setAccessToken(call: PluginCall) {
        val token = call.getString("token").orEmpty()
        val expiresAt = call.getString("expiresAt")?.let(::parseIsoTime) ?: 0L
        AccessTokenHolder.set(token, expiresAt)
        call.resolve()
        // Points that waited for a token go up now.
        if (token.isNotEmpty()) worker.execute { UploadRunner.run(context) }
    }

    @PluginMethod
    fun start(call: PluginCall) {
        val dutyId = call.getString("dutyId")
        val apiBaseUrl = call.getString("apiBaseUrl")
        val interval = call.getInt("intervalSeconds") ?: 0
        val maxBatch = call.getInt("maxBatchPoints") ?: 0
        if (dutyId.isNullOrBlank() || apiBaseUrl.isNullOrBlank() || interval <= 0 || maxBatch <= 0) {
            call.reject("dutyId, apiBaseUrl, intervalSeconds and maxBatchPoints are needed", "invalid_options")
            return
        }
        if (!Permissions.fineGranted(context)) {
            call.reject("Location isn't allowed", "permission_denied")
            return
        }
        val prefs = TrackingPrefs(context)
        prefs.duty = DutyConfig(
            dutyId = dutyId,
            since = call.getString("since").orEmpty(),
            intervalSeconds = interval,
            distanceFilterM = call.getInt("distanceFilterM") ?: 0,
            maxBatchPoints = maxBatch,
            apiBaseUrl = apiBaseUrl,
        )
        prefs.apiBaseUrl = apiBaseUrl
        prefs.lastError = null
        TrackingService.start(context)
        call.resolve()
    }

    @PluginMethod
    fun stop(call: PluginCall) {
        TrackingPrefs(context).duty = null
        TrackingService.stop(context)
        call.resolve()
        worker.execute { TrackingEvents.status(UploadRunner.statusOf(context)) }
    }

    /** Upload now: what went, and what still waits. */
    @PluginMethod
    fun flush(call: PluginCall) {
        worker.execute {
            val outcome = UploadRunner.run(context)
            call.resolve(
                JSObject()
                    .put("accepted", outcome.accepted)
                    .put("duplicates", outcome.duplicates)
                    .put("rejected", outcome.rejected)
                    .put("pending", outcome.pending),
            )
        }
    }

    @PluginMethod
    fun getStatus(call: PluginCall) {
        worker.execute { call.resolve(UploadRunner.statusOf(context).toJs()) }
    }

    private fun startSettings(call: PluginCall, first: Intent, fallback: Intent) {
        val activity = activity
        if (activity == null) {
            call.reject("No screen to open settings from", "no_activity")
            return
        }
        val intent = if (first.resolveActivity(activity.packageManager) != null) first else fallback
        activity.startActivity(intent)
        call.resolve()
    }

    private fun permissionsJs(): JSObject {
        fun state(alias: String, granted: Boolean): String =
            if (granted) "granted" else if (getPermissionState(alias) == PermissionState.DENIED) "denied" else "prompt"
        return JSObject()
            .put("location", state(LOCATION, Permissions.fineGranted(context)))
            .put("background", state(BACKGROUND, Permissions.backgroundGranted(context)))
            .put("notifications", state(NOTIFICATIONS, Permissions.notificationsGranted(context)))
            .put("batteryUnrestricted", Permissions.batteryUnrestricted(context))
            .put("gpsOn", Permissions.gpsOn(context))
    }

    private fun TrackingStatus.toJs(): JSObject =
        JSObject()
            .put("onDuty", onDuty)
            .put("dutyId", dutyId)
            .put("since", since)
            .put("lastUploadAt", lastUploadAt)
            .put("pendingPoints", pendingPoints)
            .put("lastError", lastError)

    companion object {
        const val LOCATION = "location"
        const val BACKGROUND = "background"
        const val NOTIFICATIONS = "notifications"
    }
}
