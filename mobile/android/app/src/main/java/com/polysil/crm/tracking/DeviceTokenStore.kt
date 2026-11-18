package com.polysil.crm.tracking

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.polysil.crm.tracking.core.DeviceToken
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * TRK-009 · The device token on disk, so uploads carry on after the app is closed or the phone
 * restarts. The token is sealed with AES-GCM under a key that never leaves the Android Keystore.
 *
 * The backend suggested `EncryptedSharedPreferences`; androidx.security deprecated it, and its
 * reference points to the Keystore directly, which is what this does with no extra library.
 * A backup restored onto another phone has the sealed text but not the key: it reads as no token,
 * and the next launch hands over a new one.
 */
internal class DeviceTokenStore(context: Context) {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** Keeps the token; false when the Keystore refused, so nothing is kept. */
    fun save(value: DeviceToken): Boolean {
        val sealed = try {
            seal(value.token)
        } catch (error: GeneralSecurityException) {
            clear()
            return false
        }
        return prefs.edit()
            .putString(KEY_TOKEN, sealed)
            .putLong(KEY_EXPIRES_AT, value.expiresAtMillis)
            .putString(KEY_USER_ID, value.userId)
            .commit()
    }

    /** The kept token, or null when there is none or it can't be opened. */
    fun load(): DeviceToken? {
        val sealed = prefs.getString(KEY_TOKEN, null) ?: return null
        val token = open(sealed) ?: return null
        return DeviceToken(
            token = token,
            expiresAtMillis = prefs.getLong(KEY_EXPIRES_AT, 0L),
            userId = prefs.getString(KEY_USER_ID, null).orEmpty(),
        )
    }

    /** Forgets it: signed out, refused by the server, or replaced. */
    fun clear() {
        prefs.edit().clear().commit()
    }

    private fun seal(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.iv + cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(sealed, Base64.NO_WRAP)
    }

    private fun open(sealed: String): String? = try {
        val bytes = Base64.decode(sealed, Base64.NO_WRAP)
        if (bytes.size <= IV_BYTES) {
            null
        } else {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, bytes, 0, IV_BYTES))
            String(cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES), Charsets.UTF_8)
        }
    } catch (error: GeneralSecurityException) {
        null
    } catch (error: IllegalArgumentException) {
        // Not Base64: written by something else.
        null
    }

    /** The app's own AES key in the Keystore, made on first use. */
    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(KEY_BITS)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val FILE = "polysil_device_token"
        const val KEY_TOKEN = "sealed_token"
        const val KEY_EXPIRES_AT = "expires_at"
        const val KEY_USER_ID = "user_id"
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "polysil_device_token_key"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_BITS = 256
        const val IV_BYTES = 12
        const val TAG_BITS = 128
    }
}
