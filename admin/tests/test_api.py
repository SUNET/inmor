import pytest
from django.test import TestCase
from jwcrypto import jwt
from jwcrypto.common import json_decode
from ninja.testing import TestClient

from inmoradmin.api import router


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
    data = {"tmt": 2, "domain": domain}
    client: TestClient = TestClient(router)
    response = client.post("/trustmarks", json=data)

    self.assertEqual(response.status_code, 201)
    resp = response.json()
    jwt_token = resp["mark"]
    payload = get_payload(jwt_token)
    self.assertEqual(domain, payload.get("sub"))
    self.assertEqual("https://example.com/trust_mark_type", payload.get("trust_mark_type"))


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



