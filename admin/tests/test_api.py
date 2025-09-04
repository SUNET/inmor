from django.test import TestCase
from ninja.testing import TestClient

from inmoradmin.api import router


def test_trustmarktypes_list(db):
    # don't forget to import router from code above
    self = TestCase()
    trustmark_list = [
        {"tmtype": "https://sunet.se/does_not_exist_trustmark", "valid_for": 365},
        {"tmtype": "https://example.com/trust_mark", "valid_for": 365},
    ]
    client: TestClient = TestClient(router)
    response = client.get("/trust_mark_type/list")

    self.assertEqual(response.status_code, 200)
    marks = response.json()
    self.assertEqual(marks["count"], 2)
    self.assertEqual(marks["items"], trustmark_list)
