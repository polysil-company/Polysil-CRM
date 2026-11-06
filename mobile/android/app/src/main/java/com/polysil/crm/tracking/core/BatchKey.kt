package com.polysil.crm.tracking.core

import java.security.MessageDigest

/**
 * The `Idempotency-Key` of a batch: the sha256 of its sorted point ids, so the same points always
 * make the same key and a batch with other points makes another (contract §2). The ids are joined
 * with a newline before hashing; a uuid never contains one.
 */
object BatchKey {
    fun of(ids: Collection<String>): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(ids.sorted().joinToString("\n").toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}

/** Points oldest first, in batches of at most [max]. */
fun <T> splitIntoBatches(points: List<T>, max: Int): List<List<T>> {
    require(max > 0) { "max must be above 0" }
    return points.chunked(max)
}
