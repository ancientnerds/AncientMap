"""Token, tools and the local site of the captures (capture/vite.py)."""

import http.server
import os
import re
import socket
import socketserver
import sys
import textwrap
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pipeline.studio.capture import vite
from pipeline.studio.capture.manifest import CaptureError

# Vite 5.4's start-up lines as `npm run dev` wrote them to the log on this workstation
# (colours stay on for a file on Windows), with the port as %d.
VITE_READY_BYTES = (
    b"\n  \x1b[32m\x1b[1mVITE\x1b[22m v5.4.21\x1b[39m  \x1b[2mready in \x1b[0m\x1b[1m1627"
    b"\x1b[22m\x1b[2m\x1b[0m ms\x1b[22m\n\n  \x1b[32m\xe2\x9e\x9c\x1b[39m  \x1b[1mLocal"
    b"\x1b[22m:   \x1b[36mhttp://localhost:\x1b[1m%d\x1b[22m/\x1b[39m\n"
)
# Every address of localhost as (family, host); Vite binds only the first (::1 here).
LOCALHOST = [
    (family, address[0])
    for family, _, _, _, address in socket.getaddrinfo("localhost", None, type=socket.SOCK_STREAM)
]
FIRST_LOCALHOST = LOCALHOST[0]


class _StalePage(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"stale checkout")

    def log_message(self, format, *args):
        """Keep the test output clean."""


@contextmanager
def _stale_server(family: socket.AddressFamily, host: str) -> Iterator[int]:
    """A server that already answers 200 on a free port of `host`, as a dev server left by
    an interrupted take would; yields the port."""

    class Server(socketserver.ThreadingTCPServer):
        address_family = family

    server = Server((host, 0), _StalePage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _fake_npm(tmp_path: Path, body: str) -> str:
    """An `npm` that runs the Python `body` with npm's arguments."""
    script = tmp_path / "fake_vite.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    if os.name == "nt":
        npm = tmp_path / "npm.cmd"
        npm.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        npm = tmp_path / "npm"
        npm.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        npm.chmod(0o755)
    return str(npm)


# An npm whose Vite fails on --strictPort only after a slow start, as npm does on Windows.
STRICT_PORT_FAILURE = """
    import sys, time
    from pathlib import Path
    Path(sys.argv[0]).with_name("spawned").touch()
    time.sleep(3)
    port = sys.argv[sys.argv.index("--port") + 1]
    print(f"error when starting dev server: Error: Port {port} is already in use", flush=True)
    sys.exit(1)
"""


@pytest.mark.parametrize(("family", "host"), LOCALHOST, ids=[host for _, host in LOCALHOST])
def test_a_port_in_use_at_any_localhost_address_is_refused_before_vite_starts(
    tmp_path, monkeypatch, family, host
):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    npm = _fake_npm(tmp_path, STRICT_PORT_FAILURE)
    monkeypatch.setattr(vite, "require_tool", lambda name: npm)
    entered = False
    with _stale_server(family, host) as port:
        with pytest.raises(CaptureError, match=re.escape(f"port {port} is in use on {host} ")):
            with vite.local_site(tmp_path / "vite.log", port=port):
                entered = True
    assert not entered
    assert not (tmp_path / "spawned").exists()


def test_a_server_that_takes_the_port_after_the_check_does_not_pass_for_vite(tmp_path, monkeypatch):
    # The window between the port check and Vite's bind: the other server answers 200
    # long before the spawned Vite fails, and only Vite's own announcement counts.
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    npm = _fake_npm(tmp_path, STRICT_PORT_FAILURE)
    monkeypatch.setattr(vite, "require_tool", lambda name: npm)
    monkeypatch.setattr(vite, "refuse_port_in_use", lambda port: None)
    entered = False
    with _stale_server(*FIRST_LOCALHOST) as port:
        with pytest.raises(CaptureError, match="Vite exited with 1"):
            with vite.local_site(tmp_path / "vite.log", port=port):
                entered = True
    assert not entered


def test_the_site_is_ready_when_its_own_vite_announces_the_port_and_serves(tmp_path, monkeypatch):
    family, host = FIRST_LOCALHOST
    with socket.socket(family) as probe:
        probe.bind((host, 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    body = f"""
    import http.server, socket, socketserver, sys
    port = int(sys.argv[sys.argv.index("--port") + 1])
    family, _, _, _, address = socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM)[0]

    class Server(socketserver.TCPServer):
        address_family = family

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = Server(address[:2], Page)
    sys.stdout.buffer.write({VITE_READY_BYTES!r} % port)
    sys.stdout.buffer.flush()
    server.serve_forever()
    """
    npm = _fake_npm(tmp_path, body)
    monkeypatch.setattr(vite, "require_tool", lambda name: npm)
    with vite.local_site(tmp_path / "vite.log", port=port) as url:
        assert url == f"http://localhost:{port}"


def test_a_port_probe_that_fails_otherwise_names_the_port(monkeypatch):
    """Review of Task 27: a probe that timed out (a filtered port) or failed another way
    (no IPv6 loopback) raised a bare socket error naming neither the port nor the check."""

    class Probe:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def settimeout(self, seconds):
            pass

        def connect(self, address):
            raise TimeoutError("timed out")

    monkeypatch.setattr(vite.socket, "socket", Probe)
    host = FIRST_LOCALHOST[1]
    with pytest.raises(
        CaptureError,
        match=rf"^the local site's port check: probing port 5198 on {re.escape(host)} failed "
        r"\(TimeoutError: timed out\); netstat -ano \| findstr :5198 shows what holds it$",
    ) as err:
        vite.refuse_port_in_use(5198)
    assert isinstance(err.value.__cause__, TimeoutError)


def test_the_port_announcement_is_read_through_the_log_colours():
    assert vite.announces_port(VITE_READY_BYTES % 5198, 5198)
    assert not vite.announces_port(VITE_READY_BYTES % 5199, 5198)
    assert not vite.announces_port(b"> vite --port 5198 --strictPort\n", 5198)


def test_the_mapbox_token_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", " pk.test ")
    assert vite.require_mapbox_token() == "pk.test"
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "")
    with pytest.raises(CaptureError, match="loads the main checkout's .env"):
        vite.require_mapbox_token()


def test_a_missing_tool_is_named(monkeypatch):
    monkeypatch.setattr(vite.shutil, "which", lambda name: None)
    with pytest.raises(CaptureError, match="npm not found on PATH"):
        vite.require_tool("npm")


def test_the_frontend_lives_next_to_the_pipeline():
    assert (vite.FRONTEND_DIR / "package.json").is_file()
    assert (vite.FRONTEND_DIR / "video" / "record.ts").is_file()


def test_the_analytics_tracker_is_recognised_on_every_host():
    for url in ("https://ancientnerds.com/pulse.js", "http://localhost:5198/pulse.js?x=1"):
        assert vite.ANALYTICS_URL_RE.match(url), url
    for url in (
        "https://ancientnerds.com/data/sources.json",
        "https://ancientnerds.com/research/x",
    ):
        assert not vite.ANALYTICS_URL_RE.match(url), url
