package com.polysil.crm.tracking

import com.polysil.crm.tracking.core.BatchTransport
import com.polysil.crm.tracking.core.TransportResponse
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * TRK-008 · `POST /locations/batch` from native code, never from the WebView: Android slows the
 * WebView's requests a few minutes after the app goes to the background.
 */
internal class OkHttpTransport(private val apiBaseUrl: String) : BatchTransport {
    override fun postBatch(body: String, idempotencyKey: String, accessToken: String): TransportResponse {
        val request = Request.Builder()
            .url("${apiBaseUrl.trimEnd('/')}/locations/batch")
            .header("Authorization", "Bearer $accessToken")
            .header("Idempotency-Key", idempotencyKey)
            .header("x-data-id", "TRK-008")
            .header("x-request-id", UUID.randomUUID().toString())
            .post(body.toRequestBody(JSON))
            .build()
        client.newCall(request).execute().use { response ->
            return TransportResponse(response.code, response.body.string())
        }
    }

    private companion object {
        val JSON = "application/json; charset=utf-8".toMediaType()
        val client: OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }
}
