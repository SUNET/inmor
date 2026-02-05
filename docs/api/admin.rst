Admin API Reference
===================

The Admin Portal provides a REST API built with Django Ninja for managing
Trust Anchor resources. All endpoints are prefixed with ``/api/v1/``.

Base URL: ``http://localhost:8000/api/v1/``

API Documentation UI: ``http://localhost:8000/api/v1/docs``

Authentication
--------------

All ``/api/v1/`` endpoints (except auth endpoints) require authentication.
The API accepts two authentication methods:

* **Session authentication** -- Login via ``/api/v1/auth/login`` and use the
  session cookie for subsequent requests
* **API key authentication** -- Pass an ``X-API-Key`` header (see
  :doc:`../guides/api-keys`)

Both methods grant the same access. Session auth is used by the Vue frontend;
API keys are intended for scripts and integrations.

Auth Endpoints
^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 10 30 60

   * - Method
     - Endpoint
     - Description
   * - GET
     - ``/api/v1/auth/csrf``
     - Get CSRF token (sets cookie)
   * - POST
     - ``/api/v1/auth/login``
     - Login with ``{"username": "...", "password": "..."}``
   * - POST
     - ``/api/v1/auth/logout``
     - Logout and clear session
   * - GET
     - ``/api/v1/auth/me``
     - Get current authenticated user info

**Login Example:**

.. code-block:: bash

   # Get CSRF token
   curl -c cookies.txt http://localhost:8000/api/v1/auth/csrf

   # Login
   curl -b cookies.txt -c cookies.txt \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: <token-from-cookie>" \
     -X POST http://localhost:8000/api/v1/auth/login \
     -d '{"username": "admin", "password": "password"}'

**API Key Example:**

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY_HERE" \
        http://localhost:8000/api/v1/trustmarktypes

Trust Mark Types
----------------

Trust Mark Types define categories of trust marks that can be issued to entities.

Create Trust Mark Type
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/trustmarktypes

Creates a new trust mark type.

**Request Body:**

.. code-block:: json

   {
     "tmtype": "https://example.com/trustmarks/member",
     "autorenew": true,
     "valid_for": 8760,
     "renewal_time": 48,
     "active": true
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``tmtype``
     - string
     - Yes
     - URL identifier for the trust mark type
   * - ``autorenew``
     - boolean
     - No
     - Auto-renew trust marks of this type (default: true)
   * - ``valid_for``
     - integer
     - No
     - Validity period in hours (default: 8760 = 1 year)
   * - ``renewal_time``
     - integer
     - No
     - Hours before expiry to trigger renewal (default: 48)
   * - ``active``
     - boolean
     - No
     - Whether this type is active (default: true)

**Response (201 Created):**

.. code-block:: json

   {
     "id": 1,
     "tmtype": "https://example.com/trustmarks/member",
     "autorenew": true,
     "valid_for": 8760,
     "renewal_time": 48,
     "active": true
   }

**Response (403 Forbidden):** Returned if the trust mark type already exists.

**Example:**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarktypes \
     -H "Content-Type: application/json" \
     -d '{
       "tmtype": "https://example.com/trustmarks/member",
       "valid_for": 8760,
       "autorenew": true
     }'

List Trust Mark Types
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/trustmarktypes

Returns a paginated list of all trust mark types.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``limit``
     - integer
     - Maximum number of results (default: 100)
   * - ``offset``
     - integer
     - Offset for pagination (default: 0)

**Response (200 OK):**

.. code-block:: json

   {
     "count": 2,
     "items": [
       {
         "id": 1,
         "tmtype": "https://example.com/trustmarks/member",
         "autorenew": true,
         "valid_for": 8760,
         "renewal_time": 48,
         "active": true
       },
       {
         "id": 2,
         "tmtype": "https://example.com/trustmarks/verified",
         "autorenew": true,
         "valid_for": 720,
         "renewal_time": 48,
         "active": true
       }
     ]
   }

Get Trust Mark Type by ID
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/trustmarktypes/{id}

**Response (200 OK):**

.. code-block:: json

   {
     "id": 1,
     "tmtype": "https://example.com/trustmarks/member",
     "autorenew": true,
     "valid_for": 8760,
     "renewal_time": 48,
     "active": true
   }

Get Trust Mark Type by URL
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/trustmarktypes/?tmtype=https://example.com/trustmarks/member

Update Trust Mark Type
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   PUT /api/v1/trustmarktypes/{id}

**Request Body:**

.. code-block:: json

   {
     "autorenew": false,
     "valid_for": 720,
     "renewal_time": 24,
     "active": false
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``autorenew``
     - boolean
     - No
     - Whether trust marks of this type auto-renew
   * - ``valid_for``
     - integer
     - No
     - Validity period in hours
   * - ``renewal_time``
     - integer
     - No
     - Hours before expiry to trigger renewal
   * - ``active``
     - boolean
     - No
     - Whether this type is active

All fields are optional. Only provided fields will be updated.

Trust Marks
-----------

Trust marks are issued to entities and stored as signed JWTs.

Create Trust Mark
^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/trustmarks

Issues a new trust mark to an entity.

**Request Body:**

.. code-block:: json

   {
     "tmt": 1,
     "domain": "https://example-rp.com",
     "valid_for": 24,
     "autorenew": true,
     "additional_claims": {
       "ref": "https://github.com/example/verification"
     }
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``tmt``
     - integer
     - Yes
     - Trust Mark Type ID
   * - ``domain``
     - string
     - Yes
     - Entity ID (URL) to issue the trust mark to
   * - ``autorenew``
     - boolean
     - No
     - Override auto-renewal setting (defaults to trust mark type value)
   * - ``valid_for``
     - integer
     - No
     - Override validity period in hours (cannot exceed trust mark type value)
   * - ``renewal_time``
     - integer
     - No
     - Override renewal time in hours (cannot exceed trust mark type value)
   * - ``active``
     - boolean
     - No
     - Whether the trust mark is active (defaults to trust mark type value)
   * - ``additional_claims``
     - object
     - No
     - Extra claims to include in the JWT

**Response (201 Created):**

.. code-block:: json

   {
     "id": 1,
     "tmt_id": 1,
     "domain": "https://example-rp.com",
     "expire_at": "2026-01-15T12:00:00Z",
     "autorenew": true,
     "valid_for": 24,
     "renewal_time": 48,
     "active": true,
     "mark": "eyJhbGciOiJFUzI1NiIsInR5cCI6InRydXN0LW1hcmsrand0In0...",
     "additional_claims": {
       "ref": "https://github.com/example/verification"
     }
   }

**Response (403 Forbidden):** Returned if a trust mark already exists for this entity and type.

**Example:**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks \
     -H "Content-Type: application/json" \
     -d '{
       "tmt": 1,
       "domain": "https://example-rp.com"
     }'

List Trust Marks
^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/trustmarks

Returns a paginated list of all issued trust marks.

**Response (200 OK):**

.. code-block:: json

   {
     "count": 2,
     "items": [
       {
         "id": 1,
         "tmt_id": 1,
         "domain": "https://example-rp.com",
         "expire_at": "2026-01-15T12:00:00Z",
         "autorenew": true,
         "valid_for": 8760,
         "renewal_time": 48,
         "active": true,
         "mark": "eyJ...",
         "additional_claims": null
       }
     ]
   }

List Trust Marks by Entity
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/trustmarks/list

**Request Body:**

.. code-block:: json

   {
     "domain": "https://example-rp.com"
   }

Renew Trust Mark
^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/trustmarks/{id}/renew

Generates a new JWT with extended expiry for an existing trust mark.

**Response (200 OK):**

.. code-block:: json

   {
     "id": 1,
     "tmt_id": 1,
     "domain": "https://example-rp.com",
     "expire_at": "2027-01-15T12:00:00Z",
     "autorenew": true,
     "valid_for": 8760,
     "renewal_time": 48,
     "active": true,
     "mark": "eyJ...",
     "additional_claims": null
   }

Update Trust Mark
^^^^^^^^^^^^^^^^^

.. code-block:: text

   PUT /api/v1/trustmarks/{id}

**Request Body:**

.. code-block:: json

   {
     "active": false,
     "autorenew": false,
     "additional_claims": {
       "ref": "https://updated-reference.example.com"
     }
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``autorenew``
     - boolean
     - No
     - Whether the trust mark auto-renews
   * - ``active``
     - boolean
     - No
     - Whether the trust mark is active
   * - ``additional_claims``
     - object
     - No
     - Extra claims to include in the JWT (triggers re-signing)

Setting ``active`` to ``false`` revokes the trust mark. The entity will
no longer appear in trust mark lists, and status checks will return "revoked".

Changing ``additional_claims`` triggers re-signing of the trust mark JWT
with the updated claims.

Subordinates
------------

Subordinates are entities that have registered with the Trust Anchor.

Add Subordinate
^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/subordinates

Registers a new subordinate entity.

**Request Body:**

.. code-block:: json

   {
     "entityid": "https://example-rp.com",
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"],
         "response_types": ["code"],
         "grant_types": ["authorization_code"]
       }
     },
     "jwks": {
       "keys": [
         {
           "kty": "EC",
           "crv": "P-256",
           "x": "...",
           "y": "...",
           "kid": "key-1"
         }
       ]
     },
     "forced_metadata": {
       "openid_relying_party": {
         "application_type": "web"
       }
     },
     "valid_for": 8760,
     "autorenew": true,
     "active": true,
     "additional_claims": {
       "organization_name": "Example Corp"
     }
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``entityid``
     - string
     - Yes
     - Entity identifier URL
   * - ``metadata``
     - object
     - Yes
     - Entity metadata (from their entity configuration)
   * - ``forced_metadata``
     - object
     - Yes
     - Metadata to merge/override (TA-enforced values). Pass ``{}`` if none.
   * - ``jwks``
     - object
     - Yes
     - Entity's public keys (JWKS)
   * - ``required_trustmarks``
     - string
     - No
     - Required trust mark type URL for this subordinate
   * - ``valid_for``
     - integer
     - No
     - Statement validity in hours (cannot exceed system default)
   * - ``autorenew``
     - boolean
     - No
     - Auto-renew the subordinate statement (default: true)
   * - ``active``
     - boolean
     - No
     - Whether the subordinate is active (default: true)
   * - ``additional_claims``
     - object
     - No
     - Extra claims for the subordinate statement

**Validation:**

The API will:

1. Fetch the entity's ``/.well-known/openid-federation`` configuration
2. Verify the entity configuration signature using provided JWKS
3. Check that the TA is in the entity's ``authority_hints``
4. Apply metadata policy validation
5. Create and sign the subordinate statement
6. Store in database and sync to Redis

**Response (201 Created):**

.. code-block:: json

   {
     "id": 1,
     "entityid": "https://example-rp.com",
     "metadata": {},
     "forced_metadata": {},
     "jwks": {},
     "required_trustmarks": null,
     "valid_for": 8760,
     "expire_at": "2027-01-15T12:00:00Z",
     "autorenew": true,
     "active": true,
     "additional_claims": null
   }

**Response (400 Bad Request):** Validation errors, missing authority_hints, etc.

**Response (403 Forbidden):** Entity already registered.

**Example:**

.. code-block:: bash

   # First, fetch the entity's configuration
   ENTITY_JWT=$(curl -s https://example-rp.com/.well-known/openid-federation)

   # Then register with the TA
   curl -X POST http://localhost:8000/api/v1/subordinates \
     -H "Content-Type: application/json" \
     -d '{
       "entityid": "https://example-rp.com",
       "metadata": {"openid_relying_party": {"redirect_uris": ["..."]}},
       "jwks": {"keys": [{"kty": "EC", "crv": "P-256", "x": "...", "y": "..."}]},
       "forced_metadata": {}
     }'

List Subordinates
^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/subordinates

**Response (200 OK):**

.. code-block:: json

   {
     "count": 3,
     "items": [
       {
         "id": 1,
         "entityid": "https://example-rp.com",
         "metadata": {},
         "forced_metadata": {},
         "jwks": {},
         "required_trustmarks": null,
         "valid_for": 8760,
         "expire_at": "2027-01-15T12:00:00Z",
         "autorenew": true,
         "active": true,
         "additional_claims": null
       }
     ]
   }

Get Subordinate by ID
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /api/v1/subordinates/{id}

Update Subordinate
^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/subordinates/{id}

Updates an existing subordinate. The API will re-fetch and re-validate
the entity configuration before creating a new signed statement.

**Request Body:**

.. code-block:: json

   {
     "metadata": {},
     "forced_metadata": {},
     "jwks": {},
     "required_trustmarks": null,
     "valid_for": 8760,
     "autorenew": true,
     "active": true,
     "additional_claims": null
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``metadata``
     - object
     - Yes
     - Entity metadata
   * - ``forced_metadata``
     - object
     - Yes
     - TA-enforced metadata overrides. Pass ``{}`` if none.
   * - ``jwks``
     - object
     - Yes
     - Entity's public keys (JWKS)
   * - ``required_trustmarks``
     - string
     - No
     - Required trust mark type URL
   * - ``valid_for``
     - integer
     - No
     - Statement validity in hours (cannot exceed system default)
   * - ``autorenew``
     - boolean
     - No
     - Auto-renew the subordinate statement (default: true)
   * - ``active``
     - boolean
     - No
     - Whether the subordinate is active (default: true)
   * - ``additional_claims``
     - object
     - No
     - Extra claims for the subordinate statement

Fetch Entity Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/subordinates/fetch-config

Fetches and self-validates an entity's OpenID Federation configuration from
their ``/.well-known/openid-federation`` endpoint. Use this before adding a
subordinate to inspect their metadata and keys.

**Request Body:**

.. code-block:: json

   {
     "url": "https://example-rp.com"
   }

**Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - Field
     - Type
     - Required
     - Description
   * - ``url``
     - string
     - Yes
     - The entity URL to fetch configuration from

**Response (200 OK):**

.. code-block:: json

   {
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"]
       }
     },
     "jwks": {
       "keys": [{"kty": "EC", "crv": "P-256", "x": "...", "y": "..."}]
     },
     "authority_hints": ["https://federation.example.com"],
     "trust_marks": [
       {
         "trust_mark_type": "https://example.com/trustmarks/member",
         "trust_mark": "eyJ..."
       }
     ]
   }

**Response (400 Bad Request):** Connection errors, invalid URL, signature
validation failure, or no OpenID Federation configuration found.

**Example:**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates/fetch-config \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example-rp.com"}'

Server Operations
-----------------

These endpoints manage the Trust Anchor's own configuration.

Create Entity Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/server/entity

Creates (or recreates) the Trust Anchor's entity configuration JWT
and stores it in Redis for the ``/.well-known/openid-federation`` endpoint.

**Response (201 Created):**

.. code-block:: json

   {
     "entity_statement": "eyJhbGciOiJFUzI1NiIsInR5cCI6ImVudGl0eS1zdGF0ZW1lbnQrand0In0..."
   }

The entity statement includes:

* ``sub`` and ``iss``: Trust Anchor entity ID
* ``iat`` and ``exp``: Issuance and expiry timestamps
* ``jwks``: Trust Anchor's public keys
* ``metadata.federation_entity``: Federation endpoints
* ``trust_marks``: Trust marks issued to the TA itself
* ``authority_hints``: Parent authorities (if intermediate)

**Example:**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/server/entity

Create Historical Keys JWT
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /api/v1/server/historical_keys

Reads all JSON files from the ``historical_keys/`` directory, filters
to only include keys with an ``exp`` field, creates a signed JWT, and
stores it in Redis for the ``/historical_keys`` endpoint.

**Response (201 Created):**

.. code-block:: json

   {
     "message": "Historical keys JWT created with 2 keys"
   }

**Response (404 Not Found):** Directory not found or no valid keys.

**Example:**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/server/historical_keys

Error Responses
---------------

All error responses follow this format:

.. code-block:: json

   {
     "message": "Error description",
     "id": 0
   }

Common HTTP status codes:

* **400 Bad Request**: Invalid input or validation failure
* **403 Forbidden**: Resource already exists
* **404 Not Found**: Resource not found
* **500 Internal Server Error**: Unexpected error

Pagination
----------

List endpoints use limit-offset pagination:

.. code-block:: text

   GET /api/v1/trustmarks?limit=10&offset=20

Response includes:

* ``count``: Total number of items
* ``items``: Array of results for current page
