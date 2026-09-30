package com.schoolingrid.student

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Bitmap
import android.graphics.Canvas
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.provider.MediaStore
import android.webkit.JavascriptInterface
import android.view.View
import android.view.WindowManager
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.ValueCallback
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import org.json.JSONArray
import java.io.ByteArrayOutputStream
import java.io.File
import java.time.Instant
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.roundToInt

class IngridWebActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var captureStatusText: TextView
    private var captureActive = false
    private var awaitingCapturePermission = false
    private var kioskModeActive = false
    private var kioskExpected = false
    private var pinningLossReported = false
    private var screenshotProtectionActive = false
    private var reportedBackground = false
    private var eventUrl = ""
    private var eventCsrfToken = ""
    private var eventCookie = ""
    private var captureStateReceiverRegistered = false
    private val captureHandler = Handler(Looper.getMainLooper())
    private val captureExecutor = Executors.newSingleThreadExecutor()
    private val frameEncoding = AtomicBoolean(false)
    private var secureModeAttempt = 0
    private var pinningGuideShownForPage = false
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var pendingCameraUri: Uri? = null
    private val captureRunnable = object : Runnable {
        override fun run() {
            if (!captureActive) return
            captureSecureAppFrame()
            captureHandler.postDelayed(this, CAPTURE_INTERVAL_MS)
        }
    }
    private val securityMonitorRunnable = object : Runnable {
        override fun run() {
            if (!captureActive) return
            if (kioskExpected) {
                val manager = getSystemService(ActivityManager::class.java)
                val pinned = manager.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE
                if (!pinned && !pinningLossReported) {
                    pinningLossReported = true
                    kioskModeActive = false
                    ProctorEventReporter.send(
                        eventUrl,
                        eventCsrfToken,
                        eventCookie,
                        "PINNING_RELEASED",
                        getString(R.string.security_pinning_released_message),
                    )
                } else if (pinned && pinningLossReported) {
                    pinningLossReported = false
                    kioskModeActive = true
                    ProctorEventReporter.send(
                        eventUrl,
                        eventCsrfToken,
                        eventCookie,
                        "SECURITY_ACTIVE",
                    )
                }
            }
            captureHandler.postDelayed(this, SECURITY_CHECK_INTERVAL_MS)
        }
    }
    private val captureStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.getStringExtra(ProctorCaptureService.EXTRA_CAPTURE_STATE)) {
                ProctorCaptureService.CAPTURE_STATE_STARTED -> {
                    captureActive = true
                    showCaptureStatus(CaptureUiState.RECORDING)
                    notifyCaptureStateChanged(true, "")
                }
                ProctorCaptureService.CAPTURE_STATE_BUFFERING -> {
                    showCaptureStatus(
                        CaptureUiState.BUFFERING,
                        intent.getIntExtra(ProctorCaptureService.EXTRA_PENDING_COUNT, 0),
                    )
                }
                ProctorCaptureService.CAPTURE_STATE_TRANSMITTING -> {
                    showCaptureStatus(CaptureUiState.RECORDING)
                }
                ProctorCaptureService.CAPTURE_STATE_STOPPED -> {
                    captureActive = false
                    reportedBackground = false
                    leaveSecureMode()
                    showCaptureStatus(CaptureUiState.STOPPED)
                    notifyCaptureStateChanged(
                        false,
                        intent.getStringExtra(ProctorCaptureService.EXTRA_CAPTURE_MESSAGE)
                            ?: "화면 녹화가 중단되었습니다.",
                    )
                }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ingrid_web)

        webView = findViewById(R.id.ingridWebView)
        progressBar = findViewById(R.id.webProgress)
        captureStatusText = findViewById(R.id.captureStatusText)
        registerCaptureStateReceiver()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(
                OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                OnBackInvokedCallback { handleBackNavigation() },
            )
        }

        findViewById<ImageButton>(R.id.closeWebButton).setOnClickListener {
            if (kioskModeActive || awaitingCapturePermission) {
                Toast.makeText(this, R.string.secure_mode_external_blocked, Toast.LENGTH_SHORT).show()
            } else {
                stopExamSession()
                finish()
            }
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = false
            textZoom = 100
            builtInZoomControls = false
            displayZoomControls = false
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = "$userAgentString IngridStudentAndroid/0.1"
        }
        webView.addJavascriptInterface(AndroidExamBridge(), "IngridAndroid")

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                progressBar.visibility = View.VISIBLE
                pinningGuideShownForPage = false
                if (hasActiveExamSession() && !isExamPageUrl(url)) stopExamSession()
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
            }

            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean {
                val uri = request.url
                if (uri.scheme == "https" && isIngridHost(uri.host)) return false
                if (uri.scheme == "http" || uri.scheme == "https") {
                    if (kioskModeActive || awaitingCapturePermission) {
                        Toast.makeText(
                            this@IngridWebActivity,
                            R.string.secure_mode_external_blocked,
                            Toast.LENGTH_SHORT,
                        ).show()
                        return true
                    }
                    startActivity(Intent(Intent.ACTION_VIEW, uri))
                    return true
                }
                return true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress >= 100) View.GONE else View.VISIBLE
            }

            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback

                val photoFile = File.createTempFile("ingrid-note-", ".jpg", cacheDir)
                pendingCameraUri = FileProvider.getUriForFile(
                    this@IngridWebActivity,
                    "${packageName}.fileprovider",
                    photoFile,
                )
                val cameraIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                    putExtra(MediaStore.EXTRA_OUTPUT, pendingCameraUri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                }
                val galleryIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "image/*"
                }
                val chooser = Intent.createChooser(galleryIntent, getString(R.string.note_photo_chooser_title)).apply {
                    putExtra(Intent.EXTRA_INITIAL_INTENTS, arrayOf(cameraIntent))
                }
                return try {
                    startActivityForResult(chooser, NOTE_FILE_CHOOSER_REQUEST)
                    true
                } catch (_: Exception) {
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    pendingCameraUri = null
                    false
                }
            }
        }

        if (savedInstanceState == null) {
            webView.loadUrl(LOGIN_URL)
        } else {
            webView.restoreState(savedInstanceState)
        }
    }

    override fun onStart() {
        super.onStart()
        if (captureActive && reportedBackground) {
            reportedBackground = false
            updateCaptureContext(false)
            ProctorEventReporter.send(eventUrl, eventCsrfToken, eventCookie, "APP_FOREGROUND")
        }
    }

    @Deprecated("Deprecated in Android")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == NOTE_FILE_CHOOSER_REQUEST) {
            val result = if (resultCode != RESULT_OK) {
                null
            } else if (data?.data != null) {
                arrayOf(data.data!!)
            } else {
                pendingCameraUri?.let { arrayOf(it) }
            }
            fileChooserCallback?.onReceiveValue(result)
            fileChooserCallback = null
            pendingCameraUri = null
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun onStop() {
        if (captureActive && !awaitingCapturePermission && !isChangingConfigurations) {
            reportedBackground = true
            updateCaptureContext(true)
            ProctorEventReporter.send(eventUrl, eventCsrfToken, eventCookie, "APP_BACKGROUND")
        }
        super.onStop()
    }

    @SuppressLint("GestureBackNavigation")
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        handleBackNavigation()
    }

    private fun handleBackNavigation() {
        if (kioskModeActive || awaitingCapturePermission) {
            Toast.makeText(this, R.string.secure_mode_external_blocked, Toast.LENGTH_SHORT).show()
            return
        }
        if (webView.canGoBack()) webView.goBack() else finish()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        if (isFinishing) stopExamSession()
        captureHandler.removeCallbacksAndMessages(null)
        captureExecutor.shutdownNow()
        if (captureStateReceiverRegistered) {
            unregisterReceiver(captureStateReceiver)
            captureStateReceiverRegistered = false
        }
        webView.apply {
            stopLoading()
            webChromeClient = null
            destroy()
        }
        super.onDestroy()
    }

    private fun notifyCaptureResult(success: Boolean, message: String) {
        val escaped = message
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
        webView.evaluateJavascript(
            "window.onIngridCaptureResult && window.onIngridCaptureResult(${success}, '$escaped');",
            null,
        )
    }

    private fun notifyCaptureStateChanged(active: Boolean, message: String) {
        val escaped = message
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
        webView.evaluateJavascript(
            "window.onIngridCaptureStateChanged && window.onIngridCaptureStateChanged(${active}, '$escaped');",
            null,
        )
    }

    private fun showCaptureStatus(state: CaptureUiState, pendingCount: Int = 0) {
        captureStatusText.visibility = View.VISIBLE
        when (state) {
            CaptureUiState.RECORDING -> {
                captureStatusText.text = getString(R.string.capture_status_recording)
                captureStatusText.setTextColor(android.graphics.Color.rgb(217, 52, 71))
            }
            CaptureUiState.BUFFERING -> {
                captureStatusText.text = getString(
                    R.string.capture_status_buffering,
                    pendingCount.coerceAtLeast(1),
                )
                captureStatusText.setTextColor(android.graphics.Color.rgb(193, 103, 0))
            }
            CaptureUiState.STOPPED -> {
                captureStatusText.text = getString(R.string.capture_status_stopped)
                captureStatusText.setTextColor(android.graphics.Color.rgb(217, 52, 71))
            }
        }
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    private fun registerCaptureStateReceiver() {
        val filter = IntentFilter(ProctorCaptureService.ACTION_CAPTURE_STATE_CHANGED)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(captureStateReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(captureStateReceiver, filter)
        }
        captureStateReceiverRegistered = true
    }

    private inner class AndroidExamBridge {
        @JavascriptInterface
        fun requestScreenCapture(uploadUrl: String, eventUrl: String, csrfToken: String) {
            runOnUiThread {
                webView.evaluateJavascript(
                    "(() => (document.querySelector('.exam-student-identity')?.textContent || '').trim().split('·')[0].trim())()",
                ) { encodedName ->
                    val pageName = runCatching {
                        JSONArray("[$encodedName]").optString(0).trim()
                    }.getOrDefault("")
                    beginScreenCapture(
                        uploadUrl,
                        eventUrl,
                        csrfToken,
                        pageName.ifBlank { "학생" },
                    )
                }
            }
        }

        @JavascriptInterface
        fun requestScreenCaptureWithStudent(
            uploadUrl: String,
            eventUrl: String,
            csrfToken: String,
            studentName: String,
        ) {
            beginScreenCapture(uploadUrl, eventUrl, csrfToken, studentName, CAPTURE_SCOPE_FULL_DISPLAY)
        }

        @JavascriptInterface
        fun requestConfiguredScreenCapture(
            uploadUrl: String,
            eventUrl: String,
            csrfToken: String,
            studentName: String,
            captureScope: String,
        ) {
            beginScreenCapture(
                uploadUrl,
                eventUrl,
                csrfToken,
                studentName,
                captureScope,
                EXAM_MODE_CLOSED_LOCK,
            )
        }

        @JavascriptInterface
        fun requestExamScreenCapture(
            uploadUrl: String,
            eventUrl: String,
            csrfToken: String,
            studentName: String,
            captureScope: String,
            examMode: String,
        ) {
            beginScreenCapture(uploadUrl, eventUrl, csrfToken, studentName, captureScope, examMode)
        }

        @JavascriptInterface
        fun requestExamSecurity(examMode: String) {
            runOnUiThread {
                val normalizedExamMode = normalizeExamMode(examMode)
                val requiresKiosk = normalizedExamMode.startsWith("CLOSED_")
                val requiresScreenshotProtection = requiresKiosk || normalizedExamMode.endsWith("_LOCK")
                screenshotProtectionActive = requiresScreenshotProtection
                if (requiresScreenshotProtection) {
                    window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                } else {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                }
                if (!requiresKiosk) {
                    kioskModeActive = false
                    notifyExamSecurityResult(true, "")
                    return@runOnUiThread
                }
                awaitingCapturePermission = true
                runCatching { startLockTask() }.onFailure {
                    failStandaloneSecurityStart()
                    return@runOnUiThread
                }
                secureModeAttempt = 0
                waitForStandaloneSecureMode()
            }
        }

        @JavascriptInterface
        fun showAppPinningGuide() {
            runOnUiThread {
                if (pinningGuideShownForPage || isFinishing) return@runOnUiThread
                pinningGuideShownForPage = true
                AlertDialog.Builder(this@IngridWebActivity)
                    .setTitle(R.string.pinning_guide_title)
                    .setMessage(R.string.pinning_guide_message)
                    .setPositiveButton(R.string.pinning_guide_open_settings) { _, _ ->
                        val intent = Intent(Settings.ACTION_SECURITY_SETTINGS)
                        runCatching { startActivity(intent) }.onFailure {
                            startActivity(Intent(Settings.ACTION_SETTINGS))
                        }
                    }
                    .setNegativeButton(R.string.pinning_guide_already_enabled, null)
                    .show()
            }
        }

        private fun beginScreenCapture(
            uploadUrl: String,
            eventUrl: String,
            csrfToken: String,
            studentName: String,
            captureScope: String = CAPTURE_SCOPE_FULL_DISPLAY,
            examMode: String = EXAM_MODE_CLOSED_LOCK,
        ) {
            runOnUiThread {
                val uri = Uri.parse(uploadUrl)
                val eventUri = Uri.parse(eventUrl)
                if (uri.scheme != "https" || !isIngridHost(uri.host) ||
                    eventUri.scheme != "https" || !isIngridHost(eventUri.host)
                ) {
                    notifyCaptureResult(false, getString(R.string.invalid_capture_url))
                    return@runOnUiThread
                }
                if (captureActive) {
                    notifyCaptureResult(true, "")
                    return@runOnUiThread
                }
                val normalizedExamMode = normalizeExamMode(examMode)
                val requiresKiosk = normalizedExamMode.startsWith("CLOSED_")
                val requiresScreenshotProtection = requiresKiosk || normalizedExamMode.endsWith("_LOCK")
                screenshotProtectionActive = requiresScreenshotProtection
                if (requiresScreenshotProtection) {
                    window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                } else {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                }

                if (!requiresKiosk) {
                    awaitingCapturePermission = false
                    kioskModeActive = false
                    startSecureCapture(uploadUrl, eventUrl, csrfToken, studentName.take(40), false)
                    return@runOnUiThread
                }

                awaitingCapturePermission = true
                runCatching { startLockTask() }.onFailure {
                    failSecureModeStart()
                    return@runOnUiThread
                }
                secureModeAttempt = 0
                waitForSecureMode(uploadUrl, eventUrl, csrfToken, studentName.take(40))
            }
        }

        @JavascriptInterface
        fun stopScreenCapture() {
            runOnUiThread {
                stopExamSession()
            }
        }
    }

    private fun hasActiveExamSession(): Boolean {
        return captureActive || kioskModeActive || screenshotProtectionActive || awaitingCapturePermission
    }

    private fun isExamPageUrl(url: String): Boolean {
        val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return false
        return isIngridHost(uri.host) && uri.path.orEmpty().startsWith(EXAM_PATH_PREFIX)
    }

    private fun stopExamSession() {
        if (captureActive) {
            startService(Intent(this, ProctorCaptureService::class.java).apply {
                action = ProctorCaptureService.ACTION_STOP
            })
        }
        captureActive = false
        reportedBackground = false
        kioskExpected = false
        pinningLossReported = false
        leaveSecureMode()
    }

    private fun waitForSecureMode(
        uploadUrl: String,
        requestedEventUrl: String,
        csrfToken: String,
        studentName: String,
    ) {
        val manager = getSystemService(ActivityManager::class.java)
        if (manager.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE) {
            startSecureCapture(uploadUrl, requestedEventUrl, csrfToken, studentName, true)
            return
        }
        if (++secureModeAttempt >= SECURE_MODE_CHECK_LIMIT) {
            failSecureModeStart()
            return
        }
        captureHandler.postDelayed({
            waitForSecureMode(uploadUrl, requestedEventUrl, csrfToken, studentName)
        }, SECURE_MODE_CHECK_INTERVAL_MS)
    }

    private fun waitForStandaloneSecureMode() {
        val manager = getSystemService(ActivityManager::class.java)
        if (manager.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE) {
            awaitingCapturePermission = false
            kioskModeActive = true
            notifyExamSecurityResult(true, "")
            return
        }
        if (++secureModeAttempt >= SECURE_MODE_CHECK_LIMIT) {
            failStandaloneSecurityStart()
            return
        }
        captureHandler.postDelayed(
            { waitForStandaloneSecureMode() },
            SECURE_MODE_CHECK_INTERVAL_MS,
        )
    }

    private fun startSecureCapture(
        uploadUrl: String,
        requestedEventUrl: String,
        csrfToken: String,
        studentName: String,
        kioskEnabled: Boolean,
    ) {
        awaitingCapturePermission = false
        kioskModeActive = kioskEnabled
        kioskExpected = kioskEnabled
        pinningLossReported = false
        val cookie = CookieManager.getInstance().getCookie(INGRID_ORIGIN).orEmpty()
        eventUrl = requestedEventUrl
        eventCsrfToken = csrfToken
        eventCookie = cookie
        captureActive = true
        startForegroundService(Intent(this, ProctorCaptureService::class.java).apply {
            action = ProctorCaptureService.ACTION_START_SECURE
            putExtra(ProctorCaptureService.EXTRA_UPLOAD_URL, uploadUrl)
            putExtra(ProctorCaptureService.EXTRA_EVENT_URL, requestedEventUrl)
            putExtra(ProctorCaptureService.EXTRA_CSRF_TOKEN, csrfToken)
            putExtra(ProctorCaptureService.EXTRA_COOKIE, cookie)
            putExtra(ProctorCaptureService.EXTRA_STUDENT_NAME, studentName)
            putExtra(ProctorCaptureService.EXTRA_CAPTURE_SCOPE, CAPTURE_SCOPE_SECURE_APP)
        })
        showCaptureStatus(CaptureUiState.RECORDING)
        captureHandler.removeCallbacks(captureRunnable)
        captureHandler.post(captureRunnable)
        captureHandler.removeCallbacks(securityMonitorRunnable)
        captureHandler.post(securityMonitorRunnable)
        ProctorEventReporter.send(
            eventUrl,
            eventCsrfToken,
            eventCookie,
            if (kioskEnabled) "SECURITY_ACTIVE" else "SECURITY_NOT_REQUIRED",
        )
        notifyCaptureResult(true, "")
    }

    private fun failSecureModeStart() {
        awaitingCapturePermission = false
        captureActive = false
        leaveSecureMode()
        notifyCaptureResult(false, getString(R.string.secure_mode_required))
    }

    private fun failStandaloneSecurityStart() {
        awaitingCapturePermission = false
        leaveSecureMode()
        notifyExamSecurityResult(false, getString(R.string.secure_mode_required))
    }

    private fun notifyExamSecurityResult(success: Boolean, message: String) {
        val escaped = message
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
        webView.evaluateJavascript(
            "window.onIngridExamSecurityResult && window.onIngridExamSecurityResult(${success}, '$escaped');",
            null,
        )
    }

    private fun leaveSecureMode() {
        captureHandler.removeCallbacks(captureRunnable)
        captureHandler.removeCallbacks(securityMonitorRunnable)
        if (kioskModeActive || awaitingCapturePermission) runCatching { stopLockTask() }
        if (screenshotProtectionActive) window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        kioskModeActive = false
        kioskExpected = false
        pinningLossReported = false
        screenshotProtectionActive = false
        awaitingCapturePermission = false
    }

    private fun normalizeExamMode(examMode: String): String {
        return when (examMode) {
            EXAM_MODE_CLOSED_LOCK,
            EXAM_MODE_CLOSED_FREE,
            EXAM_MODE_OPEN_LOCK,
            EXAM_MODE_OPEN_FREE
            -> examMode
            else -> EXAM_MODE_CLOSED_LOCK
        }
    }

    private fun captureSecureAppFrame() {
        if (!frameEncoding.compareAndSet(false, true)) return
        val root = findViewById<View>(android.R.id.content)
        val sourceWidth = root.width
        val sourceHeight = root.height
        if (sourceWidth <= 0 || sourceHeight <= 0) {
            frameEncoding.set(false)
            return
        }
        val scale = minOf(1f, MAX_CAPTURE_WIDTH.toFloat() / sourceWidth)
        val bitmap = Bitmap.createBitmap(
            (sourceWidth * scale).roundToInt().coerceAtLeast(1),
            (sourceHeight * scale).roundToInt().coerceAtLeast(1),
            Bitmap.Config.ARGB_8888,
        )
        Canvas(bitmap).apply {
            scale(scale, scale)
            root.draw(this)
        }
        captureExecutor.execute {
            try {
                val output = ByteArrayOutputStream()
                bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)
                val jpeg = output.toByteArray()
                if (jpeg.size <= MAX_SECURE_FRAME_BYTES && captureActive) {
                    startService(Intent(this, ProctorCaptureService::class.java).apply {
                        action = ProctorCaptureService.ACTION_ENQUEUE_SECURE_FRAME
                        putExtra(ProctorCaptureService.EXTRA_JPEG, jpeg)
                        putExtra(ProctorCaptureService.EXTRA_CAPTURED_AT, Instant.now().toString())
                    })
                }
            } finally {
                bitmap.recycle()
                frameEncoding.set(false)
            }
        }
    }

    private fun updateCaptureContext(isAway: Boolean) {
        startService(Intent(this, ProctorCaptureService::class.java).apply {
            action = if (isAway) {
                ProctorCaptureService.ACTION_APP_BACKGROUND
            } else {
                ProctorCaptureService.ACTION_APP_FOREGROUND
            }
            putExtra(ProctorCaptureService.EXTRA_OCCURRED_AT_MILLIS, System.currentTimeMillis())
        })
    }

    private fun isIngridHost(host: String?): Boolean {
        return host == "schoolingrid.com" || host?.endsWith(".schoolingrid.com") == true
    }

    companion object {
        private const val INGRID_ORIGIN = "https://schoolingrid.com"
        private const val LOGIN_URL = "https://schoolingrid.com/accounts/login/"
        private const val EXAM_PATH_PREFIX = "/activities/take/"
        private const val CAPTURE_SCOPE_FULL_DISPLAY = "FULL_DISPLAY"
        private const val CAPTURE_SCOPE_APP_ONLY = "APP_ONLY"
        private const val CAPTURE_SCOPE_SECURE_APP = "SECURE_APP"
        private const val CAPTURE_INTERVAL_MS = 3_000L
        private const val NOTE_FILE_CHOOSER_REQUEST = 4107
        private const val SECURE_MODE_CHECK_INTERVAL_MS = 500L
        private const val SECURITY_CHECK_INTERVAL_MS = 1_000L
        private const val SECURE_MODE_CHECK_LIMIT = 30
        private const val MAX_CAPTURE_WIDTH = 960
        private const val JPEG_QUALITY = 55
        private const val MAX_SECURE_FRAME_BYTES = 480_000
        private const val EXAM_MODE_CLOSED_LOCK = "CLOSED_LOCK"
        private const val EXAM_MODE_CLOSED_FREE = "CLOSED_FREE"
        private const val EXAM_MODE_OPEN_LOCK = "OPEN_LOCK"
        private const val EXAM_MODE_OPEN_FREE = "OPEN_FREE"
    }

    private enum class CaptureUiState {
        RECORDING,
        BUFFERING,
        STOPPED,
    }
}
