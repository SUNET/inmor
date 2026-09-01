Authentication Plugins
======================

Inmor's Admin API uses a pluggable authentication system. The built-in
backends (session and API key) can be extended with custom backends to
support additional authentication methods such as JWT Bearer tokens,
mTLS, or OAuth 2.0 token introspection.

This guide explains how the plugin architecture works and walks through
building a JWT Bearer Token authentication backend from scratch.

.. contents:: On this page
   :local:
   :depth: 2

Plugin Architecture
-------------------

All authentication for the Admin API (``/api/v1/``) flows through a
single chain defined in ``admin/inmoradmin/auth.py``.

.. code-block:: text

   Incoming Request
        │
        ▼
   CombinedAuthentication
        │
        ├── Backend 1: APIKeyAuthBackend
        │       └── Checks X-API-Key header
        ├── Backend 2: SessionAuthBackend
        │       └── Checks Django session cookie + CSRF
        └── Backend N: YourCustomBackend   ◄── you add this
                └── Your custom logic

The chain iterates ``backends`` in order. The first backend that returns
an ``AuthResult`` wins. If no backend matches, the request is rejected
with HTTP 401.

Key Components
^^^^^^^^^^^^^^

**AuthResult** (``admin/inmoradmin/auth.py``):

A dataclass that carries authentication metadata through the entire
request lifecycle — from the auth backend to audit logging.

.. code-block:: python

   @dataclass
   class AuthResult:
       user: User              # Django User the request acts as
       auth_method: str        # "session", "api_key", "jwt", etc.
       api_key_name: str | None = None
       tenant: str = "default" # Tenant identifier

**AuthBackend** (``admin/inmoradmin/auth.py``):

The base class for all authentication backends. Subclass it and
implement ``authenticate()`` to create a new backend.

.. code-block:: python

   class AuthBackend:
       name: str = "base"

       def authenticate(self, request: HttpRequest) -> AuthResult | None:
           raise NotImplementedError

Return ``None`` to pass to the next backend in the chain. Return an
``AuthResult`` to authenticate the request. Raise ``HttpError`` to
reject the request immediately (e.g. for a malformed token).

**CombinedAuthentication** (``admin/inmoradmin/auth.py``):

The django-ninja auth class that chains backends together. Its
``backends`` class attribute is a list you append to.

.. code-block:: python

   class CombinedAuthentication(APIKeyBase):
       backends: list[AuthBackend] = [APIKeyAuthBackend(), SessionAuthBackend()]

What You Get for Free
^^^^^^^^^^^^^^^^^^^^^

When you add a new backend, the following works automatically without
any additional code:

* **Audit logging** — ``auditlog/helpers.py`` reads ``request.auth_result``
  to record ``auth_method`` and ``tenant`` on every state-changing operation
* **Tenant scoping** — the ``tenant`` field on ``AuthResult`` propagates
  through the audit log and is available to any endpoint handler
* **CSRF handling** — only the session backend enforces CSRF; token-based
  backends (API key, JWT) skip it by returning before the session check

Building a JWT Bearer Token Backend
------------------------------------

This section walks through implementing a backend that verifies JWT
Bearer tokens against configured OIDC/federation issuers.

The backend will:

1. Extract a JWT from the ``Authorization: Bearer <token>`` header
2. Fetch the issuer's JWKS (with caching)
3. Verify the token signature, expiry, and audience
4. Map the token's ``sub`` claim to a Django user

Step 1: Configuration
^^^^^^^^^^^^^^^^^^^^^

Add the following to ``admin/inmoradmin/settings.py`` (or
``localsettings.py`` for per-deployment overrides):

.. code-block:: python

   # JWT Bearer Token Authentication
   # Each entry defines a trusted issuer and how to verify its tokens.
   JWT_AUTH_ISSUERS = [
       {
           "issuer": "https://idp.example.com",
           "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
           "audience": "inmor-admin",
           # Optional: map JWT claims to tenant
           "tenant_claim": "org_id",
           "default_tenant": "default",
       },
   ]

   # How long to cache a JWKS response (seconds). Default: 1 hour.
   JWT_AUTH_JWKS_CACHE_TTL = 3600

Step 2: JWKS Cache
^^^^^^^^^^^^^^^^^^

Create ``admin/inmoradmin/jwks_cache.py`` to avoid fetching the issuer's
key set on every request:

.. code-block:: python

   """Simple time-based JWKS cache for JWT auth."""

   from __future__ import annotations

   import time
   from typing import Any

   import httpx
   from django.conf import settings
   from jwcrypto.jwk import JWKSet


   _cache: dict[str, tuple[JWKSet, float]] = {}


   def get_jwks(jwks_uri: str) -> JWKSet:
       """Fetch and cache a JWKS from the given URI.

       Returns a cached copy if the TTL has not expired.
       """
       ttl = getattr(settings, "JWT_AUTH_JWKS_CACHE_TTL", 3600)
       now = time.monotonic()

       if jwks_uri in _cache:
           keyset, fetched_at = _cache[jwks_uri]
           if now - fetched_at < ttl:
               return keyset

       resp = httpx.get(jwks_uri, timeout=10)
       resp.raise_for_status()
       keyset = JWKSet.from_json(resp.text)
       _cache[jwks_uri] = (keyset, now)
       return keyset

.. note::

   This in-memory cache works for single-process deployments. For
   multi-process setups (e.g. gunicorn with multiple workers), consider
   using Django's cache framework backed by Redis instead.

Step 3: The Backend
^^^^^^^^^^^^^^^^^^^

Create ``admin/inmoradmin/jwt_auth.py``:

.. code-block:: python

   """JWT Bearer Token authentication backend for Inmor Admin API."""

   from __future__ import annotations

   import json
   import logging

   from django.conf import settings
   from django.contrib.auth.models import User
   from django.http import HttpRequest
   from jwcrypto.jwt import JWT, JWTExpired, JWTMissingKey
   from ninja.errors import HttpError

   from .auth import AuthBackend, AuthResult
   from .jwks_cache import get_jwks

   logger = logging.getLogger(__name__)


   class JWTAuthBackend(AuthBackend):
       """Authenticate via an ``Authorization: Bearer <JWT>`` header.

       Verifies the token signature against the JWKS published by a
       configured issuer, then maps the ``sub`` claim to a Django user.
       """

       name = "jwt"

       def authenticate(self, request: HttpRequest) -> AuthResult | None:
           header = request.META.get("HTTP_AUTHORIZATION", "")
           if not header.startswith("Bearer "):
               return None  # Not a Bearer token — pass to next backend

           token = header[7:]
           issuers = getattr(settings, "JWT_AUTH_ISSUERS", [])
           if not issuers:
               return None  # No issuers configured — skip

           for issuer_conf in issuers:
               result = self._try_issuer(token, issuer_conf)
               if result is not None:
                   return result

           # Token was present but could not be verified against any issuer
           raise HttpError(401, "Invalid or unrecognised JWT")

       def _try_issuer(
           self, token: str, issuer_conf: dict
       ) -> AuthResult | None:
           issuer = issuer_conf["issuer"]
           jwks_uri = issuer_conf["jwks_uri"]
           audience = issuer_conf.get("audience")

           try:
               keyset = get_jwks(jwks_uri)
           except Exception:
               logger.warning("Failed to fetch JWKS from %s", jwks_uri)
               return None

           try:
               jwt = JWT(
                   key=keyset,
                   jwt=token,
                   check_claims={
                       "iss": issuer,
                       "exp": None,     # Must be present
                       "sub": None,     # Must be present
                   },
               )
               if audience:
                   jwt.validate({"aud": audience})
           except JWTExpired:
               raise HttpError(401, "JWT has expired")
           except (JWTMissingKey, Exception):
               return None  # Wrong issuer or key — try next

           claims = json.loads(jwt.claims)
           sub = claims["sub"]

           # Map JWT sub to Django user
           user = self._resolve_user(sub, claims)
           if user is None:
               raise HttpError(
                   401, f"No local user mapped to JWT subject: {sub}"
               )

           tenant = claims.get(
               issuer_conf.get("tenant_claim", ""),
               issuer_conf.get("default_tenant", "default"),
           )

           return AuthResult(
               user=user,
               auth_method="jwt",
               tenant=tenant,
           )

       @staticmethod
       def _resolve_user(sub: str, claims: dict) -> User | None:
           """Map a JWT ``sub`` claim to a Django user.

           Override this method to implement a different mapping strategy
           (e.g. auto-creating users, using email, or looking up a
           federated identity table).
           """
           try:
               return User.objects.get(username=sub)
           except User.DoesNotExist:
               return None

.. tip::

   The ``_resolve_user`` method is a deliberate extension point. Override
   it in a subclass to implement auto-provisioning, email-based lookup,
   or any other user-mapping strategy your deployment requires.

Step 4: Register the Backend
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In ``admin/inmoradmin/auth.py``, import the backend and append it to the
chain. The position in the list determines priority — backends earlier in
the list are checked first.

.. code-block:: python

   from .jwt_auth import JWTAuthBackend

   class CombinedAuthentication(APIKeyBase):
       backends: list[AuthBackend] = [
           APIKeyAuthBackend(),
           JWTAuthBackend(),       # <-- add here
           SessionAuthBackend(),
       ]

Placing the JWT backend between API key and session means:

1. API key is checked first (cheapest — header lookup + hash comparison)
2. JWT is checked second (requires signature verification)
3. Session is checked last (for browser-based access)

Step 5: Using the Backend
^^^^^^^^^^^^^^^^^^^^^^^^^

Clients authenticate by sending the JWT in the ``Authorization`` header:

.. code-block:: bash

   curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..." \
        https://your-server/api/v1/trustmarktypes

All ``/api/v1/`` endpoints accept the JWT in the same way — no per-endpoint
configuration is needed.

**List trust mark types:**

.. code-block:: bash

   curl -H "Authorization: Bearer $JWT_TOKEN" \
        https://your-server/api/v1/trustmarktypes

**Create a trust mark:**

.. code-block:: bash

   curl -X POST \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"tmt": 1, "domain": "https://example.com"}' \
        https://your-server/api/v1/trustmarks

Testing
^^^^^^^

Write tests in ``admin/tests/`` using pytest-django. The key technique is
mocking the JWKS fetch and generating test JWTs with ``jwcrypto``:

.. code-block:: python

   import json
   import time

   import pytest
   from django.test import RequestFactory
   from jwcrypto.jwk import JWK, JWKSet
   from jwcrypto.jwt import JWT

   from inmoradmin.jwt_auth import JWTAuthBackend


   @pytest.fixture
   def rsa_key():
       return JWK.generate(kty="RSA", size=2048, kid="test-key-1")


   @pytest.fixture
   def jwks(rsa_key):
       ks = JWKSet()
       ks.add(rsa_key)
       return ks


   def _make_jwt(key, claims):
       token = JWT(
           header={"alg": "RS256", "kid": key.key_id},
           claims=json.dumps(claims),
       )
       token.make_signed_token(key)
       return token.serialize()


   @pytest.mark.django_db
   def test_jwt_auth_valid_token(rsa_key, jwks, settings, monkeypatch):
       """A valid JWT from a configured issuer authenticates the user."""
       from django.contrib.auth.models import User

       user = User.objects.create_user("test-sub", password="unused")

       settings.JWT_AUTH_ISSUERS = [
           {
               "issuer": "https://idp.example.com",
               "jwks_uri": "https://idp.example.com/jwks",
               "audience": "inmor-admin",
           },
       ]

       # Mock the JWKS fetch
       monkeypatch.setattr(
           "inmoradmin.jwks_cache.get_jwks", lambda uri: jwks
       )

       token = _make_jwt(rsa_key, {
           "iss": "https://idp.example.com",
           "sub": "test-sub",
           "aud": "inmor-admin",
           "exp": int(time.time()) + 3600,
           "iat": int(time.time()),
       })

       factory = RequestFactory()
       request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}")

       backend = JWTAuthBackend()
       result = backend.authenticate(request)

       assert result is not None
       assert result.user == user
       assert result.auth_method == "jwt"


   @pytest.mark.django_db
   def test_jwt_auth_expired_token(rsa_key, jwks, settings, monkeypatch):
       """An expired JWT is rejected with 401."""
       from ninja.errors import HttpError

       settings.JWT_AUTH_ISSUERS = [
           {
               "issuer": "https://idp.example.com",
               "jwks_uri": "https://idp.example.com/jwks",
           },
       ]
       monkeypatch.setattr(
           "inmoradmin.jwks_cache.get_jwks", lambda uri: jwks
       )

       token = _make_jwt(rsa_key, {
           "iss": "https://idp.example.com",
           "sub": "test-sub",
           "exp": int(time.time()) - 3600,  # expired
           "iat": int(time.time()) - 7200,
       })

       factory = RequestFactory()
       request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}")

       backend = JWTAuthBackend()
       with pytest.raises(HttpError, match="expired"):
           backend.authenticate(request)

Writing Your Own Backend
------------------------

The JWT example above demonstrates the full pattern. To summarise, any
custom backend needs to:

1. **Subclass** ``AuthBackend`` from ``admin/inmoradmin/auth.py``
2. **Set** the ``name`` class attribute to a unique string (this appears
   in audit logs as the ``auth_method``)
3. **Implement** ``authenticate(self, request) -> AuthResult | None``:

   * Return ``None`` to pass to the next backend
   * Return an ``AuthResult`` to authenticate the request
   * Raise ``HttpError(401, ...)`` to reject immediately

4. **Append** an instance to ``CombinedAuthentication.backends``

No changes are needed to API endpoints, audit logging, or the frontend.

Other Backend Ideas
^^^^^^^^^^^^^^^^^^^

**mTLS / Client Certificate**:

Read the client certificate from ``request.META["SSL_CLIENT_CERT"]``
(set by the reverse proxy) and map the certificate subject DN to a
Django user. Requires nginx/Caddy configuration to pass certificate
headers.

**OAuth 2.0 Token Introspection**:

Accept an opaque access token in the ``Authorization: Bearer`` header,
call the authorization server's introspection endpoint to validate it,
and map the ``sub`` from the introspection response to a Django user.
Cache active token responses briefly to avoid per-request round-trips.

**OpenID Federation Entity Authentication**:

Accept an entity statement JWT, self-verify it, resolve the trust chain
back to a configured trust anchor (using the ``/resolve`` endpoint on
the Rust TA server), and grant access based on entity type or trust
marks. This is the most complex option as it requires trust chain
resolution.

Security Considerations
-----------------------

* **Always validate ``exp``** — never accept tokens without an expiry claim
* **Always validate ``iss``** — only accept tokens from configured issuers
* **Validate ``aud`` when possible** — prevents tokens intended for other
  services from being accepted here
* **Reject ``alg: "none"``** — the ``jwcrypto`` library does this by
  default when you supply a keyset, but be explicit if using other libraries
* **Cache JWKS, not tokens** — cache the issuer's public keyset to avoid
  per-request fetches, but always verify each token individually
* **Use HTTPS for JWKS URIs** — the keyset fetch must be encrypted in
  transit to prevent key substitution attacks
* **Log authentication failures** — the backend should log failed
  verification attempts for security monitoring
