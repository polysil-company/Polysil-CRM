package com.polysil.crm.tracking.core

import java.io.IOException

/** Points in memory, oldest first, as Room keeps them on the phone. */
class MemoryStore(points: List<TrackPoint>) : PointStore {
    val points = points.toMutableList()

    override fun oldest(limit: Int): List<TrackPoint> = points.take(limit)

    override fun delete(ids: Collection<String>) {
        points.removeAll { it.id in ids }
    }

    override fun count(): Int = points.size
}

class MemoryLedger : UploadLedger {
    var current: InFlight? = null
    val burned = mutableSetOf<String>()

    override fun inFlight(): InFlight? = current

    override fun setInFlight(batch: InFlight?) {
        current = batch
    }

    override fun isBurned(key: String): Boolean = key in burned

    override fun burn(key: String) {
        burned += key
    }
}

/** One request the fake server saw. */
data class Sent(val body: String, val key: String, val token: String, val ids: List<String>)

/** A server that answers each request with the next scripted reply; a null reply is a network error. */
class ScriptedTransport(private val replies: MutableList<(Sent) -> TransportResponse?>) : BatchTransport {
    val sent = mutableListOf<Sent>()

    override fun postBatch(body: String, idempotencyKey: String, accessToken: String): TransportResponse {
        val ids = Regex("\"id\":\"([^\"]+)\"").findAll(body).map { it.groupValues[1] }.toList()
        val request = Sent(body, idempotencyKey, accessToken, ids)
        sent += request
        val reply: (Sent) -> TransportResponse? =
            if (replies.isEmpty()) { sent -> okFor(sent) } else replies.removeAt(0)
        return reply(request) ?: throw IOException("offline")
    }
}

fun point(n: Int, duty: String = "duty-1"): TrackPoint =
    TrackPoint(
        id = "p-%04d".format(n),
        dutyId = duty,
        recordedAt = "2026-10-22T09:%02d:00+05:30".format(n % 60),
        lat = 23.02 + n / 10_000.0,
        lng = 72.57,
        accuracyM = 9.0,
        batteryPct = 80,
    )

fun okFor(request: Sent, endedAt: String? = null): TransportResponse {
    val duty = if (endedAt == null) "null" else "\"$endedAt\""
    return TransportResponse(
        200,
        """{"data":{"accepted":${request.ids.size},"duplicates":0,"rejected":[],""" +
            """"duty":{"id":"duty-1","ended_at":$duty,"end_reason":${if (endedAt == null) "null" else "\"auto\""}}}}""",
    )
}

fun error(status: Int, code: String): TransportResponse =
    TransportResponse(status, """{"error":{"code":"$code","message":"refused"}}""")
