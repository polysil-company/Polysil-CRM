package com.polysil.crm.tracking.core

/**
 * TRK-009 · The device token the screens hand over (BE-032, `POST /tracking/device-token`): good
 * only for location batches, duty end and the tracking config, for 30 days, and only while the
 * sign-in it came from lives. The native side never asks for one itself.
 */
data class DeviceToken(
    /** `pdt_…`: sent as `Authorization: Bearer`. */
    val token: String,
    val expiresAtMillis: Long,
    /** Whose token it is. One person per phone (client question 9.5). */
    val userId: String,
) {
    /** The token while it can still be sent, else null. */
    fun usable(nowMillis: Long): String? =
        token.takeIf { it.isNotBlank() && nowMillis < expiresAtMillis - MARGIN_MS }

    private companion object {
        /** Stop using a token this long before it expires. */
        const val MARGIN_MS = 60_000L
    }
}
