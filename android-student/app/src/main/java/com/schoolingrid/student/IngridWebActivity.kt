package com.schoolingrid.student

import android.annotation.SuppressLint
import android.app.Activity
import android.app.Activity.RESULT_OK
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Bitmap
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray

class IngridWebActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var captureStatusText: TextView
    private lateinit var projectionManager: MediaProjectionManager
    private var pendingUploadUrl: String? = null
    private var pendingEventUrl: String? = null
    private var pendingCsrfToken: String? = null
    private var pendingStudentName: String? = null
    private var pendingCaptureScope: String = CAPTURE_SCOPE_FULL_DISPLAY
    private var captureActive = false
    private var awaitingCapturePermission = false
    private var reportedBackground = false
    private var eventUrl = ""
    private var eventCsrfToken = ""
    private var eventCookie = ""
    private var captureStateReceiverRegistered = false
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
        projectionManager = getSystemService(MediaProjectionManager::class.java)
        registerCaptureStateReceiver()

        findViewById<ImageButton>(R.id.closeWebButton).setOnClickListener { finish() }

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
        }

        if (savedInstanceState == null) {
            webView.loadUrl(LOGIN_URL)
        } else {
            webView.restoreState(savedInstanceState)
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != SCREEN_CAPTURE_REQUEST) return

        val uploadUrl = pendingUploadUrl
        val requestedEventUrl = pendingEventUrl
        val csrfToken = pendingCsrfToken
        val studentName = pendingStudentName.orEmpty()
        val captureScope = pendingCaptureScope
        pendingUploadUrl = null
        pendingEventUrl = null
        pendingCsrfToken = null
        pendingStudentName = null
        pendingCaptureScope = CAPTURE_SCOPE_FULL_DISPLAY
        awaitingCapturePermission = false

        if (resultCode != RESULT_OK || data == null || uploadUrl == null || requestedEventUrl == null || csrfToken == null) {
            notifyCaptureResult(false, getString(R.string.capture_permission_required))
            return
        }

        val cookie = CookieManager.getInstance().getCookie(INGRID_ORIGIN).orEmpty()
        eventUrl = requestedEventUrl
        eventCsrfToken = csrfToken
        eventCookie = cookie
        val serviceIntent = Intent(this, ProctorCaptureService::class.java).apply {
            action = ProctorCaptureService.ACTION_START
            putExtra(ProctorCaptureService.EXTRA_RESULT_CODE, resultCode)
            putExtra(ProctorCaptureService.EXTRA_RESULT_DATA, data)
            putExtra(ProctorCaptureService.EXTRA_UPLOAD_URL, uploadUrl)
            putExtra(ProctorCaptureService.EXTRA_EVENT_URL, requestedEventUrl)
            putExtra(ProctorCaptureService.EXTRA_CSRF_TOKEN, csrfToken)
            putExtra(ProctorCaptureService.EXTRA_COOKIE, cookie)
            putExtra(ProctorCaptureService.EXTRA_STUDENT_NAME, studentName)
            putExtra(ProctorCaptureService.EXTRA_CAPTURE_SCOPE, captureScope)
        }
        startForegroundService(serviceIntent)
        captureActive = true
        showCaptureStatus(CaptureUiState.RECORDING)
        notifyCaptureResult(true, "")
    }

    override fun onStart() {
        super.onStart()
        if (captureActive && reportedBackground) {
            reportedBackground = false
            updateCaptureContext(false)
            ProctorEventReporter.send(eventUrl, eventCsrfToken, eventCookie, "APP_FOREGROUND")
        }
    }

    override fun onStop() {
        if (captureActive && !awaitingCapturePermission && !isChangingConfigurations) {
            reportedBackground = true
            updateCaptureContext(true)
            ProctorEventReporter.send(eventUrl, eventCsrfToken, eventCookie, "APP_BACKGROUND")
        }
        super.onStop()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
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
            beginScreenCapture(uploadUrl, eventUrl, csrfToken, studentName, captureScope)
        }

        private fun beginScreenCapture(
            uploadUrl: String,
            eventUrl: String,
            csrfToken: String,
            studentName: String,
            captureScope: String = CAPTURE_SCOPE_FULL_DISPLAY,
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
                val normalizedScope = if (captureScope == CAPTURE_SCOPE_APP_ONLY) {
                    CAPTURE_SCOPE_APP_ONLY
                } else {
                    CAPTURE_SCOPE_FULL_DISPLAY
                }
                if (normalizedScope == CAPTURE_SCOPE_APP_ONLY &&
                    Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE
                ) {
                    notifyCaptureResult(false, "이 기기는 인그리드 앱만 감독을 지원하지 않습니다. 교사에게 전체 화면 감독으로 변경을 요청해 주세요.")
                    return@runOnUiThread
                }
                pendingUploadUrl = uploadUrl
                pendingEventUrl = eventUrl
                pendingCsrfToken = csrfToken
                pendingStudentName = studentName.take(40)
                pendingCaptureScope = normalizedScope
                awaitingCapturePermission = true
                val captureIntent = when {
                    normalizedScope == CAPTURE_SCOPE_APP_ONLY && Build.VERSION.SDK_INT >= 37 -> {
                        val config = MediaProjectionConfig.Builder()
                            .setSourceEnabled(MediaProjectionConfig.PROJECTION_SOURCE_DISPLAY, false)
                            .setSourceEnabled(MediaProjectionConfig.PROJECTION_SOURCE_APP, true)
                            .setInitiallySelectedSource(MediaProjectionConfig.PROJECTION_SOURCE_APP)
                            .build()
                        projectionManager.createScreenCaptureIntent(config)
                    }
                    normalizedScope == CAPTURE_SCOPE_APP_ONLY -> {
                        Toast.makeText(
                            this@IngridWebActivity,
                            "공유할 앱에서 인그리드를 선택해 주세요.",
                            Toast.LENGTH_LONG,
                        ).show()
                        projectionManager.createScreenCaptureIntent(
                            MediaProjectionConfig.createConfigForUserChoice(),
                        )
                    }
                    Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE -> {
                        projectionManager.createScreenCaptureIntent(
                            MediaProjectionConfig.createConfigForDefaultDisplay(),
                        )
                    }
                    else -> projectionManager.createScreenCaptureIntent()
                }
                startActivityForResult(
                    captureIntent,
                    SCREEN_CAPTURE_REQUEST,
                )
            }
        }

        @JavascriptInterface
        fun stopScreenCapture() {
            runOnUiThread {
                startService(Intent(this@IngridWebActivity, ProctorCaptureService::class.java).apply {
                    action = ProctorCaptureService.ACTION_STOP
                })
                captureActive = false
                reportedBackground = false
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
        private const val SCREEN_CAPTURE_REQUEST = 4102
        private const val INGRID_ORIGIN = "https://schoolingrid.com"
        private const val LOGIN_URL = "https://schoolingrid.com/accounts/login/"
        private const val CAPTURE_SCOPE_FULL_DISPLAY = "FULL_DISPLAY"
        private const val CAPTURE_SCOPE_APP_ONLY = "APP_ONLY"
    }

    private enum class CaptureUiState {
        RECORDING,
        BUFFERING,
        STOPPED,
    }
}
