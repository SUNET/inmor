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


def test_trust_marked_list(loaddata: Redis, start_server: int):
    "Tests /trust_marked_list"
    _rdb = loaddata
    port = start_server
    url = f"http://localhost:{port}/trust_marked_list?trust_mark_type=https://sunet.se/does_not_exist_trustmark"
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
    data = resp.json()
    assert data.get("active")


def test_trust_mark_status_invalid(loaddata: Redis, start_server: int):
    "Tests /trust_mark_status for invalid input"
    _rdb = loaddata
    port = start_server
    with open(os.path.join(file_dir, "data/invalid_for_trust_mark.txt")) as fobj:
        jwt_text = fobj.read()
    jwt_text = jwt_text.strip()
    url = f"http://localhost:{port}/trust_mark_status?trust_mark={jwt_text}"
    resp = httpx.get(url)
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("error") == "invalid_request"
    assert data.get("error_description") == "Could not verify the request"


def test_trust_mark_status_invalid_jwt(loaddata: Redis, start_server: int):
    "Tests /trust_mark_status for invalid input"
    _rdb = loaddata
    port = start_server
    jwt_text = "hello_this_is_invalid_jwt"
    url = f"http://localhost:{port}/trust_mark_status?trust_mark={jwt_text}"
    resp = httpx.get(url)
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("error") == "invalid_request"
    assert data.get("error_description") == "Could not verify the request"
