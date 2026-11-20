"""Resolve a local, three-entity federation and verify the exact JWTs returned."""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from httpx import Client
from pyjosers import jwk, jws, jwt

if TYPE_CHECKING:
    from conftest import _FakeSubject


def new_key():
    key = jwk.JWK.generate(kty="EC", crv="P-256", alg="ES256")
    key.kid = key.thumbprint()
    return key


def keyset(*keys):
    return {"keys": [key.export_public(as_dict=True) for key in keys]}


@dataclass
class Statement:
    signer: jwk.JWK
    claims: dict
    typ: str = "entity-statement+jwt"

    def sign(self):
        header = {"alg": self.signer["alg"], "kid": self.signer.kid, "typ": self.typ}
        token = jwt.JWT(header=header, claims=self.claims)
        token.make_signed_token(self.signer)
        return token.serialize()


@dataclass
class FederationChain:
    peer: _FakeSubject
    resolver: str
    client: Client
    statements: dict[str, Statement]
    wire: dict[str, str] = field(default_factory=dict)

    def entity(self, name):
        return self.peer.entity_id + "/" + name

    def resolve(self, *requested):
        self.wire = {name: statement.sign() for name, statement in self.statements.items()}
        for name in ("leaf", "intermediate", "anchor"):
            self.peer.set_document(f"/{name}/.well-known/openid-federation", self.wire[name])
        self.peer.set_document("/intermediate/fetch?sub=" + self.entity("leaf"), self.wire["child"])
        self.peer.set_document(
            "/anchor/fetch?sub=" + self.entity("intermediate"), self.wire["parent"]
        )
        return self.client.get(
            self.resolver + "/resolve",
            params={
                "sub": self.entity("leaf"),
                "trust_anchor": requested or [self.entity("anchor")],
            },
        )

    def verified_response(self, response):
        assert response.status_code == 200, response.text
        token = jwt.JWT.from_jose_token(response.text)
        with open("private.json") as f:
            token.validate(jwk.JWK(**json.load(f)).public())
        assert isinstance(token.token, jws.JWS)
        assert "trust_chain" not in token.token.jose_header
        claims = json.loads(token.token.objects["payload"])
        assert claims["sub"] == self.entity("leaf")
        assert claims["trust_chain"] == [
            self.wire[k] for k in ("leaf", "child", "parent", "anchor")
        ]
        return claims


@pytest.fixture
def chain(pinned_peer, start_server, http_client):
    peer, anchor_key = pinned_peer
    chain = FederationChain(peer, f"https://localhost:{start_server}", http_client, {})
    leaf, intermediate, anchor = (chain.entity(name) for name in ("leaf", "intermediate", "anchor"))
    leaf_key, discovery_key, child_key = new_key(), new_key(), new_key()
    now = int(time.time())

    def statement(issuer, subject, signer, *keys):
        claims = {"iss": issuer, "sub": subject, "jwks": keyset(*keys), "iat": now, "exp": now + 90}
        return Statement(signer, claims)

    def config(entity, signer, *others):
        ec = statement(entity, entity, signer, signer, *others)
        ec.claims["metadata"] = {
            "federation_entity": {"federation_fetch_endpoint": entity + "/fetch"}
        }
        return ec

    # During rollover the intermediate signs its discovery EC with one key
    # and its child statement with the other. Only the latter is in the chain.
    chain.statements = {
        "leaf": config(leaf, leaf_key),
        "intermediate": config(intermediate, discovery_key, child_key),
        "anchor": config(anchor, anchor_key, discovery_key),
        "child": statement(intermediate, leaf, child_key, leaf_key),
        "parent": statement(anchor, intermediate, anchor_key, child_key),
    }
    chain.statements["leaf"].claims["authority_hints"] = [intermediate]
    chain.statements["intermediate"].claims["authority_hints"] = [anchor]
    return chain


def assert_invalid(response):
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_trust_chain"


def test_rollover_and_alternative_hints(chain):
    chain.statements["leaf"].claims["authority_hints"].insert(0, chain.entity("absent"))
    # The intermediate also has a stale pin. The resolver can still validate
    # it as an intermediate on a path to the independently pinned anchor.
    response = chain.resolve(
        *(chain.entity(name) for name in ("unknown", "intermediate", "anchor"))
    )
    chain.verified_response(response)


def test_unconfigured_anchor(chain):
    response = chain.resolve(chain.entity("unknown"))
    assert response.status_code == 404
    assert response.json()["error"] == "invalid_trust_anchor"


@pytest.mark.parametrize("name", ["leaf", "intermediate", "anchor"])
def test_entity_configuration_must_match_requested_identity(chain, name):
    claims = chain.statements[name].claims
    claims["iss"] = claims["sub"] = chain.entity("other")
    assert_invalid(chain.resolve())


@pytest.mark.parametrize("name", ["child", "parent"])
@pytest.mark.parametrize("claim", ["iss", "sub"])
def test_subordinate_statement_identities(chain, name, claim):
    chain.statements[name].claims[claim] = chain.entity("other")
    assert_invalid(chain.resolve())


@pytest.mark.parametrize("claim", ["iat", "exp"])
def test_required_dates(chain, claim):
    del chain.statements["leaf"].claims[claim]
    assert_invalid(chain.resolve())


def test_future_issue_time(chain):
    chain.statements["parent"].claims["iat"] = int(time.time()) + 60
    assert_invalid(chain.resolve())


def test_entity_statement_type(chain):
    chain.statements["child"].typ = "trust-mark+jwt"
    assert_invalid(chain.resolve())


def test_anchor_configuration_must_use_a_pin(chain):
    # The anchor's SS still verifies with the pin. Its EC must independently
    # verify with a pin, even though the EC's self-signature is valid.
    chain.statements["anchor"].signer = chain.statements["intermediate"].signer
    assert_invalid(chain.resolve())


def test_anchor_subordinate_statement_must_use_a_pin(chain):
    chain.statements["parent"].signer = chain.statements["intermediate"].signer
    assert_invalid(chain.resolve())


def test_intermediate_child_signature_must_match_endorsed_key_material(chain):
    keys = keyset(chain.statements["intermediate"].signer)
    keys["keys"][0]["kid"] = chain.statements["child"].signer.kid
    chain.statements["parent"].claims["jwks"] = keys
    assert_invalid(chain.resolve())


def test_selected_anchor_controls_trust_mark_recognition(chain, rdb):
    leaf = chain.entity("leaf")
    mark_type = chain.entity("membership")
    with open("private.json") as f:
        issuer_key = jwk.JWK(**json.load(f))
    issuer_key["alg"] = "RS256"
    now = int(time.time())
    mark = Statement(
        issuer_key,
        {
            "iss": chain.resolver,
            "sub": leaf,
            "iat": now,
            "exp": now + 90,
            "trust_mark_type": mark_type,
        },
        "trust-mark+jwt",
    ).sign()
    entry = {"trust_mark_type": mark_type, "trust_mark": mark}
    chain.statements["leaf"].claims["trust_marks"] = [entry]
    rdb.sadd("inmor:tm:alltime", hashlib.sha256(mark.encode()).hexdigest())
    rdb.hset("inmor:tm:" + leaf, mark_type, mark)

    anchor = chain.statements["anchor"]
    anchor.claims["trust_mark_issuers"] = {mark_type: [chain.resolver]}
    assert chain.verified_response(chain.resolve())["trust_marks"] == [entry]
    # Local recognition survives withdrawal by the foreign federation.
    rdb.set(
        "inmor:entity_id",
        Statement(
            issuer_key,
            {
                **anchor.claims,
                "sub": chain.resolver,
                "iss": chain.resolver,
                "jwks": keyset(issuer_key),
            },
        ).sign(),
    )
    del anchor.claims["trust_mark_issuers"]
    assert "trust_marks" not in chain.verified_response(chain.resolve())


@pytest.mark.parametrize(
    "restriction,allowed",
    [
        ({"permitted": ["127.0.0.1"]}, True),
        ({"permitted": ["elsewhere.example"]}, False),
        ({"permitted": ["127.0.0.1"], "excluded": ["127.0.0.1"]}, False),
        ({"permitted": []}, False),
        ({"permitted": None}, False),
        ({"excluded": ["."]}, False),
        ({"excluded": ["https://example.org/path"]}, False),
    ],
)
def test_standard_host_constraints(chain, restriction, allowed):
    """Resolve with a signed host restriction and check the outcome for the leaf."""
    chain.statements["parent"].claims["constraints"] = {"naming_constraints": restriction}
    response = chain.resolve()
    if allowed:
        chain.verified_response(response)
    else:
        assert_invalid(response)


def test_standard_host_constraints_cover_intermediate(chain):
    """Verify that excluding an intermediate invalidates the whole path."""
    # Serve the intermediate at a different hostname on the same loopback
    # server. The anchor permits the leaf's host but excludes the intermediate.
    original = chain.entity("intermediate")
    alias = original.replace("127.0.0.1", "localhost")
    chain.statements["intermediate"].claims.update(iss=alias, sub=alias)
    chain.statements["leaf"].claims["authority_hints"] = [alias]
    chain.statements["child"].claims["iss"] = alias
    parent = chain.statements["parent"]
    parent.claims.update(sub=alias, constraints={"naming_constraints": {"excluded": ["localhost"]}})
    chain.peer.set_document("/anchor/fetch?sub=" + alias, parent.sign())
    assert_invalid(chain.resolve())
    del parent.claims["constraints"]
    chain.peer.set_document("/anchor/fetch?sub=" + alias, parent.sign())
    chain.verified_response(chain.resolve())


def test_legacy_url_restriction_still_applies(chain):
    """A legacy URL exclusion still rejects a leaf whose hostname is permitted."""
    chain.statements["parent"].claims["constraints"] = {
        "naming_constraints": {"permitted": ["127.0.0.1"]},
        "excluded_subtrees": [chain.entity("leaf")],
    }
    assert_invalid(chain.resolve())


@pytest.mark.parametrize("statement", ["parent", "child"])
@pytest.mark.parametrize(
    "bad_policy",
    [
        None,
        [],
        {"federation_entity": []},
        {"federation_entity": {"organization_name": {"one_of": ["x"], "add": ["x"]}}},
    ],
)
def test_invalid_policy_at_either_level(chain, statement, bad_policy):
    """Require every superior on the path to issue a well-formed policy."""
    chain.statements[statement].claims["metadata_policy"] = bad_policy
    assert_invalid(chain.resolve())


def test_merged_policies_apply_to_immediate_superior_override(chain):
    """Verify the signed leaf metadata after merging both policies and checking the override."""
    leaf = chain.statements["leaf"].claims
    parent = chain.statements["parent"].claims  # Anchor's statement about the intermediate.
    child = chain.statements["child"].claims  # Intermediate's statement about the leaf.
    leaf["metadata"]["federation_entity"]["organization_name"] = "Leaf"
    parent["metadata_policy"] = {
        "federation_entity": {"organization_name": {"one_of": ["Campus", "Anchor only"]}}
    }
    child["metadata_policy"] = {
        "federation_entity": {"organization_name": {"one_of": ["Campus", "Intermediate only"]}}
    }
    # Only the immediate superior supplies overrides for the leaf. Applying policy
    # to the original leaf value or taking the anchor's override would reject this path.
    parent["metadata"] = {"federation_entity": {"organization_name": "Anchor only"}}
    child["metadata"] = {"federation_entity": {"organization_name": "Campus"}}
    claims = chain.verified_response(chain.resolve())
    assert claims["metadata"] == {
        "federation_entity": {
            "federation_fetch_endpoint": chain.entity("leaf") + "/fetch",
            "organization_name": "Campus",
        }
    }

    # Each value satisfies exactly one superior. Both must fail the merged rule.
    for name in ("Anchor only", "Intermediate only"):
        child["metadata"]["federation_entity"]["organization_name"] = name
        assert_invalid(chain.resolve())


def test_malformed_superior_metadata_is_rejected(chain):
    """Require an object for every role, even when the leaf omits that role."""
    chain.statements["child"].claims["metadata"] = {"unknown_entity_type": "scalar"}
    assert_invalid(chain.resolve())


def test_critical_declaration_applies_across_the_chain(chain):
    """Reject an unknown operator once a superior declares it critical."""
    chain.statements["child"].claims["metadata_policy"] = {
        "federation_entity": {"organization_name": {"extension": "operand", "default": "Campus"}}
    }
    claims = chain.verified_response(chain.resolve())
    assert claims["metadata"]["federation_entity"]["organization_name"] == "Campus"
    chain.statements["parent"].claims["metadata_policy_crit"] = ["extension"]
    assert_invalid(chain.resolve())


def test_policy_failure_tries_next_signed_path(chain):
    """Verify that the signed response uses the chain and metadata of the successful path."""
    # Both paths are signed. The leaf's immediate superior on the first path
    # imposes an unsatisfied rule, so only the direct anchor path can be used.
    chain.statements["child"].claims["metadata_policy"] = {
        "federation_entity": {"organization_name": {"essential": True}}
    }
    assert_invalid(chain.resolve())
    leaf = chain.statements["leaf"]
    anchor = chain.entity("anchor")
    leaf.claims["authority_hints"].append(anchor)
    direct = Statement(
        chain.statements["anchor"].signer,
        {
            **chain.statements["child"].claims,
            "iss": anchor,
            "metadata_policy": {"federation_entity": {"organization_name": {"value": "Direct"}}},
        },
    ).sign()
    chain.peer.set_document("/anchor/fetch?sub=" + chain.entity("leaf"), direct)
    response = chain.resolve()
    assert response.status_code == 200, response.text
    token = jwt.JWT.from_jose_token(response.text)
    with open("private.json") as f:
        token.validate(jwk.JWK(**json.load(f)).public())
    claims = json.loads(token.claims)
    assert claims["trust_chain"] == [chain.wire["leaf"], direct, chain.wire["anchor"]]
    assert claims["metadata"]["federation_entity"]["organization_name"] == "Direct"


@pytest.mark.parametrize("claim", ["metadata_policy", "metadata_policy_crit", "constraints"])
def test_policy_claims_require_a_subordinate_statement(chain, claim):
    """Reject subordinate-only claims in a self-signed leaf configuration."""
    chain.statements["leaf"].claims[claim] = {}
    assert_invalid(chain.resolve())
