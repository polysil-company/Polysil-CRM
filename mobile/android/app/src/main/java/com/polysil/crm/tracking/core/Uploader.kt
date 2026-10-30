package com.polysil.crm.tracking.core

import java.io.IOException

/** Where points wait until the server confirms them: Room on the phone, a list in tests. */
interface PointStore {
    /** The oldest points, oldest first. */
    fun oldest(limit: Int): List<TrackPoint>
    fun delete(ids: Collection<String>)
    fun count(): Int
}

/**
 * A batch sent but not yet answered. A network failure or a `5xx` resends exactly this body under
 * this key (contract §2), so it is kept until an answer arrives.
 */
data class InFlight(val key: String, val body: String, val ids: List<String>)

/** The one batch in flight, and the keys a `4xx` used up: never sent again (contract §2). */
interface UploadLedger {
    fun inFlight(): InFlight?
    fun setInFlight(batch: InFlight?)
    fun isBurned(key: String): Boolean
    fun burn(key: String)
}

/** The server's answer, or [IOException] when there was none (offline, timeout). */
data class TransportResponse(val status: Int, val body: String)

fun interface BatchTransport {
    @Throws(IOException::class)
    fun postBatch(body: String, idempotencyKey: String, token: String): TransportResponse
}

/** What an upload run ended with. */
sealed interface UploadResult {
    /** Every waiting point went (or nothing was waiting). */
    data class Done(val accepted: Int, val duplicates: Int, val rejected: Int) : UploadResult

    /** No usable device token, or a `401`: the points wait for the screens to hand over a new one. */
    data object WaitingForToken : UploadResult

    /** Offline, a timeout or a `5xx`: the same body goes again later, with backoff. */
    data class RetryLater(val reason: String) : UploadResult

    /** The server ended the duty: stop tracking. The batch's points are deleted first. */
    data class ServerEndedDuty(val endReason: String?) : UploadResult

    /** Any `403`: this role doesn't track (now). Stop; the points and the batch's key are kept. */
    data object Forbidden : UploadResult

    /** `422 bad_clock`: the phone's clock is more than a day off. Say so; the key is used up. */
    data object BadClock : UploadResult

    /** Any other `4xx`: its key is used up, and the points are split until the bad one is found. */
    data class Refused(val status: Int, val code: String?) : UploadResult
}

/**
 * TRK-008 · Sends the waiting points, oldest first, at most `maxBatchPoints` a batch, and applies
 * the contract's answers:
 * - `200`: delete every point sent, counted or named; a rejected point is never accepted later.
 *   `duty.ended_at` set: stop.
 * - `422 batch_too_large`: split, each part under its own key.
 * - `422 bad_clock`: tell the person.
 * - `401` or any `403` (contract §1 step 9): keep every point and the batch in flight, and wait
 *   for a new device token. Both are refused before the server records the key, so the same body
 *   may go again under it.
 * - Any other `4xx`: never retry under the same key. The key is recorded as used, and the next run
 *   halves the batch until the point at fault is alone; that point is then dropped, since the
 *   server will never take it.
 * - Network error or `5xx`: resend the same body under the same key, later.
 */
class Uploader(
    private val store: PointStore,
    private val ledger: UploadLedger,
    private val transport: BatchTransport,
    private val deviceId: String,
    /** The phone's clock now, ISO 8601 with an offset: a batch's `sent_at`. */
    private val sentAt: () -> String,
    /** The device token while it is usable, or null. */
    private val token: () -> String?,
) {
    fun uploadAll(maxBatchPoints: Int): UploadResult {
        require(maxBatchPoints > 0) { "maxBatchPoints must be above 0" }
        var accepted = 0
        var duplicates = 0
        var rejected = 0
        var size = maxBatchPoints
        // A guard against a loop that never ends: every pass sends or deletes something.
        repeat(MAX_PASSES) {
            val bearer = token() ?: return UploadResult.WaitingForToken
            val batch = ledger.inFlight() ?: nextBatch(size) ?: return UploadResult.Done(accepted, duplicates, rejected)
            ledger.setInFlight(batch)
            val response = try {
                transport.postBatch(batch.body, batch.key, bearer)
            } catch (error: IOException) {
                return UploadResult.RetryLater(error.message ?: "network error")
            }
            when {
                response.status == 200 -> {
                    ledger.setInFlight(null)
                    store.delete(batch.ids)
                    val answer = parseBatchAnswer(response.body)
                        ?: return UploadResult.RetryLater("unreadable answer")
                    accepted += answer.accepted
                    duplicates += answer.duplicates
                    rejected += answer.rejectedIds.size
                    size = maxBatchPoints
                    if (answer.dutyEndedAt != null) {
                        return UploadResult.ServerEndedDuty(answer.dutyEndReason)
                    }
                }
                // Refused before the key was recorded: the same body may go again.
                response.status == 401 -> return UploadResult.WaitingForToken
                response.status == 403 -> return UploadResult.Forbidden
                response.status >= 500 -> return UploadResult.RetryLater("server ${response.status}")
                else -> {
                    ledger.setInFlight(null)
                    ledger.burn(batch.key)
                    val code = parseErrorCode(response.body)
                    when {
                        code == "bad_clock" -> return UploadResult.BadClock
                        code == "batch_too_large" -> size = maxOf(1, batch.ids.size / 2)
                        else -> {
                            if (batch.ids.size == 1) {
                                store.delete(batch.ids)
                            }
                            return UploadResult.Refused(response.status, code)
                        }
                    }
                }
            }
        }
        return UploadResult.RetryLater("too many batches in one run")
    }

    /**
     * The next batch of at most [size] oldest points. A batch whose key a `4xx` used up is halved
     * until its key is new; a single point whose key is used up is dropped.
     */
    private fun nextBatch(size: Int): InFlight? {
        var take = size
        while (true) {
            val points = store.oldest(take)
            if (points.isEmpty()) return null
            val ids = points.map { it.id }
            val key = BatchKey.of(ids)
            if (!ledger.isBurned(key)) {
                return InFlight(key, batchBody(deviceId, sentAt(), points), ids)
            }
            if (points.size == 1) {
                store.delete(ids)
                continue
            }
            take = points.size / 2
        }
    }

    private companion object {
        const val MAX_PASSES = 1_000
    }
}
