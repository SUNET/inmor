import json
import os
import socket
from typing import Any

import httpx
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


def test_federation_get_pins_validated_public_address(monkeypatch, settings):
    """Connect to the validated address while retaining the HTTP and TLS host."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        ],
    )
    captured = []

    def send(_client, request):
        """Capture the pinned request and return a redirect without following it."""
        captured.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/"}, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)

    response = lib._federation_get("https://federation.example/path?value=1")

    assert response.status_code == 302
    assert len(captured) == 1  # redirects stay disabled
    assert str(captured[0].url) == "https://8.8.8.8/path?value=1"
    assert captured[0].headers["Host"] == "federation.example"
    assert captured[0].extensions["sni_hostname"] == "federation.example"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::ffff:127.0.0.1", "ff02::1"],
)
def test_federation_get_rejects_internal_addresses(monkeypatch, settings, address):
    """Reject non-public IPv4, IPv6, and mapped DNS answers."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
        ],
    )

    with pytest.raises(ValueError, match="private/internal"):
        lib._federation_get("https://federation.example/path")


def test_federation_get_rejects_any_internal_dns_answer(monkeypatch, settings):
    """Reject a DNS response if any returned address is internal."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(ValueError, match="private/internal"):
        lib._federation_get("https://federation.example/path")


@pytest.mark.parametrize("address", ["4000::1", "fec0::1"])
def test_federation_get_rejects_reserved_ipv6(monkeypatch, settings, address):
    """Reject reserved and deprecated IPv6 space that Python marks global."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
        ],
    )

    with pytest.raises(ValueError, match="private/internal"):
        lib._resolve_federation_destination("https://federation.example/path")


@pytest.mark.parametrize("address", ["64:ff9b::7f00:1", "64:ff9b:1::1"])
def test_federation_get_rejects_unsafe_nat64(monkeypatch, settings, address):
    """Reject NAT64 addresses targeting private IPv4 or local-use space."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
        ],
    )

    with pytest.raises(ValueError, match="private/internal"):
        lib._resolve_federation_destination("https://federation.example/path")


@pytest.mark.parametrize("address", ["2607:f8b0:4004:800::200e", "64:ff9b::5db8:d822"])
def test_federation_get_allows_public_ipv6(monkeypatch, settings, address):
    """Retain ordinary public IPv6 and public-destination NAT64 addresses."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, 443),
            )
        ],
    )

    _, addresses = lib._resolve_federation_destination("https://federation.example/path")

    assert addresses == [address]


def test_federation_get_does_not_replay_cookies_between_origins(monkeypatch, settings):
    """Keep cookies isolated when separate origins resolve to the same IP."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        ],
    )
    captured = []
    clients = []
    real_client = httpx.Client

    def handler(request):
        """Set a cookie on the first origin and capture both pinned requests."""
        captured.append(request)
        headers = {"Set-Cookie": "session=secret; Path=/"} if len(captured) == 1 else {}
        return httpx.Response(200, headers=headers)

    def client_with_test_transport(*args, **kwargs):
        """Inject the test transport while retaining the production factory."""
        kwargs["transport"] = httpx.MockTransport(handler)
        client = real_client(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(lib.httpx, "Client", client_with_test_transport)

    lib._federation_get("https://first.example/path")
    lib._federation_get("https://second.example/path")

    assert captured[0].headers["Host"] == "first.example"
    assert captured[1].headers["Host"] == "second.example"
    assert "Cookie" not in captured[1].headers
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert all(client.is_closed for client in clients)


def test_federation_get_retries_validated_addresses(monkeypatch, settings):
    """Retry validated addresses without changing the original Host or SNI."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", 443)),
        ],
    )
    captured = []

    def handler(request):
        """Fail the first address and return a response from the second."""
        captured.append(request)
        if len(captured) == 1:
            raise httpx.ConnectError("first address failed", request=request)
        return httpx.Response(200, text="ok")

    def new_client(timeout):
        """Create a fetch-scoped client using the deterministic test transport."""
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
            timeout=timeout,
        )

    monkeypatch.setattr(lib, "_new_federation_client", new_client)

    response = lib._federation_get("https://federation.example/path")

    assert response.text == "ok"
    assert [str(request.url) for request in captured] == [
        "https://8.8.8.8/path",
        "https://1.1.1.1/path",
    ]
    assert all(request.headers["Host"] == "federation.example" for request in captured)
    assert all(request.extensions["sni_hostname"] == "federation.example" for request in captured)


def test_federation_get_preserves_explicit_development_mode(monkeypatch, settings):
    """Allow explicit local HTTP destinations only in development mode."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = True
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8080))
        ],
    )
    captured = []

    def send(_client, request):
        """Capture the development request and return a successful response."""
        captured.append(request)
        return httpx.Response(200, text="ok", request=request)

    monkeypatch.setattr(httpx.Client, "send", send)

    response = lib._federation_get("http://ta:8080/fetch")

    assert response.text == "ok"
    assert str(captured[0].url) == "http://127.0.0.1:8080/fetch"
    assert captured[0].headers["Host"] == "ta:8080"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/path",
        "https://user@example.com/path",
        "https://example.com/path#fragment",
    ],
)
def test_federation_get_rejects_unsafe_urls(monkeypatch, settings, url):
    """Reject unsafe schemes, credentials, and fragments before DNS lookup."""
    settings.FEDERATION_FETCH_ALLOW_HTTP = False
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: pytest.fail("DNS used"))

    with pytest.raises(ValueError):
        lib._federation_get(url)


def test_entity_configuration_url_rejects_query_and_fragment():
    """Append the well-known path without query or fragment truncation."""
    for entity_id in ["https://example.com?target=other", "https://example.com/#ignored"]:
        with pytest.raises(ValueError, match="query or fragment"):
            lib._entity_configuration_url(entity_id)

    assert (
        lib._entity_configuration_url("https://example.com/tenant/")
        == "https://example.com/tenant/.well-known/openid-federation"
    )


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
        # Falsy non-dict values: previously silently bypassed validation.
        pytest.param(None, id="outer-none"),
        pytest.param([], id="outer-empty-list"),
        pytest.param("", id="outer-empty-string"),
        # Empty key
        pytest.param({"": _VALID_OWNER}, id="empty-type-key"),
        # trust_mark_type that isn't a URL
        pytest.param({"not-a-url": _VALID_OWNER}, id="tm-type-not-url"),
        pytest.param({"ftp://owner.test/tm": _VALID_OWNER}, id="tm-type-non-http-scheme"),
        # sub that isn't a URL
        pytest.param(
            {"https://x.test/tm": {"sub": "not-a-url", "jwks": _VALID_OWNER["jwks"]}},
            id="sub-not-url",
        ),
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
