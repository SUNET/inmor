Configuration Reference
=======================

Inmor is configured through multiple configuration files and environment variables.

Trust Anchor Configuration (taconfig.toml)
------------------------------------------

The Trust Anchor reads its configuration from ``taconfig.toml``.

.. code-block:: toml

   # Trust Anchor entity ID (must match public URL)
   domain = "https://federation.example.com"

   # Redis connection URI
   redis_uri = "redis://redis:6379"

   # TLS certificate and key (optional if behind reverse proxy)
   tls_cert = "cert.pem"
   tls_key = "key.pem"

**Configuration Options:**

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Option
     - Required
     - Description
   * - ``domain``
     - Yes
     - The Trust Anchor's entity identifier URL. This must match the public URL where the TA is accessible.
   * - ``redis_uri``
     - Yes
     - Redis connection URI for storing federation data.
   * - ``tls_cert``
     - No
     - Path to TLS certificate file. Not required if running behind a reverse proxy.
   * - ``tls_key``
     - No
     - Path to TLS private key file. Not required if running behind a reverse proxy.

Admin Portal Configuration (settings.py)
-----------------------------------------

The Admin Portal is configured through Django settings. Create ``admin/inmoradmin/localsettings.py``
to override defaults.

Core Settings
^^^^^^^^^^^^^

.. code-block:: python

   # Trust Anchor entity ID (must match TA domain)
   TA_DOMAIN = "https://federation.example.com"

   # Endpoint for trust mark services (usually same as TA_DOMAIN)
   TRUSTMARK_PROVIDER = "https://federation.example.com"

   # Django security settings
   DEBUG = False
   SECRET_KEY = "your-production-secret-key"
   ALLOWED_HOSTS = ["admin.federation.example.com"]

Federation Endpoints
^^^^^^^^^^^^^^^^^^^^

These are automatically derived from ``TA_DOMAIN``:

.. code-block:: python

   FEDERATION_ENTITY = {
       "federation_fetch_endpoint": f"{TA_DOMAIN}/fetch",
       "federation_list_endpoint": f"{TA_DOMAIN}/list",
       "federation_resolve_endpoint": f"{TA_DOMAIN}/resolve",
       "federation_trust_mark_status_endpoint": f"{TA_DOMAIN}/trust_mark_status",
       "federation_trust_mark_list_endpoint": f"{TA_DOMAIN}/trust_mark_list",
       "federation_trust_mark_endpoint": f"{TA_DOMAIN}/trust_mark",
       "federation_historical_keys_endpoint": f"{TA_DOMAIN}/historical_keys",
   }

Default Values
^^^^^^^^^^^^^^

.. code-block:: python

   # Default validity for subordinate statements (in hours)
   SUBORDINATE_DEFAULT_VALID_FOR = 8760  # 1 year

   # Server entity statement expiry (in hours)
   SERVER_EXPIRY = 8760  # 1 year

   # Default values for new trust mark types and trust marks
   TA_DEFAULTS = {
       "trustmarktype": {
           "autorenew": True,
           "valid_for": 8760,      # 1 year in hours
           "renewal_time": 48,      # Hours before expiry to renew
           "active": True,
       },
       "trustmark": {
           "autorenew": True,
           "valid_for": 8760,
           "renewal_time": 48,
           "active": True,
       },
   }

Authority Hints
^^^^^^^^^^^^^^^

For intermediate authorities, configure parent authorities:

.. code-block:: python

   # List of parent Trust Anchors/Intermediates
   AUTHORITY_HINTS = [
       "https://parent-ta.example.com",
   ]

Trust Marks for the TA
^^^^^^^^^^^^^^^^^^^^^^

Configure trust marks issued to the TA itself by external issuers:

.. code-block:: python

   # Trust marks that appear in TA's entity configuration
   TA_TRUSTMARKS = [
       {
           "trust_mark_type": "https://federation-operator.example.com/trustmarks/verified-ta",
           "mark": "eyJhbGciOiJFUzI1NiIsInR5cCI6InRydXN0LW1hcmsrand0In0..."
       },
   ]

   # Trusted trust mark issuers
   # Maps trust_mark_type URLs to lists of trusted issuer entity_ids
   TA_TRUSTED_TRUSTMARK_ISSUERS = {
       "https://accreditation-body.example.com/trustmarks/certified": [
           "https://accreditation-body.example.com"
       ],
       "https://industry-group.example.com/trustmarks/member": [
           "https://industry-group.example.com",
           "https://secondary-issuer.example.com"
       ],
   }

Metadata Policy
^^^^^^^^^^^^^^^

Define metadata policy for subordinates:

.. code-block:: python

   # Policy applied to all subordinate metadata
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
               }
           }
       }
   }

Database Configuration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.postgresql",
           "NAME": "inmor",
           "USER": "inmor",
           "PASSWORD": "secure-password",
           "HOST": "db.example.com",
           "PORT": 5432,
       }
   }

Redis Configuration
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   REDIS_LOCATION = "redis://redis.example.com:6379/0"

   CACHES = {
       "default": {
           "BACKEND": "django_redis.cache.RedisCache",
           "LOCATION": REDIS_LOCATION,
           "OPTIONS": {
               "CLIENT_CLASS": "django_redis.client.DefaultClient",
           },
       }
   }

Historical Keys
^^^^^^^^^^^^^^^

.. code-block:: python

   # Directory containing historical/expired key files
   HISTORICAL_KEYS_DIR = "./historical_keys"

Environment Variables
---------------------

Trust Anchor (Rust)
^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Variable
     - Description
   * - ``RUST_LOG``
     - Log level: ``error``, ``warn``, ``info``, ``debug``, ``trace``

Admin Portal (Django)
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Variable
     - Description
   * - ``INSIDE_CONTAINER``
     - Set to ``true`` when running in Docker
   * - ``DB_HOST``
     - PostgreSQL host (default: ``db``)
   * - ``DB_PORT``
     - PostgreSQL port (default: ``5432``)
   * - ``REDIS_LOCATION``
     - Redis connection URI (default: ``redis://redis:6379/0``)
   * - ``HISTORICAL_KEYS_DIR``
     - Path to historical keys directory (default: ``./historical_keys``)

Key Files
---------

Signing Keys
^^^^^^^^^^^^

Inmor uses JWK-formatted keys for signing:

.. code-block:: text

   inmor/
   ├── private.json           # TA primary signing key
   ├── publickeys/            # Public keys (included in JWKS)
   │   ├── key1.json
   │   └── key2.json
   └── admin/
       └── private.json       # Admin signing key

**private.json Example:**

.. code-block:: json

   {
     "kty": "EC",
     "crv": "P-256",
     "x": "MKBCTNIcKUSDii11ySs3526iDZ8AiTo7Tu6KPAqv7D4",
     "y": "4Etl6SRW2YiLUrN5vfvVHuhp7x8PxltmWWlbbM4IFyM",
     "d": "870MB6gfuTJ4HtUnUvYMyJpr5eUZNP4Bk43bVdj3eAE",
     "kid": "key-1",
     "use": "sig",
     "alg": "ES256"
   }

Historical Keys
^^^^^^^^^^^^^^^

Historical keys are stored in ``historical_keys/`` with an ``exp`` field:

.. code-block:: json

   {
     "kty": "EC",
     "crv": "P-256",
     "x": "...",
     "y": "...",
     "kid": "old-key-1",
     "use": "sig",
     "alg": "ES256",
     "exp": 1704067200,
     "revoked": {
       "revoked_at": 1704067200,
       "reason": "superseded"
     }
   }

Use the ``scripts/add_historical_key.py`` script to retire keys:

.. code-block:: bash

   # Move a key to historical with expiry
   python scripts/add_historical_key.py publickeys/old-key.json

   # Mark as superseded
   python scripts/add_historical_key.py publickeys/old-key.json --revoked superseded

   # Mark as compromised
   python scripts/add_historical_key.py publickeys/old-key.json --revoked compromised

Redis Key Structure
-------------------

The Trust Anchor stores federation data in Redis:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Key
     - Description
   * - ``inmor:entity_id``
     - TA's entity configuration JWT
   * - ``inmor:historical_keys``
     - Historical keys JWT
   * - ``inmor:subordinates``
     - Hash: entity_id → subordinate statement JWT
   * - ``inmor:subordinates:jwt``
     - Hash: entity_id → entity configuration JWT
   * - ``inmor:rp``
     - Set of Relying Party entity IDs
   * - ``inmor:op``
     - Set of OpenID Provider entity IDs
   * - ``inmor:taia``
     - Set of TA/IA entity IDs
   * - ``inmor:tm:{domain}``
     - Hash: trust_mark_type → JWT or "revoked"
   * - ``inmor:tmtype:{type}``
     - Set of entity IDs with this trust mark type
   * - ``inmor:tm:alltime``
     - Set of all trust mark SHA256 hashes (for validation)

Example Configuration Files
---------------------------

Production localsettings.py
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # admin/inmoradmin/localsettings.py

   DEBUG = False
   SECRET_KEY = "your-very-secure-production-secret-key"
   ALLOWED_HOSTS = ["admin.federation.example.com", "localhost"]

   # Trust Anchor configuration
   TA_DOMAIN = "https://federation.example.com"
   TRUSTMARK_PROVIDER = "https://federation.example.com"

   # For intermediate authorities
   AUTHORITY_HINTS = []

   # Trust marks issued to this TA
   TA_TRUSTMARKS = [
       {
           "trust_mark_type": "https://root-ta.example.com/trustmarks/verified",
           "mark": "eyJ..."
       }
   ]

   # Trusted issuers for trust mark validation
   TA_TRUSTED_TRUSTMARK_ISSUERS = {
       "https://accreditation.example.com/trustmarks/certified": [
           "https://accreditation.example.com"
       ]
   }

   # Custom defaults
   SUBORDINATE_DEFAULT_VALID_FOR = 4320  # 180 days

   TA_DEFAULTS = {
       "trustmarktype": {
           "autorenew": True,
           "valid_for": 4320,  # 180 days
           "renewal_time": 168,  # 1 week
           "active": True,
       },
       "trustmark": {
           "autorenew": True,
           "valid_for": 4320,
           "renewal_time": 168,
           "active": True,
       },
   }

   # Metadata policy
   POLICY_DOCUMENT = {
       "metadata_policy": {
           "openid_relying_party": {
               "grant_types": {
                   "subset_of": ["authorization_code", "refresh_token"]
               }
           }
       }
   }

Production taconfig.toml
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: toml

   # taconfig.toml

   domain = "https://federation.example.com"
   redis_uri = "redis://redis:6379"

   # TLS handled by reverse proxy, omit these
   # tls_cert = "cert.pem"
   # tls_key = "key.pem"
