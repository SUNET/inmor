"""Authentication module for Inmor Admin API.

Provides session-based and API key authentication for django-ninja API.
Designed to be extensible for future SAML/OAuth providers.
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from ninja import Router, Schema
from ninja.security import APIKeyHeader, SessionAuth


class SessionAuthentication(SessionAuth):
    """Session-based authentication for API endpoints."""

    def authenticate(self, request: HttpRequest, key: str | None = None):
        if request.user.is_authenticated:
            return request.user
        return None


class APIKeyAuthentication(APIKeyHeader):
    """API Key authentication via X-API-Key header."""

    param_name = "X-API-Key"

    def authenticate(self, request: HttpRequest, key: str | None):
        if key:
            # Import here to avoid circular imports
            from apikeys.models import APIKey

            user = APIKey.authenticate(key)
            if user:
                return user
        return None


# Create reusable auth instances
session_auth = SessionAuthentication()
api_key_auth = APIKeyAuthentication()

# Combined auth - accepts either session or API key
combined_auth = [session_auth, api_key_auth]


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
