"""Check database rollback, Redis retries, and ordering at real commit boundaries."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event

import httpx
import pytest
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from redis.exceptions import WatchError

from auditlog.models import AuditLogEntry
from common.signing import create_signed_jwt
from entities import publication
from entities.models import IssuedTrustMarkHash, PendingPublication, Subordinate
from trustmarks.models import TrustMark


pytestmark = pytest.mark.django_db(transaction=True)


def test_registration_waits_for_commit(auth_client, loadredis, settings, monkeypatch):
    """An outer rollback must discard the registration, its audit entry and its Redis work."""
    entity = "https://registration.example"
    key = settings.SIGNING_PRIVATE_KEY
    jwks = {"keys": [key.export_public(as_dict=True)]}
    metadata = {"openid_relying_party": {}}
    config = create_signed_jwt(
        {
            "iss": entity,
            "sub": entity,
            "jwks": jwks,
            "authority_hints": [settings.TA_DOMAIN],
            "metadata": metadata,
        },
        key,
        "entity-statement+jwt",
    )
    monkeypatch.setattr(
        "entities.lib._federation_get", lambda url: httpx.Response(200, text=config)
    )
    data = {"entityid": entity, "jwks": jwks, "metadata": metadata, "forced_metadata": {}}
    url = "/api/v1/subordinates"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            assert auth_client.post(url, data, "application/json").status_code == 201
            assert PendingPublication.objects.filter(subordinate__entityid=entity).exists()
            assert not loadredis.hexists("inmor:subordinates", entity)
            # PostgreSQL checks this foreign key at COMMIT, after the view returned.
            PendingPublication.objects.create(subordinate_id=-1)
    assert not Subordinate.objects.filter(entityid=entity).exists()
    assert not AuditLogEntry.objects.filter(resource_repr=entity).exists()
    assert not PendingPublication.objects.exists()
    assert not loadredis.sismember("inmor:rp", entity)

    # Exercise a successful commit and a subsequently rolled-back reactivation.
    result = auth_client.post(url, data, "application/json")
    assert result.status_code == 201
    assert loadredis.hget("inmor:subordinates:jwt", entity) == config.encode()
    detail = f"{url}/{result.json()['id']}"
    assert auth_client.post(detail, {"active": False}, "application/json").status_code == 200
    with transaction.atomic():
        assert (
            auth_client.post(detail, {**data, "active": True}, "application/json").status_code
            == 200
        )
        transaction.set_rollback(True)
    assert not Subordinate.objects.get(entityid=entity).active
    assert not loadredis.hexists("inmor:subordinates", entity)
    assert not loadredis.lrange("inmor:newsubordinate", 0, -1)


def test_trustmark_audit_failure_keeps_revocation(auth_client, loadredis, monkeypatch):
    """A failed reactivation audit must preserve both the stored and the public revocation."""
    domain = "https://revoked.example"
    result = auth_client.post(
        "/api/v1/trustmarks", {"tmt": 2, "domain": domain}, "application/json"
    )
    assert result.status_code == 201
    tm = TrustMark.objects.get(pk=result.json()["id"])
    url = f"/api/v1/trustmarks/{tm.pk}"
    assert auth_client.put(url, {"active": False}, "application/json").status_code == 200

    # Even a signed and queued token must disappear if the enclosing transaction rolls back.
    with transaction.atomic():
        assert auth_client.put(url, {"active": True}, "application/json").status_code == 200
        assert IssuedTrustMarkHash.objects.count() == 2
        transaction.set_rollback(True)
    assert IssuedTrustMarkHash.objects.count() == 1

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr("inmoradmin.api.log_update", fail_audit)
    assert auth_client.put(url, {"active": True}, "application/json").status_code == 500
    tm.refresh_from_db()
    assert not tm.active and tm.mark is None
    assert not PendingPublication.objects.exists()
    assert loadredis.hget(f"inmor:tm:{domain}", tm.tmt.tmtype) == b"revoked"
    assert not loadredis.sismember(f"inmor:tmtype:{tm.tmt.tmtype}", domain)
    assert loadredis.scard("inmor:tm:alltime") == 1
    assert IssuedTrustMarkHash.objects.count() == 1


def test_redis_outage_keeps_committed_mark_for_retry(auth_client, loadredis, monkeypatch):
    """Retry delivery of the signed and audited mark after Redis becomes available."""
    domain = "https://outage.example"

    def unavailable(alias):
        raise ConnectionError("Redis unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(publication, "get_redis_connection", unavailable)
        response = auth_client.post(
            "/api/v1/trustmarks", {"tmt": 2, "domain": domain}, "application/json"
        )
    assert response.status_code == 500
    tm = TrustMark.objects.get(domain=domain)
    assert tm.mark is not None
    assert AuditLogEntry.objects.filter(resource_type="TrustMark", resource_id=tm.pk).exists()
    assert PendingPublication.objects.filter(trust_mark=tm).exists()
    assert not loadredis.exists(f"inmor:tm:{domain}")

    # Recovery uses the committed JWT, including its original issue time and expiry.
    call_command("retry_publications")
    assert not PendingPublication.objects.exists()
    assert loadredis.hget(f"inmor:tm:{domain}", tm.tmt.tmtype) == tm.mark.encode()


def test_retry_after_interrupted_subordinate_publication(loadredis, monkeypatch):
    """Replay the committed payload even when Redis succeeded before acknowledgement failed."""
    sub = Subordinate.objects.create(entityid="https://retry.example", statement="statement")
    with monkeypatch.context() as patch:

        def lose_ack(*args, **kwargs):
            raise RuntimeError("acknowledgement failed")

        patch.setattr(PendingPublication, "delete", lose_ack)
        with pytest.raises(RuntimeError, match="acknowledgement failed"):
            with transaction.atomic():
                publication.queue_publication(sub, "configuration")

    assert PendingPublication.objects.filter(subordinate=sub).exists()
    call_command("retry_publications")
    assert not PendingPublication.objects.exists()
    assert loadredis.hget("inmor:subordinates", sub.entityid) == b"statement"
    assert loadredis.lrange("inmor:newsubordinate", 0, -1) == [sub.entityid.encode()]


@pytest.mark.parametrize("replacement", [{"active": False}, {"additional_claims": {"ref": "new"}}])
def test_late_callback_preserves_issuance_history(auth_client, loadredis, monkeypatch, replacement):
    """Both callbacks preserve the first JWT and publish only the latest membership state."""
    entered, resume = Event(), Event()
    deliver = publication.deliver_publication
    domain = "https://ordering.example"

    def delayed(pk):
        # Pause the first callback after commit, before it acquires the job lock.
        if not entered.is_set():
            entered.set()
            assert resume.wait(15)
        deliver(pk)

    def issue():
        try:
            return auth_client.post(
                "/api/v1/trustmarks", {"tmt": 2, "domain": domain}, "application/json"
            )
        finally:
            connections.close_all()

    monkeypatch.setattr(publication, "deliver_publication", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(issue)
        try:
            assert entered.wait(15)
            tm = TrustMark.objects.get(domain=domain)
            response = auth_client.put(
                f"/api/v1/trustmarks/{tm.pk}", replacement, "application/json"
            )
            assert response.status_code == 200
        finally:
            resume.set()
        issued = result.result()
        assert issued.status_code == 201
    first = issued.json()["mark"]
    expected = {sha256(first.encode()).hexdigest().encode()}
    latest = response.json()["mark"]
    if latest is not None:
        assert latest != first
        expected.add(sha256(latest.encode()).hexdigest().encode())
    assert not PendingPublication.objects.exists()
    assert loadredis.hget(f"inmor:tm:{domain}", tm.tmt.tmtype) == (latest or "revoked").encode()
    assert bool(loadredis.sismember(f"inmor:tmtype:{tm.tmt.tmtype}", domain)) == bool(latest)
    assert loadredis.smembers("inmor:tm:alltime") == expected
    # Rebuilding the status index after Redis loss also preserves the superseded JWT.
    loadredis.delete("inmor:tm:alltime")
    call_command("reload_issued_tms")
    assert expected <= loadredis.smembers("inmor:tm:alltime")


@pytest.mark.parametrize("update", [{"active": True}, {"additional_claims": {"ref": "changed"}}])
def test_identical_update_retries_committed_jwt(auth_client, loadredis, monkeypatch, update):
    """A replay of a failed PUT delivers the saved JWT without signing another token."""
    domain = "https://replay.example"
    issued = auth_client.post(
        "/api/v1/trustmarks", {"tmt": 2, "domain": domain}, "application/json"
    )
    assert issued.status_code == 201
    tm = TrustMark.objects.get(pk=issued.json()["id"])
    url = f"/api/v1/trustmarks/{tm.pk}"
    if "active" in update:
        assert auth_client.put(url, {"active": False}, "application/json").status_code == 200

    def unavailable(alias):
        raise ConnectionError("Redis unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(publication, "get_redis_connection", unavailable)
        assert auth_client.put(url, update, "application/json").status_code == 500
        tm.refresh_from_db()
        saved = tm.mark
        assert saved and saved != issued.json()["mark"]
        assert loadredis.hget(f"inmor:tm:{domain}", tm.tmt.tmtype) != saved.encode()
        # A second attempt during the outage must still report delivery failure.
        assert auth_client.put(url, update, "application/json").status_code == 500

    monkeypatch.setattr("inmoradmin.api.issue_trustmark", lambda *args: pytest.fail("re-signed"))
    result = auth_client.put(url, update, "application/json")
    assert result.status_code == 200
    assert result.json()["mark"] == saved
    assert not PendingPublication.objects.exists()
    assert loadredis.hget(f"inmor:tm:{domain}", tm.tmt.tmtype) == saved.encode()
    assert loadredis.sismember("inmor:tm:alltime", sha256(saved.encode()).hexdigest())


def test_delayed_redis_execution_after_withdrawal(loadredis):
    """Redis rejects a late publication even when an earlier writer lost its SQL lock."""
    with pytest.raises(WatchError):
        with publication.publication_pipeline("subordinate:1") as delayed:
            delayed.hset("inmor:subordinates", "example", "old statement")
            # Deliver the withdrawal on another Redis connection before the old EXEC arrives.
            with publication.publication_pipeline("subordinate:1") as current:
                current.hdel("inmor:subordinates", "example")
    assert not loadredis.hexists("inmor:subordinates", "example")
