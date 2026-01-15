Installation
============

This guide covers how to install and set up Inmor Trust Anchor for development and production use.

Prerequisites
-------------

* Docker and Docker Compose
* Git
* ``just`` command runner (optional but recommended)
* ``uv`` for Python dependency management (for local development)

Installing just
^^^^^^^^^^^^^^^

``just`` is a task runner similar to ``make``. Install it using your package manager::

   # macOS
   brew install just

   # Ubuntu/Debian
   sudo apt install just

   # Arch Linux
   sudo pacman -S just

   # Using cargo
   cargo install just

Quick Installation
------------------

1. Clone the repository::

      git clone https://github.com/SUNET/inmor.git
      cd inmor

   The repository includes development signing keys, so no key generation
   is needed to get started.

2. Build the Docker images::

      just build

3. Start all services::

      just up

4. Initialize the Trust Anchor::

      # Create the entity configuration
      curl -X POST http://localhost:8000/api/v1/server/entity

      # Create historical keys JWT (if you have any)
      curl -X POST http://localhost:8000/api/v1/server/historical_keys

The Trust Anchor is now running at ``http://localhost:8080`` and the Admin API at ``http://localhost:8000``.

.. note::

   For production deployments, you should generate your own signing keys.
   See the `Key Generation`_ section below.

Key Generation
--------------

The repository includes development signing keys that are ready to use.
These keys are sufficient for development and testing.

For production deployments, you should generate your own keys::

   # Remove existing development keys
   just clean

   # Generate new keys for production
   just dev

Inmor generates multiple key types for signing operations, following `RFC 9864 Section 2 <https://www.rfc-editor.org/rfc/rfc9864.html#section-2>`_:

* RSA keys (RS256, PS256) - 2048 bit
* EC keys (ES256, ES384, ES512) - P-256, P-384, P-521 curves
* Edwards curve keys (Ed25519, Ed448)

Each key is stored as a JWK JSON file with the key ID (kid) as the thumbprint.

.. warning::

   Regenerating keys will invalidate all existing entity statements and trust marks.
   Make sure to backup and properly rotate keys in production.

Directory Structure
-------------------

After installation, your directory structure should look like::

   inmor/
   ├── publickeys/           # Public keys (JWK format)
   │   └── *.json
   ├── privatekeys/          # Private keys (JWK format)
   │   └── *.json
   ├── historical_keys/      # Expired/rotated keys
   │   └── *.json
   ├── private.json          # TA primary signing key
   ├── admin/
   │   └── private.json      # Admin signing key
   ├── taconfig.toml         # TA configuration
   └── docker-compose.yml

Verifying Installation
----------------------

1. Check that all containers are running::

      docker compose ps

   You should see four containers: ``ta``, ``admin``, ``db``, and ``redis``.

2. Test the Trust Anchor::

      curl http://localhost:8080/.well-known/openid-federation

   This should return a signed JWT containing the entity configuration.

3. Test the Admin API::

      curl http://localhost:8000/api/v1/trustmarktypes

   This should return an empty list or existing trust mark types.

Stopping Services
-----------------

To stop all services::

   just down

To stop and remove all data (including database)::

   docker compose down -v
   rm -rf db/ redis/

Development Setup
-----------------

For local development without Docker:

1. Install uv (if not already installed)::

      # macOS/Linux
      curl -LsSf https://astral.sh/uv/install.sh | sh

      # Or with pip
      pip install uv

2. Set up Python environment::

      just venv

   This runs ``uv sync`` in the admin directory to create a virtual environment
   and install all dependencies.

3. Install the development root CA certificate to the system trust store.

   The repository includes self-signed TLS certificates for development.
   To allow your system to trust these certificates, install the root CA:

   **Ubuntu/Debian**::

      sudo cp rootCA.pem /usr/local/share/ca-certificates/rootCA.crt
      sudo update-ca-certificates

   **Fedora/RHEL/CentOS**::

      sudo cp rootCA.pem /etc/pki/ca-trust/source/anchors/rootCA.pem
      sudo update-ca-trust

   **macOS**::

      sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain rootCA.pem

   **Arch Linux**::

      sudo cp rootCA.pem /etc/ca-certificates/trust-source/anchors/rootCA.crt
      sudo trust extract-compat

4. Set up Rust environment::

      cargo build --release

5. Start dependencies (Redis and PostgreSQL)::

      docker compose up -d db redis

6. Run Django migrations::

      cd admin
      uv run python manage.py migrate

7. Start the Admin server::

      uv run python manage.py runserver

8. Start the Trust Anchor::

      cargo run --release -- -c taconfig.toml

Troubleshooting
---------------

Container won't start
^^^^^^^^^^^^^^^^^^^^^

Check the logs::

   docker compose logs ta
   docker compose logs admin

Common issues:

* Port already in use - stop other services on ports 8000, 8080, 5432
* Redis not ready - wait for healthcheck to pass

Database connection errors
^^^^^^^^^^^^^^^^^^^^^^^^^^

Ensure PostgreSQL is running and healthy::

   docker compose ps db

If the database is corrupted, remove and recreate::

   docker compose down
   rm -rf db/
   docker compose up -d

Key file errors
^^^^^^^^^^^^^^^

Ensure private.json exists and is valid JSON::

   cat private.json | python -m json.tool

If the file is corrupted or missing, restore from git::

   git checkout -- private.json admin/private.json publickeys/

TLS certificate errors
^^^^^^^^^^^^^^^^^^^^^^

If you see SSL/TLS certificate verification errors when running tests or
making requests to the Trust Anchor, ensure the root CA is installed::

   # Verify the root CA is installed (Ubuntu/Debian)
   ls /usr/local/share/ca-certificates/rootCA.crt

   # If missing, install it
   sudo cp rootCA.pem /usr/local/share/ca-certificates/rootCA.crt
   sudo update-ca-certificates

For other operating systems, see the root CA installation steps in the
`Development Setup`_ section above.
