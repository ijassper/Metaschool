package com.schoolingrid.student

import android.app.NotificationChannel
import android.app.Notification
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.graphics.Bitmap
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
    private var csrfToken = ""
    private var cookie = ""
    private val uploadInFlight = AtomicBoolean(false)
    private val uploadExecutor = Executors.newSingleThreadExecutor()

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
            ACTION_START -> startProjection(intent)
        }
        return START_NOT_STICKY
    }

    private fun startProjection(intent: Intent) {
        if (mediaProjection != null) return

        startForeground(NOTIFICATION_ID, buildNotification())
        uploadUrl = intent.getStringExtra(EXTRA_UPLOAD_URL).orEmpty()
        csrfToken = intent.getStringExtra(EXTRA_CSRF_TOKEN).orEmpty()
        cookie = intent.getStringExtra(EXTRA_COOKIE).orEmpty()
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
    }

    private fun onImageAvailable(reader: ImageReader) {
        val image = reader.acquireLatestImage() ?: return
        val now = SystemClock.elapsedRealtime()
        if (now - lastCaptureAt < CAPTURE_INTERVAL_MS || !uploadInFlight.compareAndSet(false, true)) {
            image.close()
            return
        }
        lastCaptureAt = now
        try {
            val jpeg = imageToJpeg(image)
            uploadExecutor.execute {
                try {
                    val status = uploadSnapshot(jpeg)
                    if (status == HTTP_INSUFFICIENT_STORAGE) stopSelf()
                } finally {
                    uploadInFlight.set(false)
                }
            }
        } catch (_: Exception) {
            uploadInFlight.set(false)
        } finally {
            image.close()
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
        val output = ByteArrayOutputStream()
        cropped.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)
        cropped.recycle()
        padded.recycle()
        return output.toByteArray()
    }

    private fun uploadSnapshot(jpeg: ByteArray): Int {
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
            field("captured_at", Instant.now().toString())
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

    private fun buildNotification() = Notification.Builder(this, NOTIFICATION_CHANNEL)
        .setSmallIcon(android.R.drawable.presence_video_online)
        .setContentTitle(getString(R.string.capture_notification_title))
        .setContentText(getString(R.string.capture_notification_body))
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .build()

    override fun onDestroy() {
        imageReader?.setOnImageAvailableListener(null, null)
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        captureThread?.quitSafely()
        uploadExecutor.shutdownNow()
        virtualDisplay = null
        imageReader = null
        mediaProjection = null
        captureThread = null
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.schoolingrid.student.action.START_PROCTOR"
        const val ACTION_STOP = "com.schoolingrid.student.action.STOP_PROCTOR"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val EXTRA_UPLOAD_URL = "upload_url"
        const val EXTRA_CSRF_TOKEN = "csrf_token"
        const val EXTRA_COOKIE = "cookie"
        private const val NOTIFICATION_CHANNEL = "ingrid_proctor_capture"
        private const val NOTIFICATION_ID = 2101
        private const val MAX_CAPTURE_WIDTH = 960
        private const val CAPTURE_INTERVAL_MS = 3_000L
        private const val JPEG_QUALITY = 55
        private const val HTTP_INSUFFICIENT_STORAGE = 507
        private const val ActivityResultCodeMissing = Int.MIN_VALUE
    }
}
