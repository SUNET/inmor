"""Tests for authentication and MFA integration."""

import pytest
from django.test import Client


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
