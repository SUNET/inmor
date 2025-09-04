from django.test import TestCase
from ninja.testing import TestClient

from inmoradmin.api import router


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
