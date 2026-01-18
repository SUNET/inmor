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

Screenshots
-----------

Login
^^^^^

The login page provides username/password authentication.

.. figure:: /_static/screenshots/01-login.png
   :alt: Login Page
   :width: 100%

   Admin UI Login Page

Dashboard
^^^^^^^^^

The dashboard shows the Trust Anchor status and provides quick access to
regenerate the entity configuration.

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
   just up

   # Start frontend dev server (from admin/frontend/)
   cd admin/frontend
   pnpm install
   pnpm dev

   # Or use the just command
   just dev-frontend

The frontend will be available at ``http://localhost:5173``.

Production Mode
^^^^^^^^^^^^^^^

For production, the frontend is built and served via nginx or the
Docker frontend container:

.. code-block:: bash

   # Build frontend
   cd admin/frontend
   pnpm build

   # Or use Docker
   just build

The Docker Compose setup includes a frontend container that serves the
built assets on port 3000.

Authentication
--------------

The Admin UI uses session-based authentication:

1. **CSRF Token**: On page load, the frontend fetches a CSRF token from
   ``/api/auth/csrf``

2. **Login**: Users authenticate via ``/api/auth/login`` with username/password

3. **Session**: A session cookie is set for subsequent API requests

4. **Auth Check**: The router guard checks ``/api/auth/me`` before each
   navigation to verify authentication

Configuration
-------------

Vite Proxy
^^^^^^^^^^

In development, Vite proxies API requests to the Django backend:

.. code-block:: typescript

   // vite.config.ts
   server: {
     proxy: {
       '/api': {
         target: 'http://localhost:8000',
         changeOrigin: true,
       },
     },
   }

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

For production builds, set the API URL:

.. code-block:: bash

   VITE_API_URL=https://admin.federation.example.com pnpm build

Tech Stack
----------

The frontend is built with:

* **Vue 3** - Composition API with TypeScript
* **Vue Router** - Client-side routing with authentication guards
* **Vite 7** - Build tool and development server
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
