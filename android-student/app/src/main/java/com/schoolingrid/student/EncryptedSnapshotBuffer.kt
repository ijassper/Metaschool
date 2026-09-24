package com.schoolingrid.student

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.File
import java.nio.ByteBuffer
import java.security.KeyStore
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class EncryptedSnapshotBuffer(
    context: Context,
    uploadUrl: String,
    private val maxItems: Int,
) {
    data class Item(
        val file: File,
        val capturedAt: String,
    )

    private val root = File(context.filesDir, ROOT_DIRECTORY)
    private val sessionDirectory = File(root, sha256(uploadUrl))

    init {
        sessionDirectory.mkdirs()
        removeExpiredSessions()
        trimToLimit()
    }

    @Synchronized
    fun restore(): List<Item> = snapshotFiles()
        .mapNotNull { file ->
            val capturedAtMillis = file.name.substringBefore('-').toLongOrNull() ?: run {
                file.delete()
                return@mapNotNull null
            }
            Item(file, Instant.ofEpochMilli(capturedAtMillis).toString())
        }

    @Synchronized
    fun save(jpeg: ByteArray, capturedAt: String): Item? = runCatching {
        val capturedAtMillis = Instant.parse(capturedAt).toEpochMilli()
        val finalFile = File(sessionDirectory, "$capturedAtMillis-${UUID.randomUUID()}$FILE_SUFFIX")
        val temporaryFile = File(sessionDirectory, "${finalFile.name}.tmp")
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, secretKey())
        }
        val encrypted = cipher.doFinal(jpeg)
        val payload = ByteBuffer.allocate(1 + cipher.iv.size + encrypted.size)
            .put(cipher.iv.size.toByte())
            .put(cipher.iv)
            .put(encrypted)
            .array()
        temporaryFile.writeBytes(payload)
        check(temporaryFile.renameTo(finalFile))
        trimToLimit()
        Item(finalFile, capturedAt)
    }.getOrNull()

    fun read(item: Item): ByteArray? = runCatching {
        val payload = item.file.readBytes()
        val buffer = ByteBuffer.wrap(payload)
        val ivSize = buffer.get().toInt() and 0xff
        require(ivSize in 12..32 && buffer.remaining() > ivSize)
        val iv = ByteArray(ivSize).also(buffer::get)
        val encrypted = ByteArray(buffer.remaining()).also(buffer::get)
        Cipher.getInstance(TRANSFORMATION).run {
            init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
            doFinal(encrypted)
        }
    }.getOrNull()

    fun delete(item: Item) {
        item.file.delete()
    }

    private fun snapshotFiles(): List<File> = sessionDirectory
        .listFiles { file -> file.isFile && file.name.endsWith(FILE_SUFFIX) }
        .orEmpty()
        .sortedBy(File::getName)

    private fun trimToLimit() {
        val files = snapshotFiles()
        files.take((files.size - maxItems).coerceAtLeast(0)).forEach(File::delete)
    }

    private fun removeExpiredSessions() {
        val cutoff = System.currentTimeMillis() - MAX_RETENTION_MS
        root.listFiles { file -> file.isDirectory }
            .orEmpty()
            .filter { it != sessionDirectory && it.lastModified() < cutoff }
            .forEach { it.deleteRecursively() }
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .build(),
            )
            generateKey()
        }
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    companion object {
        private const val ROOT_DIRECTORY = "proctor_pending"
        private const val FILE_SUFFIX = ".snapshot"
        private const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        private const val KEY_ALIAS = "ingrid_proctor_snapshot_buffer_v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val MAX_RETENTION_MS = 24L * 60L * 60L * 1_000L
    }
}
