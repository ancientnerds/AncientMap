"""The workstation side of the captures: paths, the Mapbox token, tools, an awake
display and a local Vite dev server of the frontend.

Same setup as the Puppeteer recorder (ancient-nerds-map/video/record.ts): data and API
from production through VITE_DEV_API_TARGET, VIDEO_RECORD=1 so Vite neither watches
nor hot-reloads mid-take. Vite takes VITE_MAPBOX_ACCESS_TOKEN from the environment;
`python -m pipeline.studio` loads the main checkout's .env into it (config.load_env),
because a worktree has no .env of its own.

The port must be free. A dev server left by an interrupted take (Windows does not end
npm's children when the Python process dies) or another session's capture would answer
first and serve the take from an older checkout, with its watcher off: the failure
record.ts's --strictPort is there for. local_site() refuses a port in use and counts as
ready only what its own Vite announces in its log.

Headed Chrome draws only while the Windows display is on: when the display slept
during a recorder take (2026-09-26, the first studio-mapbox-flyin), no animation frame
came for 15 minutes and the take died on Puppeteer's protocol timeout. display_awake()
holds the display on for the length of a take (SetThreadExecutionState, as video
players do); if the display stops drawing anyway, the recorder scenes fail within 30 s
with that reason (ancient-nerds-map/video/scenes/studio-frames.ts).

The site's Umami tracker (/pulse.js, ancient-nerds-map/src/analytics) would count every
take of production, and every paper-page capture, as a human visitor: the Playwright
captures abort its request (ANALYTICS_URL_RE) before they load a page.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.config import REPO
from pipeline.utils.slugs import BASE_URL

FRONTEND_DIR = REPO / "ancient-nerds-map"
# The production site (target "production" of a platform take, our paper pages, the dev
# server's data and API): the repo's one definition of the public base URL.
PRODUCTION_URL = BASE_URL
# The Umami tracker script on any host (production or the local dev server).
ANALYTICS_URL_RE = re.compile(r"^https?://[^/]+/pulse\.js(\?.*)?$")
LOCAL_PORT = 5198
READY_TIMEOUT_S = 90
PORT_PROBE_TIMEOUT_S = 5
# Vite colours its output even into a file on Windows (picocolors), e.g. "\x1b[1mLocal\x1b[22m:".
ANSI_ESCAPE_RE = re.compile(rb"\x1b\[[0-9;]*m")
MAPBOX_ENV_VAR = "VITE_MAPBOX_ACCESS_TOKEN"
# SetThreadExecutionState flags (winbase.h)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def require_mapbox_token() -> str:
    """The frontend's public Mapbox token from the environment."""
    token = os.environ.get(MAPBOX_ENV_VAR, "").strip()
    if not token:
        raise CaptureError(
            f"{MAPBOX_ENV_VAR} is not set: run the capture through `python -m pipeline.studio`, "
            "which loads the main checkout's .env"
        )
    return token


def require_tool(name: str) -> str:
    """Absolute path of a command on PATH."""
    path = shutil.which(name)
    if path is None:
        raise CaptureError(f"{name} not found on PATH; the capture needs it")
    return path


def serves_globe(url: str) -> bool:
    """Whether the dev server at `url` answers globe.html with 200."""
    try:
        return httpx.get(f"{url}/globe.html", timeout=2).status_code == 200
    except httpx.TransportError:
        return False  # not listening yet; local_site's deadline bounds the wait


def kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Stop npm and its node child (child.kill() alone leaves Vite running on Windows)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        proc.terminate()
    proc.wait(timeout=30)


@contextmanager
def display_awake() -> Iterator[None]:
    """Keep the Windows display and system awake for the block (headed Chrome needs it)."""
    if os.name != "nt":
        raise CaptureError("captures run on the Windows workstation (headed Chrome on the NVIDIA)")
    kernel32 = ctypes.windll.kernel32
    if not kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    ):
        raise CaptureError("SetThreadExecutionState refused to keep the display awake")
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def refuse_port_in_use(port: int) -> None:
    """Refuse `port` when something accepts connections on it at any address of localhost.

    A server already there answers before npm has even started Vite, which only then fails
    on --strictPort. Vite binds just the first address of localhost (::1 here), so a
    server on the other one does not trip --strictPort at all.
    """
    for family, kind, proto, _, address in socket.getaddrinfo(
        "localhost", port, type=socket.SOCK_STREAM
    ):
        with socket.socket(family, kind, proto) as probe:
            # a refused connection takes ~2 s on Windows loopback (measured 2026-09-27)
            probe.settimeout(PORT_PROBE_TIMEOUT_S)
            try:
                probe.connect(address)
            except ConnectionRefusedError:
                continue
        raise CaptureError(
            f"port {port} is in use on {address[0]} (a dev server left by an interrupted take, "
            f"or another session's capture?); stop it first: netstat -ano | findstr :{port}"
        )


def announces_port(log: bytes, port: int) -> bool:
    """Whether Vite's start-up output says it serves `port` ("Local:   http://localhost:5198/")."""
    plain = ANSI_ESCAPE_RE.sub(b"", log)
    return re.search(rb"Local:\s+http://localhost:%d/" % port, plain) is not None


@contextmanager
def local_site(log_path: Path, port: int = LOCAL_PORT) -> Iterator[str]:
    """Run `npm run dev` on `port` for the duration of the block and yield its base URL.

    Ready means this process's own Vite announced the port in its log, still runs, and
    serves globe.html: a 200 alone may come from another server on the port.
    """
    npm = require_tool("npm")
    require_mapbox_token()
    env = {**os.environ, "VITE_DEV_API_TARGET": PRODUCTION_URL, "VIDEO_RECORD": "1"}
    url = f"http://localhost:{port}"
    refuse_port_in_use(port)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            [npm, "run", "dev", "--", "--port", str(port), "--strictPort"],
            cwd=FRONTEND_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + READY_TIMEOUT_S
            while True:
                ready = announces_port(log_path.read_bytes(), port) and serves_globe(url)
                if proc.poll() is not None:
                    raise CaptureError(f"Vite exited with {proc.returncode}; see {log_path}")
                if ready:
                    break
                if time.monotonic() > deadline:
                    raise CaptureError(
                        f"Vite did not serve {url} within {READY_TIMEOUT_S} s; see {log_path}"
                    )
                time.sleep(0.5)
            yield url
        finally:
            kill_tree(proc)
