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


# ---------------------------------------------------------------------------
# create_server_statement() — trust_mark_issuers auto-include semantics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_server_statement_auto_includes_ta_for_active_types(db_with_fixtures, settings):
    "Active TrustMarkType rows get the TA's entity_id appended to trust_mark_issuers."
    settings.TA_TRUSTED_TRUSTMARK_ISSUERS = {}

    token = lib.create_server_statement()
    payload = get_payload(token)

    issuers = payload.get("trust_mark_issuers", {})
    ta_id = settings.TRUSTMARK_PROVIDER
    # Fixture has two active TrustMarkType rows.
    assert "https://sunet.se/does_not_exist_trustmark" in issuers
    assert "https://example.com/trust_mark_type" in issuers
    for tmtype, allowed in issuers.items():
        assert ta_id in allowed, f"TA must be in allowed list for {tmtype}"


@pytest.mark.django_db
def test_create_server_statement_preserves_explicit_empty_list(db_with_fixtures, settings):
    "An explicit `{type: []}` in settings means 'anyone may issue' and must not be overridden."
    open_type = "https://sunet.se/does_not_exist_trustmark"  # has a TrustMarkType row
    settings.TA_TRUSTED_TRUSTMARK_ISSUERS = {open_type: []}

    token = lib.create_server_statement()
    payload = get_payload(token)

    issuers = payload.get("trust_mark_issuers", {})
    # The explicitly-open type must stay empty — auto-include would silently flip
    # the spec §3.1.2 "anyone may issue" semantics to "TA only".
    assert issuers.get(open_type) == [], (
        f"explicit empty list for {open_type} must be preserved; got {issuers.get(open_type)!r}"
    )


@pytest.mark.django_db
def test_create_server_statement_merges_external_issuers_with_ta(db_with_fixtures, settings):
    "Settings-provided external issuers are kept; TA is appended for active types."
    tmtype = "https://example.com/trust_mark_type"  # has a TrustMarkType row
    external = "https://external-issuer.example.com"
    settings.TA_TRUSTED_TRUSTMARK_ISSUERS = {tmtype: [external]}

    token = lib.create_server_statement()
    payload = get_payload(token)

    issuers = payload.get("trust_mark_issuers", {})
    allowed = issuers.get(tmtype, [])
    assert external in allowed, "external issuer from settings must survive"
    assert settings.TRUSTMARK_PROVIDER in allowed, (
        "TA must still be appended for an active TrustMarkType"
    )
