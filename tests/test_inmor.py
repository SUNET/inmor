import hashlib
import json
import os

from httpx import Client
from jwcrypto import jwt
from redis.client import Redis

file_dir = os.path.dirname(os.path.abspath(__file__))


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
    assert resp.text == "Index page."


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


def test_ta_fetch_missing_sub_returns_400(
    loaddata: Redis, start_server: int, http_client: Client
):
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
