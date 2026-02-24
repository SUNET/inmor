"""Tests for API Key authentication."""

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apikeys.models import APIKey, generate_api_key, hash_api_key


class TestAPIKeyModel:
    """Tests for the APIKey model."""

    def test_generate_api_key(self):
        """Test API key generation."""
        full_key, prefix, key_hash = generate_api_key()

        assert len(full_key) > 20  # Should be a long random string
        assert len(prefix) == 8  # First 8 chars
        assert full_key.startswith(prefix)
        assert len(key_hash) == 64  # SHA-256 hex digest

    def test_hash_api_key(self):
        """Test API key hashing is consistent."""
        key = "test_key_12345"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)

        assert hash1 == hash2
        assert len(hash1) == 64

    @pytest.mark.django_db
    def test_create_key(self, user):
        """Test creating an API key."""
        api_key, plaintext = APIKey.create_key(
            name="Test Key",
            user=user,
        )

        assert api_key.name == "Test Key"
        assert api_key.user == user
        assert api_key.is_active is True
        assert api_key.is_valid is True
        assert len(api_key.prefix) == 8
        assert plaintext.startswith(api_key.prefix)

    @pytest.mark.django_db
    def test_create_key_with_expiry(self, user):
        """Test creating an API key with expiration."""
        expires = timezone.now() + timedelta(days=30)
        api_key, plaintext = APIKey.create_key(
            name="Expiring Key",
            user=user,
            expires_at=expires,
        )

        assert api_key.expires_at == expires
        assert api_key.is_valid is True

    @pytest.mark.django_db
    def test_expired_key_is_invalid(self, user):
        """Test that expired keys are invalid."""
        expires = timezone.now() - timedelta(days=1)  # Already expired
        api_key, _ = APIKey.create_key(
            name="Expired Key",
            user=user,
            expires_at=expires,
        )

        assert api_key.is_valid is False

    @pytest.mark.django_db
    def test_deactivated_key_is_invalid(self, user):
        """Test that deactivated keys are invalid."""
        api_key, _ = APIKey.create_key(
            name="Deactivated Key",
            user=user,
        )
        api_key.is_active = False
        api_key.save()

        assert api_key.is_valid is False

    @pytest.mark.django_db
    def test_authenticate_valid_key(self, user):
        """Test authentication with a valid API key."""
        api_key, plaintext = APIKey.create_key(
            name="Auth Test Key",
            user=user,
        )

        result = APIKey.authenticate(plaintext)
        assert result is not None
        authenticated_user, returned_key = result
        assert authenticated_user == user
        assert returned_key.pk == api_key.pk

    @pytest.mark.django_db
    def test_authenticate_invalid_key(self, user):
        """Test authentication with an invalid API key."""
        result = APIKey.authenticate("invalid_key_123")
        assert result is None

    @pytest.mark.django_db
    def test_authenticate_expired_key(self, user):
        """Test authentication with an expired API key."""
        expires = timezone.now() - timedelta(days=1)
        _, plaintext = APIKey.create_key(
            name="Expired Auth Key",
            user=user,
            expires_at=expires,
        )

        result = APIKey.authenticate(plaintext)
        assert result is None

    @pytest.mark.django_db
    def test_authenticate_deactivated_key(self, user):
        """Test authentication with a deactivated API key."""
        api_key, plaintext = APIKey.create_key(
            name="Deactivated Auth Key",
            user=user,
        )
        api_key.is_active = False
        api_key.save()

        result = APIKey.authenticate(plaintext)
        assert result is None

    @pytest.mark.django_db
    def test_last_used_updated(self, user):
        """Test that last_used_at is updated on authentication."""
        api_key, plaintext = APIKey.create_key(
            name="Last Used Key",
            user=user,
        )
        assert api_key.last_used_at is None

        APIKey.authenticate(plaintext)

        api_key.refresh_from_db()
        assert api_key.last_used_at is not None

    @pytest.mark.django_db
    def test_tenant_default(self, user):
        """Test that tenant defaults to 'default'."""
        api_key, _ = APIKey.create_key(name="Default Tenant Key", user=user)
        assert api_key.tenant == "default"

    @pytest.mark.django_db
    def test_tenant_custom(self, user):
        """Test creating a key with a custom tenant."""
        api_key, _ = APIKey.create_key(name="Custom Tenant Key", user=user, tenant="acme-corp")
        assert api_key.tenant == "acme-corp"

    @pytest.mark.django_db
    def test_authenticate_returns_tenant(self, user):
        """Test that authenticate returns the key with correct tenant."""
        api_key, plaintext = APIKey.create_key(
            name="Tenant Auth Key", user=user, tenant="my-tenant"
        )

        result = APIKey.authenticate(plaintext)
        assert result is not None
        _, returned_key = result
        assert returned_key.tenant == "my-tenant"


class TestAPIKeyAuthentication:
    """Tests for API Key authentication via API endpoints."""

    @pytest.mark.django_db
    def test_api_access_with_valid_key(self, user):
        """Test API access with a valid API key."""
        _, plaintext = APIKey.create_key(
            name="API Access Key",
            user=user,
        )

        client = Client()
        response = client.get(
            "/api/v1/trustmarktypes",
            HTTP_X_API_KEY=plaintext,
        )

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_api_access_with_invalid_key(self, db):
        """Test API access with an invalid API key."""
        client = Client()
        response = client.get(
            "/api/v1/trustmarktypes",
            HTTP_X_API_KEY="invalid_key_123",
        )

        assert response.status_code == 401

    @pytest.mark.django_db
    def test_api_access_without_key(self, db):
        """Test API access without any authentication."""
        client = Client()
        response = client.get("/api/v1/trustmarktypes")

        assert response.status_code == 401

    @pytest.mark.django_db
    def test_api_post_with_key(self, user):
        """Test POST request with API key."""
        _, plaintext = APIKey.create_key(
            name="POST Test Key",
            user=user,
        )

        client = Client()
        data = {"tmtype": "https://test.example.com/apikey_test_trustmark"}
        response = client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )

        assert response.status_code == 201

    @pytest.mark.django_db
    def test_session_auth_still_works(self, auth_client):
        """Test that session authentication still works."""
        response = auth_client.get("/api/v1/trustmarktypes")
        assert response.status_code == 200


class TestAPIKeyManagementCommand:
    """Tests for the apikey management command."""

    @pytest.mark.django_db
    def test_apikey_create(self, user):
        """Test creating an API key via management command."""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command(
            "apikey", "create", "--username", "testuser", "--key-name", "test key", stdout=out
        )
        plaintext = out.getvalue().strip()

        assert len(plaintext) > 20
        key = APIKey.objects.get(name="test key", user=user)
        assert key.is_active is True
        assert key.tenant == "default"
        assert plaintext.startswith(key.prefix)

    @pytest.mark.django_db
    def test_apikey_create_with_tenant(self, user):
        """Test creating an API key with --tenant via management command."""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command(
            "apikey",
            "create",
            "--username",
            "testuser",
            "--key-name",
            "tenant key",
            "--tenant",
            "acme-corp",
            stdout=out,
        )
        plaintext = out.getvalue().strip()

        assert len(plaintext) > 20
        key = APIKey.objects.get(name="tenant key", user=user)
        assert key.tenant == "acme-corp"

    @pytest.mark.django_db
    def test_apikey_create_user_not_found(self, db):
        """Test creating an API key for a non-existent user."""
        from io import StringIO

        from django.core.management import call_command, CommandError

        with pytest.raises(CommandError, match="does not exist"):
            call_command("apikey", "create", "--username", "nobody", stdout=StringIO())

    @pytest.mark.django_db
    def test_apikey_list(self, user):
        """Test listing API keys for a user."""
        from io import StringIO

        from django.core.management import call_command

        APIKey.create_key(name="key-one", user=user)
        APIKey.create_key(name="key-two", user=user)

        out = StringIO()
        call_command("apikey", "list", "--username", "testuser", stdout=out)
        output = out.getvalue()

        assert "key-one" in output
        assert "key-two" in output
        assert "Tenant" in output  # Header includes tenant column
        assert "default" in output  # Default tenant value shown

    @pytest.mark.django_db
    def test_apikey_list_all(self, user):
        """Test listing all API keys across users."""
        from io import StringIO

        from django.contrib.auth.models import User
        from django.core.management import call_command

        user2 = User.objects.create_user(username="otheruser", password="pass123")
        APIKey.create_key(name="key-for-test", user=user)
        APIKey.create_key(name="key-for-other", user=user2)

        out = StringIO()
        call_command("apikey", "list", "--all", stdout=out)
        output = out.getvalue()

        assert "key-for-test" in output
        assert "key-for-other" in output
        assert "testuser" in output
        assert "otheruser" in output

    @pytest.mark.django_db
    def test_apikey_list_empty(self, user):
        """Test listing keys when user has none."""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("apikey", "list", "--username", "testuser", stdout=out)
        output = out.getvalue()

        assert "No API keys found" in output

    @pytest.mark.django_db
    def test_apikey_revoke(self, user):
        """Test revoking an API key by name."""
        from io import StringIO

        from django.core.management import call_command

        APIKey.create_key(name="revoke-me", user=user)

        out = StringIO()
        call_command(
            "apikey", "revoke", "--username", "testuser", "--key-name", "revoke-me", stdout=out
        )
        output = out.getvalue()

        assert "Revoked 1 key(s)" in output
        key = APIKey.objects.get(name="revoke-me", user=user)
        assert key.is_active is False

    @pytest.mark.django_db
    def test_apikey_revoke_not_found(self, user):
        """Test revoking a non-existent key."""
        from io import StringIO

        from django.core.management import call_command, CommandError

        with pytest.raises(CommandError, match="No active API key"):
            call_command(
                "apikey",
                "revoke",
                "--username",
                "testuser",
                "--key-name",
                "nope",
                stdout=StringIO(),
            )
