package com.polysil.crm.tracking.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/** The body of `POST /locations/batch`, oldest point first. Optional fields are left out. */
fun batchBody(deviceId: String, sentAt: String, points: List<TrackPoint>): String {
    val body = buildJsonObject {
        put("device_id", deviceId)
        put("sent_at", sentAt)
        put(
            "points",
            buildJsonArray {
                points.forEach { point ->
                    add(
                        buildJsonObject {
                            put("id", point.id)
                            put("duty_id", point.dutyId)
                            put("recorded_at", point.recordedAt)
                            put("lat", point.lat)
                            put("lng", point.lng)
                            point.accuracyM?.let { put("accuracy_m", it) }
                            point.speedMps?.let { put("speed_mps", it) }
                            point.heading?.let { put("heading", it) }
                            point.altitudeM?.let { put("altitude_m", it) }
                            point.batteryPct?.let { put("battery_pct", it) }
                            put("is_mock", point.isMock)
                        },
                    )
                }
            },
        )
    }
    return body.toString()
}

/** A `200` answer: what the server counted, what it refused, and whether it ended the duty. */
data class BatchAnswer(
    val accepted: Int,
    val duplicates: Int,
    val rejectedIds: List<String>,
    /** Set when the server ended the duty: idle after hours, consent withdrawn, deactivated. */
    val dutyEndedAt: String?,
    val dutyEndReason: String?,
)

private val json = Json { ignoreUnknownKeys = true }

private fun JsonElement?.objectOrNull(): JsonObject? = this as? JsonObject

private fun JsonElement?.textOrNull(): String? =
    (this as? JsonPrimitive)?.takeUnless { it is JsonNull }?.contentOrNull

/** Reads a `200` answer; null when it isn't the shape the contract promises. */
fun parseBatchAnswer(body: String): BatchAnswer? {
    val data = runCatching { json.parseToJsonElement(body).jsonObject["data"] }.getOrNull()
        .objectOrNull() ?: return null
    val accepted = (data["accepted"] as? JsonPrimitive)?.intOrNull ?: return null
    val duplicates = (data["duplicates"] as? JsonPrimitive)?.intOrNull ?: 0
    val rejected = (data["rejected"] as? JsonArray).orEmpty().mapNotNull { item ->
        item.objectOrNull()?.get("id").textOrNull()
    }
    val duty = data["duty"].objectOrNull()
    return BatchAnswer(
        accepted = accepted,
        duplicates = duplicates,
        rejectedIds = rejected,
        dutyEndedAt = duty?.get("ended_at").textOrNull(),
        dutyEndReason = duty?.get("end_reason").textOrNull(),
    )
}

/** The `error.code` of a refusal, when the body has one. */
fun parseErrorCode(body: String): String? =
    runCatching { json.parseToJsonElement(body).jsonObject["error"] }.getOrNull()
        .objectOrNull()?.get("code").textOrNull()
