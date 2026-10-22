Releasing
=========

This page lists every place that carries the inmor release version and the
steps for cutting a release. ``Cargo.toml`` is the source of truth; all other
references must match it.

Version references
------------------

Update all of these together when bumping the version:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - File
     - What to change
   * - ``Cargo.toml``
     - ``[package] version`` (source of truth)
   * - ``Cargo.lock``
     - The ``inmor`` package entry; refreshed by ``cargo build``
   * - ``pyproject.toml``
     - ``[project] version``
   * - ``uv.lock``
     - The ``pyinmor`` package entry; refreshed by ``uv lock``
   * - ``admin/pyproject.toml``
     - ``[project] version``
   * - ``admin/uv.lock``
     - The ``inmoradmin`` package entry; refreshed by ``uv lock`` in ``admin/``
   * - ``docs/conf.py``
     - ``release``
   * - ``docker-compose.yml``
     - ``docker.sunet.se/inmor``, ``inmor-admin`` and (commented)
       ``inmor-frontend`` image tags
   * - ``dev/docker-compose.dev.yml``
     - ``inmor``, ``inmor-admin`` and ``inmor-frontend`` image tags
   * - ``dev/docker-compose.prod.yml``
     - ``inmor``, ``inmor-admin`` and ``inmor-frontend`` image tags
   * - ``docs/deployment.rst``
     - Image tags in the compose example and the ``inmor-keygeneration``
       command
   * - ``CHANGELOG.md``
     - Rename ``Unreleased`` to ``<version> - <YYYY-MM-DD>`` with a
       ``changelog-<version>`` anchor

The compose image tags matter at runtime, not just for documentation: the
root ``docker-compose.yml`` bind-mounts ``./templates`` into the TA
container, so an image older than the checkout may fail to load the
templates (0.5.0, for example, moved them to Tera 2 component syntax).

``admin/frontend/package.json`` has its own version and is not part of the
release version.

Checking
--------

``just check-version`` compares every reference above (except
``CHANGELOG.md``) with ``Cargo.toml`` and lists any mismatch. It runs as
part of ``just lint`` and therefore in CI::

   just check-version

When adding a new file that pins an inmor image tag or version, add it to
``scripts/check_version.py`` and to the table above.

Release steps
-------------

1. Update every version reference listed above, then run ``cargo build``,
   ``uv lock`` and ``uv lock`` in ``admin/`` to refresh the lockfiles.
2. Run ``just lint`` and the test suites (``just test-ta``, ``just test-admin``).
3. Build the release images with a fresh base and package index so security
   updates (for example ``ca-certificates``) are included::

      docker compose -f dev/docker-compose.prod.yml --project-directory . build --pull --no-cache

   ``just build-prod`` builds the same images but may reuse cached layers.
