package com.polysil.crm.tracking.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey
import com.polysil.crm.tracking.core.TrackPoint

/** A stored fix. `seq` keeps them in the order they were taken, for oldest-first batches. */
@Entity(tableName = "points")
data class PointEntity(
    @PrimaryKey(autoGenerate = true) val seq: Long = 0,
    @ColumnInfo(index = true) val id: String,
    @ColumnInfo(name = "duty_id") val dutyId: String,
    @ColumnInfo(name = "recorded_at") val recordedAt: String,
    val lat: Double,
    val lng: Double,
    @ColumnInfo(name = "accuracy_m") val accuracyM: Double?,
    @ColumnInfo(name = "speed_mps") val speedMps: Double?,
    val heading: Double?,
    @ColumnInfo(name = "altitude_m") val altitudeM: Double?,
    @ColumnInfo(name = "battery_pct") val batteryPct: Int?,
    @ColumnInfo(name = "is_mock") val isMock: Boolean,
) {
    fun toPoint(): TrackPoint =
        TrackPoint(id, dutyId, recordedAt, lat, lng, accuracyM, speedMps, heading, altitudeM, batteryPct, isMock)

    companion object {
        fun of(point: TrackPoint): PointEntity =
            PointEntity(
                id = point.id,
                dutyId = point.dutyId,
                recordedAt = point.recordedAt,
                lat = point.lat,
                lng = point.lng,
                accuracyM = point.accuracyM,
                speedMps = point.speedMps,
                heading = point.heading,
                altitudeM = point.altitudeM,
                batteryPct = point.batteryPct,
                isMock = point.isMock,
            )
    }
}
