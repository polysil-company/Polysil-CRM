package com.polysil.crm.tracking.core

/**
 * TRK-008 · One GPS fix as the phone keeps it until the server confirms it
 * (`POST /locations/batch`, `field-tracking-contract.md` §3). Pure Kotlin: no Android types, so
 * the batching and retry rules run as plain JVM unit tests.
 */
data class TrackPoint(
    /** A uuid made on the phone when the fix is stored. */
    val id: String,
    val dutyId: String,
    /** ISO 8601 with an offset: "2026-10-05T09:04:11+05:30". */
    val recordedAt: String,
    val lat: Double,
    val lng: Double,
    val accuracyM: Double? = null,
    val speedMps: Double? = null,
    val heading: Double? = null,
    val altitudeM: Double? = null,
    val batteryPct: Int? = null,
    /** The phone reported a fake location (`Location.isMock`). */
    val isMock: Boolean = false,
)
