package com.schoolingrid.student

import android.content.Context

internal object StudentAppUpdateNotice {
    private const val PREFS_NAME = "student_app_updates"
    private const val DISMISSED_VERSION = "dismissed_version_code"
    private const val DISMISSED_AT = "dismissed_at"
    private const val REMIND_AFTER_MS = 24 * 60 * 60 * 1000L

    fun wasRecentlyDismissed(context: Context, versionCode: Long): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val dismissedAt = prefs.getLong(DISMISSED_AT, 0L)
        val elapsed = System.currentTimeMillis() - dismissedAt
        return prefs.getLong(DISMISSED_VERSION, 0L) == versionCode &&
            elapsed in 0 until REMIND_AFTER_MS
    }

    fun dismiss(context: Context, versionCode: Long) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putLong(DISMISSED_VERSION, versionCode)
            .putLong(DISMISSED_AT, System.currentTimeMillis())
            .apply()
    }
}
