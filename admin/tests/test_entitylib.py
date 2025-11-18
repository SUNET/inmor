import json
import os
from typing import Any

import pytest
from django.test import TestCase
from jwcrypto import jwt
from jwcrypto.common import json_decode

from entities import lib

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def get_payload(token_str: str):
    "Helper method to get payload"
    jose = jwt.JWT.from_jose_token(token_str)
    return json_decode(jose.token.objects.get("payload", ""))


def test_fetch_entity_configuration_with_keys():
    "Tests fetching entity configuration and verification."
    self = TestCase()
    self.maxDiff = None
    with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
        metadata: dict[Any, Any] = json.load(fobj)
    keys = metadata["openid_relying_party"]["jwks"]
    metadata.pop("openid_relying_party")
    _ = lib.fetch_entity_configuration("https://fakerp0.labb.sunet.se", keys)
