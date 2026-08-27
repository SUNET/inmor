from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from jwcrypto import jwk, jwt
from jwcrypto.common import json_decode

from entities.lib import create_subordinate_statement
from trustmarks.lib import add_trustmark


TRUST_MARK_PROTECTED_CLAIMS = ("iss", "sub", "iat", "exp", "trust_mark_type")
SUBORDINATE_PROTECTED_CLAIMS = (
    "iss",
    "sub",
    "iat",
    "exp",
    "jwks",
    "metadata",
    "metadata_policy",
)


def get_payload(token: str) -> dict:
    """Decode a JWT payload without verifying it."""
    parsed = jwt.JWT.from_jose_token(token)
    return json_decode(parsed.token.objects["payload"])


def public_keyset() -> jwk.JWKSet:
    """Create a public key set suitable for a subordinate statement."""
    keyset = jwk.JWKSet()
    keyset.add(jwk.JWK.generate(kty="EC", crv="P-256"))
    return keyset


@pytest.mark.parametrize("protected_claim", TRUST_MARK_PROTECTED_CLAIMS)
def test_trust_mark_signing_rejects_protected_additional_claim(protected_claim):
    """Reject Trust Mark claim collisions before signing or writing to Redis."""
    redis = Mock()

    with pytest.raises(ValueError, match=protected_claim):
        add_trustmark(
            "https://subject.example",
            "https://issuer.example/trust-mark-type",
            24,
            {protected_claim: "attacker-controlled"},
            redis,
        )

    redis.hset.assert_not_called()
    redis.sadd.assert_not_called()


@pytest.mark.parametrize("protected_claim", SUBORDINATE_PROTECTED_CLAIMS)
def test_subordinate_signing_rejects_protected_additional_claim(protected_claim):
    """Reject subordinate claim collisions at the signing boundary."""
    now = datetime.now()

    with pytest.raises(ValueError, match=protected_claim):
        create_subordinate_statement(
            "https://subject.example",
            public_keyset(),
            now,
            now + timedelta(hours=24),
            {"openid_relying_party": {}},
            {protected_claim: "attacker-controlled"},
        )


def test_subordinate_signing_preserves_extension_claims(settings):
    """Keep legitimate top-level and nested extension claims in the signed statement."""
    now = datetime.now()
    extensions = {
        "constraints": {"max_path_length": 1},
        "organization": {"iss": "nested-values-do-not-collide", "exp": 1},
    }

    token = create_subordinate_statement(
        "https://subject.example",
        public_keyset(),
        now,
        now + timedelta(hours=24),
        {"openid_relying_party": {}},
        extensions,
    )
    payload = get_payload(token)

    assert payload["constraints"] == extensions["constraints"]
    assert payload["organization"] == extensions["organization"]
    assert payload["iss"] == settings.TA_DOMAIN
    assert payload["sub"] == "https://subject.example"
    assert payload["metadata"] == {"openid_relying_party": {}}
