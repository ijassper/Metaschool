package com.schoolingrid.student

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.concurrent.Executors

object ProctorEventReporter {
    private val executor = Executors.newSingleThreadExecutor()

    fun send(
        eventUrl: String,
        csrfToken: String,
        cookie: String,
        eventType: String,
        message: String = "",
    ) {
        if (eventUrl.isBlank()) return
        executor.execute {
            runCatching {
                val payload = JSONObject().apply {
                    put("event_type", eventType)
                    put("occurred_at", Instant.now().toString())
                    put("message", message)
                }.toString()
                val connection = (URL(eventUrl).openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 10_000
                    readTimeout = 10_000
                    doOutput = true
                    useCaches = false
                    setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                    setRequestProperty("X-CSRFToken", csrfToken)
                    setRequestProperty("X-Requested-With", "XMLHttpRequest")
                    setRequestProperty("Cookie", cookie)
                    setRequestProperty("Referer", "https://schoolingrid.com/")
                    setRequestProperty("User-Agent", "IngridStudentAndroid/0.1")
                }
                connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
                connection.responseCode
                connection.disconnect()
            }
        }
    }
}
