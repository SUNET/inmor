Admin UI Guide
==============

The Admin UI provides a modern web interface for Trust Anchor administration.
It's built with Vue 3 and communicates with the Django Admin API.

.. contents:: On this page
   :local:
   :depth: 2

Overview
--------

The Admin UI allows administrators to:

* View server status and regenerate entity configuration
* Manage Trust Mark Types
* Issue and revoke Trust Marks
* Add and manage Subordinates with automatic configuration fetching

The subordinate, trust mark and trust mark type lists show 25 records per
page in ID order. Use **Previous** and **Next** to move between pages. When
issuing a trust mark, the type selector includes types from every page.

Screenshots
-----------

Login
^^^^^

Select **Sign In** to open the Django allauth login page.

.. figure:: /_static/screenshots/01-login.png
   :alt: Login Page
   :width: 100%

   Admin UI Login Page

Dashboard
^^^^^^^^^

The dashboard shows the Trust Anchor status and provides quick access to
regenerate the entity configuration. A count of zero means the list is
empty. An unavailable count means the API request failed.

.. figure:: /_static/screenshots/02-dashboard.png
   :alt: Dashboard
   :width: 100%

   Dashboard with server status

Trust Mark Types
^^^^^^^^^^^^^^^^

Manage Trust Mark Type definitions. Each type has a URL identifier,
validity period, and auto-renewal settings.

.. figure:: /_static/screenshots/03-trustmark-types.png
   :alt: Trust Mark Types List
   :width: 100%

   Trust Mark Types management

.. figure:: /_static/screenshots/03a-trustmark-type-create.png
   :alt: Create Trust Mark Type
   :width: 100%

   Creating a new Trust Mark Type

Trust Marks
^^^^^^^^^^^

Issue Trust Marks to entities. Select the Trust Mark Type and enter
the entity's domain.

.. figure:: /_static/screenshots/04-trustmarks.png
   :alt: Trust Marks List
   :width: 100%

   Trust Marks management

.. figure:: /_static/screenshots/04a-trustmark-issue.png
   :alt: Issue Trust Mark
   :width: 100%

   Issuing a Trust Mark to an entity

Subordinates
^^^^^^^^^^^^

Add federation subordinates with automatic configuration fetching.
The UI fetches the entity's published configuration and validates it.
If discovery returns no public keys, the form keeps the JWKS already
entered and shows the published key URI when available.

.. figure:: /_static/screenshots/05-subordinates.png
   :alt: Subordinates List
   :width: 100%

   Subordinates management

.. figure:: /_static/screenshots/06-add-subordinate.png
   :alt: Add Subordinate
   :width: 100%

   Adding a new subordinate with Fetch Config

Running the Frontend
--------------------

Development Mode
^^^^^^^^^^^^^^^^

For development, run the frontend separately from Docker:

.. code-block:: bash

   # Start backend services
   docker compose -f dev/docker-compose.dev.yml --project-directory . up -d admin

   # Start frontend dev server (from admin/frontend/)
   cd admin/frontend
   pnpm install
   pnpm dev

   # Or use the just command
   just dev-frontend

The frontend will be available at ``http://localhost:5173``.

Production Mode
^^^^^^^^^^^^^^^

To build the assets locally, run these commands from the repository root:

.. code-block:: bash

   # Build frontend
   cd admin/frontend
   pnpm install --frozen-lockfile
   pnpm build

To build the production images, run ``just build-prod`` from the repository
root. Enable the frontend when starting the production Compose stack::

   docker compose -f dev/docker-compose.prod.yml --project-directory . --profile frontend up -d

The frontend container serves the assets through nginx on host port 5173.

Authentication
--------------

The Admin UI uses a django-allauth browser session with optional Multi-Factor
Authentication (MFA) support. Direct API clients must use API keys.

.. figure:: /_static/screenshots/mfa-01-login.png
   :alt: Login Page
   :width: 100%

   Styled login page with SUNET/Inmor branding

Authentication Flow
^^^^^^^^^^^^^^^^^^^

1. **Authentication check**: The frontend checks ``/api/v1/auth/me``.
   Signed-out users see the sign-in page. A signed-in user who lacks
   ``entities.manage_federation`` sees an access-denied message. If the
   session check fails, the UI offers a retry.

2. **Login**: django-allauth validates the user's primary credentials

3. **MFA Challenge**: If MFA is enabled, django-allauth requires the configured
   second factor (TOTP code or security key)

4. **Session**: Only after the complete allauth flow succeeds is a session
   cookie available to the Admin UI

5. **Admin API requests**: The browser sends the session cookie. For writes,
   the frontend reads Django's ``csrftoken`` cookie and sends its value in
   the ``X-CSRFToken`` header.

There is no password-login endpoint under ``/api/v1/``. Scripts, integrations,
and other direct API clients must authenticate with ``X-API-Key``.

For detailed MFA configuration, see :doc:`mfa`.

Configuration
-------------

Vite Proxy
^^^^^^^^^^

Vite forwards ``/api/``, ``/accounts/``, ``/admin/``, and ``/static/`` to
Django on port 8000. Open the frontend on port 5173 so login, MFA, logout,
and the management API share the browser session. The nginx frontend uses
the same routes.

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

Production builds use the frontend origin by default. To configure a separate
API origin at build time:

.. code-block:: bash

   VITE_API_URL=https://admin.federation.example.com pnpm build

Tech Stack
----------

The frontend is built with:

* **Vue 3** - Composition API with TypeScript
* **Vue Router** - Client-side routing with authentication guards
* **Vite 8** - Build tool and development server
* **CodeMirror 6** - JSON editor with syntax validation
* **Lucide Vue** - Icon library
* **Valibot** - Schema validation

CSS Design System
-----------------

The UI uses CSS custom properties for consistent theming:

.. code-block:: css

   /* Primary colors */
   --ir--color--primary: #2563eb;
   --ir--color--danger: #ef4444;
   --ir--color--success: #22c55e;

   /* Typography */
   --ir--font-family: 'Cantarell', 'Roboto', sans-serif;

   /* Spacing scale */
   --ir--space--1: 4px;
   --ir--space--2: 8px;
   --ir--space--3: 16px;
   --ir--space--4: 32px;

Recording Demo Videos
---------------------

A Playwright script is provided to record demo videos:

.. code-block:: bash

   # Prerequisites
   pip install playwright
   playwright install chromium

   # Flush database and create admin user
   docker compose exec admin python manage.py flush --no-input
   docker compose exec redis redis-cli FLUSHALL
   docker compose exec admin python manage.py createsuperuser

   # Run the recording script
   python scripts/record_demo.py

Videos are saved to the ``videos/`` directory.

Taking Screenshots
------------------

For documentation screenshots:

.. code-block:: bash

   python scripts/take_screenshots.py

Screenshots are saved to the ``screenshots/`` directory.
