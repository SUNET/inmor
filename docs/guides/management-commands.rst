Management Commands
===================

Inmor's Admin portal provides custom Django management commands for operational
tasks. These commands are run via ``python manage.py <command>`` (or
``docker compose exec admin python manage.py <command>`` in a Docker deployment).

apikey
------

Manage API keys: create, list, or revoke. This is the primary command for API
key lifecycle management.

**Create a key**::

   python manage.py apikey create --username admin --key-name "CI deploy"
   python manage.py apikey create --username admin --key-name "monitoring" --tenant prod

The plaintext key is printed to stdout. Store it securely — it cannot be
retrieved again.

Options:

* ``--username`` (required) — Owner of the key.
* ``--key-name`` — Descriptive label (default: ``auto-generated``).
* ``--tenant`` — Tenant the key belongs to (default: ``default``).

**List keys**::

   python manage.py apikey list --username admin
   python manage.py apikey list --all

One of ``--username`` or ``--all`` is required. Output includes name, prefix,
tenant, active status, creation date, expiry, and last-used timestamp.

**Revoke a key**::

   python manage.py apikey revoke --username admin --key-name "CI deploy"

Deactivates all active keys matching the given name for the user.

reload_issued_tms
-----------------

Reload existing trust mark JWTs from the database into Redis. This does **not**
re-sign anything — it reads the stored ``mark`` field from each active
``TrustMark`` row and inserts its SHA-256 hash into the ``inmor:tm:alltime``
Redis set.

::

   python manage.py reload_issued_tms

Use this after a Redis restart or data loss to restore trust mark lookup data
without re-issuing.

reissue_alltms
--------------

Re-sign and re-issue every active trust mark. For each active ``TrustMark`` in
the database, a new JWT is generated with the current signing key and validity
period, and the result is written to Redis.

::

   python manage.py reissue_alltms

Use this after a key rotation to ensure all trust marks are signed with the
new key.

readd_subordinates
------------------

Re-synchronise subordinates from the database to Redis. Clears the
``inmor:subordinates`` Redis hash and re-adds every subordinate from
PostgreSQL.

::

   python manage.py readd_subordinates

Use this after a Redis flush or if the Redis subordinate data is out of sync
with the database.

pre_migrate_check
-----------------

Pre-migration safety check for the ``CharField`` to ``JSONField`` schema
migration (introduced in 0.2.3). Scans every ``Subordinate`` row and:

1. Converts empty-string ``metadata`` and ``forced_metadata`` values to ``{}``.
2. Validates that all values are valid JSON.

::

   python manage.py pre_migrate_check

If invalid JSON is found, the command prints the offending rows and aborts.
This command runs automatically in the Docker entrypoint before ``migrate``,
but can also be run manually.

.. note::

   If the columns are already ``jsonb`` (migration already applied), the
   command exits immediately with no changes.

create_api_key
--------------

Simplified single-purpose command to create an API key. This is an older
alternative to ``apikey create`` and does not support tenant assignment or
listing/revoking.

::

   python manage.py create_api_key --username admin
   python manage.py create_api_key --username admin --key-name "CI script key"

The plaintext key is printed to stdout. For full API key management, prefer
the ``apikey`` command instead.
