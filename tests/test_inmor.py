import hashlib
import json
import os

import httpx
from jwcrypto import jwt
from redis.client import Redis

file_dir = os.path.dirname(os.path.abspath(__file__))


def test_server(loaddata: Redis, start_server: int):
    "Checks redis"
    _rdb = loaddata
    port = start_server
    resp = httpx.get(f"http://localhost:{port}")
    assert resp.status_code == 200


def test_index_view(loaddata: Redis, start_server: int):
    "Tests index view of the server."
    _rdb = loaddata
    port = start_server
    resp = httpx.get(f"http://localhost:{port}")
    assert resp.status_code == 200
    assert resp.text == "Index page."


def test_trust_mark_list(loaddata: Redis, start_server: int):
    "Tests /trust_mark_list"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/trust_mark_list?trust_mark_type=https://sunet.se/does_not_exist_trustmark"
    resp = httpx.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakeop0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
    }

    # make sure that the list of subordinates matches
    assert set(data) == subs


def test_trust_mark_for_entity(loaddata: Redis, start_server: int):
    "Tests /trust_mark"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp0.labb.sunet.se"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("trust_mark_type") == "https://sunet.se/does_not_exist_trustmark"
    assert payload.get("sub") == "https://fakerp0.labb.sunet.se"
    # TODO:What else should we test here?


def test_trust_mark_for_missing_entity(loaddata: Redis, start_server: int):
    "Tests for unknown/missing entity trustmark"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp31.labb.sunet.se"
    resp = httpx.get(url)
    assert resp.status_code == 404
    data = resp.json()
    assert data.get("error") == "not_found"
    assert data.get("error_description") == "Trust mark not found."


def test_trust_mark_status(loaddata: Redis, start_server: int):
    "Tests /trust_mark_status"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/trust_mark?trust_mark_type=https://sunet.se/does_not_exist_trustmark&sub=https://fakerp0.labb.sunet.se"
    resp = httpx.get(url)
    assert resp.status_code == 200
    url = f"http://localhost:{port}/trust_mark_status?trust_mark={resp.text}"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "http://localhost:8080"
    assert payload.get("status") == "active"


def test_trust_mark_status_invalid(loaddata: Redis, start_server: int):
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
    url = f"http://localhost:{port}/trust_mark_status?trust_mark={jwt_text}"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "http://localhost:8080"
    assert payload.get("status") == "invalid"


def test_trust_mark_status_invalid_jwt(loaddata: Redis, start_server: int):
    "Tests /trust_mark_status for invalid input"
    rdb = loaddata
    port = start_server
    jwt_text = "hello_this_is_invalid_jwt"
    # First we will load that on redis to simulate that is from us.
    h = hashlib.new("sha256")
    h.update(jwt_text.encode("utf-8"))
    _ = rdb.sadd("inmor:tm:alltime", h.hexdigest())
    # now normal flow
    url = f"http://localhost:{port}/trust_mark_status?trust_mark={jwt_text}"
    resp = httpx.get(url)
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("iss") == "http://localhost:8080"
    assert payload.get("status") == "invalid"


def test_ta_list_subordinates(loaddata: Redis, start_server: int):
    "Tests /list endpoint"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/list"
    resp = httpx.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    subs = {
        "https://fakerp0.labb.sunet.se",
        "https://fakeop0.labb.sunet.se",
        "https://fakerp1.labb.sunet.se",
    }
    # make sure that the list of subordinates matches
    assert set(data) == subs


def test_ta_fetch_subordinate(loaddata: Redis, start_server: int):
    "Tests /fetch endpoint"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/fetch?sub=https://fakerp0.lab.sunet.se"
    resp = httpx.get(url)
    assert resp.status_code == 404
    url = f"http://localhost:{port}/fetch?sub=https://fakerp0.labb.sunet.se"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakerp0.labb.sunet.se"
    assert payload.get("iss") == "http://localhost:8080"


def test_ta_resolve_subordinate(loaddata: Redis, start_server: int):
    "Tests /resolve endpoint"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/.well-known/openid-federation"
    resp = httpx.get(url)
    assert resp.status_code == 200
    print(resp.text)

    url = f"http://localhost:{port}/resolve?sub=https://fakeop0.labb.sunet.se&entity_type=openid_provider&trust_anchor=http://localhost:8080"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "https://fakeop0.labb.sunet.se"
    assert payload.get("iss") == f"http://localhost:{port}"
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
    assert payload.get("iss") == "http://localhost:8080"
    # 2nd position is the TA's entity configuration
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(trust_chain[2])
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "http://localhost:8080"
    assert payload.get("iss") == "http://localhost:8080"


def test_ta_entity_configuration(loaddata: Redis, start_server: int):
    "Tests /resolve endpoint"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/.well-known/openid-federation"
    resp = httpx.get(url)
    assert resp.status_code == 200
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))
    assert payload.get("sub") == "http://localhost:8080"
    assert payload.get("iss") == "http://localhost:8080"

    # Check that metadata contains federation_entity with correct endpoints
    metadata = payload.get("metadata")
    assert metadata is not None, "metadata missing from payload"
    federation_entity = metadata.get("federation_entity")
    assert federation_entity is not None, "federation_entity missing from metadata"

    # Verify all FEDERATION_ENTITY endpoints are present and have expected values
    base_url = "http://localhost:8080"
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
