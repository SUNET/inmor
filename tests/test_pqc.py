"""Exercise Admin/TA interoperability using fresh keys and real Actix workers."""

import hashlib
import json
import stat
import subprocess
import sys
import time
from pathlib import Path

import httpx
import port_for
import pytest
from pyjosers import JWK, JWKSet, jws

from admin.common.signing import PQC_ALGORITHMS, create_signed_jwt, verify_federation_jwt

ROOT = Path(__file__).resolve().parents[1]


def test_development_pqc_keys(tmp_path):
    subprocess.run(
        [sys.executable, ROOT / "scripts/create-keys.py", "--pqc", "all"], cwd=tmp_path, check=True
    )
    algorithms = []
    for path in (tmp_path / "privatekeys").glob("*.json"):
        key = JWK.from_json(path.read_text())
        assert key.has_private and path.stem == key.kid == key.thumbprint()
        public = tmp_path / "publickeys" / path.name
        assert json.loads(public.read_text()) == key.export_public(as_dict=True)
        algorithms.append(key["alg"])
    assert sorted(algorithms) == sorted(PQC_ALGORITHMS)
    assert not (tmp_path / "private.json").exists()


def damage_signature(token):
    protected_payload, signature = token.rsplit(".", 1)
    first = "A" if signature[0] != "A" else "B"
    return f"{protected_payload}.{first}{signature[1:]}"


@pytest.mark.parametrize("alg", PQC_ALGORITHMS)
def test_pqc_trust_mark_status(alg, tmp_path, rdb):
    binaries = ROOT / "target/debug"
    subprocess.run(
        [binaries / "inmor-keygeneration", "--type", alg, "--output", tmp_path], check=True
    )
    private = tmp_path / "private.json"
    key = JWK.from_json(private.read_text())
    public = tmp_path / "publickeys" / f"{key.kid}.json"
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert stat.S_IMODE(public.stat().st_mode) == 0o644
    assert key.has_private and key.kid == key.thumbprint()
    pub = json.loads(public.read_text())
    assert pub == {"alg": alg, "kty": "AKP", "use": "sig", "pub": key["pub"], "kid": key.kid}
    keys = JWKSet.from_json(json.dumps({"keys": [pub]}))

    port = port_for.get_port(None)
    issuer = f"http://127.0.0.1:{port}"
    config = tmp_path / "ta.toml"
    config.write_text(f'domain = "{issuer}"\nredis_uri = "redis://localhost:6088"\n')
    claims = {
        "iss": issuer,
        "sub": issuer,
        "trust_mark_type": "test",
        "exp": int(time.time()) + 600,
    }
    mark = create_signed_jwt(claims, key, "trust-mark+jwt")
    rdb.sadd("inmor:tm:alltime", hashlib.sha256(mark.encode()).hexdigest())
    rdb.hset(f"inmor:tm:{issuer}", "test", mark)

    with subprocess.Popen(
        [binaries / "inmor", "-p", str(port), "-c", config], cwd=tmp_path
    ) as server:
        try:
            with httpx.Client(base_url=issuer, timeout=15) as client:
                for _ in range(100):
                    assert server.poll() is None
                    try:
                        client.get("/health").raise_for_status()
                        break
                    except httpx.ConnectError:
                        time.sleep(0.05)
                response = client.post("/trust_mark_status", data={"trust_mark": mark})
                response.raise_for_status()
                verified = verify_federation_jwt(response.text, keys)
                header = json.loads(verified.header)
                assert (header["alg"], header["kid"], header["typ"]) == (
                    alg,
                    key.kid,
                    "trust-mark-status-response+jwt",
                )
                payload = json.loads(verified.claims)
                assert payload["trust_mark"] == mark
                assert payload["status"] == "active"

                with pytest.raises(jws.InvalidJWSSignature):
                    verify_federation_jwt(damage_signature(response.text), keys)

                # Status verifies only previously recorded marks. Register the
                # modified token's hash so the request reaches signature verification.
                damaged_mark = damage_signature(mark)
                rdb.sadd("inmor:tm:alltime", hashlib.sha256(damaged_mark.encode()).hexdigest())
                response = client.post("/trust_mark_status", data={"trust_mark": damaged_mark})
                response.raise_for_status()
                verified = verify_federation_jwt(response.text, keys)
                assert json.loads(verified.claims)["status"] == "invalid"
        finally:
            server.terminate()


def test_composite_draft_03_vector():
    # Appendix A.1, first example. Its signed payload is plain text.
    vector = json.loads((ROOT / "tests/data/composite-03.json").read_text())
    key = JWK(**vector["jwk"])
    assert key.kid == key.thumbprint()
    signed = jws.JWS()
    signed.deserialize(vector["jws"])
    signed.verify(key)
    assert signed.payload == b"It's a dangerous business, Frodo, going out your door."
