Inmor Trust Anchor Documentation
=================================

Inmor is a Trust Anchor (TA) implementation for `OpenID Federation <https://openid.net/specs/openid-federation-1_0.html>`_ (Draft 46).
It provides a complete solution for managing OpenID Federation trust chains, subordinate entities, and trust marks.

The system consists of two components:

* **Trust Anchor (Rust)**: High-performance federation server handling entity statements, trust marks, and resolution
* **Admin Portal (Python/Django)**: REST API for managing subordinates, trust mark types, and trust marks

.. note::

   Inmor is currently under active development and is not yet production-ready.

.. danger::

   **Production Security:** The Admin API must be protected with authentication
   (at minimum HTTP Basic Auth) before exposing to any network. See
   :ref:`securing-admin-api` for details.

Quick Start
-----------

The fastest way to get Inmor running is with Docker Compose::

   # Clone the repository (includes signing keys for development)
   git clone https://github.com/SUNET/inmor.git
   cd inmor

   # Build and start all services
   just build
   just up

   # Initialize the Trust Anchor
   curl -X POST http://localhost:8000/api/v1/server/entity
   curl -X POST http://localhost:8000/api/v1/server/historical_keys

The repository includes development signing keys, so no key generation is needed
for getting started. For production, you should generate your own keys.

For detailed instructions, see :doc:`installation`.

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   deployment
   reverse-proxy

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/admin
   api/trust-anchor

.. toctree::
   :maxdepth: 2
   :caption: Configuration

   configuration

.. toctree::
   :maxdepth: 2
   :caption: User Guides

   guides/admin-ui
   guides/mfa
   guides/trustmarks
   guides/subordinates

Architecture Overview
---------------------

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────────┐
   │                        External Clients                         │
   │                    (Federation Entities, RPs, OPs)              │
   └─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    Reverse Proxy (nginx)                        │
   │                     TLS Termination                             │
   └─────────────────────────────────────────────────────────────────┘
              │                                        │
              ▼                                        ▼
   ┌─────────────────────┐                ┌─────────────────────────┐
   │   Trust Anchor      │                │    Admin Portal         │
   │   (Rust/Actix)      │◄──────────────►│    (Django/Ninja)       │
   │   Port 8080         │    Redis       │    Port 8000            │
   └─────────────────────┘                └─────────────────────────┘
              │                                        │
              ▼                                        ▼
   ┌─────────────────────┐                ┌─────────────────────────┐
   │       Redis         │                │      PostgreSQL         │
   │   Federation Cache  │                │   Persistent Storage    │
   └─────────────────────┘                └─────────────────────────┘

OpenID Federation Compliance
----------------------------

Inmor implements the following OpenID Federation endpoints:

* ``/.well-known/openid-federation`` - Entity configuration
* ``/fetch`` - Fetch subordinate statements
* ``/list`` - List subordinates
* ``/resolve`` - Resolve trust chains
* ``/trust_mark`` - Get trust marks
* ``/trust_mark_list`` - List entities with trust marks
* ``/trust_mark_status`` - Validate trust marks
* ``/historical_keys`` - Historical/expired key set

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
