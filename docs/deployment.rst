Docker Compose Deployment
=========================

This guide covers deploying Inmor using Docker Compose for production environments.

.. danger::

   **Security Critical: Protect the Admin API**

   The Admin API (port 8000) provides full management access to the Trust Anchor,
   including the ability to:

   * Create and revoke trust marks
   * Add and remove subordinate entities
   * Modify the Trust Anchor's entity configuration

   **In production, you MUST secure the Admin API behind authentication.**
   At minimum, use HTTP Basic Authentication at the reverse proxy level.
   Consider additional measures such as:

   * IP allowlisting (restrict to management network)
   * VPN-only access
   * Client certificate authentication (mTLS)
   * OAuth2/OIDC authentication

   **Never expose the Admin API directly to the internet without authentication.**

   See :doc:`reverse-proxy` for configuration examples.

Architecture
------------

The Docker Compose setup includes four services:

* **ta** - Trust Anchor (Rust) on port 8080
* **admin** - Admin Portal (Django) on port 8000
* **db** - PostgreSQL 14 database
* **redis** - Redis 7 for caching and federation data

.. code-block:: yaml

   services:
     ta:
       image: docker.sunet.se/inmor:0.2.0
       ports:
         - "8080:8080"
       depends_on:
         redis:
           condition: service_healthy

     admin:
       image: docker.sunet.se/inmor-admin:0.2.0
       ports:
         - "8000:8000"
       depends_on:
         db:
           condition: service_healthy
         redis:
           condition: service_healthy
         ta:
           condition: service_healthy

     db:
       image: postgres:14-alpine
       ports:
         - "5432:5432"

     redis:
       image: redis:7-alpine

Production Deployment
---------------------

For production, you typically deploy behind a reverse proxy (nginx, Apache, Traefik)
that handles TLS termination. The internal services communicate over HTTP.

1. Create production configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create a ``docker-compose.prod.yml`` override::

   services:
     ta:
       ports:
         - "127.0.0.1:8080:8080"  # Only bind to localhost
       environment:
         - RUST_LOG=info

     admin:
       ports:
         - "127.0.0.1:8000:8000"  # Only bind to localhost
       volumes:
         - ./localsettings.py:/app/inmoradmin/localsettings.py

     db:
       ports: []  # Don't expose to host
       environment:
         - POSTGRES_PASSWORD=your_secure_password

2. Create production settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create ``localsettings.py`` for Django::

   # Production settings override
   DEBUG = False
   ALLOWED_HOSTS = ['your-domain.example.com', 'admin.your-domain.example.com']
   SECRET_KEY = 'your-production-secret-key'

   # Use your production domain
   TA_DOMAIN = 'https://federation.your-domain.example.com'
   TRUSTMARK_PROVIDER = 'https://federation.your-domain.example.com'

   # Trust marks issued to the TA itself
   TA_TRUSTMARKS = [
       {
           "trust_mark_type": "https://your-domain.example.com/trustmark/member",
           "mark": "eyJ...<JWT>..."  # Pre-issued trust mark JWT
       }
   ]

   # Trusted trust mark issuers
   TA_TRUSTED_TRUSTMARK_ISSUERS = {
       "https://other-ta.example.com/trustmark/verified": [
           "https://other-ta.example.com"
       ]
   }

3. Create production taconfig.toml
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Update ``taconfig.toml`` for production::

   domain = "https://federation.your-domain.example.com"
   redis_uri = "redis://redis:6379"

   # TLS is handled by reverse proxy, so these can be self-signed or omitted
   # tls_cert = "cert.pem"
   # tls_key = "key.pem"

4. Deploy with production compose
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

Volume Mounts
-------------

The following volumes should be mounted for production:

Trust Anchor (ta)
^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Volume
     - Description
   * - ``./taconfig.toml:/app/taconfig.toml``
     - TA configuration file
   * - ``./private.json:/app/private.json``
     - Primary signing key
   * - ``./publickeys:/app/publickeys``
     - Public keys directory
   * - ``./historical_keys:/app/historical_keys``
     - Historical/expired keys

Admin Portal (admin)
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Volume
     - Description
   * - ``./admin/private.json:/app/private.json``
     - Admin signing key
   * - ``./publickeys:/app/publickeys``
     - Public keys directory
   * - ``./historical_keys:/app/historical_keys``
     - Historical keys for JWT generation
   * - ``./localsettings.py:/app/inmoradmin/localsettings.py``
     - Production settings override

Database Persistence
--------------------

The PostgreSQL database stores:

* Subordinate entities and their statements
* Trust mark types and issued trust marks
* Entity metadata and configurations

Mount a persistent volume::

   services:
     db:
       volumes:
         - postgres_data:/var/lib/postgresql/data

   volumes:
     postgres_data:

Database Backup
^^^^^^^^^^^^^^^

Backup the database regularly::

   docker compose exec db pg_dump -U postgres postgres > backup.sql

Restore from backup::

   docker compose exec -T db psql -U postgres postgres < backup.sql

Redis Data
----------

Redis stores the federation runtime data:

* Entity configurations (``inmor:entity_id``)
* Subordinate statements (``inmor:subordinates``)
* Trust marks by entity (``inmor:tm:{domain}``)
* Trust mark type memberships (``inmor:tmtype:{type}``)
* Entity type sets (``inmor:rp``, ``inmor:op``, ``inmor:taia``)
* Collection data (``inmor:collection:*``) — populated by ``inmor-collection``

Redis data is ephemeral and can be rebuilt from the database::

   # Rebuild entity configuration
   curl -X POST http://localhost:8000/api/v1/server/entity

   # Rebuild historical keys
   curl -X POST http://localhost:8000/api/v1/server/historical_keys

   # Reload trust marks from database
   docker compose exec admin python manage.py reload_issued_tms

   # Rebuild collection data (walks the federation tree)
   docker compose exec ta ./inmor-collection -c taconfig.toml https://ta.example.com

.. _collection-cli:

Entity Collection CLI (``inmor-collection``)
--------------------------------------------

The ``inmor-collection`` binary walks a federation tree starting from a trust anchor,
discovers all subordinate entities, and stores their collection data in Redis.
The ``/collection`` endpoint on the Trust Anchor reads this data.

**Usage:**

.. code-block:: bash

   inmor-collection -c <config-file> <trust-anchor-entity-id>

**Arguments:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Argument
     - Description
   * - ``-c, --config <FILE>``
     - Path to ``taconfig.toml`` (used for Redis URI)
   * - ``<trust_anchor>``
     - Entity ID of the trust anchor to walk (e.g., ``https://ta.example.com``)

**Example:**

.. code-block:: bash

   # Run inside the Docker container
   docker compose exec ta ./inmor-collection -c taconfig.toml https://ta.example.com

   # With debug logging
   docker compose exec ta sh -c 'RUST_LOG=debug ./inmor-collection -c taconfig.toml https://ta.example.com'

**How it works:**

1. Connects to Redis using the URI from ``taconfig.toml``
2. Fetches the trust anchor's entity configuration
3. Recursively discovers all subordinates by following ``federation_list_endpoint`` links
4. For each entity, extracts entity types, UI info (display name, logo, policy URI), and trust marks
5. Writes all data to **staging Redis keys** (``inmor:collection:staging:*``) during the walk
6. On completion, atomically swaps staging keys to live keys using a Redis RENAME pipeline

The staging-to-live swap ensures the ``/collection`` endpoint never serves partial data
during a walk.

**Redis keys populated:**

.. list-table::
   :header-rows: 1
   :widths: 40 15 45

   * - Key
     - Type
     - Content
   * - ``inmor:collection:entities``
     - Hash
     - entity_id → JSON entity object
   * - ``inmor:collection:by_type:{type}``
     - Set
     - entity_ids of that type
   * - ``inmor:collection:all_sorted``
     - ZSet
     - entity_ids for ordering
   * - ``inmor:collection:last_updated``
     - String
     - Unix timestamp of last walk

**Scheduling:**

The tool is designed to run periodically via cron or systemd-timer.
See :ref:`scheduled-tasks` for cron and systemd timer configuration examples.

.. _scheduled-tasks:

Scheduled Tasks
---------------

Inmor requires two periodic tasks for production operation:

1. **Entity configuration regeneration** — keeps the TA's entity statement up to date
   (e.g. after adding subordinates, trust marks, or changing metadata via the Admin portal)
2. **Collection walk** — discovers all entities in the federation tree and populates
   the ``/collection`` endpoint

.. _regenerate-entity:

Entity Configuration Regeneration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``regenerate_entity`` management command regenerates the Trust Anchor's entity
configuration JWT and stores it in Redis. Run this periodically so that changes made
via the Admin portal (new subordinates, trust marks, metadata) are reflected in the
entity statement served at ``/.well-known/openid-federation``.

**Manual run:**

.. code-block:: bash

   # Via just
   just regenerate-entity

   # Or directly
   docker compose exec admin python manage.py regenerate_entity

**Cron (recommended for production):**

.. code-block:: bash

   # Run every minute
   * * * * * cd /path/to/inmor && /usr/bin/docker compose exec -T admin python manage.py regenerate_entity >> /tmp/inmor-regenerate.log 2>&1

**Systemd timer (alternative):**

Create ``~/.config/systemd/user/inmor-regenerate-entity.service``:

.. code-block:: ini

   [Unit]
   Description=Regenerate inmor Trust Anchor entity configuration

   [Service]
   Type=oneshot
   WorkingDirectory=/path/to/inmor
   ExecStart=/usr/bin/docker compose exec -T admin python manage.py regenerate_entity

Create ``~/.config/systemd/user/inmor-regenerate-entity.timer``:

.. code-block:: ini

   [Unit]
   Description=Regenerate inmor entity configuration every minute

   [Timer]
   OnCalendar=*-*-* *:*:00
   Persistent=true

   [Install]
   WantedBy=timers.target

Enable the timer::

   systemctl --user daemon-reload
   systemctl --user enable --now inmor-regenerate-entity.timer

   # Ensure timers survive logout/reboot
   loginctl enable-linger $(whoami)

Collection Walk Scheduling
^^^^^^^^^^^^^^^^^^^^^^^^^^

See :ref:`collection-cli` above for details on ``inmor-collection``.

**Cron:**

.. code-block:: bash

   # Run every 5 minutes
   */5 * * * * cd /path/to/inmor && /usr/bin/docker compose exec -T ta ./inmor-collection -c taconfig.toml https://ta.example.com >> /tmp/inmor-collection.log 2>&1

**Systemd timer:**

Create ``~/.config/systemd/user/inmor-collection.service``:

.. code-block:: ini

   [Unit]
   Description=Walk federation tree and populate collection data

   [Service]
   Type=oneshot
   WorkingDirectory=/path/to/inmor
   ExecStart=/usr/bin/docker compose exec -T ta ./inmor-collection -c taconfig.toml https://ta.example.com

Create ``~/.config/systemd/user/inmor-collection.timer``:

.. code-block:: ini

   [Unit]
   Description=Run inmor collection walk every 5 minutes

   [Timer]
   OnCalendar=*-*-* *:*:00/5
   Persistent=true

   [Install]
   WantedBy=timers.target

Enable::

   systemctl --user daemon-reload
   systemctl --user enable --now inmor-collection.timer

Health Checks
-------------

All services have health checks configured:

* **ta**: Basic connectivity check
* **admin**: Django application health
* **db**: PostgreSQL ready check (``pg_isready``)
* **redis**: Redis ping

Monitor health status::

   docker compose ps
   docker compose logs --tail=100

Scaling Considerations
----------------------

For high-availability deployments:

1. **Redis**: Use Redis Cluster or Redis Sentinel
2. **PostgreSQL**: Use PostgreSQL replication or managed service
3. **Trust Anchor**: Can be scaled horizontally behind a load balancer
4. **Admin Portal**: Can be scaled horizontally, ensure shared Redis/PostgreSQL

Environment Variables
---------------------

Trust Anchor (ta)
^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``RUST_LOG``
     - Log level (debug, info, warn, error)

Admin Portal (admin)
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``INSIDE_CONTAINER``
     - Set to ``true`` when running in Docker
   * - ``DB_HOST``
     - PostgreSQL host (default: ``db``)
   * - ``DB_PORT``
     - PostgreSQL port (default: ``5432``)
   * - ``REDIS_LOCATION``
     - Redis URL (default: ``redis://redis:6379/0``)
   * - ``HISTORICAL_KEYS_DIR``
     - Path to historical keys (default: ``./historical_keys``)

Initialization Workflow
-----------------------

After deployment, initialize the Trust Anchor:

1. **Create entity configuration**::

      curl -X POST http://localhost:8000/api/v1/server/entity

   This creates the TA's self-signed entity statement and stores it in Redis.

2. **Create historical keys JWT** (if you have rotated keys)::

      curl -X POST http://localhost:8000/api/v1/server/historical_keys

   This creates a signed JWT containing all expired keys from ``historical_keys/``.

3. **Create trust mark types**::

      curl -X POST http://localhost:8000/api/v1/trustmarktypes \
        -H "Content-Type: application/json" \
        -d '{
          "tmtype": "https://your-domain.example.com/trustmark/member",
          "valid_for": 8760,
          "autorenew": true
        }'

4. **Add subordinates** as they register with your Trust Anchor.

Logs and Monitoring
-------------------

View service logs::

   # All services
   docker compose logs -f

   # Specific service
   docker compose logs -f ta
   docker compose logs -f admin

For production monitoring, consider:

* Prometheus metrics export
* Centralized logging (ELK stack, Loki)
* Alerting on health check failures
