package com.schoolingrid.student

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.view.View
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    private lateinit var networkStatusText: TextView
    private lateinit var notificationStatusText: TextView
    private lateinit var notificationPermissionButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        findViewById<TextView>(R.id.appVersionText).text = getString(
            R.string.app_version_format,
            currentVersionName(),
        )
        networkStatusText = findViewById(R.id.networkStatusText)
        notificationStatusText = findViewById(R.id.notificationStatusText)
        notificationPermissionButton = findViewById(R.id.notificationPermissionButton)
        notificationPermissionButton.setOnClickListener { requestNotificationPermission() }

        findViewById<Button>(R.id.loginButton).setOnClickListener {
            startActivity(Intent(this, IngridWebActivity::class.java))
        }

        checkForAppUpdate()
    }

    override fun onResume() {
        super.onResume()
        refreshDeviceChecks()
    }

    private fun refreshDeviceChecks() {
        val connected = isInternetValidated()
        networkStatusText.setText(
            if (connected) R.string.device_network_ready else R.string.device_network_unavailable,
        )
        networkStatusText.setTextColor(getColor(if (connected) android.R.color.holo_green_dark else android.R.color.holo_red_dark))

        val notificationGranted = hasNotificationPermission()
        notificationStatusText.setText(
            if (notificationGranted) R.string.device_notification_ready else R.string.device_notification_required,
        )
        notificationStatusText.setTextColor(
            getColor(if (notificationGranted) android.R.color.holo_green_dark else android.R.color.holo_red_dark),
        )
        notificationPermissionButton.visibility = if (notificationGranted) View.GONE else View.VISIBLE
    }

    private fun isInternetValidated(): Boolean {
        val manager = getSystemService(ConnectivityManager::class.java)
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun hasNotificationPermission(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == NOTIFICATION_PERMISSION_REQUEST) refreshDeviceChecks()
    }

    private fun checkForAppUpdate() {
        Thread {
            val updateInfo = runCatching {
                val connection = (URL(VERSION_URL).openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 5_000
                    readTimeout = 5_000
                    useCaches = false
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("User-Agent", "IngridStudentAndroid/${currentVersionName()}")
                }
                try {
                    if (connection.responseCode !in 200..299) return@runCatching null
                    val response = connection.inputStream.bufferedReader().use { it.readText() }
                    val json = JSONObject(response)
                    UpdateInfo(
                        versionCode = json.optLong("version_code", 0L),
                        versionName = json.optString("version_name", ""),
                        downloadUrl = json.optString("download_url", ""),
                        apkAvailable = json.optBoolean("apk_available", false),
                    )
                } finally {
                    connection.disconnect()
                }
            }.getOrNull() ?: return@Thread

            if (
                updateInfo.versionCode > currentVersionCode() &&
                updateInfo.apkAvailable &&
                updateInfo.downloadUrl.startsWith("https://schoolingrid.com/")
            ) {
                runOnUiThread { showUpdateDialog(updateInfo) }
            }
        }.start()
    }

    private fun showUpdateDialog(updateInfo: UpdateInfo) {
        if (isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle(getString(R.string.update_available_title))
            .setMessage(getString(R.string.update_available_body, updateInfo.versionName))
            .setNegativeButton(R.string.update_later, null)
            .setPositiveButton(R.string.update_now) { _, _ ->
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(updateInfo.downloadUrl)))
            }
            .show()
    }

    @Suppress("DEPRECATION")
    private fun currentVersionCode(): Long {
        val packageInfo = packageManager.getPackageInfo(packageName, 0)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.longVersionCode
        } else {
            packageInfo.versionCode.toLong()
        }
    }

    private fun currentVersionName(): String {
        return packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
    }

    private data class UpdateInfo(
        val versionCode: Long,
        val versionName: String,
        val downloadUrl: String,
        val apkAvailable: Boolean,
    )

    companion object {
        private const val VERSION_URL = "https://schoolingrid.com/accounts/student-app/version/"
        private const val NOTIFICATION_PERMISSION_REQUEST = 4101
    }
}
