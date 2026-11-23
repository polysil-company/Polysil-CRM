package com.polysil.crm.tracking.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UploadProtocolTest {
    @Test
    fun `the body carries the device, the send time and each point, optional fields left out`() {
        val body = batchBody("device-1", "2026-10-22T11:30:00+05:30", listOf(point(1).copy(speedMps = null, isMock = true)))
        assertTrue(body.startsWith("""{"device_id":"device-1","sent_at":"2026-10-22T11:30:00+05:30","points":[{"id":"p-0001""""))
        assertTrue(body.contains(""""is_mock":true"""))
        assertTrue(body.contains(""""accuracy_m":9.0"""))
        assertFalse(body.contains("speed_mps"))
    }

    @Test
    fun `reads a 200 answer and the error code of a refusal`() {
        val answer = parseBatchAnswer(
            """{"data":{"accepted":497,"duplicates":2,"rejected":[{"id":"x","reason":"off_duty"}],"duty":{"id":"d","ended_at":null,"end_reason":null}}}""",
        )
        assertEquals(BatchAnswer(497, 2, listOf("x"), null, null), answer)
        assertNull(parseBatchAnswer("not json"))
        assertEquals("bad_clock", parseErrorCode("""{"error":{"code":"bad_clock","message":"m"}}"""))
        assertNull(parseErrorCode(""))
    }
}
