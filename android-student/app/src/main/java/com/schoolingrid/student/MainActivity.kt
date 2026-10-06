package com.schoolingrid.student

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import android.view.View
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

class MainActivity : Activity() {
    private lateinit var networkStatusText: TextView
    private lateinit var notificationStatusText: TextView
    private lateinit var notificationPermissionButton: Button
    private lateinit var loginButton: Button
    private var pendingUpdateFile: File? = null
    private var minimumRequiredUpdate: UpdateInfo? = null
    private var versionCheckPassed = false

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

        loginButton = findViewById(R.id.loginButton)
        loginButton.isEnabled = false
        loginButton.setText(R.string.login_version_checking)
        loginButton.setOnClickListener {
            when {
                versionCheckPassed -> startActivity(Intent(this, IngridWebActivity::class.java))
                minimumRequiredUpdate != null -> showRequiredUpdateDialog(minimumRequiredUpdate!!)
                else -> checkForAppUpdate()
            }
        }

        checkForAppUpdate()
    }

    override fun onResume() {
        super.onResume()
        refreshDeviceChecks()
        pendingUpdateFile?.takeIf { it.isFile && canInstallPackages() }?.let {
            pendingUpdateFile = null
            launchPackageInstaller(it)
        }
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
        versionCheckPassed = false
        minimumRequiredUpdate = null
        loginButton.isEnabled = false
        loginButton.setText(R.string.login_version_checking)
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
                        minimumVersionCode = json.optLong("minimum_version_code", 0L),
                        minimumVersionName = json.optString("minimum_version_name", ""),
                        downloadUrl = json.optString("download_url", ""),
                        apkAvailable = json.optBoolean("apk_available", false),
                    )
                } finally {
                    connection.disconnect()
                }
            }.getOrNull()

            if (updateInfo == null) {
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    loginButton.isEnabled = true
                    loginButton.setText(R.string.login_version_retry)
                    Toast.makeText(this, R.string.update_check_failed, Toast.LENGTH_LONG).show()
                }
                return@Thread
            }

            val trustedDownload = updateInfo.apkAvailable &&
                updateInfo.downloadUrl.startsWith("https://schoolingrid.com/")
            if (currentVersionCode() < updateInfo.minimumVersionCode) {
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    minimumRequiredUpdate = updateInfo
                    loginButton.isEnabled = true
                    loginButton.setText(R.string.login_update_required)
                    showRequiredUpdateDialog(updateInfo)
                }
                return@Thread
            }

            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                versionCheckPassed = true
                loginButton.isEnabled = true
                loginButton.setText(R.string.login_button)
            }

            if (
                updateInfo.versionCode > currentVersionCode() &&
                trustedDownload
            ) {
                runOnUiThread { showUpdateDialog(updateInfo) }
            }
        }.start()
    }

    private fun showRequiredUpdateDialog(updateInfo: UpdateInfo) {
        if (isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle(R.string.update_required_title)
            .setMessage(
                getString(
                    R.string.update_required_body,
                    updateInfo.minimumVersionName.ifBlank { updateInfo.versionName },
                ),
            )
            .setCancelable(false)
            .setPositiveButton(R.string.update_now) { _, _ ->
                if (
                    updateInfo.apkAvailable &&
                    updateInfo.downloadUrl.startsWith("https://schoolingrid.com/")
                ) {
                    downloadAndInstallUpdate(updateInfo)
                } else {
                    Toast.makeText(this, R.string.update_download_failed, Toast.LENGTH_LONG).show()
                }
            }
            .show()
    }

    private fun showUpdateDialog(updateInfo: UpdateInfo) {
        if (isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle(getString(R.string.update_available_title))
            .setMessage(getString(R.string.update_available_body, updateInfo.versionName))
            .setNegativeButton(R.string.update_later, null)
            .setPositiveButton(R.string.update_now) { _, _ ->
                downloadAndInstallUpdate(updateInfo)
            }
            .show()
    }

    private fun downloadAndInstallUpdate(updateInfo: UpdateInfo) {
        val progressDialog = AlertDialog.Builder(this)
            .setTitle(R.string.update_downloading_title)
            .setMessage(getString(R.string.update_downloading_body, updateInfo.versionName))
            .setCancelable(false)
            .create()
        progressDialog.show()

        Thread {
            val apkFile = runCatching { downloadUpdate(updateInfo) }.getOrNull()
            runOnUiThread {
                if (!isFinishing && !isDestroyed) progressDialog.dismiss()
                if (apkFile == null) {
                    Toast.makeText(this, R.string.update_download_failed, Toast.LENGTH_LONG).show()
                    return@runOnUiThread
                }
                if (!isTrustedUpdate(apkFile, updateInfo.versionCode)) {
                    apkFile.delete()
                    Toast.makeText(this, R.string.update_invalid_apk, Toast.LENGTH_LONG).show()
                    return@runOnUiThread
                }
                requestInstallOrLaunch(apkFile)
            }
        }.start()
    }

    private fun downloadUpdate(updateInfo: UpdateInfo): File {
        val safeVersion = updateInfo.versionName.replace(Regex("[^0-9A-Za-z._-]"), "_")
            .ifBlank { updateInfo.versionCode.toString() }
        val updateDir = File(filesDir, "updates").apply { mkdirs() }
        updateDir.listFiles()?.forEach { oldFile ->
            if (oldFile.name.startsWith("ingrid-student-") && oldFile.extension in setOf("apk", "part")) {
                oldFile.delete()
            }
        }
        val finalFile = File(updateDir, "ingrid-student-$safeVersion.apk")
        val partialFile = File(updateDir, "ingrid-student-$safeVersion.apk.part")
        val connection = (URL(updateInfo.downloadUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 60_000
            instanceFollowRedirects = false
            useCaches = false
            setRequestProperty("User-Agent", "IngridStudentAndroid/${currentVersionName()}")
        }
        try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            connection.inputStream.use { input ->
                FileOutputStream(partialFile).use { output -> input.copyTo(output) }
            }
            if (partialFile.length() <= 0L || !partialFile.renameTo(finalFile)) {
                error("APK file could not be finalized")
            }
            return finalFile
        } finally {
            connection.disconnect()
            if (!finalFile.isFile) partialFile.delete()
        }
    }

    private fun requestInstallOrLaunch(apkFile: File) {
        if (canInstallPackages()) {
            launchPackageInstaller(apkFile)
            return
        }
        pendingUpdateFile = apkFile
        Toast.makeText(this, R.string.update_install_permission, Toast.LENGTH_LONG).show()
        startActivity(
            Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:$packageName"),
            ),
        )
    }

    private fun canInstallPackages(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || packageManager.canRequestPackageInstalls()

    private fun launchPackageInstaller(apkFile: File) {
        val apkUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apkFile)
        startActivity(
            Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(apkUri, APK_MIME_TYPE)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            },
        )
    }

    private fun isTrustedUpdate(apkFile: File, expectedVersionCode: Long): Boolean {
        val candidate = packageArchiveInfo(apkFile) ?: return false
        if (candidate.packageName != packageName || versionCode(candidate) != expectedVersionCode) return false
        val installed = packageManager.getPackageInfo(packageName, signingInfoFlag())
        return certificateDigests(candidate) == certificateDigests(installed) && certificateDigests(candidate).isNotEmpty()
    }

    @Suppress("DEPRECATION")
    private fun packageArchiveInfo(apkFile: File): PackageInfo? =
        packageManager.getPackageArchiveInfo(apkFile.absolutePath, signingInfoFlag())

    @Suppress("DEPRECATION")
    private fun signingInfoFlag(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) PackageManager.GET_SIGNING_CERTIFICATES
        else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    private fun certificateDigests(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signingInfo = info.signingInfo ?: return emptySet()
            if (signingInfo.hasMultipleSigners()) signingInfo.apkContentsSigners
            else signingInfo.signingCertificateHistory
        } else {
            info.signatures
        }
        return signatures.orEmpty().map { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                .joinToString("") { byte -> "%02x".format(byte) }
        }.toSet()
    }

    @Suppress("DEPRECATION")
    private fun versionCode(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) info.longVersionCode else info.versionCode.toLong()

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
        val minimumVersionCode: Long,
        val minimumVersionName: String,
        val downloadUrl: String,
        val apkAvailable: Boolean,
    )

    companion object {
        private const val VERSION_URL = "https://schoolingrid.com/accounts/student-app/version/"
        private const val APK_MIME_TYPE = "application/vnd.android.package-archive"
        private const val NOTIFICATION_PERMISSION_REQUEST = 4101
    }
}
