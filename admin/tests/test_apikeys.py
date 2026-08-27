"""Tests for API Key authentication."""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
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
    def test_key_owned_by_inactive_user_is_invalid(self, user):
        """Test the runtime validity check includes the owning account state."""
        user.is_active = False
        api_key = APIKey(
            name="Inactive User Key",
            prefix="inactive",
            key_hash="unused",
            user=user,
        )

        assert api_key.is_active is True
        assert api_key.is_valid is False

    @pytest.mark.django_db
    def test_bulk_user_status_changes_cannot_restore_keys(self, user):
        """Test bulk deactivation and reactivation cannot restore an API key."""
        api_key, plaintext = APIKey.create_key(name="Bulk Revoked Key", user=user)

        User.objects.filter(pk=user.pk).update(is_active=False)
        api_key.refresh_from_db()
        assert api_key.is_active is False

        User.objects.filter(pk=user.pk).update(is_active=True)
        assert APIKey.authenticate(plaintext) is None

    @pytest.mark.django_db
    def test_direct_insert_rejects_inactive_owner(self, user):
        """Test direct ORM inserts cannot create a key for an inactive owner."""
        _, prefix, key_hash = generate_api_key()
        User.objects.filter(pk=user.pk).update(is_active=False)

        with pytest.raises(IntegrityError, match="require an active user"):
            with transaction.atomic():
                APIKey.objects.create(
                    name="Rejected Inactive Owner Key",
                    prefix=prefix,
                    key_hash=key_hash,
                    user=user,
                )

        assert not APIKey.objects.filter(name="Rejected Inactive Owner Key").exists()

    @pytest.mark.django_db
    def test_bulk_reassignment_rejects_inactive_owner(self, user):
        """Test bulk updates cannot reassign an API key to an inactive owner."""
        api_key, _ = APIKey.create_key(name="Owner Reassignment Key", user=user)
        inactive_user = User.objects.create_user(username="inactive-reassignment", is_active=False)

        with pytest.raises(IntegrityError, match="require an active user"):
            with transaction.atomic():
                APIKey.objects.filter(pk=api_key.pk).update(user=inactive_user)

        api_key.refresh_from_db()
        assert api_key.user == user

    @pytest.mark.django_db
    def test_deactivating_user_revokes_all_owned_keys(self, user):
        """Test deactivating a user permanently revokes all of their API keys."""
        first_key, _ = APIKey.create_key(name="First Key", user=user)
        second_key, _ = APIKey.create_key(name="Second Key", user=user)
        other_user = User.objects.create_user(username="other-key-owner")
        other_key, _ = APIKey.create_key(name="Other User Key", user=other_user)

        user.is_active = False
        user.save()

        first_key.refresh_from_db()
        second_key.refresh_from_db()
        other_key.refresh_from_db()
        assert first_key.is_active is False
        assert second_key.is_active is False
        assert other_key.is_active is True

    @pytest.mark.django_db
    def test_reactivating_user_does_not_reactivate_keys(self, user):
        """Test reactivating an account does not restore its revoked API keys."""
        api_key, plaintext = APIKey.create_key(name="Revoked User Key", user=user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        user.is_active = True
        user.save(update_fields=["is_active"])

        api_key.refresh_from_db()
        assert api_key.is_active is False
        assert APIKey.authenticate(plaintext) is None

    @pytest.mark.django_db
    def test_key_creation_rejects_inactive_user(self, user):
        """Test key creation rejects a stale instance of an inactive owner."""
        stale_user = User.objects.get(pk=user.pk)
        User.objects.filter(pk=user.pk).update(is_active=False)
        assert stale_user.is_active is True

        with pytest.raises(ValidationError, match="inactive user"):
            APIKey.create_key(name="Dormant Key", user=stale_user)

        assert not APIKey.objects.filter(name="Dormant Key").exists()

    @pytest.mark.django_db
    def test_revoked_key_cannot_be_reactivated_with_save(self, user):
        """Test saving a revoked key as active is rejected permanently."""
        api_key, plaintext = APIKey.create_key(name="Save Revocation Key", user=user)
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])

        api_key.is_active = True
        with pytest.raises(IntegrityError, match="cannot be reactivated"):
            with transaction.atomic():
                api_key.save(update_fields=["is_active"])

        api_key.refresh_from_db()
        assert api_key.is_active is False
        assert APIKey.authenticate(plaintext) is None

    @pytest.mark.django_db
    def test_revoked_key_cannot_be_reactivated_with_bulk_update(self, user):
        """Test bulk updates cannot reactivate a revoked API key."""
        api_key, plaintext = APIKey.create_key(name="Bulk Revocation Key", user=user)
        APIKey.objects.filter(pk=api_key.pk).update(is_active=False)

        with pytest.raises(IntegrityError, match="cannot be reactivated"):
            with transaction.atomic():
                APIKey.objects.filter(pk=api_key.pk).update(is_active=True)

        api_key.refresh_from_db()
        assert api_key.is_active is False
        assert APIKey.authenticate(plaintext) is None

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
    def test_authenticate_inactive_users_key(self, user):
        """Test authentication rejects a key when its owner is inactive."""
        api_key, plaintext = APIKey.create_key(
            name="Inactive User Auth Key",
            user=user,
        )
        User.objects.filter(pk=user.pk).update(is_active=False)

        result = APIKey.authenticate(plaintext)

        assert result is None
        api_key.refresh_from_db()
        assert api_key.last_used_at is None

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
    def test_api_access_denied_when_key_owner_is_inactive(self, user):
        """Test API access is denied when the key owner is inactive."""
        api_key, plaintext = APIKey.create_key(
            name="Inactive User API Key",
            user=user,
        )
        user.is_active = False
        user.save(update_fields=["is_active"])

        api_key.refresh_from_db()
        assert api_key.is_active is False

        client = Client()
        response = client.get(
            "/api/v1/trustmarktypes",
            HTTP_X_API_KEY=plaintext,
        )

        assert response.status_code == 401

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


class TestAPIKeyAdmin:
    """Tests for irreversible revocation in the Django admin."""

    @pytest.mark.django_db
    def test_existing_key_active_state_is_readonly(self, user):
        """Test the admin cannot expose a control that restores an existing key."""
        from django.contrib import admin

        from apikeys.admin import APIKeyAdmin

        api_key, _ = APIKey.create_key(name="Admin Readonly Key", user=user)
        model_admin = APIKeyAdmin(APIKey, admin.site)
        request = RequestFactory().get("/admin/apikeys/apikey/")

        readonly_fields = model_admin.get_readonly_fields(request=request, obj=api_key)

        assert "is_active" in readonly_fields

    @pytest.mark.django_db
    def test_admin_rejects_key_for_inactive_user(self, auth_client):
        """Test the admin add form rejects an inactive key owner."""
        inactive_user = User.objects.create_user(username="inactive-key-owner", is_active=False)

        response = auth_client.post(
            "/admin/apikeys/apikey/add/",
            data={
                "name": "Rejected Admin Key",
                "user": inactive_user.pk,
                "tenant": "default",
                "is_active": "on",
                "_save": "Save",
            },
        )

        assert response.status_code == 200
        assert b"Cannot create an API key for an inactive user." in response.content
        assert not APIKey.objects.filter(name="Rejected Admin Key").exists()


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
    @pytest.mark.parametrize(
        ("command", "arguments"),
        [
            ("apikey", ["create", "--username", "testuser"]),
            ("create_api_key", ["--username", "testuser"]),
        ],
    )
    def test_create_commands_reject_inactive_user(self, user, command, arguments):
        """Test both creation commands reject inactive key owners without output."""
        from io import StringIO

        from django.core.management import call_command, CommandError

        user.is_active = False
        user.save(update_fields=["is_active"])
        out = StringIO()

        with pytest.raises(CommandError, match="inactive user"):
            call_command(command, *arguments, stdout=out)

        assert out.getvalue() == ""

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
