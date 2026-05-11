import http.server
import os
import subprocess
import tempfile
import threading
import time

import httpx
import pytest
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


class _FakeSubject:
    """A dynamically-controllable fake federation subject.

    Listens on a loopback HTTP port and serves whatever JWT body has been
    registered via `set_entity_configuration()`. Used to test /resolve
    trust-mark behaviour: the resolver fetches `<entity_id>/.well-known/openid-federation`
    and we control the response.
    """

    def __init__(self, port: int, server: http.server.HTTPServer):
        self.port = port
        self.entity_id = f"http://127.0.0.1:{port}"
        self._server = server
        self._body: bytes | None = None

    def set_entity_configuration(self, jwt_body: str) -> None:
        self._server.entity_config = jwt_body.encode()  # type: ignore[attr-defined]

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class _SubjectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — required by stdlib API
        if self.path == "/.well-known/openid-federation":
            body = getattr(self.server, "entity_config", None)
            if not body:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/entity-statement+jwt")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_):  # silence stderr spam
        return


@pytest.fixture(scope="function")
def fake_subject():
    """A loopback HTTP server that the TA can `GET` as a federation subject.

    Binds to port 0 and reads back the OS-assigned port from `server_address`
    after bind — no race window between port discovery and listener creation.
    """
    server = http.server.HTTPServer(("127.0.0.1", 0), _SubjectHandler)
    port = server.server_address[1]
    server.entity_config = None  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fs = _FakeSubject(port, server)
    try:
        yield fs
    finally:
        fs.shutdown()
        thread.join(timeout=2)


@pytest.fixture(scope="session")
def start_server(trdb):
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
        # Now start a process
        inmor_proc = subprocess.Popen([inmor_path, "-p", str(port), "-c", tconfig])
        assert not inmor_proc.poll()
        time.sleep(1)  # Wait for server to start
        yield port
        inmor_proc.terminate()
