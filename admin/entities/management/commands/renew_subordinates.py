import json
from datetime import UTC, datetime, timedelta
from typing import Any

import djclick as click
from django.conf import settings
from django.db import transaction

from entities.lib import (
    apply_server_policy,
    create_subordinate_statement,
    fetch_entity_configuration,
)
from entities.models import Subordinate
from entities.publication import queue_publication


@click.command()
def command():
    """Renew active subordinates after checking stored overrides and critical declarations."""
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

        # A deactivation or edit may have occurred during the remote fetch.
        # Record the publication in the same transaction as the conditional update.
        updates: dict[str, Any] = {"statement": signed_statement, "metadata": metadata}
        if fresh_jwks := claims.get("jwks"):
            updates["jwks"] = json.dumps(fresh_jwks)
        try:
            with transaction.atomic():
                current = Subordinate.objects.filter(
                    pk=sub.pk, active=True, statement=sub.statement
                )
                if not current.update(**updates):
                    click.secho("Skipped (subordinate changed during renewal)")
                    continue
                queue_publication(sub, entity_jwt_str)
        except Exception as e:
            click.secho(f"FAILED (renewal: {e})", fg="red")
            failed += 1
            continue

        renewed += 1
        click.secho("OK", fg="green")

    click.secho(
        f"\nDone: {renewed}/{total} renewed, {failed} failed.",
        fg="green" if failed == 0 else "yellow",
    )
