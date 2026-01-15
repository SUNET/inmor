Subordinate Management
======================

Subordinates are entities that register with the Trust Anchor to participate
in the federation. The Trust Anchor issues signed subordinate statements
that establish trust chains.

Understanding Subordinates
--------------------------

A subordinate can be:

* **OpenID Provider (OP)**: Identity providers that authenticate users
* **Relying Party (RP)**: Applications that rely on OPs for authentication
* **Intermediate Authority (IA)**: Sub-Trust Anchors in hierarchical federations

When an entity registers as a subordinate:

1. The TA verifies the entity's self-signed configuration
2. The TA checks that it's listed in the entity's ``authority_hints``
3. The TA validates metadata against its policy
4. The TA creates and signs a subordinate statement
5. The statement is stored and made available via the ``/fetch`` endpoint

Prerequisites
-------------

Before registering a subordinate, the entity must:

1. **Publish Entity Configuration**: The entity must serve a signed JWT at
   ``/.well-known/openid-federation``

2. **Include Authority Hints**: The entity's configuration must include
   your Trust Anchor in its ``authority_hints``

3. **Provide Valid Metadata**: The entity must have valid OpenID Federation
   metadata

**Example Entity Configuration (simplified):**

.. code-block:: json

   {
     "iss": "https://example-rp.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "authority_hints": ["https://federation.example.com"],
     "jwks": {
       "keys": [...]
     },
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"],
         "response_types": ["code"],
         "grant_types": ["authorization_code"]
       }
     }
   }

Registering a Subordinate
-------------------------

Basic Registration
^^^^^^^^^^^^^^^^^^

Fetch the entity's configuration and register it:

.. code-block:: bash

   # Step 1: Fetch entity configuration
   ENTITY_JWT=$(curl -s https://example-rp.com/.well-known/openid-federation)

   # Step 2: Extract metadata and JWKS (using Python)
   python3 << 'EOF'
   import json
   from jwcrypto import jwt

   entity_jwt = "..."  # paste the JWT
   jose = jwt.JWT.from_jose_token(entity_jwt)
   payload = json.loads(jose.token.objects["payload"])

   print(json.dumps({
       "entityid": payload["sub"],
       "metadata": payload["metadata"],
       "jwks": payload["jwks"],
       "forced_metadata": {}
   }))
   EOF

   # Step 3: Register with the TA
   curl -X POST http://localhost:8000/api/v1/subordinates \
     -H "Content-Type: application/json" \
     -d '{
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
       "forced_metadata": {}
     }'

**Response (201 Created):**

.. code-block:: json

   {
     "id": 1,
     "entityid": "https://example-rp.com",
     "metadata": {...},
     "forced_metadata": {},
     "jwks": {...},
     "valid_for": 8760,
     "autorenew": true,
     "active": true
   }

Validation Process
^^^^^^^^^^^^^^^^^^

During registration, the API performs these validations:

1. **Fetch Entity Configuration**: Downloads and parses the entity's
   ``/.well-known/openid-federation`` JWT

2. **Verify Signature**: Validates the JWT signature using the provided JWKS

3. **Check Authority Hints**: Confirms your TA domain is in the entity's
   ``authority_hints`` list

4. **Validate Metadata Policy**: Applies your TA's metadata policy to ensure
   the entity's metadata conforms to your requirements

5. **Create Statement**: Generates a signed subordinate statement

Registration with Forced Metadata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use ``forced_metadata`` to override or add metadata values that the TA
enforces for all statements:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates \
     -H "Content-Type: application/json" \
     -d '{
       "entityid": "https://example-op.com",
       "metadata": {
         "openid_provider": {
           "issuer": "https://example-op.com",
           "authorization_endpoint": "https://example-op.com/authorize",
           "token_endpoint": "https://example-op.com/token"
         }
       },
       "jwks": {...},
       "forced_metadata": {
         "openid_provider": {
           "subject_types_supported": ["public", "pairwise"],
           "id_token_signing_alg_values_supported": ["ES256", "RS256"]
         }
       }
     }'

The ``forced_metadata`` is merged into the subordinate statement, overriding
any conflicting values from the entity's own metadata.

Registration with Additional Claims
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add custom claims to the subordinate statement:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates \
     -H "Content-Type: application/json" \
     -d '{
       "entityid": "https://example-rp.com",
       "metadata": {...},
       "jwks": {...},
       "forced_metadata": {},
       "additional_claims": {
         "organization_name": "Example Corp",
         "registration_date": "2024-01-15",
         "sector": "finance"
       }
     }'

Custom Validity Period
^^^^^^^^^^^^^^^^^^^^^^

Set a custom validity period (cannot exceed system default):

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates \
     -H "Content-Type: application/json" \
     -d '{
       "entityid": "https://example-rp.com",
       "metadata": {...},
       "jwks": {...},
       "forced_metadata": {},
       "valid_for": 720
     }'

Viewing Subordinates
--------------------

List All Subordinates
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   curl http://localhost:8000/api/v1/subordinates

**Response:**

.. code-block:: json

   {
     "count": 3,
     "items": [
       {
         "id": 1,
         "entityid": "https://example-rp.com",
         "metadata": {...},
         "forced_metadata": {},
         "jwks": {...},
         "valid_for": 8760,
         "autorenew": true,
         "active": true
       }
     ]
   }

Get Subordinate by ID
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   curl http://localhost:8000/api/v1/subordinates/1

Via Trust Anchor (Public)
^^^^^^^^^^^^^^^^^^^^^^^^^

External parties can list subordinates via the Trust Anchor API:

.. code-block:: bash

   # List all subordinates
   curl https://federation.example.com/list

   # List only OpenID Providers
   curl "https://federation.example.com/list?entity_type=openid_provider"

   # List only Relying Parties
   curl "https://federation.example.com/list?entity_type=openid_relying_party"

   # List subordinates with a specific trust mark
   curl "https://federation.example.com/list?trust_mark_type=https://example.com/trustmarks/member"

Updating Subordinates
---------------------

Update a subordinate's configuration:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates/1 \
     -H "Content-Type: application/json" \
     -d '{
       "metadata": {...},
       "forced_metadata": {
         "openid_relying_party": {
           "application_type": "web"
         }
       },
       "jwks": {...},
       "autorenew": false
     }'

The update process:

1. Re-fetches the entity's current configuration
2. Re-validates against TA policy
3. Creates a new signed subordinate statement
4. Updates database and Redis

Disabling Subordinates
----------------------

Disable a subordinate without removing it:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates/1 \
     -H "Content-Type: application/json" \
     -d '{
       "metadata": {...},
       "forced_metadata": {...},
       "jwks": {...},
       "active": false
     }'

When ``active`` is false:

* The subordinate statement is no longer served via ``/fetch``
* The entity is removed from ``/list`` results
* Existing trust chains become invalid

Subordinate Statement Structure
-------------------------------

The Trust Anchor creates subordinate statements with this structure:

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "jwks": {
       "keys": [...]
     },
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example-rp.com/callback"],
         "application_type": "web"
       }
     },
     "metadata_policy": {},
     "organization_name": "Example Corp"
   }

Key fields:

* ``iss``: Trust Anchor entity ID
* ``sub``: Subordinate entity ID
* ``jwks``: Entity's public keys (for chain verification)
* ``metadata``: Merged and policy-applied metadata
* ``metadata_policy``: Any policy the subordinate should apply to its subordinates

Fetching Subordinate Statements
-------------------------------

External parties fetch subordinate statements via the Trust Anchor:

.. code-block:: bash

   curl "https://federation.example.com/fetch?sub=https://example-rp.com"

**Response:** Signed subordinate statement JWT

Resolving Trust Chains
----------------------

The ``/resolve`` endpoint builds complete trust chains:

.. code-block:: bash

   curl "https://federation.example.com/resolve?sub=https://example-rp.com&trust_anchor=https://federation.example.com"

**Response:** Resolution JWT containing:

* Final resolved metadata (after policy application)
* Complete trust chain (array of JWTs)

Entity Types
------------

Subordinates are categorized by their metadata:

OpenID Relying Party
^^^^^^^^^^^^^^^^^^^^

Entities with ``openid_relying_party`` metadata:

.. code-block:: json

   {
     "metadata": {
       "openid_relying_party": {
         "redirect_uris": ["https://example.com/callback"],
         "response_types": ["code"],
         "grant_types": ["authorization_code"],
         "client_name": "Example Application"
       }
     }
   }

OpenID Provider
^^^^^^^^^^^^^^^

Entities with ``openid_provider`` metadata:

.. code-block:: json

   {
     "metadata": {
       "openid_provider": {
         "issuer": "https://example-op.com",
         "authorization_endpoint": "https://example-op.com/authorize",
         "token_endpoint": "https://example-op.com/token",
         "jwks_uri": "https://example-op.com/jwks"
       }
     }
   }

Federation Entity (Intermediate Authority)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Entities with ``federation_entity`` metadata that act as intermediate
authorities:

.. code-block:: json

   {
     "metadata": {
       "federation_entity": {
         "federation_fetch_endpoint": "https://intermediate.example.com/fetch",
         "federation_list_endpoint": "https://intermediate.example.com/list"
       }
     }
   }

Metadata Policy
---------------

The Trust Anchor can enforce metadata policy on subordinates.

Configure policy in ``localsettings.py``:

.. code-block:: python

   POLICY_DOCUMENT = {
       "metadata_policy": {
           "openid_relying_party": {
               "grant_types": {
                   "subset_of": ["authorization_code", "refresh_token"]
               },
               "response_types": {
                   "subset_of": ["code"]
               }
           },
           "openid_provider": {
               "subject_types_supported": {
                   "subset_of": ["public", "pairwise"]
               },
               "id_token_signing_alg_values_supported": {
                   "superset_of": ["ES256"]
               }
           }
       }
   }

Policy Operators
^^^^^^^^^^^^^^^^

* ``subset_of``: Value must be subset of allowed values
* ``superset_of``: Value must include all required values
* ``one_of``: Single value must be one of allowed values
* ``add``: Add values to the claim
* ``default``: Default value if claim is missing
* ``essential``: Claim is required

When an entity's metadata violates the policy, registration fails with
a 400 error.

Auto-Renewal
------------

Enable auto-renewal to keep subordinate statements fresh:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/subordinates/1 \
     -H "Content-Type: application/json" \
     -d '{
       ...,
       "autorenew": true
     }'

With auto-renewal:

* The statement is refreshed before expiry
* Entity configuration is re-fetched and re-validated
* New signed statement is generated

Workflow Example
----------------

Complete workflow for onboarding a new subordinate:

1. **Entity Preparation**

   The entity must:

   * Generate signing keys
   * Create entity configuration with your TA in ``authority_hints``
   * Publish at ``/.well-known/openid-federation``

2. **Verification (Manual)**

   Verify the entity meets your federation's requirements before registration.

3. **Registration**

   .. code-block:: bash

      # Fetch entity's published configuration
      curl -s https://new-entity.example.com/.well-known/openid-federation

      # Register with the TA
      curl -X POST http://localhost:8000/api/v1/subordinates \
        -H "Content-Type: application/json" \
        -d '{
          "entityid": "https://new-entity.example.com",
          "metadata": {...},
          "jwks": {...},
          "forced_metadata": {}
        }'

4. **Issue Trust Marks** (optional)

   .. code-block:: bash

      curl -X POST http://localhost:8000/api/v1/trustmarks \
        -H "Content-Type: application/json" \
        -d '{
          "tmt": 1,
          "domain": "https://new-entity.example.com"
        }'

5. **Verification**

   Confirm the entity appears in listings:

   .. code-block:: bash

      curl https://federation.example.com/list

   Verify the subordinate statement:

   .. code-block:: bash

      curl "https://federation.example.com/fetch?sub=https://new-entity.example.com"

Troubleshooting
---------------

Registration Fails with 400
^^^^^^^^^^^^^^^^^^^^^^^^^^^

* **Authority hints missing**: Entity's configuration must include your TA
  in ``authority_hints``
* **Policy violation**: Entity's metadata doesn't conform to your policy
* **Signature verification failed**: JWKS doesn't match the entity's
  published configuration

Registration Fails with 403
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Entity is already registered. Use the update endpoint instead.

Entity Not Appearing in List
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Check that ``active`` is true
* Verify the subordinate statement was created
* Check Redis contains the entity data

Check entity type filtering:

.. code-block:: bash

   # Verify entity type in metadata
   curl http://localhost:8000/api/v1/subordinates/1

   # Try different entity_type filters
   curl "https://federation.example.com/list?entity_type=openid_relying_party"
