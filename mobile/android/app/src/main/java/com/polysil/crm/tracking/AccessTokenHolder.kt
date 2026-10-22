package com.polysil.crm.tracking

/**
 * TRK-008 · The web app's access token, handed over by `setAccessToken` after each sign-in and
 * refresh. Memory only: it lasts minutes, and the native side never refreshes it, since two
 * refreshers would trip `refresh_reused` and sign the person out everywhere. When it runs out,
 * points wait on the phone until the app is opened again (BE-032 will give a device token).
 */
internal object AccessTokenHolder {
    /** Stop using a token this long before it expires. */
    private const val MARGIN_MS = 30_000L

    @Volatile private var token: String? = null
    @Volatile private var expiresAtMillis: Long = 0L

    fun set(value: String?, expiresAt: Long) {
        token = value?.takeIf { it.isNotBlank() }
        expiresAtMillis = expiresAt
    }

    fun valid(nowMillis: Long = System.currentTimeMillis()): String? =
        token?.takeIf { nowMillis < expiresAtMillis - MARGIN_MS }
}
