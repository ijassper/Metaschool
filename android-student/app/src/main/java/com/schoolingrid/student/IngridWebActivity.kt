package com.schoolingrid.student

import android.annotation.SuppressLint
import android.app.Activity
import android.app.Activity.RESULT_OK
import android.content.Intent
import android.graphics.Bitmap
import android.media.projection.MediaProjectionManager
import android.net.Uri
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

class IngridWebActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var projectionManager: MediaProjectionManager
    private var pendingUploadUrl: String? = null
    private var pendingCsrfToken: String? = null
    private var captureActive = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ingrid_web)

        webView = findViewById(R.id.ingridWebView)
        progressBar = findViewById(R.id.webProgress)
        projectionManager = getSystemService(MediaProjectionManager::class.java)

        findViewById<ImageButton>(R.id.closeWebButton).setOnClickListener { finish() }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
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
        val csrfToken = pendingCsrfToken
        pendingUploadUrl = null
        pendingCsrfToken = null

        if (resultCode != RESULT_OK || data == null || uploadUrl == null || csrfToken == null) {
            notifyCaptureResult(false, getString(R.string.capture_permission_required))
            return
        }

        val cookie = CookieManager.getInstance().getCookie(INGRID_ORIGIN).orEmpty()
        val serviceIntent = Intent(this, ProctorCaptureService::class.java).apply {
            action = ProctorCaptureService.ACTION_START
            putExtra(ProctorCaptureService.EXTRA_RESULT_CODE, resultCode)
            putExtra(ProctorCaptureService.EXTRA_RESULT_DATA, data)
            putExtra(ProctorCaptureService.EXTRA_UPLOAD_URL, uploadUrl)
            putExtra(ProctorCaptureService.EXTRA_CSRF_TOKEN, csrfToken)
            putExtra(ProctorCaptureService.EXTRA_COOKIE, cookie)
        }
        startForegroundService(serviceIntent)
        captureActive = true
        notifyCaptureResult(true, "")
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

    private inner class AndroidExamBridge {
        @JavascriptInterface
        fun requestScreenCapture(uploadUrl: String, csrfToken: String) {
            runOnUiThread {
                val uri = Uri.parse(uploadUrl)
                if (uri.scheme != "https" || !isIngridHost(uri.host)) {
                    notifyCaptureResult(false, getString(R.string.invalid_capture_url))
                    return@runOnUiThread
                }
                if (captureActive) {
                    notifyCaptureResult(true, "")
                    return@runOnUiThread
                }
                pendingUploadUrl = uploadUrl
                pendingCsrfToken = csrfToken
                startActivityForResult(
                    projectionManager.createScreenCaptureIntent(),
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
            }
        }
    }

    private fun isIngridHost(host: String?): Boolean {
        return host == "schoolingrid.com" || host?.endsWith(".schoolingrid.com") == true
    }

    companion object {
        private const val SCREEN_CAPTURE_REQUEST = 4102
        private const val INGRID_ORIGIN = "https://schoolingrid.com"
        private const val LOGIN_URL = "https://schoolingrid.com/accounts/login/"
    }
}
