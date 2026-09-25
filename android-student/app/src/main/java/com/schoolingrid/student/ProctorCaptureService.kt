package com.schoolingrid.student

import android.app.NotificationChannel
import android.app.Notification
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.SystemClock
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.roundToInt

class ProctorCaptureService : Service() {
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var captureThread: HandlerThread? = null
    private var lastCaptureAt = 0L
    private var uploadUrl = ""
    private var eventUrl = ""
    private var csrfToken = ""
    private var cookie = ""
    private var studentName = "학생"
    private var captureScope = CAPTURE_SCOPE_FULL_DISPLAY
    @Volatile private var externalAppVisible = false
    @Volatile private var externalSinceMillis = 0L
    private val uploadWorkerRunning = AtomicBoolean(false)
    private val pendingSnapshots = ArrayDeque<EncryptedSnapshotBuffer.Item>()
    private val pendingSnapshotsLock = Any()
    private val uploadExecutor = Executors.newSingleThreadExecutor()
    private var snapshotBuffer: EncryptedSnapshotBuffer? = null
    @Volatile private var bufferingSnapshots = false
    private var lastUploadStartedAt = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_APP_BACKGROUND -> {
                externalAppVisible = true
                externalSinceMillis = intent.getLongExtra(
                    EXTRA_OCCURRED_AT_MILLIS,
                    System.currentTimeMillis(),
                )
            }
            ACTION_APP_FOREGROUND -> {
                externalAppVisible = false
                externalSinceMillis = 0L
            }
            ACTION_START -> startProjection(intent)
        }
        return START_NOT_STICKY
    }

    private fun startProjection(intent: Intent) {
        if (mediaProjection != null) return

        startForeground(NOTIFICATION_ID, buildNotification())
        uploadUrl = intent.getStringExtra(EXTRA_UPLOAD_URL).orEmpty()
        eventUrl = intent.getStringExtra(EXTRA_EVENT_URL).orEmpty()
        csrfToken = intent.getStringExtra(EXTRA_CSRF_TOKEN).orEmpty()
        cookie = intent.getStringExtra(EXTRA_COOKIE).orEmpty()
        snapshotBuffer = EncryptedSnapshotBuffer(this, uploadUrl, MAX_PENDING_SNAPSHOTS)
        studentName = intent.getStringExtra(EXTRA_STUDENT_NAME)
            ?.trim()
            ?.take(40)
            ?.ifBlank { "학생" }
            ?: "학생"
        captureScope = if (intent.getStringExtra(EXTRA_CAPTURE_SCOPE) == CAPTURE_SCOPE_APP_ONLY) {
            CAPTURE_SCOPE_APP_ONLY
        } else {
            CAPTURE_SCOPE_FULL_DISPLAY
        }
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, ActivityResultCodeMissing)
        val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(EXTRA_RESULT_DATA)
        }
        if (resultCode == ActivityResultCodeMissing || resultData == null || uploadUrl.isBlank()) {
            stopSelf()
            return
        }

        val metrics = resources.displayMetrics
        val sourceWidth = metrics.widthPixels.coerceAtLeast(1)
        val sourceHeight = metrics.heightPixels.coerceAtLeast(1)
        val scale = minOf(1f, MAX_CAPTURE_WIDTH.toFloat() / sourceWidth)
        val width = (sourceWidth * scale).roundToInt().coerceAtLeast(1)
        val height = (sourceHeight * scale).roundToInt().coerceAtLeast(1)
        val density = (metrics.densityDpi * scale).roundToInt().coerceAtLeast(1)

        captureThread = HandlerThread("IngridProctorCapture").also { it.start() }
        val handler = Handler(captureThread!!.looper)
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        imageReader!!.setOnImageAvailableListener({ reader -> onImageAvailable(reader) }, handler)

        val manager = getSystemService(MediaProjectionManager::class.java)
        val projection = manager.getMediaProjection(resultCode, resultData) ?: run {
            stopSelf()
            return
        }
        projection.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                stopSelf()
            }
        }, handler)
        mediaProjection = projection
        virtualDisplay = projection.createVirtualDisplay(
            "IngridStudentProctor",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface,
            null,
            handler,
        )
        ProctorEventReporter.send(
            eventUrl,
            csrfToken,
            cookie,
            "CAPTURE_STARTED",
            metadata = deviceDiagnostics(),
        )
        notifyCaptureState(CAPTURE_STATE_STARTED)
        restorePendingSnapshots()
    }

    private fun onImageAvailable(reader: ImageReader) {
        val image = reader.acquireLatestImage() ?: return
        val now = SystemClock.elapsedRealtime()
        if (now - lastCaptureAt < CAPTURE_INTERVAL_MS) {
            image.close()
            return
        }
        lastCaptureAt = now
        try {
            val jpeg = imageToJpeg(image)
            val capturedAt = Instant.now().toString()
            snapshotBuffer?.save(jpeg, capturedAt)?.let(::enqueueSnapshot)
        } catch (_: Exception) {
            // 다음 3초 촬영에서 다시 시도합니다.
        } finally {
            image.close()
        }
    }

    private fun restorePendingSnapshots() {
        val restored = snapshotBuffer?.restore().orEmpty()
        synchronized(pendingSnapshotsLock) {
            pendingSnapshots.clear()
            pendingSnapshots.addAll(restored)
        }
        if (restored.isNotEmpty()) {
            bufferingSnapshots = true
            notifyTransmissionState(CAPTURE_STATE_BUFFERING, restored.size)
            startUploadWorker()
        }
    }

    private fun enqueueSnapshot(snapshot: EncryptedSnapshotBuffer.Item) {
        synchronized(pendingSnapshotsLock) {
            if (pendingSnapshots.size >= MAX_PENDING_SNAPSHOTS) {
                snapshotBuffer?.delete(pendingSnapshots.removeFirst())
            }
            pendingSnapshots.addLast(snapshot)
            if (bufferingSnapshots) {
                notifyTransmissionState(CAPTURE_STATE_BUFFERING, pendingSnapshots.size)
            }
        }
        startUploadWorker()
    }

    private fun startUploadWorker() {
        if (!uploadWorkerRunning.compareAndSet(false, true)) return
        uploadExecutor.execute {
            try {
                drainPendingSnapshots()
            } finally {
                uploadWorkerRunning.set(false)
                val hasPending = synchronized(pendingSnapshotsLock) { pendingSnapshots.isNotEmpty() }
                if (hasPending && !uploadExecutor.isShutdown) startUploadWorker()
            }
        }
    }

    private fun drainPendingSnapshots() {
        while (!Thread.currentThread().isInterrupted) {
            val pending = synchronized(pendingSnapshotsLock) {
                if (pendingSnapshots.isEmpty()) null else pendingSnapshots.removeFirst()
            } ?: run {
                updateNotification(getString(R.string.capture_notification_body))
                return
            }

            val jpeg = snapshotBuffer?.read(pending)
            if (jpeg == null) {
                snapshotBuffer?.delete(pending)
                updateTransmissionProgress()
                continue
            }
            val status = uploadSnapshotWithRetry(jpeg, pending.capturedAt)
            if (status == HTTP_INSUFFICIENT_STORAGE) {
                stopSelf()
                return
            }
            if (status != null && status !in RETRYABLE_HTTP_STATUS) {
                snapshotBuffer?.delete(pending)
                updateTransmissionProgress()
                continue
            }
            if (status == null || status in RETRYABLE_HTTP_STATUS) {
                synchronized(pendingSnapshotsLock) {
                    if (pendingSnapshots.size >= MAX_PENDING_SNAPSHOTS) {
                        snapshotBuffer?.delete(pendingSnapshots.removeFirst())
                    }
                    pendingSnapshots.addFirst(pending)
                    bufferingSnapshots = true
                    notifyTransmissionState(CAPTURE_STATE_BUFFERING, pendingSnapshots.size)
                }
                updateNotification(getString(R.string.capture_notification_buffering))
                Thread.sleep(QUEUE_RETRY_DELAY_MS)
            }
        }
    }

    private fun updateTransmissionProgress() {
        if (!bufferingSnapshots) return
        val pendingCount = synchronized(pendingSnapshotsLock) { pendingSnapshots.size }
        if (pendingCount == 0) {
            bufferingSnapshots = false
            notifyTransmissionState(CAPTURE_STATE_TRANSMITTING, 0)
        } else {
            notifyTransmissionState(CAPTURE_STATE_BUFFERING, pendingCount)
        }
    }

    private fun imageToJpeg(image: Image): ByteArray {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPadding = rowStride - pixelStride * image.width
        val paddedWidth = image.width + rowPadding / pixelStride
        val padded = Bitmap.createBitmap(paddedWidth, image.height, Bitmap.Config.ARGB_8888)
        padded.copyPixelsFromBuffer(buffer)
        val cropped = Bitmap.createBitmap(padded, 0, 0, image.width, image.height)
        val uploadBitmap = if (externalAppVisible) {
            cropped.copy(Bitmap.Config.ARGB_8888, true).also {
                addExternalAppEvidenceOverlay(it, externalSinceMillis)
            }
        } else {
            cropped
        }
        val output = ByteArrayOutputStream()
        uploadBitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)
        if (uploadBitmap !== cropped) uploadBitmap.recycle()
        cropped.recycle()
        padded.recycle()
        return output.toByteArray()
    }

    private fun addExternalAppEvidenceOverlay(bitmap: Bitmap, detectedAtMillis: Long) {
        val canvas = Canvas(bitmap)
        val width = bitmap.width.toFloat()
        val height = bitmap.height.toFloat()
        val systemMask = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(32, 33, 36)
            style = Paint.Style.FILL
        }
        canvas.drawRect(0f, 0f, width, (height * 0.05f).coerceAtLeast(12f), systemMask)
        canvas.drawRect(0f, height - (height * 0.055f).coerceAtLeast(12f), width, height, systemMask)

        val messageSize = 60f
        val detailSize = 45f
        val messageLineGap = 72f
        val detailLineGap = 28f
        val centerY = height / 2f
        val banner = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = if (captureScope == CAPTURE_SCOPE_APP_ONLY) {
                Color.rgb(8, 8, 10)
            } else {
                Color.argb(204, 8, 8, 10)
            }
            style = Paint.Style.FILL
        }
        canvas.drawRect(0f, 0f, width, height, banner)

        val messagePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textAlign = Paint.Align.CENTER
            textSize = messageSize
            isFakeBoldText = true
        }
        val detailPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(255, 205, 210)
            textAlign = Paint.Align.CENTER
            textSize = detailSize
            isFakeBoldText = true
        }
        val displayName = studentName.ifBlank { "학생" }
        val studentLabel = if (displayName.endsWith("학생")) "${displayName}이" else "${displayName} 학생이"
        val occurredAt = if (detectedAtMillis > 0L) detectedAtMillis else System.currentTimeMillis()
        val timestamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.KOREA).format(Date(occurredAt))
        canvas.drawText(
            "$studentLabel 외부 페이지를",
            width / 2f,
            centerY - messageLineGap,
            messagePaint,
        )
        canvas.drawText(
            "화면에 띄우고 있습니다.",
            width / 2f,
            centerY,
            messagePaint,
        )
        canvas.drawText(
            "외부 앱 이탈 감지  ·  $timestamp",
            width / 2f,
            centerY + messageSize + detailLineGap,
            detailPaint,
        )
    }

    private fun uploadSnapshotWithRetry(jpeg: ByteArray, capturedAt: String): Int? {
        var retrying = false
        try {
            for (attempt in 0 until MAX_UPLOAD_ATTEMPTS) {
                waitForUploadSlot()
                val status = runCatching { uploadSnapshot(jpeg, capturedAt) }.getOrNull()
                if (status == HTTP_INSUFFICIENT_STORAGE) {
                    return status
                }
                if (status != null && status in 200..299 && status !in RETRYABLE_HTTP_STATUS) {
                    return status
                }
                if (status != null && status !in RETRYABLE_HTTP_STATUS) return status
                if (attempt == MAX_UPLOAD_ATTEMPTS - 1) return status

                retrying = true
                updateNotification(getString(R.string.capture_notification_retrying))
                Thread.sleep(RETRY_DELAYS_MS[attempt])
            }
            return null
        } finally {
            if (retrying) updateNotification(getString(R.string.capture_notification_body))
        }
    }

    private fun waitForUploadSlot() {
        val now = SystemClock.elapsedRealtime()
        val waitMillis = (lastUploadStartedAt + MIN_UPLOAD_SPACING_MS - now).coerceAtLeast(0L)
        if (waitMillis > 0L) Thread.sleep(waitMillis)
        lastUploadStartedAt = SystemClock.elapsedRealtime()
    }

    private fun uploadSnapshot(jpeg: ByteArray, capturedAt: String): Int {
        val boundary = "----IngridAndroid${System.currentTimeMillis()}"
        val connection = (URL(uploadUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 20_000
            doOutput = true
            useCaches = false
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            setRequestProperty("X-CSRFToken", csrfToken)
            setRequestProperty("X-Requested-With", "XMLHttpRequest")
            setRequestProperty("Cookie", cookie)
            setRequestProperty("Referer", "https://schoolingrid.com/")
            setRequestProperty("User-Agent", "IngridStudentAndroid/0.1")
        }
        DataOutputStream(connection.outputStream).use { output ->
            fun field(name: String, value: String) {
                output.writeBytes("--$boundary\r\n")
                output.writeBytes("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
                output.write(value.toByteArray(Charsets.UTF_8))
                output.writeBytes("\r\n")
            }
            field("captured_at", capturedAt)
            output.writeBytes("--$boundary\r\n")
            output.writeBytes("Content-Disposition: form-data; name=\"snapshot\"; filename=\"screen-${System.currentTimeMillis()}.jpg\"\r\n")
            output.writeBytes("Content-Type: image/jpeg\r\n\r\n")
            output.write(jpeg)
            output.writeBytes("\r\n--$boundary--\r\n")
        }
        return try {
            connection.responseCode
        } finally {
            connection.disconnect()
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL,
                getString(R.string.capture_notification_title),
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun deviceDiagnostics(): Map<String, String> {
        val appVersion = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
        }.getOrDefault("")
        return mapOf(
            "app_version" to appVersion,
            "android_version" to "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
            "device_model" to "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
            "capture_scope" to captureScope,
        )
    }

    private fun updateNotification(body: String) {
        getSystemService(NotificationManager::class.java).notify(
            NOTIFICATION_ID,
            buildNotification(body),
        )
    }

    private fun buildNotification(
        body: String = getString(R.string.capture_notification_body),
    ) = Notification.Builder(this, NOTIFICATION_CHANNEL)
        .setSmallIcon(android.R.drawable.presence_video_online)
        .setContentTitle(getString(R.string.capture_notification_title))
        .setContentText(body)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .build()

    override fun onDestroy() {
        if (eventUrl.isNotBlank()) {
            ProctorEventReporter.send(eventUrl, csrfToken, cookie, "CAPTURE_STOPPED")
        }
        imageReader?.setOnImageAvailableListener(null, null)
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        captureThread?.quitSafely()
        uploadExecutor.shutdownNow()
        synchronized(pendingSnapshotsLock) { pendingSnapshots.clear() }
        virtualDisplay = null
        imageReader = null
        mediaProjection = null
        captureThread = null
        notifyCaptureState(CAPTURE_STATE_STOPPED, "화면 녹화가 중단되었습니다. 다시 시작해 주세요.")
        super.onDestroy()
    }

    private fun notifyCaptureState(state: String, message: String = "") {
        sendBroadcast(Intent(ACTION_CAPTURE_STATE_CHANGED).apply {
            setPackage(packageName)
            putExtra(EXTRA_CAPTURE_STATE, state)
            putExtra(EXTRA_CAPTURE_MESSAGE, message)
        })
    }

    private fun notifyTransmissionState(state: String, pendingCount: Int) {
        sendBroadcast(Intent(ACTION_CAPTURE_STATE_CHANGED).apply {
            setPackage(packageName)
            putExtra(EXTRA_CAPTURE_STATE, state)
            putExtra(EXTRA_PENDING_COUNT, pendingCount)
        })
    }

    companion object {
        const val ACTION_START = "com.schoolingrid.student.action.START_PROCTOR"
        const val ACTION_STOP = "com.schoolingrid.student.action.STOP_PROCTOR"
        const val ACTION_APP_BACKGROUND = "com.schoolingrid.student.action.APP_BACKGROUND"
        const val ACTION_APP_FOREGROUND = "com.schoolingrid.student.action.APP_FOREGROUND"
        const val ACTION_CAPTURE_STATE_CHANGED = "com.schoolingrid.student.action.CAPTURE_STATE_CHANGED"
        const val CAPTURE_STATE_STARTED = "started"
        const val CAPTURE_STATE_BUFFERING = "buffering"
        const val CAPTURE_STATE_TRANSMITTING = "transmitting"
        const val CAPTURE_STATE_STOPPED = "stopped"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val EXTRA_UPLOAD_URL = "upload_url"
        const val EXTRA_EVENT_URL = "event_url"
        const val EXTRA_CSRF_TOKEN = "csrf_token"
        const val EXTRA_COOKIE = "cookie"
        const val EXTRA_STUDENT_NAME = "student_name"
        const val EXTRA_CAPTURE_SCOPE = "capture_scope"
        const val EXTRA_OCCURRED_AT_MILLIS = "occurred_at_millis"
        const val EXTRA_CAPTURE_STATE = "capture_state"
        const val EXTRA_CAPTURE_MESSAGE = "capture_message"
        const val EXTRA_PENDING_COUNT = "pending_count"
        private const val NOTIFICATION_CHANNEL = "ingrid_proctor_capture"
        private const val NOTIFICATION_ID = 2101
        private const val MAX_CAPTURE_WIDTH = 960
        private const val CAPTURE_INTERVAL_MS = 3_000L
        private const val JPEG_QUALITY = 55
        private const val HTTP_INSUFFICIENT_STORAGE = 507
        private const val MAX_UPLOAD_ATTEMPTS = 3
        private const val MAX_PENDING_SNAPSHOTS = 20
        private const val QUEUE_RETRY_DELAY_MS = 5_000L
        private const val MIN_UPLOAD_SPACING_MS = 2_250L
        private val RETRY_DELAYS_MS = longArrayOf(1_500L, 3_000L)
        // 202 means the server ignored a frame sent inside its two-second throttle window.
        private val RETRYABLE_HTTP_STATUS = setOf(202, 408, 425, 429, 500, 502, 503, 504)
        private const val ActivityResultCodeMissing = Int.MIN_VALUE
        private const val CAPTURE_SCOPE_FULL_DISPLAY = "FULL_DISPLAY"
        private const val CAPTURE_SCOPE_APP_ONLY = "APP_ONLY"
    }

}
