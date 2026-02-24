Audit Logging
=============

Inmor tracks all state-changing API operations in an audit log. Every
create and update is recorded with who made the change, how they
authenticated, and what exactly changed.

.. contents:: On this page
   :local:
   :depth: 2

Overview
--------

The audit log captures:

* **Who**: User and authentication method (session or API key)
* **What**: Action (CREATE/UPDATE), resource type, and resource ID
* **When**: Timestamp of the operation
* **How**: Full before/after snapshots and a field-level diff
* **Tenant**: Tenant identifier from the authentication context

Only state-changing endpoints are logged. Read operations (list, get)
are not recorded.

Logged Operations
-----------------

**TrustMarkType** (2 endpoints):

* ``POST /api/v1/trustmarktypes`` — CREATE
* ``PUT /api/v1/trustmarktypes/{id}`` — UPDATE

**TrustMark** (3 endpoints):

* ``POST /api/v1/trustmarks`` — CREATE
* ``POST /api/v1/trustmarks/{id}/renew`` — UPDATE (renew)
* ``PUT /api/v1/trustmarks/{id}`` — UPDATE

**Subordinate** (2 endpoints):

* ``POST /api/v1/subordinates`` — CREATE
* ``POST /api/v1/subordinates/{id}`` — UPDATE

Event Types
-----------

Each audit log entry has an ``event_type`` derived from the operation:

**Subordinate events** (per OpenID Federation Subordinate Events spec):

* ``registration`` — new subordinate created
* ``revocation`` — subordinate deactivated (``active=False``)
* ``metadata_update`` — metadata changed
* ``metadata_policy_update`` — forced_metadata changed
* ``jwks_update`` — JWKS changed

When multiple fields change, the most significant event wins
(revocation > metadata_policy_update > metadata_update > jwks_update).

**TrustMarkType events**:

* ``trustmarktype_created``
* ``trustmarktype_deactivated``
* ``trustmarktype_updated``

**TrustMark events**:

* ``trustmark_issued``
* ``trustmark_renewed``
* ``trustmark_revoked``
* ``trustmark_updated``

Querying the Audit Log
----------------------

**List entries** (paginated):

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY" \
        "https://your-server/api/v1/auditlog"

**Filter by resource type**:

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY" \
        "https://your-server/api/v1/auditlog?resource_type=TrustMarkType"

**Filter by action**:

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY" \
        "https://your-server/api/v1/auditlog?action=CREATE"

**Filter by event type**:

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY" \
        "https://your-server/api/v1/auditlog?event_type=registration"

**Get a single entry with full snapshots**:

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY" \
        "https://your-server/api/v1/auditlog/42"

Response Fields
^^^^^^^^^^^^^^^

Each audit log entry contains:

* ``timestamp`` — when the operation occurred
* ``username`` — who made the change
* ``auth_method`` — ``session`` or ``api_key``
* ``tenant`` — tenant identifier
* ``action`` — ``CREATE`` or ``UPDATE``
* ``resource_type`` — model name (e.g. ``Subordinate``)
* ``resource_repr`` — human-readable identifier
* ``diff`` — field-level changes (for updates)
* ``event_type`` — spec-defined event type

Django Admin
------------

Audit log entries are visible in the Django admin at
``/admin/auditlog/auditlogentry/``. The admin view is read-only —
entries cannot be created, modified, or deleted through the admin
interface.

The list view supports filtering by action, resource type, auth method,
tenant, success status, and event type.
