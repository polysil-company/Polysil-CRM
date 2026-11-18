package com.polysil.crm.tracking.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DeviceTokenTest {
    private val expiresAt = 1_800_000_000_000L
    private val token = DeviceToken("pdt_abc", expiresAt, "user-1")

    @Test
    fun `a token is sent until a minute before it expires`() {
        assertEquals("pdt_abc", token.usable(expiresAt - 120_000L))
        assertNull(token.usable(expiresAt - 60_000L))
        assertNull(token.usable(expiresAt + 1L))
    }

    @Test
    fun `a blank token is never sent`() {
        assertNull(DeviceToken(" ", expiresAt, "user-1").usable(0L))
    }
}
