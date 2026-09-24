package com.schoolingrid.student

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        findViewById<TextView>(R.id.appVersionText).text = getString(
            R.string.app_version_format,
            currentVersionName(),
        )

        findViewById<Button>(R.id.loginButton).setOnClickListener {
            startActivity(Intent(this, IngridWebActivity::class.java))
        }

        checkForAppUpdate()
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
    }
}
