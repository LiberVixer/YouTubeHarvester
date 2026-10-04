package com.liberivixer.youtubeharvester.data

import org.junit.Assert.assertEquals
import org.junit.Test

class SecretRecoveryTest {
    @Test fun validSecretIsPreserved() = assertEquals("token", recoverSecret { "token" })
    @Test fun damagedCiphertextDisablesOnlyTheCredential() {
        assertEquals("", recoverSecret { throw javax.crypto.AEADBadTagException() })
        assertEquals("", recoverSecret { throw IllegalArgumentException("bad base64") })
        assertEquals("", recoverSecret { throw java.security.ProviderException("keystore unavailable") })
        assertEquals("", recoverSecret { throw java.io.IOException("keystore service unavailable") })
    }
}
