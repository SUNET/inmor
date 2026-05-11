import base64
import hashlib
import json
import os
import time

from httpx import Client
from jwcrypto import jwk, jwt
from redis.client import Redis

file_dir = os.path.dirname(os.path.abspath(__file__))


# Helpers for the trust-mark-in-resolve tests below.
#
# Each test starts from the same loaded Redis dump and may need to rewrite the
# TA's `trust_mark_issuers` claim. The TA's entity configuration JWT lives at
# Redis key `inmor:entity_id` and is served verbatim via
# /.well-known/openid-federation. Because `resolve_entity_to_trustanchor`
# self-verifies the TA's entity configuration during chain validation, we
# must re-sign the JWT after editing the payload — see `_repatch_ta_ec()`.
# The TA's resolve trust-mark gate intentionally trusts Redis (uses
# `get_unverified_payload_header`) so the re-signed JWT just needs to be
# decodable; the signature is checked by chain validation which uses the
# inline `jwks` claim.

_TM_TYPE = "https://sunet.se/does_not_exist_trustmark"
_TA_ENTITY_ID = "https://localhost:8080"
_PRIVATE_KEY_PATH = os.path.join(os.path.dirname(file_dir), "private.json")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _decode_jwt_payload(jwt_str: str) -> dict:
    return json.loads(_b64url_decode(jwt_str.split(".")[1]).decode())


def _decode_jwt_header(jwt_str: str) -> dict:
    return json.loads(_b64url_decode(jwt_str.split(".")[0]).decode())


def _ta_signing_key() -> jwk.JWK:
    with open(_PRIVATE_KEY_PATH) as f:
        key_dict = json.load(f)
    return jwk.JWK(**key_dict)


def _resign_payload(payload: dict, original_header: dict) -> str:
    """Sign `payload` with the TA's signing key, preserving the original `typ`.

    The `kid` is taken from the signing key (or its thumbprint if the key has
    none); we don't carry over `original_header["kid"]` because the signature
    has to validate against whatever key we're actually signing with.
    """
    key = _ta_signing_key()
    header = {
        "alg": "RS256",
        "kid": key.thumbprint() if key.kid is None else key.kid,
        "typ": original_header.get("typ", "entity-statement+jwt"),
    }
    token = jwt.JWT(header=header, claims=payload)
    token.make_signed_token(key)
    return token.serialize()


def _repatch_ta_ec(rdb: Redis, **payload_changes):
    """Mutate the TA's entity-config payload and re-sign so chain verification
    still succeeds.

    Pass `trust_mark_issuers=None` to drop the claim.
    """
    raw = rdb.get("inmor:entity_id")
    jwt_str = raw.decode() if isinstance(raw, bytes) else raw
    payload = _decode_jwt_payload(jwt_str)
    header = _decode_jwt_header(jwt_str)
    for k, v in payload_changes.items():
        if v is None:
            payload.pop(k, None)
        else:
            payload[k] = v
    rdb.set("inmor:entity_id", _resign_payload(payload, header))


def _set_trust_mark_issuers(rdb: Redis, mapping):
    """Replace `trust_mark_issuers` in the TA's entity configuration. Pass
    `None` to drop the claim entirely."""
    _repatch_ta_ec(rdb, trust_mark_issuers=mapping)


def _accept_trust_mark(rdb: Redis, sub: str, trust_mark_obj: dict) -> None:
    """Make a trust mark eligible for the TA-issued verification path."""
    jwt_str = trust_mark_obj["trust_mark"]
    h = hashlib.sha256(jwt_str.encode()).hexdigest()
    rdb.sadd("inmor:tm:alltime", h)
    rdb.hset(
        f"inmor:tm:{sub}",
        trust_mark_obj["trust_mark_type"],
        jwt_str,
    )


def _resolve_payload(http_client: Client, port: int, sub: str) -> dict:
    url = (
        f"https://localhost:{port}/resolve"
        f"?sub={sub}&trust_anchor={_TA_ENTITY_ID}"
    )
    resp = http_client.get(url)
    assert resp.status_code == 200, resp.text
    return _decode_jwt_payload(resp.text)


def _sign_with_ta(payload: dict, typ: str) -> str:
    key = _ta_signing_key()
    header = {"alg": "RS256", "kid": key.kid, "typ": typ}
    token = jwt.JWT(header=header, claims=payload)
    token.make_signed_token(key)
    return token.serialize()


def _build_subject(
    rdb: Redis,
    fake_subject,
    trust_marks: list[dict] | None,
) -> str:
    """Spin up a fake subject EC reachable by the TA, register a subordinate
    statement for it in Redis, and return the subject's entity_id.

    The subject signs its EC with a fresh ephemeral RSA key; the TA verifies
    the subordinate statement using the inline `jwks` claim (which carries
    that key). Trust marks (if any) are signed by the TA and embedded in the
    subject's EC.
    """
    subject_id = fake_subject.entity_id
    subject_key = jwk.JWK.generate(kty="RSA", size=2048, alg="RS256", use="sig")
    subject_key.kid = subject_key.thumbprint()
    subject_jwks = {"keys": [json.loads(subject_key.export(private_key=False))]}
    now = int(time.time())
    exp = now + 3600

    subject_ec_payload: dict = {
        "iss": subject_id,
        "sub": subject_id,
        "iat": now,
        "exp": exp,
        "authority_hints": [_TA_ENTITY_ID],
        "jwks": subject_jwks,
        "metadata": {
            "federation_entity": {"organization_name": "Fake Test Subject"},
        },
    }
    if trust_marks is not None:
        subject_ec_payload["trust_marks"] = trust_marks

    subject_header = {"alg": "RS256", "kid": subject_key.kid, "typ": "entity-statement+jwt"}
    subject_ec_token = jwt.JWT(header=subject_header, claims=subject_ec_payload)
    subject_ec_token.make_signed_token(subject_key)
    fake_subject.set_entity_configuration(subject_ec_token.serialize())

    # Register a subordinate statement for this subject in the TA. The TA's
    # /fetch endpoint reads it via `HGET inmor:subordinates {subject_id}` (see
    # `fetch_subordinates` in src/lib.rs). The statement asserts the subject's
    # keyset and is signed by the TA.
    sub_statement = _sign_with_ta(
        {
            "iss": _TA_ENTITY_ID,
            "sub": subject_id,
            "iat": now,
            "exp": exp,
            "jwks": subject_jwks,
        },
        "entity-statement+jwt",
    )
    # The /fetch endpoint reads `inmor:subordinates` (the signed sub statement);
    # `inmor:subordinates:jwt` is a separate hash used by /list (subject's own EC).
    rdb.hset("inmor:subordinates", subject_id, sub_statement)

    return subject_id


def _build_trust_mark(
    sub: str,
    trust_mark_type: str = _TM_TYPE,
    issuer: str = _TA_ENTITY_ID,
    exp_offset: int = 3600,
) -> dict:
    """Sign a trust mark with the TA's key. Returns the {trust_mark, trust_mark_type} object."""
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
        "trust_mark_type": trust_mark_type,
    }
    jwt_str = _sign_with_ta(payload, "trust-mark+jwt")
    return {"trust_mark": jwt_str, "trust_mark_type": trust_mark_type}


def test_server(loaddata: Redis, start_server: int, http_client: Client):
    "Checks redis"
    _rdb = loaddata
    port = start_server
    resp = http_client.get(f"https://localhost:{port}")
    assert resp.status_code == 200


def test_index_view(loaddata: Redis, start_server: int, http_client: Client):
    "Tests index view of the server."
    _rdb = loaddata
    port = start_server
    resp = http_client.get(f"https://localhost:{port}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "OpenID Federation Trust Anchor" in resp.text


def test_trust_mark_list(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark_list"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark_list?trust_mark_type=https://sunet.se/does_not_exist_trustmark"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakeop0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
        "https://localhost:8080",
    }

    # make sure that the list of subordinates matches
    assert set(data) == subs


def test_trust_mark_list_with_sub_filter(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark_list with sub filter returns single-element array"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark_list?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakeop0.labb.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data == ["https://fakeop0.labb.sunet.se"]


def test_trust_mark_list_with_unknown_sub_returns_empty(
    loaddata: Redis, start_server: int, http_client: Client
):
    "Tests /trust_mark_list with unknown sub returns empty array (spec 8.5.1)"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark_list?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://nobody.example.com"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


def test_trust_mark_for_entity(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp0.labb.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("trust_mark_type") == "https://sunet.se/does_not_exist_trustmark"
    assert payload.get("sub") == "https://fakerp0.labb.sunet.se"
    # Verify JWT header has correct typ per spec
    protected = jwt_net.token.objects.get("protected")
    if isinstance(protected, bytes):
        protected = protected.decode("utf-8")
    header = json.loads(protected)
    assert header.get("typ") == "trust-mark+jwt"


def test_trust_mark_for_missing_entity(loaddata: Redis, start_server: int, http_client: Client):
    "Tests for unknown/missing entity trustmark"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp31.labb.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 404
    data = resp.json()
    assert data.get("error") == "not_found"
    assert data.get("error_description") == "Trust mark not found."


def test_trust_mark_status(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark_status"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp0.labb.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 200
    original_trust_mark = resp.text
    url = f"https://localhost:{port}/trust_mark_status"
    resp = http_client.post(url, data={"trust_mark": original_trust_mark})
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "https://localhost:8080"
    assert payload.get("status") == "active"
    # Per spec Section 8.4.2, trust_mark claim contains the full trust mark JWT
    assert payload.get("trust_mark") == original_trust_mark


def test_trust_mark_status_invalid(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark_status for invalid input"
    rdb = loaddata
    port = start_server
    with open(os.path.join(file_dir, "data/invalid_for_trust_mark.txt")) as fobj:
        jwt_text = fobj.read()
    jwt_text = jwt_text.strip()
    # First we will load that on redis to simulate that is from us.
    h = hashlib.new("sha256")
    h.update(jwt_text.encode("utf-8"))
    _ = rdb.sadd("inmor:tm:alltime", h.hexdigest())
    # now normal flow
    url = f"https://localhost:{port}/trust_mark_status"
    resp = http_client.post(url, data={"trust_mark": jwt_text})
    print(resp.text)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "https://localhost:8080"
    assert payload.get("status") == "invalid"
    # Per spec Section 8.4.2, trust_mark claim echoes back the original JWT
    assert payload.get("trust_mark") == jwt_text


def test_trust_mark_status_invalid_jwt(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /trust_mark_status for invalid input"
    rdb = loaddata
    port = start_server
    jwt_text = "hello_this_is_invalid_jwt"
    # First we will load that on redis to simulate that is from us.
    h = hashlib.new("sha256")
    h.update(jwt_text.encode("utf-8"))
    _ = rdb.sadd("inmor:tm:alltime", h.hexdigest())
    # now normal flow
    url = f"https://localhost:{port}/trust_mark_status"
    resp = http_client.post(url, data={"trust_mark": jwt_text})
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "https://localhost:8080"
    assert payload.get("status") == "invalid"
    # Per spec Section 8.4.2, trust_mark claim echoes back the original JWT
    assert payload.get("trust_mark") == jwt_text


def test_ta_list_subordinates(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /list endpoint"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/list"
    resp = http_client.get(url)
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/json"
    data = resp.json()
    assert len(data) == 3
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakeop0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
    }
    # make sure that the list of subordinates matches
    assert set(data) == subs


def test_ta_list_subordinates_trust_marked_false(
    loaddata: Redis, start_server: int, http_client: Client
):
    "Tests /list?trust_marked=false returns all subordinates (spec 8.2.1)"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/list?trust_marked=false"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    # trust_marked=false should NOT filter — return all subordinates
    assert len(data) == 3
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakeop0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
    }
    assert set(data) == subs


def test_ta_list_subordinates_bytrustmark(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /list endpoint for given trust_mark_type"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/list?trust_mark_type=https://example.com/trust_mark_type"
    resp = http_client.get(url)
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/json"
    data = resp.json()
    assert len(data) == 2
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
    }
    # make sure that the list of subordinates matches
    assert set(data) == subs


def test_ta_fetch_missing_sub_returns_400(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /fetch without sub parameter returns 400, not 500 (spec 8.9)"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/fetch"
    resp = http_client.get(url)
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("error") == "invalid_request"


def test_ta_fetch_subordinate(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /fetch endpoint"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/fetch?sub=https://fakerp0.lab.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 404
    url = f"https://localhost:{port}/fetch?sub=https://fakerp0.labb.sunet.se"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakerp0.labb.sunet.se"
    assert payload.get("iss") == "https://localhost:8080"


def test_ta_resolve_subordinate(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /resolve endpoint"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/.well-known/openid-federation"
    resp = http_client.get(url)
    assert resp.status_code == 200
    print(resp.text)

    url = f"https://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&entity_type=openid_provider&trust_anchor=https://localhost:8080"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"
    assert payload.get("iss") == f"https://localhost:{port}"
    # We have forced metadata from authority
    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    openid_provider = metadata.get("openid_provider")
    assert openid_provider is not None, "openid_provider missing from metadata"
    assert set(openid_provider.get("subject_types_supported")) == {"public", "pairwise", "e2e"}
    assert openid_provider.get("application_type") == "mutant"
    # Verify entity_type filtering - only openid_provider should be present
    assert "federation_entity" not in metadata, "federation_entity should be filtered out"
    assert list(metadata.keys()) == ["openid_provider"], (
        "only openid_provider should be in metadata"
    )
    # forced metadata are valid
    trust_chain = payload.get("trust_chain", [])
    assert len(trust_chain) == 3
    # 0th position is the fakeop0
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(trust_chain[0])
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"
    assert payload.get("iss") == "https://fakeop0.labb.sunet.se"
    # 1st position is the subordinate statement
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(trust_chain[1])
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"
    assert payload.get("iss") == "https://localhost:8080"
    # 2nd position is the TA's entity configuration
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(trust_chain[2])
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://localhost:8080"
    assert payload.get("iss") == "https://localhost:8080"


def test_resolve_with_multiple_entity_types(
    loaddata: Redis, start_server: int, http_client: Client
):
    "Tests /resolve endpoint with multiple entity_type parameters (openid_provider and federation_entity)"
    _rdb = loaddata
    port = start_server
    # Request both openid_provider and federation_entity
    url = f"https://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&entity_type=openid_provider&entity_type=federation_entity&trust_anchor=https://localhost:8080"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"

    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    # Both entity types should be present
    assert "openid_provider" in metadata, "openid_provider should be in metadata"
    assert "federation_entity" in metadata, "federation_entity should be in metadata"
    assert set(metadata.keys()) == {"openid_provider", "federation_entity"}, (
        "Only openid_provider and federation_entity should be in metadata"
    )


def test_resolve_with_wrong_entity_type(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /resolve endpoint with a non-existent entity_type - should return all metadata"
    _rdb = loaddata
    port = start_server
    # Request a wrong/non-existent entity type
    url = f"https://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&entity_type=a_wrong_type&trust_anchor=https://localhost:8080"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"

    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    # When entity_type doesn't match, all metadata should be returned
    assert "openid_provider" in metadata, "openid_provider should be in metadata"
    assert "federation_entity" in metadata, "federation_entity should be in metadata"
    assert set(metadata.keys()) == {"openid_provider", "federation_entity"}, (
        "All metadata should be returned when entity_type doesn't match"
    )


def test_resolve_without_entity_type(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /resolve endpoint without entity_type parameter - should return all metadata"
    _rdb = loaddata
    port = start_server
    # Request without entity_type parameter
    url = f"https://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&trust_anchor=https://localhost:8080"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"

    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    # Without entity_type, all metadata should be returned
    assert "openid_provider" in metadata, "openid_provider should be in metadata"
    assert "federation_entity" in metadata, "federation_entity should be in metadata"
    assert set(metadata.keys()) == {"openid_provider", "federation_entity"}, (
        "All metadata should be returned when entity_type is not specified"
    )


def test_resolve_exp_is_minimum_of_trust_chain(
    loaddata: Redis, start_server: int, http_client: Client
):
    "Tests /resolve response exp is the minimum exp from the trust chain (spec 8.3.2)"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&trust_anchor=https://localhost:8080"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    resolve_payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    resolve_exp = resolve_payload.get("exp")
    assert resolve_exp is not None, "resolve response must have exp"

    # Extract exp from each entry in the trust chain
    trust_chain = resolve_payload.get("trust_chain", [])
    assert len(trust_chain) > 0, "trust chain must not be empty"
    chain_exps = []
    for entry in trust_chain:
        entry_jwt: jwt.JWT = jwt.JWT.from_jose_token(entry)
        entry_payload = json.loads(entry_jwt.token.objects.get("payload").decode("utf-8"))
        entry_exp = entry_payload.get("exp")
        if entry_exp is not None:
            chain_exps.append(entry_exp)

    assert len(chain_exps) > 0, "at least one trust chain entry must have exp"
    min_chain_exp = min(chain_exps)
    # Per spec Section 8.3.2: resolve exp MUST be <= minimum exp of the trust chain
    assert resolve_exp <= min_chain_exp, (
        f"resolve exp ({resolve_exp}) must be <= minimum trust chain exp ({min_chain_exp})"
    )


def test_ta_entity_configuration(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /resolve endpoint"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/.well-known/openid-federation"
    resp = http_client.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://localhost:8080"
    assert payload.get("iss") == "https://localhost:8080"

    # Check that metadata contains federation_entity with correct endpoints
    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    federation_entity = metadata.get("federation_entity")
    assert federation_entity is not None, "federation_entity missing from metadata"

    # Verify all FEDERATION_ENTITY endpoints are present and have expected values
    base_url = "https://localhost:8080"
    assert federation_entity.get("federation_fetch_endpoint") == f"{base_url}/fetch"
    assert federation_entity.get("federation_list_endpoint") == f"{base_url}/list"
    assert federation_entity.get("federation_resolve_endpoint") == f"{base_url}/resolve"
    assert (
        federation_entity.get("federation_trust_mark_status_endpoint")
        == f"{base_url}/trust_mark_status"
    )
    assert (
        federation_entity.get("federation_trust_mark_list_endpoint")
        == f"{base_url}/trust_mark_list"
    )
    assert federation_entity.get("federation_trust_mark_endpoint") == f"{base_url}/trust_mark"


def test_historical_keys_endpoint(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /historical_keys endpoint returns signed JWT with historical keys"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/historical_keys"
    resp = http_client.get(url)
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/jwk-set+jwt"

    # Parse and verify the JWT
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)

    # Check the header has correct typ
    protected = jwt_net.token.objects.get("protected")
    if isinstance(protected, bytes):
        protected = protected.decode("utf-8")
    header = json.loads(protected)
    assert header.get("typ") == "jwk-set+jwt", "JWT typ header should be 'jwk-set+jwt'"

    # Check the payload
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "https://localhost:8080", "iss should match TA domain"
    assert payload.get("iat") is not None, "iat should be present"

    # Check that keys array exists and contains keys with exp
    keys = payload.get("keys")
    assert keys is not None, "keys array should be present in payload"
    assert isinstance(keys, list), "keys should be a list"
    assert len(keys) > 0, "at least one historical key should be present"

    for key in keys:
        assert "exp" in key, "each historical key should have an exp field"
        assert "kid" in key, "each historical key should have a kid field"
        assert "kty" in key, "each historical key should have a kty field"


def test_historical_keys_contains_expected_keys(
    loaddata: Redis, start_server: int, http_client: Client
):
    "Tests /historical_keys contains the expected key IDs from historical_keys directory"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/historical_keys"
    resp = http_client.get(url)
    assert resp.status_code == 200

    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    keys = payload.get("keys")

    # Get all the key IDs from the response
    key_ids = {key.get("kid") for key in keys}

    # These are the expected historical key IDs based on historical_keys directory
    expected_kids = {
        "5RmZ0dJYzWYHNkG2mdOU6e-pPSucOcTg8_utbJxqKp4",
        "j70psMhRU24mNbHDHHt2cFFYmlpTdu72XdPs-TLTISg",
    }

    # The response should contain all expected keys
    assert expected_kids.issubset(key_ids), (
        f"Expected keys {expected_kids} not found in response keys {key_ids}"
    )


def test_historical_keys_revoked_field(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /historical_keys properly includes revoked field if present"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/historical_keys"
    resp = http_client.get(url)
    assert resp.status_code == 200

    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    keys = payload.get("keys")

    # Check if any keys have revoked field and if so verify structure
    for key in keys:
        if "revoked" in key:
            revoked = key.get("revoked")
            assert isinstance(revoked, dict), "revoked should be an object"
            assert "revoked_at" in revoked, "revoked object should contain revoked_at"
            assert "reason" in revoked, "revoked object should contain reason"
            # Check reason is valid per spec
            assert revoked.get("reason") in ["unspecified", "compromised", "superseded"], (
                f"revoked reason should be one of: unspecified, compromised, superseded"
            )


def test_health_endpoint(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /health endpoint returns ok when Redis is reachable"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/health"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


def test_status_endpoint(loaddata: Redis, start_server: int, http_client: Client):
    "Tests /status endpoint returns detailed operational status"
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/status"
    resp = http_client.get(url)
    assert resp.status_code == 200
    data = resp.json()

    # Verify top-level fields
    assert data.get("entity_id") == f"https://localhost:{port}"
    assert data.get("version") is not None
    assert data.get("status") == "ok"

    # Verify keys section
    keys = data.get("keys")
    assert keys is not None, "keys section missing"
    assert isinstance(keys.get("public_keys"), int)
    assert keys["public_keys"] > 0
    assert isinstance(keys.get("historical_keys_available"), bool)

    # Verify subordinates section
    subordinates = data.get("subordinates")
    assert subordinates is not None, "subordinates section missing"
    assert isinstance(subordinates.get("direct"), int)
    assert subordinates["direct"] == 3  # test data has 3 subordinates

    # Verify trust_marks section
    trust_marks = data.get("trust_marks")
    assert trust_marks is not None, "trust_marks section missing"
    assert isinstance(trust_marks.get("types"), list)
    assert isinstance(trust_marks.get("total_issued"), int)

    # Verify collection section
    collection = data.get("collection")
    assert collection is not None, "collection section missing"
    assert isinstance(collection.get("total_entities"), int)
    assert isinstance(collection.get("openid_providers"), int)
    assert isinstance(collection.get("openid_relying_parties"), int)
    assert isinstance(collection.get("intermediates"), int)


def test_resolve_rejects_private_ip(loaddata: Redis, start_server: int, http_client: Client):
    """C1: SSRF protection blocks requests to private IPs when not in dev mode.

    Note: The test server runs with allow_http=true so it allows private IPs.
    This test verifies the resolve endpoint correctly returns 400 for an
    unreachable private IP target (the request fails during fetch, not SSRF block,
    because dev mode is enabled). To fully test SSRF blocking, see the Rust
    unit tests in ssrf_tests module.
    """
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/resolve"
    # Try to resolve an entity at a private IP — should fail with 400
    # because the entity configuration cannot be fetched
    resp = http_client.get(
        url,
        params={
            "sub": "https://192.168.1.1:9999",
            "trust_anchor": f"https://localhost:{port}",
        },
    )
    assert resp.status_code == 400


def test_resolve_timeout_on_unreachable(loaddata: Redis, start_server: int, http_client: Client):
    """C2: Server does not hang indefinitely on unreachable entities."""
    _rdb = loaddata
    port = start_server
    url = f"https://localhost:{port}/resolve"
    # TEST-NET-2 (198.51.100.0/24) is reserved and won't respond.
    # The server's 10s request timeout should kick in instead of hanging.
    resp = http_client.get(
        url,
        params={
            "sub": "https://198.51.100.1",
            "trust_anchor": f"https://localhost:{port}",
        },
        timeout=30,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /resolve trust mark verification (spec §8.3, §8.3.2)
# ---------------------------------------------------------------------------
#
# These tests exercise verify_trust_marks_for_resolve in src/lib.rs. Each test
# spins up a `fake_subject` HTTP server on a loopback port, configures it to
# return a custom entity configuration (built fresh, signed with an ephemeral
# subject key, with TA-signed trust marks embedded), registers a subordinate
# statement for the subject in Redis, and resolves it. The TA's allow_http
# test config lets the resolver fetch http://127.0.0.1:PORT/.well-known/...
#
# Trust marks are signed with the TA's own private key (loaded from
# private.json) so the TA-issued verification path
# (verify_ta_issued_trust_mark in lib.rs) verifies them against the TA's
# in-memory public keyset.


def test_resolve_includes_ta_issued_trust_mark(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Active TA-issued trust mark must appear in /resolve response (spec §8.3)."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    marks = payload.get("trust_marks")
    assert marks is not None and len(marks) == 1
    assert marks[0]["trust_mark_type"] == _TM_TYPE
    assert marks[0]["trust_mark"] == tm_obj["trust_mark"]


def test_resolve_excludes_revoked_ta_issued_trust_mark(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "A revoked TA-issued trust mark must not appear in /resolve response."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    _accept_trust_mark(rdb, subject_id, tm_obj)
    rdb.hset(f"inmor:tm:{subject_id}", _TM_TYPE, "revoked")

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload


def test_resolve_excludes_unrecognized_trust_mark_type(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Trust marks whose type is not in trust_mark_issuers must be excluded."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)  # uses _TM_TYPE
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    # Restrict the federation to a different type — the subject's mark is unrecognised.
    _set_trust_mark_issuers(rdb, {"https://example.com/some_other_type": []})
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload


def test_resolve_excludes_trust_mark_from_disallowed_issuer(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Trust mark whose `iss` is not in the allowed list for its type must be excluded."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)  # iss=_TA_ENTITY_ID
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    # Allowed list for the type contains a different issuer — TA's iss must not pass.
    _set_trust_mark_issuers(rdb, {_TM_TYPE: ["https://other-issuer.example.com"]})
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload


def test_resolve_includes_trust_mark_when_issuer_list_empty(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Empty allowed-issuer list means anyone may issue (spec §3.1.2)."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: []})
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    marks = payload.get("trust_marks")
    assert marks is not None and len(marks) == 1
    assert marks[0]["trust_mark_type"] == _TM_TYPE


def test_resolve_omits_trust_marks_claim_when_no_trust_mark_issuers(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "If the TA's entity config has no trust_mark_issuers claim, no marks are recognised."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, None)
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload


def test_resolve_exp_is_min_of_chain_and_trust_marks(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Per spec §8.3.2, response exp = min(chain exp, trust mark exp)."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    # Trust mark expires soon (5 minutes); chain entries are typically longer.
    tm_obj = _build_trust_mark(subject_id, exp_offset=300)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    marks = payload.get("trust_marks")
    assert marks is not None and len(marks) == 1, "trust mark must be included"

    tm_exp = int(_decode_jwt_payload(tm_obj["trust_mark"])["exp"])
    chain_exps = []
    for entry in payload.get("trust_chain", []):
        chain_payload = _decode_jwt_payload(entry)
        if "exp" in chain_payload:
            chain_exps.append(int(chain_payload["exp"]))
    assert chain_exps, "trust chain must have at least one exp"

    expected_min = min(min(chain_exps), tm_exp)
    response_exp = int(payload["exp"])
    assert response_exp <= expected_min, (
        f"response exp {response_exp} must be <= min(chain exp {min(chain_exps)}, "
        f"trust mark exp {tm_exp}) = {expected_min}"
    )


def test_resolve_excludes_unknown_trust_mark(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "A trust mark whose hash is not in inmor:tm:alltime must be excluded."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id
    tm_obj = _build_trust_mark(subject_id)
    _build_subject(rdb, fake_subject, trust_marks=[tm_obj])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    # Intentionally skip _accept_trust_mark — the SISMEMBER check fails.

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload


def test_resolve_caps_trust_marks_at_limit(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Subject EC with more marks than MAX_TRUST_MARKS_PER_RESOLVE must be capped."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id

    # 50 valid TA-issued marks (well over the 32 cap).
    marks = [_build_trust_mark(subject_id) for _ in range(50)]
    _build_subject(rdb, fake_subject, trust_marks=marks)
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    for m in marks:
        _accept_trust_mark(rdb, subject_id, m)

    payload = _resolve_payload(http_client, port, subject_id)
    response_marks = payload.get("trust_marks") or []
    assert len(response_marks) <= 32, (
        f"response carried {len(response_marks)} marks; resolver must cap at 32"
    )


def test_resolve_rejects_outer_inner_trust_mark_type_mismatch(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "Per spec §7.4, outer trust_mark_type MUST equal inner; mismatch → skip."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id

    # Build a perfectly valid TA-issued mark (inner trust_mark_type=_TM_TYPE).
    tm_obj = _build_trust_mark(subject_id)
    # Then lie in the outer wrapper.
    tampered = {
        "trust_mark": tm_obj["trust_mark"],
        "trust_mark_type": "https://example.com/some_other_type",
    }
    _build_subject(rdb, fake_subject, trust_marks=[tampered])
    # Recognise BOTH types so the mismatch (not the recognition gate) is what skips it.
    _set_trust_mark_issuers(
        rdb,
        {
            _TM_TYPE: [_TA_ENTITY_ID],
            "https://example.com/some_other_type": [_TA_ENTITY_ID],
        },
    )
    _accept_trust_mark(rdb, subject_id, tm_obj)

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload, (
        "outer/inner trust_mark_type mismatch must be rejected (spec §7.4)"
    )


def test_resolve_rejects_trust_mark_for_different_subject(
    loaddata: Redis, start_server: int, http_client: Client, fake_subject
):
    "A trust mark whose inner `sub` differs from the resolve subject must be skipped."
    rdb = loaddata
    port = start_server

    subject_id = fake_subject.entity_id

    # Build a mark issued to someone else and embed it in our subject's EC.
    other_entity = "https://other.example.com"
    foreign_mark = _build_trust_mark(other_entity)
    _build_subject(rdb, fake_subject, trust_marks=[foreign_mark])
    _set_trust_mark_issuers(rdb, {_TM_TYPE: [_TA_ENTITY_ID]})
    # Accept the mark under the *correct* (foreign) subject — so the only
    # remaining barrier is the sub-mismatch check we're testing.
    _accept_trust_mark(rdb, other_entity, foreign_mark)

    payload = _resolve_payload(http_client, port, subject_id)
    assert "trust_marks" not in payload, (
        "trust mark whose JWT sub doesn't match the resolve subject must not be included"
    )
