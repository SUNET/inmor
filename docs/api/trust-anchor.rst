Trust Anchor API Reference
==========================

The Trust Anchor (TA) provides the OpenID Federation protocol endpoints.
These are public endpoints consumed by federation participants.

Base URL: ``https://federation.example.com/`` (or ``http://localhost:8080`` for development)

OpenID Federation Endpoints
---------------------------

Entity Configuration
^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /.well-known/openid-federation

Returns the Trust Anchor's entity configuration as a signed JWT.

**Response:**

* Content-Type: ``application/entity-statement+jwt``
* Body: Signed JWT

**JWT Payload Example:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://federation.example.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "jwks": {
       "keys": [
         {
           "kty": "EC",
           "crv": "P-256",
           "x": "...",
           "y": "...",
           "kid": "key-1",
           "use": "sig",
           "alg": "ES256"
         }
       ]
     },
     "metadata": {
       "federation_entity": {
         "federation_fetch_endpoint": "https://federation.example.com/fetch",
         "federation_list_endpoint": "https://federation.example.com/list",
         "federation_resolve_endpoint": "https://federation.example.com/resolve",
         "federation_trust_mark_status_endpoint": "https://federation.example.com/trust_mark_status",
         "federation_trust_mark_list_endpoint": "https://federation.example.com/trust_mark_list",
         "federation_trust_mark_endpoint": "https://federation.example.com/trust_mark",
         "federation_historical_keys_endpoint": "https://federation.example.com/historical_keys"
       }
     },
     "trust_marks": [
       {
         "trust_mark_type": "https://example.com/trustmarks/ta",
         "trust_mark": "eyJ..."
       }
     ]
   }

**Example:**

.. code-block:: bash

   curl https://federation.example.com/.well-known/openid-federation

List Subordinates
^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /list

Returns a list of subordinate entity IDs registered with this Trust Anchor.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``entity_type``
     - string
     - Filter by entity type (see below)
   * - ``trust_marked``
     - boolean
     - Only return entities with at least one trust mark
   * - ``trust_mark_type``
     - string
     - Only return entities with this specific trust mark type
   * - ``intermediate``
     - boolean
     - Only return intermediate authorities (federation_entity)

**Entity Types:**

* ``openid_provider`` - OpenID Providers (OPs)
* ``openid_relying_party`` - Relying Parties (RPs)
* ``federation_entity`` - Intermediate Authorities (IAs)

**Response (200 OK):**

.. code-block:: json

   [
     "https://example-rp.com",
     "https://example-op.com",
     "https://other-entity.com"
   ]

**Examples:**

.. code-block:: bash

   # List all subordinates
   curl https://federation.example.com/list

   # List only OpenID Providers
   curl "https://federation.example.com/list?entity_type=openid_provider"

   # List entities with a specific trust mark
   curl "https://federation.example.com/list?trust_mark_type=https://example.com/trustmarks/member"

   # List only intermediate authorities
   curl "https://federation.example.com/list?intermediate=true"

Fetch Subordinate Statement
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /fetch

Fetches the subordinate statement for a specific entity.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``sub``
     - string
     - **Required.** Entity ID to fetch
   * - ``iss``
     - string
     - Optional issuer filter

**Response (200 OK):**

* Content-Type: ``application/entity-statement+jwt``
* Body: Signed subordinate statement JWT

**JWT Payload Example:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "jwks": {
       "keys": ["...key data..."]
     },
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"]
       }
     },
     "metadata_policy": {}
   }

**Response (404 Not Found):**

.. code-block:: json

   {
     "error": "not_found",
     "error_description": "No statement for https://example-rp.com"
   }

**Example:**

.. code-block:: bash

   curl "https://federation.example.com/fetch?sub=https://example-rp.com"

Resolve Entity
^^^^^^^^^^^^^^

.. code-block:: text

   GET /resolve

Resolves an entity through the trust chain to the Trust Anchor, performing
tree-walking and policy application.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``sub``
     - string
     - **Required.** Subject entity ID to resolve
   * - ``trust_anchor``
     - string
     - Trust anchor(s) to resolve against (can be repeated)
   * - ``entity_type``
     - string
     - Filter to specific entity types (can be repeated)

**Response (200 OK):**

* Content-Type: ``application/resolve-response+jwt``
* Body: Signed resolution response JWT

**JWT Payload Example:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1705401600,
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"],
         "response_types": ["code"]
       }
     },
     "trust_chain": [
       "eyJ...(entity config of example-rp.com)...",
       "eyJ...(subordinate statement from TA)...",
       "eyJ...(TA entity config)..."
     ]
   }

The ``trust_chain`` array contains:

1. Subject's entity configuration (self-signed)
2. Subordinate statement from the TA (or intermediate)
3. TA's entity configuration

Per OpenID Federation §4.3, the same chain also rides in the JWS header
of the resolve response as the ``trust_chain`` header parameter. Clients
may read either form; the header lets them short-circuit chain resolution
without parsing the payload.

**Examples:**

.. code-block:: bash

   # Resolve an entity
   curl "https://federation.example.com/resolve?sub=https://example-rp.com&trust_anchor=https://federation.example.com"

   # Resolve with specific entity type
   curl "https://federation.example.com/resolve?sub=https://example-op.com&entity_type=openid_provider&trust_anchor=https://federation.example.com"

   # Resolve with multiple entity types
   curl "https://federation.example.com/resolve?sub=https://example-op.com&entity_type=openid_provider&entity_type=federation_entity&trust_anchor=https://federation.example.com"

Trust Mark Endpoints
--------------------

Get Trust Mark
^^^^^^^^^^^^^^

.. code-block:: text

   GET /trust_mark

Retrieves a specific trust mark JWT for an entity.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``trust_mark_type``
     - string
     - **Required.** Trust mark type URL
   * - ``sub``
     - string
     - **Required.** Subject entity ID

**Response (200 OK):**

* Content-Type: ``application/trust-mark+jwt``
* Body: Signed trust mark JWT

**JWT Payload Example:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "trust_mark_type": "https://example.com/trustmarks/member",
     "ref": "https://github.com/example/verification"
   }

**Response (404 Not Found):**

.. code-block:: json

   {
     "error": "not_found",
     "error_description": "Trust mark not found."
   }

**Example:**

.. code-block:: bash

   curl "https://federation.example.com/trust_mark?trust_mark_type=https://example.com/trustmarks/member&sub=https://example-rp.com"

List Trust Mark Holders
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /trust_mark_list

Returns a list of entity IDs that have been issued a specific trust mark type.

**Query Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Parameter
     - Type
     - Description
   * - ``trust_mark_type``
     - string
     - **Required.** Trust mark type URL

**Response (200 OK):**

.. code-block:: json

   [
     "https://example-rp.com",
     "https://other-entity.com",
     "https://federation.example.com"
   ]

**Example:**

.. code-block:: bash

   curl "https://federation.example.com/trust_mark_list?trust_mark_type=https://example.com/trustmarks/member"

Validate Trust Mark Status
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   POST /trust_mark_status

Validates a trust mark JWT and returns its current status.

**Request:**

* Content-Type: ``application/x-www-form-urlencoded``

**Form Parameters:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Parameter
     - Description
   * - ``trust_mark``
     - The trust mark JWT to validate

**Response (200 OK):**

* Content-Type: ``application/trust-mark-status+jwt``
* Body: Signed status response JWT

**JWT Payload Example (Active):**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "iat": 1705315200,
     "status": "active",
     "sub": "https://example-rp.com",
     "trust_mark_type": "https://example.com/trustmarks/member"
   }

**Status Values:**

* ``active`` - Trust mark is valid and not revoked
* ``revoked`` - Trust mark has been revoked by the TA
* ``expired`` - Trust mark JWT has expired
* ``invalid`` - Trust mark signature verification failed or unknown issuer

**Example:**

.. code-block:: bash

   # First, get a trust mark
   TRUST_MARK=$(curl -s "https://federation.example.com/trust_mark?trust_mark_type=https://example.com/trustmarks/member&sub=https://example-rp.com")

   # Then validate it
   curl -X POST https://federation.example.com/trust_mark_status \
     -d "trust_mark=$TRUST_MARK"

Historical Keys
^^^^^^^^^^^^^^^

.. code-block:: text

   GET /historical_keys

Returns a signed JWT containing the Trust Anchor's historical (expired/rotated) keys.
This allows verification of old signatures after key rotation.

**Response (200 OK):**

* Content-Type: ``application/jwk-set+jwt``
* Body: Signed JWK Set JWT

**JWT Payload Example:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "iat": 1705315200,
     "keys": [
       {
         "kty": "EC",
         "crv": "P-256",
         "x": "...",
         "y": "...",
         "kid": "old-key-1",
         "use": "sig",
         "alg": "ES256",
         "exp": 1704067200
       },
       {
         "kty": "EC",
         "crv": "P-256",
         "x": "...",
         "y": "...",
         "kid": "old-key-2",
         "use": "sig",
         "alg": "ES256",
         "exp": 1701388800,
         "revoked": {
           "revoked_at": 1701388800,
           "reason": "superseded"
         }
       }
     ]
   }

**Key Revocation Reasons:**

* ``unspecified`` - No specific reason given
* ``compromised`` - Key has been compromised
* ``superseded`` - Key replaced by a newer key

**Example:**

.. code-block:: bash

   curl https://federation.example.com/historical_keys

Other Endpoints
---------------

Entity Collection
^^^^^^^^^^^^^^^^^

.. code-block:: text

   GET /collection

Returns a list of all entities discovered in the federation tree, per the
`Entity Collection Endpoint specification <https://openid.net/specs/openid-federation-entity-collection-endpoint-1_0.html>`_
(draft 00).

This endpoint reads pre-populated data from Redis. The data is populated by running the
``inmor-collection`` CLI tool, which walks the federation tree from a trust anchor and
stores entity information. See :ref:`collection-cli` for details.

**Response (200 OK):**

* Content-Type: ``application/json``

.. code-block:: json

   {
     "entities": [
       {
         "entity_id": "https://op.example.com",
         "entity_types": ["openid_provider", "federation_entity"],
         "ui_infos": {
           "openid_provider": {
             "display_name": "Example OP",
             "logo_uri": "https://op.example.com/logo.png"
           },
           "federation_entity": {
             "display_name": "Example Organization"
           }
         },
         "trust_marks": [
           {"id": "https://ta.example.com/tm/member", "trust_mark": "eyJ..."}
         ]
       },
       {
         "entity_id": "https://rp.example.com",
         "entity_types": ["openid_relying_party", "federation_entity"],
         "ui_infos": {
           "openid_relying_party": {
             "display_name": "Example RP"
           }
         }
       }
     ],
     "last_updated": 1770983002
   }

**Response Fields:**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Description
   * - ``entities``
     - Array of entity objects discovered in the federation tree
   * - ``entities[].entity_id``
     - The entity identifier (URL)
   * - ``entities[].entity_types``
     - Array of entity types (``openid_provider``, ``openid_relying_party``, ``federation_entity``, ``oauth_authorization_server``, ``oauth_client``, ``oauth_resource``)
   * - ``entities[].ui_infos``
     - Optional. UI information per entity type (display_name, logo_uri, policy_uri)
   * - ``entities[].trust_marks``
     - Optional. Array of trust marks attached to the entity
   * - ``last_updated``
     - Unix timestamp of the last collection walk

**Example:**

.. code-block:: bash

   curl https://federation.example.com/collection

If no collection data has been populated yet, the response will be an empty entity list
with ``last_updated: 0``.

Index Page
^^^^^^^^^^

.. code-block:: text

   GET /

Returns a simple index page confirming the server is running.

**Response (200 OK):**

.. code-block:: text

   Index page.

Error Responses
---------------

All error responses follow this format:

.. code-block:: json

   {
     "error": "error_code",
     "error_description": "Human-readable description"
   }

**Common Error Codes:**

* ``not_found`` - Resource not found
* ``invalid_request`` - Missing or invalid parameters
* ``invalid_trust_chain`` - Trust chain build, signature, temporal, or policy
  validation failed. ``error_description`` carries a precise reason in two
  cases that the resolver propagates verbatim:

  - Leaf entity-configuration verification failures detected at the start
    of the walk (bad self-signature, missing ``jwks``, ``iss`` / ``sub``
    mismatch under §3.1, or an unknown ``crit`` entry under §3.1.1 -- the
    offending claim name appears in the message).
  - Metadata-policy merge failures from the ``oidfed_metadata_policy`` crate
    (§6.1.3.2), including the offending critical operator name when
    ``metadata_policy_crit`` rejects it.

  Other chain-walking failures (subordinate-statement signature, constraint
  violation, permitted/excluded-subtree mismatch) cause the walker to skip
  the offending authority and try another branch. If no chain reaches a
  trust anchor after exploring all branches, the response is the generic
  ``"Failed to find trust chain"`` -- the per-authority reasons are
  recorded in the server log rather than surfaced to the client.
* ``server_error`` - Internal server error

Chain constraints (§6.2)
------------------------

Subordinate Statements can carry a ``constraints`` object that restricts
which entities may appear below the SS subject in the chain. inmor parses
and enforces all four standard constraint shapes during trust-chain
walking:

* ``max_path_length`` (§6.2.1) — the SS rejects any chain where the leaf is
  more than ``max_path_length`` entities below the SS subject. inmor also
  retains a fixed depth backstop (``MAX_RESOLVE_DEPTH = 10``).
* ``permitted_subtrees`` (§6.2.2) — array of URL prefixes. The resolve
  subject MUST be a subordinate of at least one entry. Matching is
  URL-component-aware: scheme + host case-insensitive, port (or scheme
  default) equal, path is a prefix at a path-segment boundary, trailing
  slashes normalized. A subtree containing a query or fragment is treated
  as malformed.
* ``excluded_subtrees`` (§6.2.2) — array of URL prefixes the resolve
  subject MUST NOT be a subordinate of.
* ``allowed_entity_types`` / ``allowed_leaf_entity_types`` (§6.2.3) — every
  entity type the subject declares (top-level keys of its ``metadata``)
  MUST appear in the allowlist (subset semantics). A subject that declares
  even one disallowed type is rejected, so an entity cannot mix an allowed
  type with a disallowed one to slip through. A subject with no declared
  entity types is also rejected when the allowlist is set (fail-closed:
  a missing or empty ``metadata`` cannot bypass the restriction). The
  ``leaf`` variant applies only when the subject is the chain leaf.

A violation by any single Subordinate Statement causes the walker to skip
that authority and try sibling branches. The conjunction across all
superiors falls out of these per-SS checks against the same leaf.

**Example** — a Subordinate Statement issued by an intermediate that wants
to scope its subordinates to one URL subtree and limit chain depth:

.. code-block:: json

   {
     "iss": "https://intermediate.example",
     "sub": "https://leaf.example",
     "constraints": {
       "max_path_length": 1,
       "permitted_subtrees": ["https://leaf.example/"],
       "excluded_subtrees": ["https://leaf.example/banned/"],
       "allowed_entity_types": ["openid_relying_party", "federation_entity"]
     }
   }

Signed JWKS URIs (§5.2.1)
-------------------------

When an Entity Configuration sets ``signed_jwks_uri``, inmor's JWKS
resolver fetches the URL and treats the response body as a JWT whose
payload contains a JWKS. The JWT MUST be signed by a key that appears in
that same inner JWKS (self-signing, mirroring the entity-configuration
pattern). Verification covers signature, ``exp`` / ``nbf`` / ``iat``,
``kid`` resolution against the inner JWKS, and the ``crit`` allowlist.

Preference order when multiple key sources are present:

#. Inline ``jwks`` claim — used directly without a network round-trip.
#. ``signed_jwks_uri`` — fetched and verified.
#. ``jwks_uri`` — fetched, no signature on the response itself; this is
   the unsigned fallback path.

If ``signed_jwks_uri`` fetch or verification fails, the resolver logs a
warning and falls back to ``jwks_uri`` when one is configured. This
preserves resilience during signed-JWKS rollout but does introduce a
documented downgrade-attack surface: a network attacker who can disrupt
the signed path AND tamper with the unsigned path can force the
downgrade. Operators that want strict-signed-only behavior should omit
the plain ``jwks_uri``.

Verified signed-JWKS responses are **not** cached today. A Redis cache
parallel to ``inmor:jwks_cache:*`` (keyed by the URI hash, TTL bounded by
the inner JWT's ``exp``) is tracked as future work.

Transient-error retry semantics (§10.5)
---------------------------------------

Outbound federation fetches (Entity Configurations, Subordinate Statements,
JWKS) classify upstream failures into two categories:

* **Transient** — HTTP 5xx, HTTP 429, connection-level errors (TCP reset,
  connect timeout, DNS failure). ``get_query`` retries up to
  ``FETCH_MAX_RETRIES = 2`` times with exponential backoff starting at
  250 ms, capped at 1 s. When the upstream provides a ``Retry-After``
  header, the resolver honours it (capped at the backoff ceiling).
* **Permanent** — HTTP 4xx other than 429, SSRF gate denial, body cap
  exceeded, malformed UTF-8. Not retried.

The chain walker also enforces a 15-second wall-clock budget for the
combined chain-fetch phase of a ``/resolve`` request. Exceeding it is
treated as transient.

At the ``/resolve`` boundary:

* **Transient failure** → HTTP 503 ``Service Unavailable`` with a
  ``Retry-After`` header (10 s default, or the upstream's value if shorter)
  and a JSON body ``{"error": "temporarily_unavailable",
  "error_description": "..."}``. Clients should back off and retry.
* **Permanent failure** → existing HTTP 400 with ``{"error":
  "invalid_trust_chain", ...}``.

Critical-claim handling
-----------------------

Per OpenID Federation §3.1.1, an issuer may attach a ``crit`` claim listing
claim names that recipients MUST understand. The Trust Anchor enforces this
inside ``verify_jwt_with_jwks`` against a static allowlist (``KNOWN_CLAIMS``
in ``src/lib.rs``) of every claim this codebase parses. A statement whose
``crit`` contains an unknown name is rejected. During trust-chain walking
this manifests as the offending authority being skipped (the walker tries
sibling authorities); for an entity's self-signed configuration the
verification error propagates to the caller.

The allowlist is parser capability, not per-federation policy. Producer-side
per-tenant ``crit`` policy on outgoing statements is deferred to the
multi-tenant track tracked in ``multitenant_plan.md``.

Content Types
-------------

The Trust Anchor uses standard OpenID Federation content types:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Content-Type
     - Used For
   * - ``application/entity-statement+jwt``
     - Entity configurations and subordinate statements
   * - ``application/trust-mark+jwt``
     - Trust mark JWTs
   * - ``application/trust-mark-status+jwt``
     - Trust mark status responses
   * - ``application/resolve-response+jwt``
     - Entity resolution responses
   * - ``application/jwk-set+jwt``
     - Historical keys JWT
   * - ``application/json``
     - List endpoints
