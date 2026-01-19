"""Custom MFA adapter with encrypted secret storage.

This adapter encrypts TOTP secrets before storing them in the database,
ensuring secrets are not stored in plain text.
"""

from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet
from django.conf import settings


class EncryptedMFAAdapter(DefaultMFAAdapter):
    """MFA adapter that encrypts TOTP secrets using Fernet symmetric encryption.

    Requires MFA_ENCRYPTION_KEY to be set in Django settings. The key must be
    a 32-byte URL-safe base64-encoded string, which can be generated with:

        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    """

    def _get_fernet(self) -> Fernet:
        """Get a Fernet instance using the configured encryption key."""
        key = getattr(settings, "MFA_ENCRYPTION_KEY", None)
        if not key:
            raise ValueError(
                "MFA_ENCRYPTION_KEY must be set in Django settings for encrypted MFA storage"
            )
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    def encrypt(self, text: str) -> str:
        """Encrypt a TOTP secret before storing in the database.

        :param text: Plain text TOTP secret
        :return: Encrypted and base64-encoded secret
        """
        f = self._get_fernet()
        return f.encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt a TOTP secret retrieved from the database.

        :param encrypted_text: Encrypted secret from database
        :return: Decrypted plain text secret
        """
        f = self._get_fernet()
        return f.decrypt(encrypted_text.encode()).decode()
