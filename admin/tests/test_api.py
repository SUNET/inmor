import datetime
import json
import os

import pytest
from django.test import TestCase
from jwcrypto import jwt
from jwcrypto.common import json_decode
from ninja.testing import TestClient

from inmoradmin.api import router

# from pprint import pprint


data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def get_payload(token_str: str):
    "Helper method to get payload"
    jose = jwt.JWT.from_jose_token(token_str)
    return json_decode(jose.token.objects.get("payload", ""))


def test_trustmarktypes_list(db):
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
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
    client: TestClient = TestClient(router)
    response = client.get("/trustmarktypes")

    self.assertEqual(response.status_code, 200)
    marks = response.json()
    self.assertEqual(marks["count"], 2)
    self.assertEqual(marks["items"], trustmark_list)


def test_trustmarktypes_get_byid(db):
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
    data = {
        "tmtype": "https://example.com/trust_mark_type",
        "id": 2,
        "valid_for": 720,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    client: TestClient = TestClient(router)
    response = client.get("/trustmarktypes/2")
    self.assertEqual(response.status_code, 200)
    mark = response.json()
    self.assertEqual(mark, data)


def test_trustmarktypes_get_bytype(db):
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
    data = {
        "tmtype": "https://example.com/trust_mark_type",
        "id": 2,
        "valid_for": 720,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    client: TestClient = TestClient(router)
    response = client.get(
        "/trustmarktypes/", json={"tmtype": "https://example.com/trust_mark_type"}
    )
    self.assertEqual(response.status_code, 200)
    mark = response.json()
    self.assertEqual(mark, data)


@pytest.mark.django_db
def test_trustmarktypes_create(db):
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
        "valid_for": 8760,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }
    client: TestClient = TestClient(router)
    response = client.post("/trustmarktypes", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    for key in data:
        self.assertEqual(data[key], resp.get(key))


@pytest.mark.django_db
def test_trustmarktypes_create_default(db):
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
    }
    client: TestClient = TestClient(router)
    response = client.get("/trustmarktypes")
    marks = response.json()
    self.assertEqual(marks["count"], 2)
    response = client.post("/trustmarktypes", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    for key in data:
        self.assertEqual(data[key], resp.get(key))


@pytest.mark.django_db
def test_trustmarktypes_create_double(db):
    "We will try to create same entry twice."
    # don't forget to import router from code above
    self = TestCase()
    self.maxDiff = None
    data = {
        "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
        "valid_for": 8760,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    }

    client: TestClient = TestClient(router)
    response = client.get("/trustmarktypes")
    marks = response.json()
    self.assertEqual(marks["count"], 2)
    response = client.post("/trustmarktypes", json=data)
    self.assertEqual(response.status_code, 201)
    response = client.post("/trustmarktypes", json=data)
    self.assertEqual(response.status_code, 403)
    resp = response.json()
    for key in data:
        self.assertEqual(data[key], resp.get(key))


@pytest.mark.django_db
def test_trustmarktypes_update(db):
    """Updates the values of an existing TrustMarkType."""
    self = TestCase()
    self.maxDiff = None
    data = {
        "active": False,
        "autorenew": False,
        "renewal_time": 4,
        "valid_for": 100,
    }
    client: TestClient = TestClient(router)
    response = client.put("/trustmarktypes/2", json=data)
    mark = response.json()
    for key in data:
        self.assertEqual(data[key], mark.get(key))
    # Now the other values
    self.assertEqual(2, mark.get("id"))
    self.assertEqual("https://example.com/trust_mark_type", mark.get("tmtype"))


@pytest.mark.django_db
def test_trustmark_create(db, loadredis):
    domain = "https://fakerp0.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    data = {"tmt": 2, "domain": domain, "valid_for": 24}
    client: TestClient = TestClient(router)
    response = client.post("/trustmarks", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual(domain, payload.get("sub"))
    self.assertEqual("https://example.com/trust_mark_type", payload.get("trust_mark_type"))
    # Here data is signed JWT
    data = loadredis.hget(f"inmor:tm:{domain}", payload["trust_mark_type"])
    self.assertIsNotNone(data)
    # Also this should be the same we received via response
    self.assertEqual(data.decode("utf-8"), jwt_token)
    # The following is to test #51
    iat = datetime.datetime.fromtimestamp(payload.get("iat"), datetime.timezone.utc)
    exp = datetime.datetime.fromtimestamp(payload.get("exp"), datetime.timezone.utc)
    diff = exp - iat
    self.assertEqual(diff.days, 1)


@pytest.mark.django_db
def test_trustmark_create_with_additional_claims(db, loadredis):
    """Test creating a trustmark with additional_claims and verify they appear in the JWT payload."""
    domain = "https://fakerp0.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    additional_claims = {"ref": "https://github.com/SUNET/inmor"}
    data = {"tmt": 2, "domain": domain, "valid_for": 24, "additional_claims": additional_claims}
    client: TestClient = TestClient(router)
    response = client.post("/trustmarks", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual(domain, payload.get("sub"))
    self.assertEqual("https://example.com/trust_mark_type", payload.get("trust_mark_type"))
    # Verify the additional claim is present in the JWT payload
    self.assertEqual("https://github.com/SUNET/inmor", payload.get("ref"))


@pytest.mark.django_db
def test_trustmark_update_additional_claims(db, loadredis):
    """Test updating a trustmark's additional_claims and verify changes in JWT payload."""
    domain = "https://fakerp2.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None

    # Step 1: Create trustmark with initial additional_claims
    additional_claims = {"ref": "https://github.com/SUNET/inmor"}
    data = {"tmt": 2, "domain": domain, "valid_for": 24, "additional_claims": additional_claims}
    client: TestClient = TestClient(router)
    response = client.post("/trustmarks", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    trustmark_id = resp["id"]
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual("https://github.com/SUNET/inmor", payload.get("ref"))

    # Step 2: Update additional_claims with different value
    update_data = {"additional_claims": {"ref": "https://python.org"}}
    response = client.put(f"/trustmarks/{trustmark_id}", json=update_data)
    self.assertEqual(response.status_code, 200)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Verify the updated claim is present in the JWT payload
    self.assertEqual("https://python.org", payload.get("ref"))

    # Step 3: Update additional_claims to None
    update_data = {"additional_claims": None}
    response = client.put(f"/trustmarks/{trustmark_id}", json=update_data)
    self.assertEqual(response.status_code, 200)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Verify the claim is removed from the JWT payload
    self.assertIsNone(payload.get("ref"))


@pytest.mark.django_db
def test_trustmark_create_twice(db, loadredis):
    domain = "https://fakerp0.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    data = {"tmt": 2, "domain": domain}
    client: TestClient = TestClient(router)
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual(domain, payload.get("sub"))
    self.assertEqual("https://example.com/trust_mark_type", payload.get("trust_mark_type"))
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 403)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual(domain, payload.get("sub"))
    self.assertEqual("https://example.com/trust_mark_type", payload.get("trust_mark_type"))


@pytest.mark.django_db
def test_trustmark_list(db, loadredis):
    domain0 = "https://fakerp0.labb.sunet.se"
    domain1 = "https://fakerp1.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)
    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)
    # Add the second trustmark
    data = {"tmt": 2, "domain": domain1}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)

    response = client.get("/trustmarks")
    self.assertEqual(response.status_code, 200)

    # Now verify the data we received
    resp = response.json()
    self.assertTrue(isinstance(resp.get("items"), list))
    self.assertEqual(2, resp["count"])


@pytest.mark.django_db
def test_trustmark_list_entity(db, loadredis):
    domain0 = "https://fakerp0.labb.sunet.se"
    domain1 = "https://fakerp1.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)
    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)
    # Add the second trustmark
    data = {"tmt": 2, "domain": domain1}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)

    data = {"domain": domain0}
    response = client.post("/trustmarks/list", json=data)
    self.assertEqual(response.status_code, 200)

    # Now verify the data we received
    resp = response.json()
    self.assertTrue(isinstance(resp.get("items"), list))
    self.assertEqual(1, resp["count"])


@pytest.mark.django_db
def test_trustmark_renew(db, loadredis):
    domain0 = "https://fakerp0.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)
    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)
    resp = response.json()
    response = client.post(f"/trustmarks/{resp['id']}/renew")
    self.assertEqual(response.status_code, 200)
    # TODO: Now verify the rewnewd trustmark


@pytest.mark.django_db
def test_trustmark_update(db, loadredis):
    domain0 = "https://fakerp0.labb.sunet.se"

    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)
    # Add the first trustmark
    data = {"tmt": 2, "domain": domain0}
    response = client.post("/trustmarks", json=data)
    self.assertEqual(response.status_code, 201)
    resp = response.json()
    # At this moment redis MUST have the data related to the trustmark
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    # Here data is signed JWT
    data = loadredis.hget(f"inmor:tm:{domain0}", payload["trust_mark_type"])
    self.assertIsNotNone(data)
    update_data = {"autorenew": False, "active": False}
    response = client.put(f"/trustmarks/{resp['id']}", json=update_data)
    self.assertEqual(response.status_code, 200)
    resp = response.json()
    # The response itself should have JWT anymore.
    self.assertFalse(resp["mark"])
    # Here data is signed JWT
    data = loadredis.hget(f"inmor:tm:{domain0}", payload["trust_mark_type"])
    self.assertEqual(data, b"revoked")
    self.assertEqual(False, resp.get("autorenew"))
    self.assertEqual(False, resp.get("active"))


@pytest.mark.django_db
def test_add_subordinate(db, loadredis, conf_settings):  # type: ignore
    "Tests adding subordinate without passing any JWKS"
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

    with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
        metadata = json.load(fobj)
    data = {
        "entityid": "https://fakerp0.labb.sunet.se",
        "metadata": metadata,
        "forced_metadata": {},
    }

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 422)


@pytest.mark.django_db
def test_add_subordinate_with_key(db, loadredis):  # type: ignore
    "Tests adding subordinate"
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

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

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 201)
    d1 = response.json()
    # This is because the keys are sent separately
    self.assertEqual(keys, d1.get("jwks"))


@pytest.mark.django_db
def test_add_subordinate_with_key_twice(db, loadredis):  # type: ignore
    "Tests adding subordinate"
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

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

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 201)
    d1 = response.json()
    # This is because the keys are sent separately
    self.assertEqual(keys, d1.get("jwks"))

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 403)


@pytest.mark.django_db
def test_list_subordinates(db, loadredis):  # type: ignore
    "Tests listing subordinates"
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

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

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 201)

    response = client.get("/subordinates")
    self.assertEqual(response.status_code, 200)

    marks = response.json()
    self.assertEqual(marks["count"], 1)


@pytest.mark.django_db
def test_get_subordinate_byid(db, loadredis):  # type: ignore
    "Tests listing subordinates"
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

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

    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 201)
    original = response.json()

    response = client.get(f"/subordinates/{original['id']}")
    self.assertEqual(response.status_code, 200)

    new = response.json()
    self.assertEqual(original, new)


@pytest.mark.django_db
def test_update_subordinate_autorenew(db, loadredis):
    """Test updating a subordinate's autorenew field to False and verify the update."""
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

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
    response = client.post("/subordinates", json=data)
    self.assertEqual(response.status_code, 201)
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
    response = client.post(f"/subordinates/{original['id']}", json=update_data)
    self.assertEqual(response.status_code, 200)
    updated = response.json()
    self.assertEqual(updated.get("autorenew"), False)


@pytest.mark.django_db
def test_create_server_entity(db, loadredis):
    """Tests creation of server's entity_id"""
    self = TestCase()
    self.maxDiff = None
    client: TestClient = TestClient(router)

    response = client.post("/server/entity")
    self.assertEqual(response.status_code, 201)
    _entity_statement = response.json()
    # TODO: Add the checks in the response
