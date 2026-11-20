"""Restore the all-time trust mark digest index from committed issuance history."""

from hashlib import sha256
from itertools import batched, chain

import djclick as click
from django_redis import get_redis_connection

from entities.models import IssuedTrustMarkHash
from trustmarks.models import TrustMark


@click.command()
def command():
    """Restore status lookup for issued JWTs, including superseded and revoked marks."""
    con = get_redis_connection("default")
    digests = IssuedTrustMarkHash.objects.values_list("digest", flat=True)
    # SADD is idempotent and keeps older entries that exist only in Redis.
    # Legacy fixtures can be loaded after the migration that imports retained JWTs.
    tokens = TrustMark.objects.filter(active=True, mark__isnull=False).values_list(
        "mark", flat=True
    )
    legacy = (sha256(token.encode()).hexdigest() for token in tokens.iterator() if token)
    for batch in batched(chain(digests.iterator(), legacy), 1000):
        con.sadd("inmor:tm:alltime", *batch)
