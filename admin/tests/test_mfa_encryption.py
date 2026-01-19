"""Tests for MFA secret encryption."""

import pytest
from cryptography.fernet import Fernet

from common.mfa_adapter import EncryptedMFAAdapter


class TestEncryptedMFAAdapter:
    """Tests for the EncryptedMFAAdapter class."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def adapter(self, settings, encryption_key):
        """Create an adapter instance with a test key."""
        settings.MFA_ENCRYPTION_KEY = encryption_key
        return EncryptedMFAAdapter()

    def test_encrypt_returns_different_value(self, adapter):
        """Test that encrypt() returns a value different from the input."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = adapter.encrypt(secret)

        assert encrypted != secret
        assert len(encrypted) > len(secret)  # Fernet adds overhead

    def test_decrypt_returns_original(self, adapter):
        """Test that decrypt() returns the original value."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = adapter.encrypt(secret)
        decrypted = adapter.decrypt(encrypted)

        assert decrypted == secret

    def test_encrypted_value_is_base64(self, adapter):
        """Test that encrypted value is valid base64."""
        import base64

        secret = "JBSWY3DPEHPK3PXP"
        encrypted = adapter.encrypt(secret)

        # Should not raise an exception
        base64.urlsafe_b64decode(encrypted)

    def test_secret_not_in_encrypted_value(self, adapter):
        """Test that the plain text secret is not visible in encrypted output."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = adapter.encrypt(secret)

        # The secret should not appear in the encrypted string
        assert secret not in encrypted
        assert secret.lower() not in encrypted.lower()

    def test_same_secret_different_ciphertexts(self, adapter):
        """Test that encrypting the same secret twice gives different ciphertexts."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted1 = adapter.encrypt(secret)
        encrypted2 = adapter.encrypt(secret)

        # Fernet uses random IV, so same plaintext should give different ciphertext
        assert encrypted1 != encrypted2

    def test_different_secrets_both_decrypt_correctly(self, adapter):
        """Test that different secrets can be encrypted and decrypted independently."""
        secret1 = "JBSWY3DPEHPK3PXP"
        secret2 = "GEZDGNBVGY3TQOJQ"

        encrypted1 = adapter.encrypt(secret1)
        encrypted2 = adapter.encrypt(secret2)

        assert adapter.decrypt(encrypted1) == secret1
        assert adapter.decrypt(encrypted2) == secret2

    def test_missing_key_raises_error(self, settings):
        """Test that missing MFA_ENCRYPTION_KEY raises ValueError."""
        settings.MFA_ENCRYPTION_KEY = None
        adapter = EncryptedMFAAdapter()

        with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY must be set"):
            adapter.encrypt("test")

    def test_invalid_key_raises_error(self, settings):
        """Test that invalid encryption key raises an error."""
        settings.MFA_ENCRYPTION_KEY = "not-a-valid-fernet-key"
        adapter = EncryptedMFAAdapter()

        with pytest.raises(Exception):  # Fernet raises ValueError or binascii.Error
            adapter.encrypt("test")


@pytest.mark.django_db
class TestTOTPSecretStorageEncryption:
    """Tests that verify TOTP secrets are stored encrypted in the database."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def setup_mfa_settings(self, settings, encryption_key):
        """Configure MFA settings for tests."""
        settings.MFA_ENCRYPTION_KEY = encryption_key
        settings.MFA_ADAPTER = "common.mfa_adapter.EncryptedMFAAdapter"
        return encryption_key

    @pytest.fixture
    def mfa_user(self, db):
        """Create a test user for MFA tests (without loading fixtures)."""
        from django.contrib.auth.models import User

        user, _ = User.objects.get_or_create(
            username="mfatestuser",
            defaults={
                "email": "mfatest@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.set_password("testpass123")
        user.save()
        return user

    def test_totp_secret_encrypted_in_database(self, setup_mfa_settings, mfa_user):
        """Test that TOTP secret is stored encrypted in the database."""
        from allauth.mfa.models import Authenticator
        from allauth.mfa.totp.internal.auth import TOTP

        # Create a TOTP authenticator
        plain_secret = "JBSWY3DPEHPK3PXP"
        TOTP.activate(mfa_user, plain_secret)

        # Retrieve from database
        auth = Authenticator.objects.get(user=mfa_user, type=Authenticator.Type.TOTP)

        # The stored secret should not be the plain text
        stored_secret = auth.data.get("secret")
        assert stored_secret is not None
        assert stored_secret != plain_secret
        assert plain_secret not in stored_secret

    def test_totp_secret_decrypts_correctly(self, setup_mfa_settings, mfa_user):
        """Test that stored encrypted TOTP secret can be decrypted."""
        from allauth.mfa.models import Authenticator
        from allauth.mfa.totp.internal.auth import TOTP
        from allauth.mfa.utils import decrypt

        # Create a TOTP authenticator
        plain_secret = "JBSWY3DPEHPK3PXP"
        TOTP.activate(mfa_user, plain_secret)

        # Retrieve from database
        auth = Authenticator.objects.get(user=mfa_user, type=Authenticator.Type.TOTP)

        # Decrypt and verify
        decrypted_secret = decrypt(auth.data["secret"])
        assert decrypted_secret == plain_secret

    def test_totp_validation_works_with_encrypted_secret(
        self, setup_mfa_settings, mfa_user, settings
    ):
        """Test that TOTP code validation works with encrypted storage."""
        from allauth.mfa.totp.internal.auth import (
            TOTP,
            hotp_value,
            format_hotp_value,
            validate_totp_code,
        )
        from allauth.mfa.utils import decrypt
        from allauth.mfa.models import Authenticator
        import time

        # Create a TOTP authenticator
        plain_secret = "JBSWY3DPEHPK3PXP"
        TOTP.activate(mfa_user, plain_secret)

        # Retrieve from database and decrypt
        auth = Authenticator.objects.get(user=mfa_user, type=Authenticator.Type.TOTP)
        decrypted_secret = decrypt(auth.data["secret"])

        # Generate a valid code using the plain secret
        counter = int(time.time()) // 30
        code = format_hotp_value(hotp_value(plain_secret, counter))

        # Validate using the decrypted secret (bypassing Redis cache check)
        # This tests that the decrypted secret works for TOTP validation
        assert validate_totp_code(decrypted_secret, code) is True

    def test_raw_database_query_shows_encrypted_secret(self, setup_mfa_settings, mfa_user):
        """Test that raw database query shows encrypted (not plain) secret."""
        from django.db import connection
        from allauth.mfa.totp.internal.auth import TOTP

        # Create a TOTP authenticator
        plain_secret = "MYTESTSECRETKEY123"
        TOTP.activate(mfa_user, plain_secret)

        # Query the database directly
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT data FROM mfa_authenticator WHERE user_id = %s AND type = 'totp'",
                [mfa_user.id],
            )
            row = cursor.fetchone()

        # The raw data should not contain the plain secret
        raw_data = str(row[0]) if row else ""
        assert plain_secret not in raw_data
        assert plain_secret.lower() not in raw_data.lower()
