"""Authentication module for Inmor Admin API.

Provides session-based and API key authentication for django-ninja API.
Designed to be extensible for future SAML/OAuth providers.
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from ninja import Router, Schema
from ninja.security.apikey import APIKeyBase


class _CSRFCheck(CsrfViewMiddleware):
    """CSRF check that doesn't reject — just records the result."""

    def _reject(self, request, reason):
        return reason


class CombinedAuthentication(APIKeyBase):
    """Authenticates via API key (X-API-Key header) or Django session.

    API key is tried first and does not require CSRF.
    Session auth falls back and enforces CSRF for unsafe methods (POST, PUT, DELETE, PATCH).
    """

    # Disable Django Ninja's built-in CSRF enforcement so we can
    # handle it ourselves: skip CSRF for API key, enforce for session.
    csrf = False
    openapi_type: str = "apiKey"
    param_name: str = "X-API-Key"

    def _get_key(self, request: HttpRequest) -> str | None:
        return request.META.get("HTTP_X_API_KEY")

    def authenticate(self, request: HttpRequest, key: str | None = None):
        # 1. Try API key authentication (no CSRF needed)
        if key:
            from apikeys.models import APIKey

            user = APIKey.authenticate(key)
            if user:
                return user

        # 2. Fall back to session authentication with CSRF enforcement
        if request.user.is_authenticated:
            self._enforce_csrf(request)
            return request.user

        return None

    def _enforce_csrf(self, request: HttpRequest):
        """Enforce CSRF for session-based requests on unsafe methods."""
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            check = _CSRFCheck(lambda req: None)
            # populates request.META["CSRF_COOKIE"] from the cookie
            check.process_request(request)
            reason = check.process_view(request, None, (), {})
            if reason:
                from ninja.errors import HttpError

                raise HttpError(403, f"CSRF check Failed: {reason}")


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
