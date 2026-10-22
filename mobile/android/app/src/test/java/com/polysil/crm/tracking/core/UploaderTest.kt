package com.polysil.crm.tracking.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BatchKeyTest {
    @Test
    fun `the key is the sha256 of the sorted ids, whatever their order`() {
        val key = BatchKey.of(listOf("b", "a"))
        assertEquals(BatchKey.of(listOf("a", "b")), key)
        assertEquals(64, key.length)
        assertEquals(key, java.security.MessageDigest.getInstance("SHA-256")
            .digest("a\nb".toByteArray()).joinToString("") { "%02x".format(it) })
        assertNotEquals(BatchKey.of(listOf("a", "b", "c")), key)
    }

    @Test
    fun `points split oldest first at the batch limit`() {
        val batches = splitIntoBatches((1..1201).toList(), 500)
        assertEquals(listOf(500, 500, 201), batches.map { it.size })
        assertEquals(1, batches.first().first())
    }
}

class UploaderTest {
    private fun uploader(
        store: MemoryStore,
        ledger: MemoryLedger,
        transport: ScriptedTransport,
        token: String? = "token-1",
    ) = Uploader(store, ledger, transport, "device-1", { "2026-10-22T11:30:00+05:30" }, { token })

    @Test
    fun `a 200 deletes every point sent, oldest first, in batches of the limit`() {
        val store = MemoryStore((1..1201).map(::point))
        val transport = ScriptedTransport(mutableListOf())
        val result = uploader(store, MemoryLedger(), transport).uploadAll(500)

        assertEquals(UploadResult.Done(accepted = 1201, duplicates = 0, rejected = 0), result)
        assertEquals(0, store.count())
        assertEquals(listOf(500, 500, 201), transport.sent.map { it.ids.size })
        assertEquals("p-0001", transport.sent.first().ids.first())
        assertEquals(BatchKey.of(transport.sent.first().ids), transport.sent.first().key)
    }

    @Test
    fun `rejected points are deleted too, since they are never accepted later`() {
        val store = MemoryStore((1..3).map(::point))
        val transport = ScriptedTransport(
            mutableListOf({ _ ->
                TransportResponse(
                    200,
                    """{"data":{"accepted":1,"duplicates":1,"rejected":[{"id":"p-0003","reason":"off_duty"}],"duty":{"id":"duty-1","ended_at":null,"end_reason":null}}}""",
                )
            }),
        )
        val result = uploader(store, MemoryLedger(), transport).uploadAll(500)

        assertEquals(UploadResult.Done(accepted = 1, duplicates = 1, rejected = 1), result)
        assertEquals(0, store.count())
    }

    @Test
    fun `a network error keeps the points and resends the same body under the same key`() {
        val store = MemoryStore((1..3).map(::point))
        val ledger = MemoryLedger()
        val transport = ScriptedTransport(mutableListOf({ null }))
        val sut = uploader(store, ledger, transport)

        assertTrue(sut.uploadAll(500) is UploadResult.RetryLater)
        assertEquals(3, store.count())

        assertEquals(UploadResult.Done(3, 0, 0), sut.uploadAll(500))
        assertEquals(2, transport.sent.size)
        assertEquals(transport.sent[0].key, transport.sent[1].key)
        assertEquals(transport.sent[0].body, transport.sent[1].body)
    }

    @Test
    fun `a 5xx is retried later under the same key`() {
        val store = MemoryStore((1..2).map(::point))
        val ledger = MemoryLedger()
        val transport = ScriptedTransport(mutableListOf({ TransportResponse(503, "") }))
        val sut = uploader(store, ledger, transport)

        assertEquals(UploadResult.RetryLater("server 503"), sut.uploadAll(500))
        assertEquals(2, store.count())
        sut.uploadAll(500)
        assertEquals(transport.sent[0].key, transport.sent[1].key)
        assertTrue(ledger.burned.isEmpty())
    }

    @Test
    fun `a 401 keeps the points and waits for a new token`() {
        val store = MemoryStore((1..2).map(::point))
        val transport = ScriptedTransport(mutableListOf({ error(401, "unauthenticated") }))
        assertEquals(UploadResult.WaitingForToken, uploader(store, MemoryLedger(), transport).uploadAll(500))
        assertEquals(2, store.count())
    }

    @Test
    fun `without a valid token nothing is sent`() {
        val store = MemoryStore((1..2).map(::point))
        val transport = ScriptedTransport(mutableListOf())
        assertEquals(
            UploadResult.WaitingForToken,
            uploader(store, MemoryLedger(), transport, token = null).uploadAll(500),
        )
        assertTrue(transport.sent.isEmpty())
    }

    @Test
    fun `the server ending the duty stops the run after deleting what it took`() {
        val store = MemoryStore((1..700).map(::point))
        val transport = ScriptedTransport(mutableListOf({ request -> okFor(request, endedAt = "2026-10-22T19:30:00+05:30") }))
        val result = uploader(store, MemoryLedger(), transport).uploadAll(500)

        assertEquals(UploadResult.ServerEndedDuty("auto"), result)
        assertEquals(1, transport.sent.size)
        assertEquals(200, store.count())
    }

    @Test
    fun `a 403 stops tracking`() {
        val store = MemoryStore((1..2).map(::point))
        val transport = ScriptedTransport(mutableListOf({ error(403, "forbidden") }))
        assertEquals(UploadResult.Forbidden, uploader(store, MemoryLedger(), transport).uploadAll(500))
        assertEquals(2, store.count())
    }

    @Test
    fun `batch_too_large splits, each part under a new key`() {
        val store = MemoryStore((1..8).map(::point))
        val transport = ScriptedTransport(mutableListOf({ error(422, "batch_too_large") }))
        val result = uploader(store, MemoryLedger(), transport).uploadAll(8)

        assertEquals(UploadResult.Done(8, 0, 0), result)
        assertEquals(listOf(8, 4, 4), transport.sent.map { it.ids.size })
        assertEquals(3, transport.sent.map { it.key }.toSet().size)
    }

    @Test
    fun `bad_clock is reported and its key is never used again`() {
        val store = MemoryStore((1..4).map(::point))
        val ledger = MemoryLedger()
        val transport = ScriptedTransport(mutableListOf({ error(422, "bad_clock") }))
        val sut = uploader(store, ledger, transport)

        assertEquals(UploadResult.BadClock, sut.uploadAll(500))
        assertEquals(4, store.count())
        sut.uploadAll(500)
        assertTrue(transport.sent.drop(1).none { it.key == transport.sent[0].key })
    }

    @Test
    fun `after any other 4xx the key is never reused, and the point at fault is dropped`() {
        val store = MemoryStore((1..2).map(::point))
        val ledger = MemoryLedger()
        // The pair is refused; then the first point alone is refused; the second goes through.
        val transport = ScriptedTransport(
            mutableListOf(
                { error(422, "validation_error") },
                { error(422, "validation_error") },
            ),
        )
        val sut = uploader(store, ledger, transport)

        assertEquals(UploadResult.Refused(422, "validation_error"), sut.uploadAll(500))
        assertEquals(UploadResult.Refused(422, "validation_error"), sut.uploadAll(500))
        assertEquals(listOf("p-0002"), store.points.map { it.id })
        assertEquals(UploadResult.Done(1, 0, 0), sut.uploadAll(500))

        val keys = transport.sent.map { it.key }
        assertEquals(keys.size, keys.toSet().size)
        assertEquals(0, store.count())
        assertNull(ledger.current)
    }
}
