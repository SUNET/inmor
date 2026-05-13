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


# ---------------------------------------------------------------------------
# create_server_statement() -- trust_mark_owners emission (spec sec 7.2)
# ---------------------------------------------------------------------------


_VALID_OWNER = {
    "sub": "https://owner.example.org",
    "jwks": {
        "keys": [
            {
                "kty": "RSA",
                "kid": "owner-key-1",
                "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx",
                "e": "AQAB",
            }
        ]
    },
}


@pytest.mark.django_db
def test_create_server_statement_emits_trust_mark_owners(db_with_fixtures, settings):
    "A valid TA_TRUST_MARK_OWNERS dict appears verbatim in the TA EC payload."
    tmtype = "https://refeds.org/sirtfi"
    settings.TA_TRUST_MARK_OWNERS = {tmtype: _VALID_OWNER}

    token = lib.create_server_statement()
    payload = get_payload(token)

    owners = payload.get("trust_mark_owners")
    assert owners is not None, "trust_mark_owners must be published when set"
    assert tmtype in owners
    assert owners[tmtype]["sub"] == _VALID_OWNER["sub"]
    assert owners[tmtype]["jwks"]["keys"][0]["kid"] == "owner-key-1"


@pytest.mark.django_db
def test_create_server_statement_omits_trust_mark_owners_when_empty(db_with_fixtures, settings):
    "Empty TA_TRUST_MARK_OWNERS must NOT emit the claim (spec: OPTIONAL when no delegations)."
    settings.TA_TRUST_MARK_OWNERS = {}

    token = lib.create_server_statement()
    payload = get_payload(token)

    assert "trust_mark_owners" not in payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    "broken",
    [
        # Outer container wrong type
        pytest.param(["not", "a", "dict"], id="outer-not-dict"),
        # Empty key
        pytest.param({"": _VALID_OWNER}, id="empty-type-key"),
        # Entry not a dict
        pytest.param({"https://x.test/tm": "string-instead-of-dict"}, id="entry-not-dict"),
        # Missing sub
        pytest.param({"https://x.test/tm": {"jwks": _VALID_OWNER["jwks"]}}, id="missing-sub"),
        # sub not a string
        pytest.param(
            {"https://x.test/tm": {"sub": 42, "jwks": _VALID_OWNER["jwks"]}},
            id="sub-not-string",
        ),
        # Missing jwks
        pytest.param({"https://x.test/tm": {"sub": "https://o.test"}}, id="missing-jwks"),
        # jwks not a dict
        pytest.param(
            {"https://x.test/tm": {"sub": "https://o.test", "jwks": "not-a-dict"}},
            id="jwks-not-dict",
        ),
        # jwks.keys empty
        pytest.param(
            {"https://x.test/tm": {"sub": "https://o.test", "jwks": {"keys": []}}},
            id="keys-empty",
        ),
        # key missing kid
        pytest.param(
            {
                "https://x.test/tm": {
                    "sub": "https://o.test",
                    "jwks": {"keys": [{"kty": "RSA"}]},
                }
            },
            id="key-missing-kid",
        ),
        # key missing kty
        pytest.param(
            {
                "https://x.test/tm": {
                    "sub": "https://o.test",
                    "jwks": {"keys": [{"kid": "k1"}]},
                }
            },
            id="key-missing-kty",
        ),
    ],
)
def test_create_server_statement_rejects_malformed_owner(db_with_fixtures, settings, broken):
    "Each malformed shape must raise ValueError at regenerate time (fail fast)."
    settings.TA_TRUST_MARK_OWNERS = broken
    with pytest.raises(ValueError):
        lib.create_server_statement()
