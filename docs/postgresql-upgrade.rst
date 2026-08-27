PostgreSQL 15 Upgrade
=====================

This release changes every bundled PostgreSQL container from major version 14
to 15. PostgreSQL major versions do not share a compatible on-disk data format,
so an existing PostgreSQL 14 data directory cannot be started by the new
PostgreSQL 15 container.

.. danger::

   **Upgrade PostgreSQL before starting this Inmor version.** If the existing
   database's ``PG_VERSION`` file contains ``14``, complete the procedure below
   before running ``just up`` or ``docker compose up`` with the new version.
   Do not point the PostgreSQL 15 image directly at an unconverted PostgreSQL 14
   volume.

The commands below use the ``pgautoupgrade/pgautoupgrade:15-alpine`` one-shot
container to run PostgreSQL's ``pg_upgrade`` against the same Alpine-based data
directory used by Inmor. The upgrade runs in link mode and removes its internal
copy of the old cluster, so the backup step is mandatory. Production operators
should review and pin the upgrade image according to their image-promotion
policy before use. See the `pgautoupgrade project documentation
<https://github.com/pgautoupgrade/docker-pgautoupgrade>`_ for implementation
and image details.

Before changing versions
------------------------

Run these commands while the PostgreSQL 14 service is still running::

   # Record the source version. This must print 14.x.
   docker compose exec -T db postgres --version

   # Back up every database, role, and other global object.
   docker compose exec -T db pg_dumpall -U postgres > postgres-14-backup.sql
   test -s postgres-14-backup.sql

The examples use the root ``docker-compose.yml``. If the deployment uses a
``-f`` or ``--project-directory`` option, include the same options on every
``docker compose`` command below. The development shortcuts are ``just down``
and ``just up``; the production-build shortcuts are ``just down-prod`` and
``just up-prod``.

Keep ``postgres-14-backup.sql`` somewhere outside the PostgreSQL volume. Stop
all Inmor services so nothing can write to the database during the upgrade::

   docker compose down

Named-volume deployments
------------------------

The root ``docker-compose.yml`` and ``dev/docker-compose.prod.yml`` store the
database in a named volume. Find its full Docker name::

   docker volume ls --filter label=com.docker.compose.volume=postgres_data

The name is usually ``inmor_postgres_data``. Substitute the actual name shown
above for ``<postgres-volume>`` in both commands below. Confirm that the volume
contains a PostgreSQL 14 cluster::

   docker run --rm \
     --volume <postgres-volume>:/data:ro \
     busybox:1.37 cat /data/PG_VERSION

The command must print ``14``. Run the one-shot upgrade::

   docker run --rm \
     --volume <postgres-volume>:/var/lib/postgresql/data \
     --env PGAUTO_ONESHOT=yes \
     --env POSTGRES_USER=postgres \
     --env POSTGRES_DB=postgres \
     pgautoupgrade/pgautoupgrade:15-alpine

Verify the result before starting Inmor::

   docker run --rm \
     --volume <postgres-volume>:/data:ro \
     busybox:1.37 cat /data/PG_VERSION

The final command must print ``15``.

Development bind-mount deployments
----------------------------------

``dev/docker-compose.dev.yml`` stores PostgreSQL in ``./db``. From the
repository root, confirm the old major version, preserve a filesystem copy, and
run the one-shot upgrade::

   docker run --rm \
     --volume "$PWD/db:/data:ro" \
     busybox:1.37 cat /data/PG_VERSION

   # PG_VERSION must print 14 before continuing.
   sudo cp -a db db.postgresql-14.backup

   docker run --rm \
     --volume "$PWD/db:/var/lib/postgresql/data" \
     --env PGAUTO_ONESHOT=yes \
     --env POSTGRES_USER=postgres \
     --env POSTGRES_DB=postgres \
     pgautoupgrade/pgautoupgrade:15-alpine

   docker run --rm \
     --volume "$PWD/db:/data:ro" \
     busybox:1.37 cat /data/PG_VERSION

The final command must print ``15``.

If the development database is disposable, removing ``./db`` while all
services are stopped lets PostgreSQL 15 create a new empty cluster. This
permanently deletes the local database and is not an upgrade; never use that
shortcut for data that must be retained.

Start and validate the new version
----------------------------------

After ``PG_VERSION`` reports ``15``, install and start the new Inmor version::

   docker compose up -d
   docker compose exec -T db psql -U postgres -d postgres \
     -c "SHOW server_version;"
   docker compose exec -T admin python manage.py migrate

Check the database and Admin logs before removing the backup. If the upgrade
fails, keep the new services stopped, restore the original data directory or
volume from backup, and restart the previous Inmor version with PostgreSQL 14.

For the underlying requirements, options, and recovery behavior, see the
`PostgreSQL 15 pg_upgrade documentation
<https://www.postgresql.org/docs/15/pgupgrade.html>`_.
