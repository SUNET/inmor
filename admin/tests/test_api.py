import datetime
import json
import os
from typing import Any

import pytest
from django.test import Client
from jwcrypto import jwt
from jwcrypto.common import json_decode

from entities.lib import self_validate

# from pprint import pprint


data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def get_payload(token_str: str):
    "Helper method to get payload"
    jose = jwt.JWT.from_jose_token(token_str)
    return json_decode(jose.token.objects.get("payload", ""))


def get_header(token_str: str):
    "Helper method to get JWT header"
    jose = jwt.JWT.from_jose_token(token_str)
    protected = jose.token.objects.get("protected", "")
    if isinstance(protected, bytes):
        protected = protected.decode("utf-8")
    return json.loads(protected)


def test_trustmarktypes_list(auth_client: Client):
    trustmark_list = [
        {
            "tmtype": "https://sunet.se/does_not_exist_trustmark",
            "id": 1,
            "valid_for": 8760,
            "active": True,
            "autorenew": True,
            "renewal_time": 48,
        },
        {
            "tmtype": "https://example.com/trust_mark_type",
            "id": 2,
            "valid_for": 720,
            "active": True,
            "autorenew": True,
            "renewal_time": 48,
        },
    ]
    response = auth_client.get("/api/v1/trustmarktypes")

    assert response.status_code == 200
    marks = response.json()
    assert marks["count"] == 2
    assert marks["items"] == trustmark_list


def test_trustmarktypes_get_byid(auth_client: Client):
    data = {
        "tmtype": "https://example.com/trust_mark_type",
        "id": 2,
        "valid_for": 720,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    response = auth_client.get("/api/v1/trustmarktypes/2")
    assert response.status_code == 200
    mark = response.json()
    assert mark == data


def test_trustmarktypes_get_bytype(auth_client: Client):
    data = {
        "tmtype": "https://example.com/trust_mark_type",
        "id": 2,
        "valid_for": 720,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    response = auth_client.generic(
        "GET",
        "/api/v1/trustmarktypes/",
        data=json.dumps({"tmtype": "https://example.com/trust_mark_type"}),
        content_type="application/json",
    )
    assert response.status_code == 200  # type: ignore[union-attr]
    mark = response.json()  # type: ignore[union-attr]
    assert mark == data


@pytest.mark.django_db
def test_trustmarktypes_create(auth_client: Client):
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
        "valid_for": 8760,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    response = auth_client.post(
        "/api/v1/trustmarktypes",
        data=json.dumps(data),
        content_type="application/json",
    )

    assert response.status_code == 201
    resp = response.json()
    for key in data:
        assert data[key] == resp.get(key)


@pytest.mark.django_db
def test_trustmarktypes_create_default(auth_client: Client):
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
    }
    response = auth_client.get("/api/v1/trustmarktypes")
    marks = response.json()
    assert marks["count"] == 2
    response = auth_client.post(
        "/api/v1/trustmarktypes",
        data=json.dumps(data),
        content_type="application/json",
    )

    assert response.status_code == 201
    resp = response.json()
    for key in data:
        assert data[key] == resp.get(key)


@pytest.mark.django_db
def test_trustmarktypes_create_double(auth_client: Client):
    "We will try to create same entry twice."
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
        "valid_for": 8760,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }

    response = auth_client.get("/api/v1/trustmarktypes")
    marks = response.json()
    assert marks["count"] == 2
    response = auth_client.post(
        "/api/v1/trustmarktypes",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    response = auth_client.post(
        "/api/v1/trustmarktypes",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 403
    resp = response.json()
    for key in data:
        assert data[key] == resp.get(key)


@pytest.mark.django_db
def test_trustmarktypes_update(auth_client: Client):
    """Updates the values of an existing TrustMarkType."""
    data = {
        "active": False,
        "autorenew": False,
        "renewal_time": 4,
        "valid_for": 100,
    }
    response = auth_client.put(
        "/api/v1/trustmarktypes/2",
        data=json.dumps(data),
        content_type="application/json",
    )
    mark = response.json()
    for key in data:
        assert data[key] == mark.get(key)
    # Now the other values
    assert 2 == mark.get("id")
    assert "https://example.com/trust_mark_type" == mark.get("tmtype")


@pytest.mark.django_db
def test_trustmark_create(auth_client: Client, loadredis):
    domain = "https://newrp.test.example.com"

    data = {"tmt": 2, "domain": domain, "valid_for": 24}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )

    assert response.status_code == 201
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    assert domain == payload.get("sub")
    assert "https://example.com/trust_mark_type" == payload.get("trust_mark_type")
    # Verify JWT header has correct typ per spec
    header = get_header(jwt_token)
    assert header.get("typ") == "trust-mark+jwt"
    # Here data is signed JWT
    redis_data = loadredis.hget(f"inmor:tm:{domain}", payload["trust_mark_type"])
    assert redis_data is not None
    # Also this should be the same we received via response
    assert redis_data.decode("utf-8") == jwt_token
    # The following is to test #51
    iat = datetime.datetime.fromtimestamp(payload.get("iat"), datetime.timezone.utc)
    exp = datetime.datetime.fromtimestamp(payload.get("exp"), datetime.timezone.utc)
    diff = exp - iat
    assert diff.days == 1


@pytest.mark.django_db
def test_trustmark_create_with_additional_claims(auth_client: Client, loadredis):
    """Test creating a trustmark with additional_claims and verify they appear in the JWT payload."""
    domain = "https://newrp0.test.example.com"

    additional_claims = {"ref": "https://github.com/SUNET/inmor"}
    data = {"tmt": 2, "domain": domain, "valid_for": 24, "additional_claims": additional_claims}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )

    assert response.status_code == 201
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    assert domain == payload.get("sub")
    assert "https://example.com/trust_mark_type" == payload.get("trust_mark_type")
    # Verify JWT header has correct typ per spec
    header = get_header(jwt_token)
    assert header.get("typ") == "trust-mark+jwt"
    # Verify the additional claim is present in the JWT payload
    assert "https://github.com/SUNET/inmor" == payload.get("ref")


@pytest.mark.django_db
def test_trustmark_update_additional_claims(auth_client: Client, loadredis):
    """Test updating a trustmark's additional_claims and verify changes in JWT payload."""
    domain = "https://fakerp2.labb.sunet.se"

    # Step 1: Create trustmark with initial additional_claims
    additional_claims = {"ref": "https://github.com/SUNET/inmor"}
    data = {"tmt": 2, "domain": domain, "valid_for": 24, "additional_claims": additional_claims}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )

    assert response.status_code == 201
    resp = response.json()
    trustmark_id = resp["id"]
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    assert "https://github.com/SUNET/inmor" == payload.get("ref")

    # Step 2: Update additional_claims with different value
    update_data = {"additional_claims": {"ref": "https://python.org"}}
    response = auth_client.put(
        f"/api/v1/trustmarks/{trustmark_id}",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Verify the updated claim is present in the JWT payload
    assert "https://python.org" == payload.get("ref")

    # Step 3: Update additional_claims to None
    update_data = {"additional_claims": None}
    response = auth_client.put(
        f"/api/v1/trustmarks/{trustmark_id}",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Verify the claim is removed from the JWT payload
    assert payload.get("ref") is None


@pytest.mark.django_db
def test_trustmark_create_twice(auth_client: Client, loadredis):
    domain = "https://newrp0.test.example.com"

    data = {"tmt": 2, "domain": domain}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    assert domain == payload.get("sub")
    assert "https://example.com/trust_mark_type" == payload.get("trust_mark_type")
    # Verify JWT header has correct typ per spec
    header = get_header(jwt_token)
    assert header.get("typ") == "trust-mark+jwt"
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 403
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    assert domain == payload.get("sub")
    assert "https://example.com/trust_mark_type" == payload.get("trust_mark_type")


@pytest.mark.django_db
def test_trustmark_list(auth_client: Client, loadredis):
    # Get initial count (fixture may have existing trustmarks)
    response = auth_client.get("/api/v1/trustmarks")
    initial_count = response.json()["count"]

    domain0 = "https://newrp0.test.example.com"
    domain1 = "https://newrp1.test.example.com"

    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    # Add the second trustmark
    data = {"tmt": 2, "domain": domain1}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201

    response = auth_client.get("/api/v1/trustmarks")
    assert response.status_code == 200

    # Now verify the data we received
    resp = response.json()
    assert isinstance(resp.get("items"), list)
    # Verify we have 2 more trustmarks than before
    assert resp["count"] == initial_count + 2


@pytest.mark.django_db
def test_trustmark_list_entity(auth_client: Client, loadredis):
    domain0 = "https://newrp0.test.example.com"
    domain1 = "https://newrp1.test.example.com"

    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    # Add the second trustmark
    data = {"tmt": 2, "domain": domain1}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201

    data = {"domain": domain0}
    response = auth_client.post(
        "/api/v1/trustmarks/list",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 200

    # Now verify the data we received
    resp = response.json()
    assert isinstance(resp.get("items"), list)
    assert 1 == resp["count"]


@pytest.mark.django_db
def test_trustmark_renew(auth_client: Client, loadredis):
    domain0 = "https://newrp0.test.example.com"

    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    resp = response.json()
    original_mark = resp["mark"]
    original_payload = get_payload(original_mark)
    original_exp = original_payload.get("exp")
    trustmark_id = resp["id"]

    # Renew the trustmark
    response = auth_client.post(f"/api/v1/trustmarks/{trustmark_id}/renew")
    assert response.status_code == 200
    renewed_resp = response.json()
    renewed_mark = renewed_resp["mark"]
    renewed_payload = get_payload(renewed_mark)
    renewed_exp = renewed_payload.get("exp")

    # Verify expiry date is higher after renewal
    assert renewed_exp > original_exp

    # Verify other attributes remain the same
    assert renewed_payload.get("sub") == original_payload.get("sub")
    assert renewed_payload.get("iss") == original_payload.get("iss")
    assert renewed_payload.get("trust_mark_type") == original_payload.get("trust_mark_type")
    assert renewed_resp.get("domain") == domain0
    assert renewed_resp.get("id") == trustmark_id


@pytest.mark.django_db
def test_trustmark_update(auth_client: Client, loadredis):
    domain0 = "https://newrp0.test.example.com"

    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = auth_client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    resp = response.json()
    # At this moment redis MUST have the data related to the trustmark
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Here data is signed JWT
    redis_data = loadredis.hget(f"inmor:tm:{domain0}", payload["trust_mark_type"])
    assert redis_data is not None
    update_data = {"autorenew": False, "active": False}
    response = auth_client.put(
        f"/api/v1/trustmarks/{resp['id']}",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    resp = response.json()
    # The response itself should have JWT anymore.
    assert not resp["mark"]
    # Here data is signed JWT
    redis_data = loadredis.hget(f"inmor:tm:{domain0}", payload["trust_mark_type"])
    assert redis_data == b"revoked"
    assert resp.get("autorenew") is False
    assert resp.get("active") is False


@pytest.mark.django_db
def test_add_subordinate(auth_client: Client, loadredis, conf_settings):  # type: ignore
    "Tests adding subordinate without passing any JWKS"
    with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
        metadata = json.load(fobj)
    data = {
        "entityid": "https://newsubordinate.test.example.com",
        "metadata": metadata,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_add_subordinate_with_key(auth_client: Client, loadredis, clean_subordinate):  # type: ignore
    "Tests adding subordinate"
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)

    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    d1 = response.json()
    # This is because the keys are sent separately
    assert keys == d1.get("jwks")


@pytest.mark.django_db
def test_add_subordinate_with_key_twice(auth_client: Client, loadredis, clean_subordinate):  # type: ignore
    "Tests adding subordinate"
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)

    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    d1 = response.json()
    # This is because the keys are sent separately
    assert keys == d1.get("jwks")

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_add_subordinate_with_forced_metadata(auth_client: Client, loadredis, clean_subordinate):  # type: ignore
    "Tests listing subordinates"
    with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
        metadata = json.load(fobj)

    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {"openid_relying_party": {"application_type": "mutant"}},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    resp = response.json()
    assert resp["forced_metadata"] == data["forced_metadata"]


@pytest.mark.django_db
def test_list_subordinates(auth_client: Client, loadredis, clean_subordinate):  # type: ignore
    "Tests listing subordinates"
    # Get initial count (fixture may have existing subordinates)
    response = auth_client.get("/api/v1/subordinates")
    initial_count = response.json()["count"]

    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)

    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201

    response = auth_client.get("/api/v1/subordinates")
    assert response.status_code == 200

    marks = response.json()
    # Verify we have one more subordinate than before
    assert marks["count"] == initial_count + 1


@pytest.mark.django_db
def test_get_subordinate_byid(auth_client: Client, loadredis, clean_subordinate):  # type: ignore
    "Tests listing subordinates"
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)

    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    original = response.json()

    response = auth_client.get(f"/api/v1/subordinates/{original['id']}")
    assert response.status_code == 200

    new = response.json()
    assert original == new


@pytest.mark.django_db
def test_update_subordinate_autorenew(auth_client: Client, loadredis, clean_subordinate):
    """Test updating a subordinate's autorenew field to False and verify the update."""
    # Add a subordinate first
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)
    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }

    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    original = response.json()

    # Prepare full update data, flipping autorenew to False
    update_data = {
        "metadata": metadata,
        "forced_metadata": {},
        "jwks": keys,
        "entityid": original["entityid"],
        "required_trustmarks": original.get("required_trustmarks"),
        "valid_for": original.get("valid_for"),
        "autorenew": False,
        "active": original.get("active", True),
    }
    response = auth_client.post(
        f"/api/v1/subordinates/{original['id']}",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated.get("autorenew") is False


@pytest.mark.django_db
def test_renew_subordinate(auth_client: Client, loadredis, clean_subordinate):
    """Test renewing a subordinate re-fetches and re-verifies its entity configuration."""
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)
    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    # Create a subordinate first
    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }
    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    original = response.json()

    # Now renew the subordinate
    response = auth_client.post(f"/api/v1/subordinates/{original['id']}/renew")
    assert response.status_code == 200
    renewed = response.json()
    assert renewed["entityid"] == original["entityid"]
    assert renewed["id"] == original["id"]
    assert renewed["active"] is True


@pytest.mark.django_db
def test_renew_inactive_subordinate(auth_client: Client, loadredis, clean_subordinate):
    """Test that renewing an inactive subordinate returns 400."""
    with open(os.path.join(data_dir, "fakerp0_metadata_without_key.json")) as fobj:
        metadata = json.load(fobj)
    with open(os.path.join(data_dir, "fakerp0_key.json")) as fobj:
        keys = json.load(fobj)

    # Create and then deactivate a subordinate
    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "jwks": keys,
        "forced_metadata": {},
    }
    response = auth_client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 201
    original = response.json()

    # Deactivate
    update_data = {
        "metadata": metadata,
        "forced_metadata": {},
        "jwks": keys,
        "active": False,
    }
    response = auth_client.post(
        f"/api/v1/subordinates/{original['id']}",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    assert response.status_code == 200

    # Try to renew - should fail
    response = auth_client.post(f"/api/v1/subordinates/{original['id']}/renew")
    assert response.status_code == 400


@pytest.mark.django_db
def test_renew_nonexistent_subordinate(auth_client: Client, loadredis):
    """Test that renewing a non-existent subordinate returns 404."""
    response = auth_client.post("/api/v1/subordinates/99999/renew")
    assert response.status_code == 404


@pytest.mark.django_db
def test_create_server_entity(auth_client: Client, loadredis):
    """Tests creation of server's entity_id"""
    response = auth_client.post("/api/v1/server/entity")
    assert response.status_code == 201
    entity_statement = response.json().get("entity_statement")
    assert entity_statement is not None
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(entity_statement)
    payload = self_validate(jwt_net)

    # Verify sub and iss claims
    base_url = "https://localhost:8080"
    assert payload.get("sub") == base_url
    assert payload.get("iss") == base_url

    # Check that metadata contains federation_entity with correct endpoints
    metadata: dict[str, Any] = payload.get("metadata", {})

    assert metadata is not None, "metadata missing from payload"
    federation_entity = metadata.get("federation_entity", {})
    assert federation_entity is not None, "federation_entity missing from metadata"

    # Verify all FEDERATION_ENTITY endpoints are present and have expected values
    assert federation_entity.get("federation_fetch_endpoint") == f"{base_url}/fetch"
    assert federation_entity.get("federation_list_endpoint") == f"{base_url}/list"
    assert federation_entity.get("federation_resolve_endpoint") == f"{base_url}/resolve"
    assert (
        federation_entity.get("federation_trust_mark_status_endpoint")
        == f"{base_url}/trust_mark_status"
    )
    assert (
        federation_entity.get("federation_trust_mark_list_endpoint")
        == f"{base_url}/trust_mark_list"
    )
    assert federation_entity.get("federation_trust_mark_endpoint") == f"{base_url}/trust_mark"

    # Verify we have our own Trustmark for TA
    tms = payload.get("trust_marks", [])
    assert len(tms) == 1
    assert tms[0].get("trust_mark_type", "") == "https://sunet.se/does_not_exist_trustmark"


@pytest.mark.django_db
def test_create_historical_keys(auth_client: Client, loadredis):
    """Tests creation of historical keys JWT"""
    response = auth_client.post("/api/v1/server/historical_keys")
    assert response.status_code == 201
    resp = response.json()
    assert "2 keys" in resp.get("message", "")

    # Verify JWT is stored in Redis
    token = loadredis.get("inmor:historical_keys")
    assert token is not None

    # Verify JWT payload
    payload = get_payload(token.decode("utf-8"))
    assert payload.get("iss") == "https://localhost:8080"
    assert payload.get("iat") is not None

    # Verify keys in payload (only keys with exp field)
    keys = payload.get("keys", [])
    assert len(keys) == 2


@pytest.mark.django_db
def test_create_historical_keys_missing_dir(auth_client: Client, loadredis, settings):
    """Tests that 404 is returned when historical keys directory doesn't exist"""
    settings.HISTORICAL_KEYS_DIR = "/nonexistent/path/to/keys"

    response = auth_client.post("/api/v1/server/historical_keys")
    assert response.status_code == 404
    assert "directory not found" in response.json().get("message", "")


# ============================================================================
# Unauthenticated Access Tests
# ============================================================================


def test_unauthenticated_trustmarktypes_list(db):
    """Verify unauthenticated requests to trustmarktypes list are rejected."""
    client = Client()
    response = client.get("/api/v1/trustmarktypes")
    assert response.status_code == 401


def test_unauthenticated_trustmarktypes_create(db):
    """Verify unauthenticated requests to create trustmarktype are rejected."""
    client = Client()
    data = {"tmtype": "https://test.example.com/trustmark"}
    response = client.post(
        "/api/v1/trustmarktypes",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_unauthenticated_trustmarks_list(db):
    """Verify unauthenticated requests to trustmarks list are rejected."""
    client = Client()
    response = client.get("/api/v1/trustmarks")
    assert response.status_code == 401


def test_unauthenticated_trustmarks_create(db):
    """Verify unauthenticated requests to create trustmark are rejected."""
    client = Client()
    data = {"tmt": 1, "domain": "https://example.com"}
    response = client.post(
        "/api/v1/trustmarks",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_unauthenticated_subordinates_list(db):
    """Verify unauthenticated requests to subordinates list are rejected."""
    client = Client()
    response = client.get("/api/v1/subordinates")
    assert response.status_code == 401


def test_unauthenticated_subordinates_create(db):
    """Verify unauthenticated requests to create subordinate are rejected."""
    client = Client()
    data = {"entityid": "https://example.com", "metadata": {}, "jwks": {}}
    response = client.post(
        "/api/v1/subordinates",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_unauthenticated_server_entity(db):
    """Verify unauthenticated requests to server entity are rejected."""
    client = Client()
    response = client.post("/api/v1/server/entity")
    assert response.status_code == 401
