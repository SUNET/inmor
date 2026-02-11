API Key Authentication
=====================

Inmor supports API key authentication for programmatic access to the Admin
API (``/api/v1/``). This allows external tools and scripts to interact with
the API without session cookies.

.. contents:: On this page
   :local:
   :depth: 2

Overview
--------

API keys provide an alternative to session-based authentication. They are
useful for:

* Automated scripts and CI/CD pipelines
* External monitoring tools
* Third-party integrations

Each API key is:

* Tied to a specific Django user account
* Stored as a SHA-256 hash (the plaintext is shown only once at creation)
* Optionally time-limited with an expiry date
* Revocable at any time

Creating an API Key
-------------------

Only Django superusers can create API keys through the admin interface.

1. Log in to the Django admin at ``/admin/``
2. Navigate to **API Keys** in the sidebar
3. Click **Add API Key**
4. Fill in the form:

   - **Name**: A descriptive label (e.g. "CI pipeline", "monitoring")
   - **User**: The Django user this key acts as
   - **Expires at**: Optional expiration date/time (leave blank for no expiry)

5. Click **Save**
6. **Copy the displayed key immediately** -- it will not be shown again

.. warning::

   The plaintext API key is displayed **only once** after creation. If you
   lose it, you must create a new key.

Or you can generate it via command line for the cases where you don't have frontend enabled.

.. code-block:: bash

    docker compose exec -T -e DJANGO_SUPERUSER_PASSWORD=UPDATETOalargePASSPHRASE_HERE admin python manage.py setup_admin --username admin --noinput --skip-checks
    docker compose exec -T admin python manage.py create_api_key --username admin --skip-checks

Using an API Key
----------------

Pass the key in the ``X-API-Key`` HTTP header:

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY_HERE" \
        https://your-server/api/v1/trustmarktypes

All ``/api/v1/`` endpoints accept either a session cookie or an API key.
Both authentication methods grant the same access.

Examples
^^^^^^^^

**List trust mark types:**

.. code-block:: bash

   curl -H "X-API-Key: YOUR_KEY_HERE" \
        https://your-server/api/v1/trustmarktypes

**Create a subordinate:**

.. code-block:: bash

   curl -X POST \
        -H "X-API-Key: YOUR_KEY_HERE" \
        -H "Content-Type: application/json" \
        -d '{"entityid": "https://example.com", "organization": "Example Org"}' \
        https://your-server/api/v1/subordinates

**Regenerate server entity statement:**

.. code-block:: bash

   curl -X POST \
        -H "X-API-Key: YOUR_KEY_HERE" \
        https://your-server/api/v1/server/entity

Managing API Keys
-----------------

Viewing Keys
^^^^^^^^^^^^

In the Django admin under **API Keys**, you can see all keys with:

* **Name** and **Key Prefix** (first 8 characters for identification)
* **Status** (Valid/Invalid)
* **Created**, **Expires**, and **Last Used** timestamps

Revoking Keys
^^^^^^^^^^^^^

To revoke a single key:

1. Click on the key in the admin list
2. Uncheck **Is active**
3. Click **Save**

To revoke multiple keys at once:

1. Select the keys using the checkboxes
2. Choose **Revoke selected API keys** from the action dropdown
3. Click **Go**

Revoked keys cannot be reactivated -- create a new key instead.

Security Best Practices
-----------------------

* **Always use HTTPS** -- API keys are sent in headers and must be
  encrypted in transit
* **Set expiry dates** -- avoid permanent keys when possible
* **Use descriptive names** -- makes it easy to identify and audit keys
* **Revoke unused keys** -- regularly review and clean up old keys
* **One key per client** -- don't share keys between different services
* **Store keys securely** -- treat them like passwords; use environment
  variables or a secrets manager

How It Works
------------

The authentication flow:

1. Client sends request with ``X-API-Key: <key>`` header
2. ``APIKeyAuthentication`` (in ``inmoradmin/auth.py``) extracts the header
3. The key is hashed with SHA-256 and looked up in the database
4. If found, active, and not expired, the request is authenticated as the
   key's associated user
5. The ``last_used_at`` timestamp is updated

The API router in ``inmoradmin/api.py`` accepts both session and API key
authentication via ``combined_auth``, so existing session-based workflows
(including the Vue frontend) continue to work unchanged.
