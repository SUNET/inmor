import http.server
import json
import os
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import cast
from urllib.parse import unquote

import httpx
import pytest
from pyjosers import jwk
from pytest_redis import factories
from redis.client import Redis

file_dir = os.path.dirname(os.path.abspath(__file__))
dbpath = os.path.join(file_dir, "redisdata")
inmor_path = os.path.join(os.path.dirname(file_dir), "target/debug/inmor")

# mkcert CA root certificate for TLS verification
MKCERT_CA = os.path.expanduser("./dev/rootCA.pem")


trdb = factories.redis_proc(port=6088, datadir=dbpath)

rdb = factories.redisdb("trdb")


@pytest.fixture(scope="session")
def http_client():
    """Creates an httpx client that trusts the mkcert CA."""
    with httpx.Client(verify=MKCERT_CA) as client:
        yield client


@pytest.fixture(scope="function")
def loaddata(rdb: Redis) -> Redis:
    """Loads the test data into redis instance for testing."""
    redis = rdb
    with open(os.path.join(dbpath, "dump.data"), "rb") as f:
        data = f.read()
        # Now redis-cli against this
        _ = subprocess.run(["redis-cli", "-p", "6088", "--pipe"], input=data)
    return redis


class _DocumentServer(http.server.HTTPServer):
    documents: dict[str, bytes]


class _FakeSubject:
    """A dynamically-controllable fake federation subject.

    Listens on a loopback HTTP port and serves whatever JWT body has been
    registered via `set_entity_configuration()`. Used to test /resolve
    trust-mark behaviour: the resolver fetches `<entity_id>/.well-known/openid-federation`
    and we control the response.
    """

    def __init__(self, port: int, server: _DocumentServer):
        self.port = port
        self.entity_id = f"http://127.0.0.1:{port}"
        self._server = server

    def set_entity_configuration(self, jwt_body: str) -> None:
        self.set_document("/.well-known/openid-federation", jwt_body)

    def set_document(self, path: str, body: str) -> None:
        self._server.documents[path] = body.encode()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class _SubjectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — required by stdlib API
        body = cast(_DocumentServer, self.server).documents.get(unquote(self.path))
        if body is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/entity-statement+jwt")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # silence stderr spam
        return


@contextmanager
def _subject_server():
    """A loopback HTTP server that the TA can `GET` as a federation subject.

    Binds to port 0 and reads back the OS-assigned port from `server_address`
    after bind — no race window between port discovery and listener creation.
    """
    server = _DocumentServer(("127.0.0.1", 0), _SubjectHandler)
    port = server.server_address[1]
    server.documents = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fs = _FakeSubject(port, server)
    try:
        yield fs
    finally:
        fs.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def fake_subject():
    with _subject_server() as subject:
        yield subject


@pytest.fixture(scope="session")
def pinned_peer():
    key = jwk.JWK.generate(kty="EC", crv="P-256", alg="ES256")
    key.kid = key.thumbprint()
    with _subject_server() as peer:
        yield peer, key


@pytest.fixture(scope="session")
def start_server(trdb, pinned_peer):
    """Starts the inmor rust application on a port and returns it."""
    # port = port_for.get_port(None)
    # Comment the line below and uncomment the above to run the test server
    # on a random port.
    port = 8080
    with tempfile.TemporaryDirectory() as tmpdir:
        tconfig = os.path.join(tmpdir, "testconfig.toml")
        with open(tconfig, "w") as f:
            f.write(f'domain = "https://localhost:{port}"\n')
            f.write('redis_uri = "redis://localhost:6088"\n')
            f.write('tls_cert = "dev/localhost+2.pem"\n')
            f.write('tls_key = "dev/localhost+2-key.pem"\n')
            f.write("allow_http = true\n")
            peer, key = pinned_peer
            for path in ("/anchor", "/intermediate"):
                f.write(f'[[trusted_anchors."{peer.entity_id}{path}".keys]]\n')
                for field, value in key.export_public(as_dict=True).items():
                    f.write(f"{field} = {json.dumps(value)}\n")
        # Now start a process
        inmor_proc = subprocess.Popen([inmor_path, "-p", str(port), "-c", tconfig])
        assert not inmor_proc.poll()
        time.sleep(1)  # Wait for server to start
        yield port
        inmor_proc.terminate()
