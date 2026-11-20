import json
from datetime import UTC, datetime, timedelta
from typing import Any

import djclick as click
from django.conf import settings
from django_redis import get_redis_connection

from entities.lib import (
    apply_server_policy,
    create_subordinate_statement,
    fetch_entity_configuration,
    update_redis_with_subordinate,
)
from entities.models import Subordinate


@click.command()
def command():
    """Renew active subordinates after checking stored overrides and critical declarations."""
    con = get_redis_connection("default")
    subs = Subordinate.objects.filter(active=True)
    total = subs.count()
    renewed = 0
    failed = 0

    for sub in subs:
        click.secho(f"Renewing {sub.entityid} ... ", nl=False)

        # Use stored JWKS to verify the entity's current configuration
        keys: dict[str, Any] | None = None
        if sub.jwks:
            keys = json.loads(sub.jwks) if isinstance(sub.jwks, str) else sub.jwks

        try:
            entity_jwt, keyset, entity_jwt_str = fetch_entity_configuration(sub.entityid, keys)
        except Exception as e:
            click.secho(f"FAILED (fetch: {e})", fg="red")
            failed += 1
            continue

        claims: dict[str, Any] = json.loads(entity_jwt.claims)

        # Verify that our TA_DOMAIN is in the authority_hints
        authority_hints = claims.get("authority_hints", [])
        if settings.TA_DOMAIN not in authority_hints:
            click.secho(
                f"FAILED (TA domain {settings.TA_DOMAIN} not in authority_hints)",
                fg="red",
            )
            failed += 1
            continue

        metadata: dict[str, Any] = claims["metadata"]
        # Renewal signs the stored critical declaration along with the overrides.
        try:
            apply_server_policy(
                json.dumps(metadata), sub.forced_metadata, additional_claims=sub.additional_claims
            )
        except Exception as e:
            click.secho(f"FAILED (policy apply: {e})", fg="red")
            failed += 1
            continue

        expiry = sub.valid_for or settings.SUBORDINATE_DEFAULT_VALID_FOR

        now = datetime.now(UTC)
        exp = now + timedelta(hours=expiry)
        signed_statement = create_subordinate_statement(
            sub.entityid,
            keyset,
            now,
            exp,
            sub.forced_metadata,
            additional_claims=sub.additional_claims,
        )

        # Update database
        fresh_jwks = claims.get("jwks", None)
        try:
            sub.metadata = metadata
            if fresh_jwks:
                sub.jwks = json.dumps(fresh_jwks)
            sub.statement = signed_statement
            sub.save()
        except Exception as e:
            click.secho(f"FAILED (db save: {e})", fg="red")
            failed += 1
            continue

        # Update Redis
        update_redis_with_subordinate(sub.entityid, entity_jwt_str, metadata, signed_statement, con)
        renewed += 1
        click.secho("OK", fg="green")

    click.secho(
        f"\nDone: {renewed}/{total} renewed, {failed} failed.",
        fg="green" if failed == 0 else "yellow",
    )
