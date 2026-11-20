"""Deliver committed federation changes to the public Redis indexes."""

from contextlib import contextmanager
from functools import partial
from hashlib import sha256

from django.db import transaction
from django_redis import get_redis_connection
from redis.client import Pipeline
from trustmarks.models import TrustMark

from .models import PendingPublication, Subordinate


def queue_publication(resource: Subordinate | TrustMark, entity_configuration: str = "") -> None:
    """Record the latest desired publication in the resource writer's transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Publication must be queued in the resource transaction")
    owner = (
        {"subordinate": resource} if isinstance(resource, Subordinate) else {"trust_mark": resource}
    )
    pending, _ = PendingPublication.objects.update_or_create(
        **owner, defaults={"entity_configuration": entity_configuration}
    )
    # Capture only the job identity. A subsequent edit may replace its contents.
    transaction.on_commit(partial(deliver_publication, pending.pk))


@contextmanager
def publication_pipeline(resource_key: str):
    """Discard an in-flight Redis transaction if a later delivery already completed."""
    key = f"inmor:publication:{resource_key}"
    with get_redis_connection("default").pipeline() as pipe:
        # WATCH is acknowledged before EXEC is sent. If a writer loses its database
        # lock on disconnect, a delayed EXEC cannot undo a subsequent delivery.
        pipe.watch(key)
        pipe.multi()
        yield pipe
        # Touch even on a redundant withdrawal. Redis invalidates prior watches
        # on this key, and the transaction leaves no permanent marker.
        pipe.set(key, "1")
        pipe.delete(key)
        pipe.execute()


def publish_subordinate(sub: Subordinate, config: str, pipe: Pipeline) -> None:
    """Stage the direct membership, verified configuration and walk request together."""
    entity = sub.entityid
    # Retrying after a lost acknowledgement must not duplicate pending walks.
    pipe.lrem("inmor:newsubordinate", 0, entity)
    if not sub.active:
        pipe.hdel("inmor:subordinates", entity)
        pipe.hdel("inmor:subordinates:jwt", entity)
        return
    if not sub.statement or not config:
        raise ValueError("An active subordinate needs both signed statements")
    if sub.metadata:
        if "openid_relying_party" in sub.metadata:
            role = "rp"
        elif "openid_provider" in sub.metadata:
            role = "op"
        else:
            role = "taia"
        pipe.sadd(f"inmor:{role}", entity)
    pipe.hset("inmor:subordinates", entity, sub.statement)
    pipe.hset("inmor:subordinates:jwt", entity, config)
    pipe.lpush("inmor:newsubordinate", entity)


def publish_trustmark(tm: TrustMark, pipe: Pipeline) -> None:
    """Stage the current mark and its membership while retaining historical hashes."""
    tmtype = tm.tmt.tmtype
    if not tm.active:
        pipe.hset(f"inmor:tm:{tm.domain}", tmtype, "revoked")
        pipe.srem(f"inmor:tmtype:{tmtype}", tm.domain)
        return
    if not tm.mark:
        raise ValueError("An active trust mark needs a signed token")
    pipe.hset(f"inmor:tm:{tm.domain}", tmtype, tm.mark)
    pipe.sadd(f"inmor:tmtype:{tmtype}", tm.domain)
    pipe.sadd("inmor:tmtypes", tmtype)
    pipe.sadd("inmor:tm:alltime", sha256(tm.mark.encode()).hexdigest())


@transaction.atomic
def deliver_publication(pk: int) -> None:
    """Publish the committed record and acknowledge the job after Redis succeeds."""
    # Writers update this same job before committing. Holding its lock through the
    # Redis transaction serializes retries, edits and withdrawals for this resource.
    pending = PendingPublication.objects.select_for_update().filter(pk=pk).first()
    if pending is None:
        return
    if pending.subordinate_id is not None:
        with publication_pipeline(f"subordinate:{pending.subordinate_id}") as pipe:
            # Read the resource after WATCH so losing the SQL connection before
            # opening the Redis transaction cannot publish a stale local snapshot.
            sub = pending.subordinate
            if sub is None:
                raise ValueError("Missing subordinate for publication")
            publish_subordinate(sub, pending.entity_configuration, pipe)
    else:
        with publication_pipeline(f"trustmark:{pending.trust_mark_id}") as pipe:
            tm = pending.trust_mark
            if tm is None:
                raise ValueError("Missing trust mark for publication")
            publish_trustmark(tm, pipe)
    pending.delete()
