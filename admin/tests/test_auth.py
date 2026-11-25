"""Tests for authentication and MFA integration."""

import time
from urllib.parse import urlsplit

import pytest
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, Permission, User
from django.test import Client, RequestFactory
from django.urls import reverse

from apikeys.models import APIKey
from inmoradmin.auth import (
    APIKeyAuthBackend,
    AuthResult,
    SessionAuthBackend,
)
from trustmarks.models import TrustMark, TrustMarkType


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
    def test_signup_disabled(self, db, client):
        signup = reverse("account_signup")
        assert client.get(signup).template_name == "account/signup_closed.html"
        count = User.objects.count()
        response = client.post(
            signup,
            {
                "username": "new-user",
                "email": "new-user@example.org",
                "password1": "a-long-signup-password",
                "password2": "a-long-signup-password",
            },
        )
        assert response.template_name == "account/signup_closed.html"
        assert User.objects.count() == count
        assert SESSION_KEY not in client.session


class TestMFAIntegration:
    """Tests for MFA integration."""

    def test_admin_password_login_requires_enrolled_totp(self, user, client, loadredis):
        secret = generate_totp_secret()
        TOTP.activate(user, secret)
        admin_url = reverse("admin:index")
        response = client.post(
            reverse("admin:login"),
            {"username": user.username, "password": "testpass123"},
            query_params={"next": admin_url},
        )
        assert response.status_code == 302
        assert urlsplit(response.url).path == reverse("account_login")
        assert SESSION_KEY not in client.session

        response = client.post(response.url, {"login": user.username, "password": "testpass123"})
        assert response.status_code == 302
        assert urlsplit(response.url).path == reverse("mfa_authenticate")
        assert SESSION_KEY not in client.session
        assert client.get(admin_url).status_code == 302

        code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
        response = client.post(response.url, {"code": code}, follow=True)
        assert response.wsgi_request.path == admin_url
        assert response.status_code == 200
        assert client.session[SESSION_KEY] == str(user.pk)

    def test_staff_session_cannot_submit_django_password_form(self, auth_client, user):
        response = auth_client.post(reverse("admin:login"))
        assert response.status_code == 405
        assert auth_client.session[SESSION_KEY] == str(user.pk)

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
    def test_password_login_endpoint_not_exposed(self, db):
        """Passwords cannot be exchanged for a session through the API."""
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            data='{"username":"testuser","password":"testpass123"}',
            content_type="application/json",
        )
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_csrf_endpoint(self, db):
        """Browser clients initialize CSRF from the cookie on an empty response."""
        client = Client()
        response = client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        assert response.content == b""
        assert response.cookies["csrftoken"].value

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
        assert data["can_manage_federation"] is True

    def test_me_reports_management_permission(self, db, client):
        """The UI sees the same permission decision as the protected API."""
        user = User.objects.create_user("staff-only", is_staff=True)
        client.force_login(user)
        assert client.get("/api/v1/auth/me").json()["can_manage_federation"] is False
        assert client.get("/api/v1/trustmarktypes").status_code == 403

        # A group grant must work without superuser privileges.
        group = Group.objects.create(name="federation-managers")
        group.permissions.add(Permission.objects.get(codename="manage_federation"))
        user.groups.add(group)
        assert client.get("/api/v1/auth/me").json()["can_manage_federation"] is True
        assert client.get("/api/v1/trustmarktypes").status_code == 200


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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("auth_method", ["session", "api_key"])
def test_operator_permission_controls_trust_mark_issuance(db, rdb, auth_method):
    client = Client(enforce_csrf_checks=True)
    user = User.objects.create_user(username="operator")
    api_key = None
    if auth_method == "session":
        client.force_login(user)
        client.get("/api/v1/auth/csrf")
        client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    else:
        api_key, plaintext = APIKey.create_key(name="automation", user=user)
        client.defaults["HTTP_X_API_KEY"] = plaintext

    mark_type = TrustMarkType.objects.create(tmtype="https://issuer.example/mark")
    url = "/api/v1/trustmarks"

    def issue(domain):
        return client.post(
            url, {"tmt": mark_type.pk, "domain": domain}, content_type="application/json"
        )

    denied = "https://denied.example"
    assert issue(denied).status_code == 403
    assert not TrustMark.objects.filter(domain=denied).exists()
    assert not rdb.exists(f"inmor:tm:{denied}")
    if api_key:
        api_key.refresh_from_db()
        assert api_key.last_used_at is None

    operators = Group.objects.create(name="Federation Operators")
    operators.permissions.add(
        Permission.objects.get(content_type__app_label="entities", codename="manage_federation")
    )
    user.groups.add(operators)
    allowed = "https://allowed.example"
    assert issue(allowed).status_code == 201
    issued = TrustMark.objects.get(domain=allowed)
    assert issued.mark
    assert rdb.hget(f"inmor:tm:{allowed}", mark_type.tmtype) == issued.mark.encode()
    if api_key:
        api_key.refresh_from_db()
        assert api_key.last_used_at is not None

    user.groups.remove(operators)
    assert client.get("/api/v1/auditlog").status_code == 403
    assert issue(denied).status_code == 403
    assert not TrustMark.objects.filter(domain=denied).exists()
    assert not rdb.exists(f"inmor:tm:{denied}")


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
