import json

import djclick as click
from django.db import connection


@click.command()
def command():
    """Pre-migration check: verify metadata/forced_metadata are valid JSON before JSONField migration.

    Fixes empty strings to '{}' and validates all values can cast to jsonb.
    Must run BEFORE 'python manage.py migrate' when upgrading to 0.2.3+.
    """
    with connection.cursor() as cursor:
        # Check current column type - skip if already jsonb
        cursor.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'entities_subordinate' AND column_name = 'metadata'
        """)
        row = cursor.fetchone()
        if row is None:
            click.secho("Table entities_subordinate does not exist yet, skipping.", fg="yellow")
            return
        if row[0] == "jsonb":
            click.secho("Columns are already jsonb, nothing to do.", fg="green")
            return

        click.secho("Columns are varchar, checking data before migration...", fg="yellow")

        # Fix empty strings to '{}' (empty strings are not valid JSON)
        cursor.execute("""
            UPDATE entities_subordinate SET metadata = '{}'
            WHERE metadata = ''
        """)
        fixed_metadata = cursor.rowcount
        cursor.execute("""
            UPDATE entities_subordinate SET forced_metadata = '{}'
            WHERE forced_metadata = ''
        """)
        fixed_forced = cursor.rowcount

        if fixed_metadata or fixed_forced:
            click.secho(
                f"Fixed empty strings: {fixed_metadata} metadata, {fixed_forced} forced_metadata",
                fg="yellow",
            )

        # Validate all values are valid JSON
        cursor.execute("SELECT id, entityid, metadata, forced_metadata FROM entities_subordinate")
        rows = cursor.fetchall()
        errors = []
        for row_id, entityid, metadata, forced_metadata in rows:
            for field_name, value in [("metadata", metadata), ("forced_metadata", forced_metadata)]:
                if value is None:
                    continue
                try:
                    json.loads(value)
                except (json.JSONDecodeError, TypeError) as e:
                    errors.append(f"  id={row_id} entityid={entityid} {field_name}: {e}")

        if errors:
            click.secho("ERRORS: The following rows contain invalid JSON:", fg="red")
            for err in errors:
                click.secho(err, fg="red")
            raise click.Abort()

        click.secho(f"All {len(rows)} subordinate(s) have valid JSON. Safe to migrate.", fg="green")
