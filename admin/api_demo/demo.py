#!/usr/bin/env python
import json
import os
from pprint import pprint
from typing import Any

import cmd2
import httpx
from cmd2 import Cmd, Fg
from jwcrypto import jwt
from jwcrypto.common import json_decode

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def s_y(line: str | int):
    return cmd2.ansi.style(line, fg=Fg.YELLOW)


def s_g(line: str | int):
    "Green style"
    return cmd2.ansi.style(line, fg=Fg.GREEN)


def get_payload(token_str: str):
    "Helper method to get payload"
    jose = jwt.JWT.from_jose_token(token_str)
    return json_decode(jose.token.objects.get("payload", ""))


def get_url(url: str):
    "Get an URL"
    resp = httpx.get(f"http://localhost:8000{url}")
    return resp.status_code, resp.json()


def get_url_json(url: str, j: dict[Any, Any]):
    "Get request with JSON data"
    headers = {"Content-Type": "application/json"}
    resp = httpx.request("GET", f"http://localhost:8000{url}", json=j, headers=headers)
    return resp.status_code, resp.json()


def post_url_json(url: str, j: dict[Any, Any]):
    "POST request with JSON data"
    headers = {"Content-Type": "application/json"}
    resp = httpx.request("POST", f"http://localhost:8000{url}", json=j, headers=headers)
    return resp.status_code, resp.json()


def put_url_json(url: str, j: dict[Any, Any]):
    "PUT request with JSON data"
    headers = {"Content-Type": "application/json"}
    resp = httpx.request("PUT", f"http://localhost:8000{url}", json=j, headers=headers)
    return resp.status_code, resp.json()


def _i():
    "waits for input"
    _ = input()


class REPL(Cmd):
    prompt = "sunet_demo> "
    intro = s_g("Welcome to inmor API demo at Sunetdagarna hösten 2025")

    def __init__(self):
        Cmd.__init__(self)

    def do_trustmarktype_list(self, line):
        print(s_y("We will list all existing TrustMarkTypes."))
        print(s_y("GET /api/v1/trustmarktypes"))
        code, output = get_url("/api/v1/trustmarktypes")
        _i()
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmarktype_byid(self, line):
        print(s_y("We will list TrustMarkType by ID number."))
        print(s_y("GET /api/v1/trustmarktypes/2"))
        _i()
        code, output = get_url("/api/v1/trustmarktypes/2")
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmarktype_bytype(self, line):
        "We will list TrustMarkType by the type."
        print(s_y("We will list TrustMarkType by the type."))
        print(
            s_y(
                "GET /api/v1/trustmarktypes/ "
                + 'json={"tmtype": "https://example.com/trust_mark_type"}'
            )
        )
        _i()
        code, output = get_url_json(
            "/api/v1/trustmarktypes/2", {"tmtype": "https://example.com/trust_mark_type"}
        )
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmarktype_create(self, line):
        "We will create a new TrustMarkType."
        print(s_y("We will create a new TrustMarkType"))
        print(s_y("POST /api/v1/trustmarktypes"))
        print()
        data = {
            "tmtype": "https://test.sunet.se/does_not_exist_trustmark",
            "valid_for": 8760,
            "active": True,
            "autorenew": True,
            "renewal_time": 48,
        }
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarktypes", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmarktype_create_default(self, line):
        "We will create a new TrustMarkType with default values."
        print(s_y("We will create a new TrustMarkType with default values."))
        print(s_y("POST /api/v1/trustmarktypes"))
        print()
        data = {
            "tmtype": "https://test.sunet.se/demo_type",
        }
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarktypes", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmarktype_update(self, line):
        "We will update a given TrustMarkType"
        print(s_y("We will update a given TrustMarkType."))
        print(s_y("PUT /api/v1/trustmarktypes/2"))
        print()

        data = {
            "active": False,
            "autorenew": False,
            "renewal_time": 4,
            "valid_for": 100,
        }
        pprint(data)
        print()
        _i()
        code, output = put_url_json("/api/v1/trustmarktypes/2", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_create_server_entity(self, line):
        "Creates Trust Anchor's entity configuration."
        print(s_y("Creates Trust Anchor's entity configuration."))
        print(s_y("POST /server/entity"))
        print()

        data = {}
        _i()
        code, output = post_url_json("/api/v1/server/entity", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_create(self, line):
        "We will create a new TrustMark for a given domain."
        domain = "https://fakerp0.labb.sunet.se"
        print(s_y(f"We will create a new TrustMark for {domain}"))
        print(s_y("POST /api/v1/trustmarks"))
        print()
        data = {"tmt": 2, "domain": domain, "active": True, "autorenew": True}
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarks", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_create_end(self, line):
        "We will create a new TrustMark for a given domain."
        domain = "https://fakerp1.labb.sunet.se"
        print(s_y(f"We will create a new TrustMark for {domain}"))
        print(s_y("POST /api/v1/trustmarks"))
        print()
        data = {"tmt": 2, "domain": domain, "active": True, "autorenew": True}
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarks", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_list(self, line):
        "Lists all existing TrustMarks"
        print(s_y("Lists all existing TrustMarks"))
        print(s_y("GET /api/v1/trustmarks"))
        print()
        _i()
        code, output = get_url("/api/v1/trustmarks")
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_list_entity(self, line):
        "Lists all existing TrustMarks for a given entity."

        domain0 = "https://fakerp0.labb.sunet.se"
        print(s_y(f"Lists all existing TrustMarks for {domain0}"))
        print(s_y("POST /api/v1/trustmarks"))
        print()
        data = {"domain": domain0}
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarks/list", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_renew_entity(self, line):
        "Renews a given TrustMark for a given entity."

        domain0 = "https://fakerp0.labb.sunet.se"
        print(s_y(f"Renews a given TrustMark for {domain0}"))
        print(s_y("POST /api/v1/trustmarks/2/renew"))
        print()
        _i()
        code, output = post_url_json("/api/v1/trustmarks/2/renew", {})
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_trustmark_update(self, line):
        "Updates a TrustMark"

        domain0 = "https://fakerp0.labb.sunet.se"
        print(s_y(f"Updates a given TrustMark for {domain0}"))
        print(s_y("POST /api/v1/trustmarks/1"))
        print()
        data = {"autorenew": False, "active": False}
        pprint(data)
        print()
        _i()
        code, output = put_url_json("/api/v1/trustmarks/1", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_subordinate_add(self, line):
        "We will add a new subordinate for a given domain/entity."
        domain = "https://fakerp0.labb.sunet.se"
        print(s_y(f"We will add {domain} as new subordinate."))
        print(s_y("POST /api/v1/subordinates"))
        print("\n")
        with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
            metadata = json.load(fobj)
        data = {
            "entityid": "https://fakerp0.labb.sunet.se",
            "metadata": metadata,
            "forced_metadata": {},
        }
        pprint(data)
        print()
        _i()
        code, output = post_url_json("/api/v1/subordinates", data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_subordinate_list(self, line):
        "We will list all subordinates for our Trust Anchor."
        print(s_y("We will list all subordinates for our Trust Anchor."))
        print(s_y("GET /api/v1/subordinates"))
        print("")
        _i()
        code, output = get_url_json("/api/v1/subordinates", {})
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()

    def do_subordinate_update(self, line):
        "We will update a subordinate"
        domain = "https://fakerp0.labb.sunet.se"
        print(s_y("We will update a given subordinate."))
        print(s_y("POST /api/v1/subordinates/1"))
        print("\n")
        with open(os.path.join(data_dir, "fakerp0_metadata.json")) as fobj:
            metadata = json.load(fobj)

        update_data = {
            "metadata": metadata,
            "forced_metadata": {},
            "jwks": None,
            "entityid": domain,
            "required_trustmarks": None,
            "valid_for": 42,
            "autorenew": False,
            "active": False,
        }
        pprint(update_data)
        print()
        _i()
        code, output = post_url_json("/api/v1/subordinates/1", update_data)
        print("HTTP Status: " + s_g(code) + "\n")
        pprint(output)
        print()


if __name__ == "__main__":
    app = REPL()
    _ = app.cmdloop()
