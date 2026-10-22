package com.polysil.crm.tracking

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** ISO 8601 with the phone's offset, "2026-10-22T09:04:11.000+05:30", on every Android from 24 up. */
internal fun isoTime(millis: Long): String =
    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).format(Date(millis))

/** Millis for an ISO 8601 time with an offset or "Z"; null when it doesn't read. */
internal fun parseIsoTime(text: String): Long? {
    val patterns = listOf("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", "yyyy-MM-dd'T'HH:mm:ssXXX")
    return patterns.firstNotNullOfOrNull { pattern ->
        runCatching { SimpleDateFormat(pattern, Locale.US).parse(text)?.time }.getOrNull()
    }
}
