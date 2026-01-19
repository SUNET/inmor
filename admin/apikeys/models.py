"""API Key model for authentication."""

import hashlib
import secrets

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        tuple: (full_key, prefix, key_hash)
        - full_key: The complete API key to show to user once
        - prefix: First 8 characters for identification
        - key_hash: SHA-256 hash of the key for storage
    """
    full_key = secrets.token_urlsafe(32)
    prefix = full_key[:8]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def hash_api_key(key: str) -> str:
    """Hash an API key for comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKey(models.Model):
    """API Key for programmatic access to the Admin API."""

    name = models.CharField(
        max_length=255,
        help_text="A descriptive name for this API key.",
    )
    prefix = models.CharField(
        max_length=8,
        db_index=True,
        help_text="First 8 characters of the key for identification.",
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hash of the API key.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
        help_text="The user this API key belongs to.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this API key was created.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this API key expires. Leave blank for no expiration.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this API key is active.",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this API key was last used.",
    )

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}...)"

    @property
    def is_valid(self) -> bool:
        """Check if the API key is currently valid."""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def update_last_used(self) -> None:
        """Update the last_used_at timestamp."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    @classmethod
    def create_key(cls, name: str, user: User, expires_at=None) -> tuple["APIKey", str]:
        """Create a new API key.

        Args:
            name: Descriptive name for the key
            user: User who owns the key
            expires_at: Optional expiration datetime

        Returns:
            tuple: (APIKey instance, plaintext key)
            Note: The plaintext key is only available at creation time!
        """
        full_key, prefix, key_hash = generate_api_key()
        api_key = cls.objects.create(
            name=name,
            prefix=prefix,
            key_hash=key_hash,
            user=user,
            expires_at=expires_at,
        )
        return api_key, full_key

    @classmethod
    def authenticate(cls, key: str) -> User | None:
        """Authenticate using an API key.

        Args:
            key: The plaintext API key

        Returns:
            User if authentication succeeds, None otherwise
        """
        key_hash = hash_api_key(key)
        try:
            api_key = cls.objects.select_related("user").get(key_hash=key_hash)
            if api_key.is_valid:
                api_key.update_last_used()
                return api_key.user
        except cls.DoesNotExist:
            pass
        return None
