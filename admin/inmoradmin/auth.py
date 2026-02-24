"""Authentication module for Inmor Admin API.

Provides session-based and API key authentication for django-ninja API.
Designed to be extensible — new auth backends (e.g. JWT) can be added by
subclassing ``AuthBackend`` and appending to ``CombinedAuthentication.backends``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from ninja import Router, Schema
from ninja.security.apikey import APIKeyBase


# ---------------------------------------------------------------------------
# Auth result and backend protocol
# ---------------------------------------------------------------------------


@dataclass
class AuthResult:
    """Structured authentication result attached to ``request.auth_result``.

    Carries metadata about *how* the request was authenticated so that
    downstream code (audit logging, tenant-scoped queries) can use it
    without re-inspecting headers.
    """

    user: User
    auth_method: str  # "session", "api_key", or future plugin names
    api_key_name: str | None = None  # Name of the API key used (None for session)
    tenant: str = "default"  # Tenant identifier


class AuthBackend:
    """Base class for authentication backends.

    Subclass this and implement ``authenticate()`` to add a new auth method.
    """

    name: str = "base"

    def authenticate(self, request: HttpRequest) -> AuthResult | None:
        raise NotImplementedError


class APIKeyAuthBackend(AuthBackend):
    """Authenticate via the ``X-API-Key`` header."""

    name = "api_key"

    def authenticate(self, request: HttpRequest) -> AuthResult | None:
        key = request.META.get("HTTP_X_API_KEY")
        if not key:
            return None

        from apikeys.models import APIKey

        result = APIKey.authenticate(key)
        if result is None:
            return None

        user, api_key = result
        return AuthResult(
            user=user,
            auth_method="api_key",
            api_key_name=api_key.name,
            tenant=api_key.tenant,
        )


class SessionAuthBackend(AuthBackend):
    """Authenticate via the Django session cookie (with CSRF enforcement)."""

    name = "session"

    def authenticate(self, request: HttpRequest) -> AuthResult | None:
        if not request.user.is_authenticated:
            return None

        _enforce_csrf(request)
        return AuthResult(
            user=request.user,
            auth_method="session",
        )


# ---------------------------------------------------------------------------
# CSRF helper
# ---------------------------------------------------------------------------


class _CSRFCheck(CsrfViewMiddleware):
    """CSRF check that doesn't reject — just records the result."""

    def _reject(self, request, reason):
        return reason


def _enforce_csrf(request: HttpRequest):
    """Enforce CSRF for session-based requests on unsafe methods."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        check = _CSRFCheck(lambda req: None)
        # populates request.META["CSRF_COOKIE"] from the cookie
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            from ninja.errors import HttpError

            raise HttpError(403, f"CSRF check Failed: {reason}")


# ---------------------------------------------------------------------------
# Combined authenticator (used by django-ninja routers)
# ---------------------------------------------------------------------------


class CombinedAuthentication(APIKeyBase):
    """Authenticates via a chain of pluggable backends.

    Iterates ``backends`` in order; the first backend that returns an
    ``AuthResult`` wins.  The result is stored on ``request.auth_result``
    so downstream code can inspect auth metadata.
    """

    csrf = False
    openapi_type: str = "apiKey"
    param_name: str = "X-API-Key"

    backends: list[AuthBackend] = [APIKeyAuthBackend(), SessionAuthBackend()]

    def _get_key(self, request: HttpRequest) -> str | None:
        return request.META.get("HTTP_X_API_KEY")

    def authenticate(self, request: HttpRequest, key: str | None = None):
        for backend in self.backends:
            result = backend.authenticate(request)
            if result is not None:
                request.auth_result = result  # type: ignore[attr-defined]
                return result.user
        return None


# Single auth instance used by the protected router
combined_auth = [CombinedAuthentication()]


class LoginSchema(Schema):
    username: str
    password: str


class UserSchema(Schema):
    id: int
    username: str
    email: str
    is_staff: bool
    is_superuser: bool


class MessageSchema(Schema):
    message: str


# Auth router for login/logout endpoints (no auth required for these)
auth_router = Router(tags=["Authentication"])


@auth_router.post("/login", response={200: UserSchema, 401: MessageSchema})
def api_login(request: HttpRequest, data: LoginSchema):
    """Authenticate user and create session."""
    user = authenticate(request, username=data.username, password=data.password)
    if user is not None and isinstance(user, User):
        login(request, user)
        return 200, {
            "id": user.pk,
            "username": user.username,
            "email": user.email or "",
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        }
    return 401, {"message": "Invalid credentials"}


@auth_router.post("/logout", response={200: MessageSchema})
def api_logout(request: HttpRequest):
    """Log out current user and clear session."""
    logout(request)
    return 200, {"message": "Logged out successfully"}


@auth_router.get("/me", response={200: UserSchema, 401: MessageSchema})
def get_current_user(request: HttpRequest):
    """Get current authenticated user info."""
    if request.user.is_authenticated:
        return 200, {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email or "",
            "is_staff": request.user.is_staff,
            "is_superuser": request.user.is_superuser,
        }
    return 401, {"message": "Not authenticated"}


@auth_router.get("/csrf", auth=None)
@ensure_csrf_cookie
@csrf_exempt
def get_csrf_token(request: HttpRequest):
    """Get CSRF token - sets the csrftoken cookie."""
    return HttpResponse()
