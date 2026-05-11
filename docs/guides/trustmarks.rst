Trust Mark Management
=====================

Trust marks are signed assertions about entities in the federation.
They indicate that an entity meets certain criteria or belongs to a
specific category defined by the trust mark type.

Understanding Trust Marks
-------------------------

A trust mark consists of:

* **Trust Mark Type**: A URL identifier defining the type/category
* **Subject**: The entity the trust mark is issued to
* **Issuer**: The Trust Anchor issuing the mark
* **Validity**: Issuance time and expiry

Trust marks are signed JWTs that can be verified by any federation participant.

Creating Trust Mark Types
-------------------------

Before issuing trust marks, define the trust mark types your federation supports.

**Example: Creating a membership trust mark type**

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarktypes \
     -H "Content-Type: application/json" \
     -d '{
       "tmtype": "https://federation.example.com/trustmarks/member",
       "valid_for": 8760,
       "autorenew": true,
       "renewal_time": 48,
       "active": true
     }'

**Response:**

.. code-block:: json

   {
     "id": 1,
     "tmtype": "https://federation.example.com/trustmarks/member",
     "valid_for": 8760,
     "autorenew": true,
     "renewal_time": 48,
     "active": true
   }

Trust Mark Type Parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Parameter
     - Description
   * - ``tmtype``
     - URL identifier for the trust mark type. This should be a URL you control.
   * - ``valid_for``
     - Maximum validity period for trust marks in hours. Individual marks can have shorter validity but not longer.
   * - ``autorenew``
     - If true, trust marks of this type will be automatically renewed before expiry.
   * - ``renewal_time``
     - Hours before expiry when renewal should occur.
   * - ``active``
     - If false, no new trust marks of this type can be issued.

Common Trust Mark Types
^^^^^^^^^^^^^^^^^^^^^^^

* **Membership**: Entity is a member of an organization
* **Certification**: Entity has passed a certification process
* **Compliance**: Entity complies with specific requirements
* **Accreditation**: Entity is accredited by an authority

Issuing Trust Marks
-------------------

Issue a trust mark to an entity:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks \
     -H "Content-Type: application/json" \
     -d '{
       "tmt": 1,
       "domain": "https://example-rp.com"
     }'

**Response:**

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
     "mark": "eyJhbGciOiJFUzI1NiIsInR5cCI6InRydXN0LW1hcmsrand0In0...",
     "additional_claims": null
   }

Trust Mark with Additional Claims
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add custom claims to the trust mark JWT:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks \
     -H "Content-Type: application/json" \
     -d '{
       "tmt": 1,
       "domain": "https://example-rp.com",
       "additional_claims": {
         "ref": "https://federation.example.com/verification/123",
         "certification_date": "2024-01-15",
         "certification_level": "gold"
       }
     }'

The ``additional_claims`` appear directly in the trust mark JWT payload:

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "sub": "https://example-rp.com",
     "iat": 1705315200,
     "exp": 1736851200,
     "trust_mark_type": "https://federation.example.com/trustmarks/member",
     "ref": "https://federation.example.com/verification/123",
     "certification_date": "2024-01-15",
     "certification_level": "gold"
   }

Trust Mark with Custom Validity
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Issue a trust mark with shorter validity than the type default:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks \
     -H "Content-Type: application/json" \
     -d '{
       "tmt": 1,
       "domain": "https://example-rp.com",
       "valid_for": 720
     }'

.. note::

   The ``valid_for`` value cannot exceed the trust mark type's ``valid_for``.

Viewing Trust Marks
-------------------

List All Trust Marks
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   curl http://localhost:8000/api/v1/trustmarks

List Trust Marks for an Entity
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks/list \
     -H "Content-Type: application/json" \
     -d '{"domain": "https://example-rp.com"}'

Renewing Trust Marks
--------------------

Manually renew a trust mark:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/v1/trustmarks/1/renew

This generates a new JWT with updated ``iat`` and ``exp`` claims while
preserving all other trust mark properties.

Automatic Renewal
^^^^^^^^^^^^^^^^^

Trust marks with ``autorenew: true`` will be automatically renewed when:

1. The ``renewal_time`` threshold is reached (e.g., 48 hours before expiry)
2. The trust mark type is active
3. The trust mark itself is active

The ``reload_issued_tms`` management command handles automatic renewal:

.. code-block:: bash

   docker compose exec admin python manage.py reload_issued_tms

This command is run automatically when the admin container starts.

Revoking Trust Marks
--------------------

Revoke a trust mark by setting it to inactive:

.. code-block:: bash

   curl -X PUT http://localhost:8000/api/v1/trustmarks/1 \
     -H "Content-Type: application/json" \
     -d '{"active": false}'

When a trust mark is revoked:

1. The ``mark`` field is cleared (set to null)
2. Redis is updated to mark the trust mark as "revoked"
3. The entity is removed from the trust mark type's member list
4. Status checks return "revoked" for the old JWT

Updating Trust Mark Claims
--------------------------

Update the additional claims in a trust mark:

.. code-block:: bash

   curl -X PUT http://localhost:8000/api/v1/trustmarks/1 \
     -H "Content-Type: application/json" \
     -d '{
       "additional_claims": {
         "ref": "https://updated-reference.example.com",
         "certification_level": "platinum"
       }
     }'

This generates a new JWT with the updated claims.

Verifying Trust Marks
---------------------

Public Verification
^^^^^^^^^^^^^^^^^^^

Any federation participant can verify a trust mark by calling the
trust mark status endpoint:

.. code-block:: bash

   # Get the trust mark JWT
   TRUST_MARK=$(curl -s "https://federation.example.com/trust_mark?trust_mark_type=https://federation.example.com/trustmarks/member&sub=https://example-rp.com")

   # Verify its status
   curl -X POST https://federation.example.com/trust_mark_status \
     -d "trust_mark=$TRUST_MARK"

**Status Response:**

.. code-block:: json

   {
     "iss": "https://federation.example.com",
     "iat": 1705315200,
     "status": "active",
     "sub": "https://example-rp.com",
     "trust_mark_type": "https://federation.example.com/trustmarks/member"
   }

Status Values
^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Status
     - Meaning
   * - ``active``
     - Trust mark is valid, not expired, and not revoked
   * - ``revoked``
     - Trust mark was explicitly revoked by the issuer
   * - ``expired``
     - Trust mark JWT has passed its expiry time
   * - ``invalid``
     - Signature verification failed or unknown issuer

Listing Trust Mark Holders
--------------------------

Get all entities with a specific trust mark:

**Via Trust Anchor API:**

.. code-block:: bash

   curl "https://federation.example.com/trust_mark_list?trust_mark_type=https://federation.example.com/trustmarks/member"

**Response:**

.. code-block:: json

   [
     "https://example-rp.com",
     "https://other-entity.com",
     "https://federation.example.com"
   ]

**Via Subordinate List with Filter:**

.. code-block:: bash

   curl "https://federation.example.com/list?trust_mark_type=https://federation.example.com/trustmarks/member"

Trust Marks for the Trust Anchor
--------------------------------

The Trust Anchor itself can have trust marks issued by external parties.
Configure these in ``localsettings.py``:

.. code-block:: python

   TA_TRUSTMARKS = [
       {
           "trust_mark_type": "https://root-ta.example.com/trustmarks/verified-anchor",
           "mark": "eyJhbGciOiJFUzI1NiIsInR5cCI6InRydXN0LW1hcmsrand0In0..."
       },
       {
           "trust_mark_type": "https://accreditation.example.com/trustmarks/certified",
           "mark": "eyJ..."
       }
   ]

These trust marks appear in the TA's entity configuration (``/.well-known/openid-federation``).

Trusted Trust Mark Issuers (Federation Recognition)
---------------------------------------------------

OpenID Federation §3.1.2 defines the ``trust_mark_issuers`` claim on a Trust
Anchor's entity configuration. It tells the federation which combinations of
trust mark type and issuer are recognised. Inmor publishes this claim on
``/.well-known/openid-federation`` and uses it during ``/resolve`` (§8.3) to
decide which trust marks may be included in the resolve response.

The recognised list is built from two sources:

1. **External issuers** — configured via ``TA_TRUSTED_TRUSTMARK_ISSUERS`` in
   ``localsettings.py`` (a Python ``dict[str, list[str]]`` mapping trust mark
   type URL to a list of allowed issuer entity IDs). This is the authoritative
   source for issuers other than this TA itself.
2. **Self-issuance** — for every active ``TrustMarkType`` row in the admin
   database, this TA's own entity ID
   (``settings.TRUSTMARK_PROVIDER`` — the ``iss`` of every trust mark issued
   by this admin) is appended automatically. Operators do not need to restate
   this in ``localsettings.py``.

.. code-block:: python

   # localsettings.py — only external issuers go here
   TA_TRUSTED_TRUSTMARK_ISSUERS = {
       "https://refeds.org/trustmarks/sirtfi": ["https://swamid.se"],
       "https://openid.net/certification/op": [],   # any issuer (per §3.1.2)
   }

After changing this setting (or after adding/removing ``TrustMarkType`` rows),
run the management command to refresh the published entity configuration:

.. code-block:: bash

   docker compose exec admin python manage.py regenerate_entity

Per spec §3.1.2, an empty list for a given type means "anyone may issue trust
marks with that identifier"; signature, expiry, and (for external issuers)
revocation status are still verified.

How ``/resolve`` Uses the List
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For every trust mark on a resolved subject, the Rust TA:

1. Skips the mark if its ``trust_mark_type`` is not a key in
   ``trust_mark_issuers``.
2. Skips the mark if its ``iss`` is not in the allowed list for that type
   (empty list bypasses this check).
3. **For TA-issued marks** (``iss`` equals this TA): verifies the signature
   against this TA's public keyset and checks Redis for a revocation entry.
4. **For external-issued marks**: fetches the issuer's entity configuration,
   discovers the issuer's
   ``federation_trust_mark_status_endpoint`` from its ``federation_entity``
   metadata, ``POST``\ s the trust mark to that endpoint, and verifies the
   response JWT signature against the issuer's JWKS. The mark is included
   only if the response's ``status`` claim is ``"active"``.

The behaviour is **fail-closed**: any error (network failure, missing status
endpoint, signature failure, non-active status, malformed JWT) causes that
single trust mark to be omitted from the resolve response. The rest of the
resolve still succeeds. Skipped marks are logged at WARN.

If an external issuer does **not** advertise
``federation_trust_mark_status_endpoint``, marks issued by it are omitted from
the resolve response (and logged at WARN, like every other skipped mark).
Issuers that want their marks honoured by Inmor MUST publish a status endpoint
(per spec §8.4.1).

The resolve response's ``exp`` claim is the minimum of every trust chain
``exp`` and every included trust mark's ``exp`` (per spec §8.3.2).

Best Practices
--------------

1. **Use Meaningful Type URLs**: Trust mark type URLs should be under your
   control and document what the mark represents.

2. **Set Appropriate Validity**: Balance security (shorter validity) with
   operational overhead (more frequent renewals).

3. **Enable Auto-Renewal**: For operational trust marks, enable auto-renewal
   to prevent accidental expiry.

4. **Document Requirements**: Clearly document what criteria an entity must
   meet to receive each trust mark type.

5. **Use Additional Claims**: Include reference URLs or other metadata that
   help verify the basis for the trust mark.

6. **Regular Audits**: Periodically review issued trust marks and revoke
   any that are no longer valid.

Workflow Example
----------------

Complete workflow for managing trust marks:

1. **Define Trust Mark Type:**

   .. code-block:: bash

      curl -X POST http://localhost:8000/api/v1/trustmarktypes \
        -H "Content-Type: application/json" \
        -d '{
          "tmtype": "https://federation.example.com/trustmarks/verified-rp",
          "valid_for": 4320,
          "autorenew": true
        }'

2. **Register Entity (if not already registered):**

   See :doc:`subordinates` for entity registration.

3. **Issue Trust Mark:**

   .. code-block:: bash

      curl -X POST http://localhost:8000/api/v1/trustmarks \
        -H "Content-Type: application/json" \
        -d '{
          "tmt": 1,
          "domain": "https://verified-rp.example.com",
          "additional_claims": {
            "verification_date": "2024-01-15",
            "ref": "https://federation.example.com/verifications/abc123"
          }
        }'

4. **Entity Retrieves Trust Mark:**

   .. code-block:: bash

      curl "https://federation.example.com/trust_mark?trust_mark_type=https://federation.example.com/trustmarks/verified-rp&sub=https://verified-rp.example.com"

5. **Other Parties Verify:**

   .. code-block:: bash

      curl -X POST https://federation.example.com/trust_mark_status \
        -d "trust_mark=eyJ..."
