package com.polysil.crm.tracking

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.location.Location
import android.net.ConnectivityManager
import android.net.Network
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.polysil.crm.tracking.core.TrackPoint
import com.polysil.crm.tracking.data.RoomPointStore
import com.polysil.crm.tracking.data.TrackingDatabase
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * TRK-008 · On duty: a foreground service of type `location`, with a permanent "Tracking on duty"
 * notification. Every fix goes into Room with a new uuid and the duty id; every `interval_seconds`,
 * and whenever the network comes back, the waiting points go up.
 */
internal class TrackingService : Service() {
    private lateinit var fused: FusedLocationProviderClient
    private val io: ExecutorService = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private var uploadTick: Runnable? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val duty = TrackingPrefs(this@TrackingService).duty ?: return
            val battery = batteryPct()
            val points = result.locations.map { location -> pointOf(location, duty.dutyId, battery) }
            background {
                val store = RoomPointStore(TrackingDatabase.get(this@TrackingService).points())
                points.forEach(store::add)
                TrackingEvents.status(UploadRunner.statusOf(this@TrackingService))
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val duty = TrackingPrefs(this).duty
        if (duty == null || !Permissions.fineGranted(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0,
        )
        requestFixes(duty)
        scheduleUploads(duty)
        watchNetwork()
        return START_STICKY
    }

    override fun onDestroy() {
        fused.removeLocationUpdates(locationCallback)
        uploadTick?.let(handler::removeCallbacks)
        networkCallback?.let { callback ->
            getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(callback)
        }
        io.shutdown()
        super.onDestroy()
    }

    /** Off the main thread, unless the service has already stopped. */
    private fun background(task: () -> Unit) {
        if (!io.isShutdown) io.execute(task)
    }

    // Fine location is checked in onStartCommand before this runs.
    @SuppressLint("MissingPermission")
    private fun requestFixes(duty: DutyConfig) {
        val intervalMs = duty.intervalSeconds * 1_000L
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, intervalMs)
            .setMinUpdateDistanceMeters(duty.distanceFilterM.toFloat())
            .setMinUpdateIntervalMillis(intervalMs / 2)
            .build()
        try {
            fused.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
        } catch (denied: SecurityException) {
            Log.w(TAG, "Location refused", denied)
            TrackingPrefs(this).lastError = "location_denied"
            stopSelf()
        }
    }

    private fun scheduleUploads(duty: DutyConfig) {
        uploadTick?.let(handler::removeCallbacks)
        val tick = object : Runnable {
            override fun run() {
                background { UploadRunner.run(this@TrackingService) }
                handler.postDelayed(this, duty.intervalSeconds * 1_000L)
            }
        }
        uploadTick = tick
        handler.postDelayed(tick, duty.intervalSeconds * 1_000L)
    }

    private fun watchNetwork() {
        if (networkCallback != null) return
        val connectivity = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                background { UploadRunner.run(this@TrackingService) }
            }
        }
        connectivity.registerDefaultNetworkCallback(callback)
        networkCallback = callback
    }

    private fun batteryPct(): Int? {
        val battery = getSystemService(BatteryManager::class.java) ?: return null
        return battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY).takeIf { it in 0..100 }
    }

    private fun pointOf(location: Location, dutyId: String, battery: Int?): TrackPoint {
        val mock = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) location.isMock else isFromMock(location)
        return TrackPoint(
            id = UUID.randomUUID().toString(),
            dutyId = dutyId,
            recordedAt = isoTime(location.time),
            lat = location.latitude,
            lng = location.longitude,
            accuracyM = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
            speedMps = if (location.hasSpeed()) location.speed.toDouble() else null,
            heading = if (location.hasBearing()) location.bearing.toDouble() else null,
            altitudeM = if (location.hasAltitude()) location.altitude else null,
            batteryPct = battery,
            isMock = mock,
        )
    }

    @Suppress("DEPRECATION")
    private fun isFromMock(location: Location): Boolean = location.isFromMockProvider

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager != null) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Duty tracking", NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Shown while you are on duty and your route is recorded."
                },
            )
        }
        val open = packageManager.getLaunchIntentForPackage(packageName)?.let { launch ->
            PendingIntent.getActivity(this, 0, launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Tracking on duty")
            .setContentText("Your route is recorded until you go off duty.")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .apply { open?.let(::setContentIntent) }
            .build()
    }

    companion object {
        private const val TAG = "PolysilTracking"
        private const val CHANNEL_ID = "polysil-duty"
        private const val NOTIFICATION_ID = 4108

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, TrackingService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, TrackingService::class.java))
        }
    }
}
