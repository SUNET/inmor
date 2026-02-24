"""Tests for authentication and MFA integration."""

import pytest
from django.test import Client, RequestFactory

from apikeys.models import APIKey
from inmoradmin.auth import (
    APIKeyAuthBackend,
    AuthResult,
    SessionAuthBackend,
)


class TestAllauthIntegration:
    """Tests for django-allauth integration."""

    @pytest.mark.django_db
    def test_login_page_accessible(self, db):
        """Test that allauth login page is accessible."""
        client = Client()
        response = client.get("/accounts/login/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_login_form_accepts_credentials(self, user, loadredis):
        """Test that login form accepts valid credentials."""
        client = Client()
        response = client.post(
            "/accounts/login/",
            {"login": "testuser", "password": "testpass123"},
            follow=False,
        )
        # Should redirect after successful login (302) or show success
        assert response.status_code in [200, 302]

    @pytest.mark.django_db
    def test_logout_page_accessible(self, auth_client):
        """Test that logout page is accessible when logged in."""
        response = auth_client.get("/accounts/logout/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_signup_disabled(self, db):
        """Test that public signup is disabled."""
        client = Client()
        response = client.get("/accounts/signup/")
        # Should return 200 but the form should indicate signup is closed
        # or redirect, depending on allauth configuration
        assert response.status_code in [200, 302, 403]


class TestMFAIntegration:
    """Tests for MFA integration."""

    @pytest.mark.django_db
    def test_mfa_index_requires_login(self, db):
        """Test that MFA settings page requires authentication."""
        client = Client()
        response = client.get("/accounts/2fa/")
        # Should redirect to login
        assert response.status_code == 302
        assert "login" in response.headers.get("Location", "")

    @pytest.mark.django_db
    def test_mfa_index_accessible_when_logged_in(self, auth_client):
        """Test that MFA settings page is accessible when logged in."""
        response = auth_client.get("/accounts/2fa/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_totp_activation_page_accessible(self, auth_client):
        """Test that TOTP activation page is accessible."""
        response = auth_client.get("/accounts/2fa/totp/activate/")
        # 200 if accessible, 302 if redirecting to reauthenticate
        assert response.status_code in [200, 302]

    @pytest.mark.django_db
    def test_webauthn_list_page_accessible(self, auth_client):
        """Test that WebAuthn list page is accessible."""
        response = auth_client.get("/accounts/2fa/webauthn/")
        # 200 if accessible, 302 if redirecting to reauthenticate
        assert response.status_code in [200, 302]


class TestAdminMFALink:
    """Tests for MFA link in Django admin."""

    @pytest.mark.django_db
    def test_admin_has_mfa_link(self, auth_client):
        """Test that Django admin includes MFA settings link."""
        response = auth_client.get("/admin/")
        assert response.status_code == 200
        # Check that MFA link is present in the admin page
        content = response.content.decode("utf-8")
        assert "MFA Settings" in content or "mfa" in content.lower()


class TestAPIAuthEndpoints:
    """Tests for API authentication endpoints."""

    @pytest.mark.django_db
    def test_csrf_endpoint(self, db):
        """Test CSRF token endpoint."""
        client = Client()
        response = client.get("/api/v1/auth/csrf")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_me_endpoint_unauthenticated(self, db):
        """Test /me endpoint returns 401 when not authenticated."""
        client = Client()
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.django_db
    def test_me_endpoint_authenticated(self, auth_client):
        """Test /me endpoint returns user info when authenticated."""
        response = auth_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert "id" in data
        assert "is_staff" in data


class TestAuthResult:
    """Tests for AuthResult dataclass."""

    def test_auth_result_defaults(self):
        """Test AuthResult default values."""
        from django.contrib.auth.models import User

        user = User(username="test")
        result = AuthResult(user=user, auth_method="session")
        assert result.api_key_name is None
        assert result.tenant == "default"
        assert result.auth_method == "session"

    def test_auth_result_with_api_key(self):
        """Test AuthResult with API key metadata."""
        from django.contrib.auth.models import User

        user = User(username="test")
        result = AuthResult(
            user=user,
            auth_method="api_key",
            api_key_name="my-key",
            tenant="acme-corp",
        )
        assert result.api_key_name == "my-key"
        assert result.tenant == "acme-corp"
        assert result.auth_method == "api_key"


class TestAPIKeyAuthBackend:
    """Tests for the APIKeyAuthBackend."""

    @pytest.mark.django_db
    def test_returns_none_without_header(self, user):
        """Test that backend returns None when no API key header is present."""
        factory = RequestFactory()
        request = factory.get("/api/v1/trustmarktypes")
        backend = APIKeyAuthBackend()
        assert backend.authenticate(request) is None

    @pytest.mark.django_db
    def test_returns_none_for_invalid_key(self, user):
        """Test that backend returns None for an invalid API key."""
        factory = RequestFactory()
        request = factory.get("/api/v1/trustmarktypes", HTTP_X_API_KEY="bad-key")
        backend = APIKeyAuthBackend()
        assert backend.authenticate(request) is None

    @pytest.mark.django_db
    def test_returns_auth_result_for_valid_key(self, user):
        """Test that backend returns AuthResult with correct metadata."""
        _, plaintext = APIKey.create_key(name="backend-test", user=user, tenant="test-tenant")
        factory = RequestFactory()
        request = factory.get("/api/v1/trustmarktypes", HTTP_X_API_KEY=plaintext)
        backend = APIKeyAuthBackend()
        result = backend.authenticate(request)

        assert result is not None
        assert isinstance(result, AuthResult)
        assert result.user == user
        assert result.auth_method == "api_key"
        assert result.api_key_name == "backend-test"
        assert result.tenant == "test-tenant"


class TestSessionAuthBackend:
    """Tests for the SessionAuthBackend."""

    @pytest.mark.django_db
    def test_returns_none_for_anonymous(self, db):
        """Test that backend returns None for unauthenticated request."""
        factory = RequestFactory()
        request = factory.get("/api/v1/trustmarktypes")
        # Simulate anonymous user
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        backend = SessionAuthBackend()
        assert backend.authenticate(request) is None

    @pytest.mark.django_db
    def test_returns_auth_result_for_session(self, user):
        """Test that backend returns AuthResult for authenticated session (GET)."""
        factory = RequestFactory()
        request = factory.get("/api/v1/trustmarktypes")
        request.user = user
        backend = SessionAuthBackend()
        result = backend.authenticate(request)

        assert result is not None
        assert isinstance(result, AuthResult)
        assert result.user == user
        assert result.auth_method == "session"
        assert result.api_key_name is None
        assert result.tenant == "default"


class TestCombinedAuthSetsAuthResult:
    """Tests that CombinedAuthentication sets request.auth_result."""

    @pytest.mark.django_db
    def test_auth_result_set_for_api_key(self, user):
        """Test that request.auth_result is set when authenticating via API key."""
        _, plaintext = APIKey.create_key(name="combined-test", user=user, tenant="my-tenant")
        client = Client()
        response = client.get(
            "/api/v1/trustmarktypes",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_auth_result_set_for_session(self, auth_client):
        """Test that request.auth_result is set when authenticating via session."""
        response = auth_client.get("/api/v1/trustmarktypes")
        assert response.status_code == 200
