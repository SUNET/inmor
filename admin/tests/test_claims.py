import json
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from django.contrib import admin
from django.test import RequestFactory
from jwcrypto import jwk, jwt
from jwcrypto.common import json_decode

from entities.lib import create_subordinate_statement
from entities.models import Subordinate
from trustmarks.lib import add_trustmark
from trustmarks.models import TrustMark


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

ADMIN_PROTECTED_CLAIMS = (
    *((TrustMark, claim) for claim in TRUST_MARK_PROTECTED_CLAIMS),
    *((Subordinate, claim) for claim in SUBORDINATE_PROTECTED_CLAIMS),
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


def get_admin_claims_form(model):
    """Return the registered admin form limited to the field under test."""
    request = RequestFactory().get("/admin/")
    return admin.site._registry[model].get_form(request, fields=("additional_claims",))


@pytest.mark.parametrize(("model", "protected_claim"), ADMIN_PROTECTED_CLAIMS)
def test_admin_form_rejects_protected_additional_claim(model, protected_claim):
    """Reject every protected claim through each registered Django admin form."""
    form_type = get_admin_claims_form(model)
    form = form_type(
        data={"additional_claims": json.dumps({protected_claim: "attacker-controlled"})}
    )

    assert not form.is_valid()
    assert protected_claim in form.errors["additional_claims"][0]


@pytest.mark.parametrize(
    ("model", "additional_claims"),
    (
        (TrustMark, {"ref": "https://example.com/reference", "nested": {"exp": 1}}),
        (Subordinate, {"constraints": {"max_path_length": 1}, "nested": {"iss": "value"}}),
    ),
)
def test_admin_form_allows_extension_claims(model, additional_claims):
    """Preserve arbitrary and nested extension claims submitted through Django admin."""
    form_type = get_admin_claims_form(model)
    form = form_type(data={"additional_claims": json.dumps(additional_claims)})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["additional_claims"] == additional_claims


@pytest.mark.parametrize("model", (TrustMark, Subordinate))
@pytest.mark.parametrize("value", ("[]", '"scalar"', "1", "true"))
def test_admin_form_rejects_non_object_additional_claims(model, value):
    """Return a field error instead of crashing on non-object JSON values."""
    form_type = get_admin_claims_form(model)
    form = form_type(data={"additional_claims": value})

    assert not form.is_valid()
    assert "additional_claims" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("model", "url_template", "protected_claim"),
    (
        (TrustMark, "/admin/trustmarks/trustmark/{id}/change/", "iss"),
        (Subordinate, "/admin/entities/subordinate/{id}/change/", "sub"),
    ),
)
def test_admin_change_rejects_protected_claim_without_persisting(
    auth_client, model, url_template, protected_claim
):
    """Reject protected claims through the admin change view without modifying the row."""
    instance = model.objects.order_by("id").first()
    assert instance is not None
    original_claims = instance.additional_claims

    response = auth_client.post(
        url_template.format(id=instance.id),
        data={"additional_claims": json.dumps({protected_claim: "attacker-controlled"})},
    )

    instance.refresh_from_db()
    assert response.status_code == 200
    assert b"additional_claims contains protected claims" in response.content
    assert instance.additional_claims == original_claims


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
