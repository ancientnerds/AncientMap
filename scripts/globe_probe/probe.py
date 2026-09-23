"""Globe load probe: bytes, time and long tasks to `globe_ready`, the no-WebGL screen,
fixed-camera screenshots and their pixel diff.

Every browser run loads https://ancientnerds.com/globe.html?demo=1 in Chromium,
with the Umami tracker replaced by an in-page recorder (nothing reaches the
production analytics) and service workers blocked (first-visit numbers).

    python scripts/globe_probe/probe.py load  --target prod  --device desktop --gpu
    python scripts/globe_probe/probe.py load  --target local --device phone --cpu 4 --gpu
    python scripts/globe_probe/probe.py nogl  --target prod
    python scripts/globe_probe/probe.py shot  --target prod  --pose 10,51,2.44 --dpr 2
    python scripts/globe_probe/probe.py diff  A.png B.png

`--target local` serves the local production build (`ancient-nerds-map/dist/`,
`npm run build` first) and the worktree's `public/data/layers/globe/` under the
production origin; the API and every other `/data/` file come from production.

Output: one directory per run under output/globe_probe/ (gitignored) with
`report.json` and the screenshots. See scripts/globe_probe/README.md.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageChops, ImageStat

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, CDPSession, Page, Playwright, Route

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "ancient-nerds-map" / "dist"
GLOBE_LAYERS = ROOT / "public" / "data" / "layers" / "globe"
OUT_ROOT = ROOT / "output" / "globe_probe"

PROD_HOST = "ancientnerds.com"
PROD_ORIGIN = f"https://{PROD_HOST}"
GLOBE_LAYER_PREFIX = "/data/layers/globe/"

# The keys `/api/sites/all?fields=globe` keeps (contract C2 of the globe-load plan).
GLOBE_KEYS = ("id", "n", "la", "lo", "s", "t", "p", "pn", "c")

# ancientnerds-nginx-config: gzip_comp_level 6, gzip_min_length 1024 and these
# gzip_types (text/html is always on in nginx). Images and woff2 go out as they are.
GZIP_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/css",
        "text/xml",
        "text/javascript",
        "application/javascript",
        "application/json",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
        "application/manifest+json",
        "image/svg+xml",
    }
)
GZIP_MIN_LENGTH = 1024

# nginx mime.types for what `vite build` emits; anything else is nginx's default_type.
CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".txt": "text/plain",
    ".xml": "text/xml",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Chrome DevTools' "Fast 4G" preset (throughput in bytes/s, latency in ms).
NETWORK_PRESETS: dict[str, dict[str, Any] | None] = {
    "fast4g": {
        "offline": False,
        "latency": 60 * 2.75,
        "downloadThroughput": 9 * 1000 * 1000 / 8 * 0.9,
        "uploadThroughput": 1.5 * 1000 * 1000 / 8 * 0.9,
    },
    "none": None,
}

# The headed-Chromium flags the video recorder proved on this machine's RTX 3080
# (ancient-nerds-map/video/record.ts). Occluded-window backgrounding is off so a
# covered probe window keeps its frame rate: the warp intro counts frames.
GPU_ARGS = [
    "--use-angle=d3d11",
    "--force_high_performance_gpu",
    "--force-high-performance-gpu",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--enable-gpu-rasterization",
    "--disable-backgrounding-occluded-windows",
]

# route.abort("blockedbyclient") surfaces as net::ERR_BLOCKED_BY_CLIENT.Inspector
BLOCKED_ERROR = "net::ERR_BLOCKED_BY_CLIENT"
PULSE_PATTERN = r"^https://ancientnerds\.com/(pulse\.js|api/pulse)(\?.*)?$"
MAPBOX_PATTERN = r"^https://(api|events)\.mapbox\.com/"
GLOBE_CANVAS = ".globe-container > canvas"
GATE_GLOBE_BUTTON = ".mobile-action-globe"
# The heading of the unsupported screen (GlobeUnsupported, unit U9); matched without
# the apostrophe so a typographic one renders the same verdict.
UNSUPPORTED_TEXT = "show the 3D globe"
AFTER_WARP_MS = 30_000
LONG_TASK_LIMIT_MS = 200.0

# Installed before any page script. Replaces the tracker (`track()` in
# src/analytics/index.ts calls window.umami.track directly), records long tasks
# and the moment the warp intro has finished (`__DEMO.isReady()`, ?demo=1 only).
PROBE_INIT_JS = r"""
(() => {
  if (window.top !== window) return;
  const probe = { events: [], longtasks: [], warpEndAt: null, gateClickAt: null };
  Object.defineProperty(window, '__probe', { value: probe });
  window.umami = { track: (n, d) => { probe.events.push({ n, d: d ?? null, t: performance.now() }); } };
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) probe.longtasks.push({ start: e.startTime, duration: e.duration });
  }).observe({ type: 'longtask', buffered: true });
  const warpPoll = setInterval(() => {
    const demo = window.__DEMO;
    if (demo && typeof demo.isReady === 'function' && demo.isReady()) {
      probe.warpEndAt = performance.now();
      clearInterval(warpPoll);
    }
  }, 50);
  document.addEventListener('click', (e) => {
    const el = e.target;
    if (probe.gateClickAt === null && el instanceof Element && el.closest('.mobile-action-globe')) {
      probe.gateClickAt = performance.now();
    }
  }, true);
})();
"""

# A browser without WebGL 2: every webgl2 context request fails the way a
# blocklisted GPU fails it (getContext returns null).
NO_WEBGL2_JS = r"""
(() => {
  for (const proto of [HTMLCanvasElement.prototype, globalThis.OffscreenCanvas && OffscreenCanvas.prototype]) {
    if (!proto) continue;
    const original = proto.getContext;
    proto.getContext = function (type, ...rest) {
      if (type === 'webgl2') return null;
      return original.call(this, type, ...rest);
    };
  }
})();
"""

GL_INFO_JS = r"""
() => {
  const gl = document.createElement('canvas').getContext('webgl2');
  if (!gl) return { renderer: null, maxTextureSize: null };
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer = gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
  const maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
  gl.getExtension('WEBGL_lose_context').loseContext();
  return { renderer, maxTextureSize };
}
"""

PROBE_STATE_JS = r"""
() => ({
  events: window.__probe.events,
  longtasks: window.__probe.longtasks,
  warpEndAt: window.__probe.warpEndAt,
  gateClickAt: window.__probe.gateClickAt,
  timeOrigin: performance.timeOrigin,
  now: performance.now(),
})
"""


# --- pure helpers -------------------------------------------------------------------


def project_globe_payload(payload: dict) -> dict:
    """What `fields=globe` returns: the same envelope, each site cut to GLOBE_KEYS."""
    sites = [{k: s[k] for k in GLOBE_KEYS if k in s} for s in payload["sites"]]
    return {**payload, "sites": sites}


def is_globe_projected(payload: dict) -> bool:
    """True when no site carries a key outside GLOBE_KEYS (the server honoured fields=globe)."""
    allowed = set(GLOBE_KEYS)
    return all(set(s) <= allowed for s in payload["sites"])


def without_query_param(url: str, name: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != name]
    return urlunsplit(parts._replace(query=urlencode(query)))


def is_sites_globe_request(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.hostname == PROD_HOST
        and parts.path == "/api/sites/all"
        and ("fields", "globe") in parse_qsl(parts.query, keep_blank_values=True)
    )


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), DEFAULT_CONTENT_TYPE)


def counted_bytes(body: bytes, content_type: str) -> int:
    """Bytes production would put on the wire for this body (gzip as nginx does)."""
    mime = content_type.split(";")[0].strip().lower()
    if mime in GZIP_TYPES and len(body) >= GZIP_MIN_LENGTH:
        return len(gzip.compress(body, compresslevel=6, mtime=0))
    return len(body)


def local_file_for(url: str, dist: Path, globe_layers: Path) -> Path | None:
    """The local file that answers `url` for `--target local`, or None (production answers).

    Local: the built frontend (html, /assets/, /sw.js, fonts, …) and the globe
    layer files. Never local: /api/, /goto/ and every other /data/ file.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != PROD_HOST:
        return None
    path = unquote(parts.path) or "/"
    if path.startswith(GLOBE_LAYER_PREFIX):
        base, rel = globe_layers, path[len(GLOBE_LAYER_PREFIX) :]
    elif path.startswith(("/data/", "/api/", "/goto/")):
        return None
    else:
        base, rel = dist, path.lstrip("/")
        if rel == "" or rel.endswith("/"):
            rel += "index.html"
    candidate = base / rel
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        return None
    return candidate


@dataclass
class _Request:
    url: str
    start_wall_ms: float
    end_wall_ms: float | None = None
    encoded: int = 0
    status: int | None = None
    error: str | None = None


class ByteLedger:
    """Network bytes per request from CDP `Network.*` events.

    CDP stamps loadingFinished with a monotonic clock; requestWillBeSent carries
    both that clock and the wall clock, which maps the one onto the other and,
    through `performance.timeOrigin`, onto the page's `performance.now()`.
    Requests the probe answered itself (`--target local`) count the size
    production would have sent (`fulfilled_locally`), not what Chromium saw.
    """

    def __init__(self) -> None:
        self._requests: dict[str, _Request] = {}
        self._offset_s = 0.0
        self._local: dict[str, int] = {}

    def request(self, request_id: str, url: str, timestamp: float, wall_time: float) -> None:
        if not url.startswith(("http://", "https://")):
            return
        self._offset_s = wall_time - timestamp
        known = self._requests.get(request_id)
        if known is not None:  # a redirect keeps its request id
            known.url = url
            return
        self._requests[request_id] = _Request(url=url, start_wall_ms=wall_time * 1000)

    def response(self, request_id: str, status: int) -> None:
        req = self._requests.get(request_id)
        if req is None:
            return
        req.status = status

    def finished(self, request_id: str, timestamp: float, encoded_length: int) -> None:
        req = self._requests.get(request_id)
        if req is None:  # a data:/blob: URL, never recorded
            return
        req.end_wall_ms = (timestamp + self._offset_s) * 1000
        req.encoded = encoded_length

    def failed(self, request_id: str, timestamp: float, error_text: str) -> None:
        req = self._requests.get(request_id)
        if req is None:
            return
        req.end_wall_ms = (timestamp + self._offset_s) * 1000
        req.error = error_text

    def fulfilled_locally(self, url: str, counted: int) -> None:
        self._local[url] = counted

    def summary(self, ready_ms: float | None, time_origin_ms: float) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for req in self._requests.values():
            local = req.url in self._local
            done = req.end_wall_ms is not None and req.error is None
            size = (self._local[req.url] if local else req.encoded) if done else 0
            rows.append(
                {
                    "url": redact_url(req.url),
                    "status": req.status,
                    "bytes": size,
                    "start_ms": req.start_wall_ms - time_origin_ms,
                    "end_ms": None if req.end_wall_ms is None else req.end_wall_ms - time_origin_ms,
                    "local": local,
                    "error": req.error,
                }
            )
        rows.sort(key=lambda r: r["start_ms"])
        out: dict[str, Any] = {
            "bytes_total": sum(r["bytes"] for r in rows),
            "requests": rows,
            "blocked": [r["url"] for r in rows if _blocked(r["error"])],
            "http_errors": [
                {"url": r["url"], "status": r["status"]}
                for r in rows
                if r["status"] is not None and r["status"] >= 400
            ],
            "failed": [
                {"url": r["url"], "error": r["error"]}
                for r in rows
                if r["error"] is not None and not _blocked(r["error"])
            ],
            "bytes_before_ready": None,
            "requests_before_ready": None,
            "in_flight_at_ready": None,
            "top_before_ready": None,
        }
        if ready_ms is None:
            return out
        before = [
            r
            for r in rows
            if r["error"] is None and r["end_ms"] is not None and r["end_ms"] <= ready_ms
        ]
        out["bytes_before_ready"] = sum(r["bytes"] for r in before)
        out["requests_before_ready"] = len(before)
        out["in_flight_at_ready"] = [
            {"url": r["url"], "start_ms": r["start_ms"]}
            for r in rows
            if r["start_ms"] <= ready_ms and (r["end_ms"] is None or r["end_ms"] > ready_ms)
        ]
        out["top_before_ready"] = [
            {"url": r["url"], "bytes": r["bytes"]}
            for r in sorted(before, key=lambda r: r["bytes"], reverse=True)[:15]
        ]
        return out


def redact_url(url: str) -> str:
    """The Mapbox token rides in the query string; reports never carry it."""
    return re.sub(r"(access_token=)[^&]*", r"\1REDACTED", url)


def _blocked(error: str | None) -> bool:
    return error is not None and error.startswith(BLOCKED_ERROR)


def long_task_window(tasks: list[dict], start_ms: float, end_ms: float) -> dict[str, Any]:
    """Long tasks that started in [start_ms, end_ms) and the ones above 200 ms."""
    inside = [t for t in tasks if start_ms <= t["start"] < end_ms]
    return {
        "count": len(inside),
        "max_ms": max((float(t["duration"]) for t in inside), default=0.0),
        "total_ms": float(sum(t["duration"] for t in inside)),
        "over_200ms": [t for t in inside if t["duration"] > LONG_TASK_LIMIT_MS],
    }


def image_diff(
    a: Image.Image, b: Image.Image, threshold: int = 24
) -> tuple[dict[str, Any], Image.Image]:
    """Mean absolute difference (0-255, over RGB) and the share of pixels whose
    largest channel difference exceeds `threshold`; plus a 4x amplified diff image."""
    a, b = a.convert("RGB"), b.convert("RGB")
    if a.size != b.size:
        raise ValueError(f"image size differs: {a.size} vs {b.size}")
    diff = ImageChops.difference(a, b)
    mean_abs = sum(ImageStat.Stat(diff).mean) / 3
    r, g, bl = diff.split()
    peak = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    over = peak.point(lambda v: 255 if v > threshold else 0).histogram()[255]
    width, height = a.size
    stats = {
        "width": width,
        "height": height,
        "mean_abs_diff": mean_abs,
        "share_over_threshold": over / (width * height),
        "threshold": threshold,
    }
    return stats, diff.point(lambda v: min(255, v * 4))


def parse_pose(text: str) -> tuple[float, float, float]:
    """`lng,lat,distance` (distance from the globe centre, radius 1)."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError(f"pose needs lng,lat,distance: {text!r}")
    lng, lat, distance = (float(p) for p in parts)
    if not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ValueError(f"pose out of range: {text!r}")
    if distance <= 1:
        raise ValueError(f"pose distance must be above the surface (> 1): {text!r}")
    return lng, lat, distance


def device_options(device: str, dpr: float | None, chrome_major: str) -> dict[str, Any]:
    """Context options: a 1080p desktop, or a Pixel 7 (412x915 at DPR 2.625, touch)."""
    if device == "desktop":
        return {
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1.0 if dpr is None else dpr,
            "is_mobile": False,
            "has_touch": False,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Safari/537.36"
            ),
        }
    if device == "phone":
        return {
            "viewport": {"width": 412, "height": 915},
            "device_scale_factor": 2.625 if dpr is None else dpr,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": (
                "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Mobile Safari/537.36"
            ),
        }
    raise ValueError(f"unknown device {device!r}")


def page_url(query: str | None) -> str:
    url = f"{PROD_ORIGIN}/globe.html?demo=1"
    return f"{url}&{query}" if query else url


def run_dir(root: Path, parts: list[str], now: datetime) -> Path:
    path = root / f"{now:%Y%m%d-%H%M%S}-{'-'.join(parts)}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def browser_args(p: argparse.ArgumentParser, block_mapbox: bool) -> None:
        p.add_argument("--target", choices=("prod", "local"), required=True)
        p.add_argument("--device", choices=("desktop", "phone"), default="desktop")
        p.add_argument("--gpu", action="store_true", help="headed Chromium on the real GPU")
        p.add_argument(
            "--block-mapbox",
            action=argparse.BooleanOptionalAction,
            default=block_mapbox,
            help="abort api/events.mapbox.com (every Mapbox init is a billed map load)",
        )
        p.add_argument("--query", help="extra query string for globe.html, e.g. basemap=med")
        p.add_argument("--timeout", type=float, default=240.0, help="seconds per wait")
        p.add_argument("--label", help="appended to the run directory name")

    load = sub.add_parser("load", help="bytes, time and long tasks until globe_ready")
    browser_args(load, block_mapbox=True)
    load.add_argument("--cpu", type=int, default=1, help="CPU slowdown factor (CDP)")
    load.add_argument("--net", choices=tuple(NETWORK_PRESETS), default="none")

    nogl = sub.add_parser("nogl", help="a browser without WebGL 2")
    browser_args(nogl, block_mapbox=True)
    nogl.add_argument("--wait", type=float, default=3.0, help="seconds before the screenshot")

    shot = sub.add_parser("shot", help="the globe canvas at a fixed camera pose")
    browser_args(shot, block_mapbox=False)
    shot.add_argument("--pose", type=parse_pose, required=True, help="lng,lat,distance")
    shot.add_argument("--dpr", type=float, default=1.0)
    shot.add_argument("--after-bg", action="store_true", help="wait for the background tiers")
    shot.add_argument(
        "--bg-tasks", default="layers,basemap", help="globe_bg tasks --after-bg waits for"
    )
    shot.add_argument("--settle", type=float, default=1.5, help="seconds after the pose")

    diff = sub.add_parser("diff", help="pixel difference of two screenshots")
    diff.add_argument("a", type=Path)
    diff.add_argument("b", type=Path)
    diff.add_argument("--threshold", type=int, default=24)
    diff.add_argument("--out", type=Path, help="diff image path (default: a new run dir)")
    return parser


# --- browser plumbing ----------------------------------------------------------------


@dataclass
class RunLog:
    console_errors: list[str]
    page_errors: list[str]
    simulated: list[dict[str, Any]]


def prod_honours_globe_fields() -> bool:
    """Whether production already serves `fields=globe` (unit U2 deployed)."""
    req = Request(
        f"{PROD_ORIGIN}/api/sites/all?limit=2&source=ancient_nerds&fields=globe",
        headers={"User-Agent": "globe-probe"},
    )
    with urlopen(req, timeout=30) as resp:
        return is_globe_projected(json.load(resp))


def launch(pw: Playwright, gpu: bool) -> Browser:
    if gpu:
        return pw.chromium.launch(headless=False, args=GPU_ARGS)
    return pw.chromium.launch()


def open_page(
    browser: Browser,
    args: argparse.Namespace,
    dpr: float | None,
    ledger: ByteLedger,
    extra_init: tuple[str, ...] = (),
) -> tuple[BrowserContext, Page, CDPSession, RunLog]:
    context = browser.new_context(
        service_workers="block",
        **device_options(args.device, dpr, chrome_major=browser.version.split(".")[0]),
    )
    for script in (PROBE_INIT_JS, *extra_init):
        context.add_init_script(script)
    log = RunLog(console_errors=[], page_errors=[], simulated=[])
    install_routes(context, args.target, args.block_mapbox, ledger, log)
    page = context.new_page()
    page.on(
        "console",
        lambda m: log.console_errors.append(redact_url(m.text)) if m.type == "error" else None,
    )
    page.on("pageerror", lambda e: log.page_errors.append(str(e)))
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.on(
        "Network.requestWillBeSent",
        lambda e: ledger.request(
            e["requestId"], e["request"]["url"], e["timestamp"], e["wallTime"]
        ),
    )
    cdp.on(
        "Network.responseReceived",
        lambda e: ledger.response(e["requestId"], int(e["response"]["status"])),
    )
    cdp.on(
        "Network.loadingFinished",
        lambda e: ledger.finished(e["requestId"], e["timestamp"], int(e["encodedDataLength"])),
    )
    cdp.on(
        "Network.loadingFailed",
        lambda e: ledger.failed(e["requestId"], e["timestamp"], e["errorText"]),
    )
    return context, page, cdp, log


def install_routes(
    context: BrowserContext, target: str, block_mapbox: bool, ledger: ByteLedger, log: RunLog
) -> None:
    if target == "local":
        if not (DIST / "globe.html").is_file():
            raise SystemExit(f"{DIST / 'globe.html'} missing: run `npm run build` first")
        simulate = not prod_honours_globe_fields()

        def serve_local(route: Route) -> None:
            url = route.request.url
            if simulate and is_sites_globe_request(url):
                full_url = without_query_param(url, "fields")
                resp = route.fetch(url=full_url)
                if resp.status != 200:
                    raise RuntimeError(f"simulated fields=globe: {full_url} answered {resp.status}")
                payload = resp.json()
                body = json.dumps(
                    project_globe_payload(payload), ensure_ascii=False, separators=(",", ":")
                ).encode()
                counted = counted_bytes(body, "application/json")
                ledger.fulfilled_locally(url, counted)
                log.simulated.append(
                    {
                        "url": url,
                        "from": full_url,
                        "sites": len(payload["sites"]),
                        "bytes_gzip": counted,
                    }
                )
                print(
                    f"[probe] SIMULATED fields=globe (production ignores it): {len(payload['sites'])} "
                    f"sites, {len(body)} B raw, {counted} B gzip-6",
                    flush=True,
                )
                route.fulfill(status=200, body=body, headers={"content-type": "application/json"})
                return
            path = local_file_for(url, DIST, GLOBE_LAYERS)
            if path is None:
                route.fallback()
                return
            body = path.read_bytes()
            ctype = content_type_for(path)
            ledger.fulfilled_locally(url, counted_bytes(body, ctype))
            route.fulfill(status=200, body=body, headers={"content-type": ctype})

        context.route(f"{PROD_ORIGIN}/**", serve_local)

    # Registered after the local handler, so they are consulted first.
    context.route(re.compile(PULSE_PATTERN), lambda r: r.abort("blockedbyclient"))
    if block_mapbox:
        context.route(re.compile(MAPBOX_PATTERN), lambda r: r.abort("blockedbyclient"))


def probe_state(page: Page) -> dict[str, Any]:
    return page.evaluate(PROBE_STATE_JS)


def pass_phone_gate(page: Page, timeout_ms: float, out: Path) -> None:
    """Screenshot the phone gate once its fonts are in (`gate.png`), then enter the globe."""
    button = page.locator(GATE_GLOBE_BUTTON)
    button.wait_for(state="visible", timeout=timeout_ms)
    page.evaluate("() => document.fonts.ready.then(() => undefined)")
    page.screenshot(path=str(out / "gate.png"))
    button.click(timeout=timeout_ms)


def wait_js(
    page: Page, expression: str, timeout_ms: float, arg: Any = None, polling_ms: int = 250
) -> bool:
    """Poll `expression` in the page; False when it did not become truthy within the timeout."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.wait_for_function(expression, arg=arg, polling=polling_ms, timeout=timeout_ms)
    except PlaywrightTimeout:
        return False
    return True


def base_report(args: argparse.Namespace, browser: Browser, url: str) -> dict[str, Any]:
    report = {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(args).items()}
    report.update(
        {
            "url": url,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "chromium": browser.version,
        }
    )
    return report


def write_report(out: Path, report: dict[str, Any]) -> None:
    (out / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[probe] wrote {out / 'report.json'}", flush=True)


# --- subcommands -------------------------------------------------------------------------


def cmd_load(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    out = run_dir(OUT_ROOT, _run_parts(args), datetime.now())
    timeout_ms = args.timeout * 1000
    ledger = ByteLedger()
    with sync_playwright() as pw:
        browser = launch(pw, args.gpu)
        context, page, cdp, log = open_page(browser, args, None, ledger)
        if args.cpu > 1:
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": args.cpu})
        preset = NETWORK_PRESETS[args.net]
        if preset is not None:
            cdp.send("Network.emulateNetworkConditions", preset)
        url = page_url(args.query)
        report = base_report(args, browser, url)
        page.goto(url, wait_until="commit")
        if args.device == "phone":
            pass_phone_gate(page, timeout_ms, out)

        status = "ok"
        ready = wait_js(
            page, "() => window.__probe.events.some(e => e.n === 'globe_ready')", timeout_ms
        )
        if ready:
            page.screenshot(path=str(out / "ready.png"))
            warped = wait_js(page, "() => window.__probe.warpEndAt !== null", timeout_ms)
            if warped:
                state = probe_state(page)
                page.wait_for_timeout(max(0.0, state["warpEndAt"] + AFTER_WARP_MS - state["now"]))
            else:
                status = "warp_timeout"
        else:
            status = "globe_ready_timeout"

        state = probe_state(page)
        page.screenshot(path=str(out / "end.png"))
        gl = page.evaluate(GL_INFO_JS)
        context.close()
        browser.close()

    ready_ev = next((e for e in state["events"] if e["n"] == "globe_ready"), None)
    ready_ms = None if ready_ev is None else ready_ev["t"]
    warp_end = state["warpEndAt"]
    gate = state["gateClickAt"]
    report.update(
        {
            "status": status,
            "gl_renderer": gl["renderer"],
            "max_texture_size": gl["maxTextureSize"],
            "globe_ready_ms": ready_ms,
            "gate_click_ms": gate,
            "ready_after_gate_ms": None if ready_ms is None or gate is None else ready_ms - gate,
            "warp_end_ms": warp_end,
            "long_tasks_before_ready": None
            if ready_ms is None
            else long_task_window(state["longtasks"], 0.0, ready_ms),
            "long_tasks_after_warp_30s": None
            if warp_end is None
            else long_task_window(state["longtasks"], warp_end, warp_end + AFTER_WARP_MS),
            "network": ledger.summary(ready_ms, state["timeOrigin"]),
            "events": state["events"],
            "console_errors": log.console_errors,
            "page_errors": log.page_errors,
            "simulated": log.simulated,
        }
    )
    write_report(out, report)
    net = report["network"]
    after = report["long_tasks_after_warp_30s"]
    line = f"[probe] {status}: globe_ready {_fmt_ms(ready_ms)}"
    if gate is not None:
        line += f" ({_fmt_ms(report['ready_after_gate_ms'])} after the gate)"
    line += f", bytes before ready {_fmt_bytes(net['bytes_before_ready'])}"
    if after is not None:
        line += f", longest task in the 30 s after the warp {after['max_ms']:.0f} ms"
    print(line, flush=True)
    return 0 if status == "ok" else 1


def cmd_nogl(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    out = run_dir(OUT_ROOT, _run_parts(args), datetime.now())
    timeout_ms = args.timeout * 1000
    ledger = ByteLedger()
    with sync_playwright() as pw:
        browser = launch(pw, args.gpu)
        context, page, _cdp, log = open_page(browser, args, None, ledger, (NO_WEBGL2_JS,))
        url = page_url(args.query)
        report = base_report(args, browser, url)
        page.goto(url, wait_until="commit")
        if args.device == "phone":
            pass_phone_gate(page, timeout_ms, out)
        shown_at = None
        wait_ms = max(0.0, args.wait * 1000 - page.evaluate("performance.now()"))
        if wait_js(
            page,
            "(text) => !!document.body && document.body.innerText.includes(text)",
            wait_ms,
            arg=UNSUPPORTED_TEXT,
            polling_ms=50,
        ):
            shown_at = page.evaluate("performance.now()")
        page.wait_for_timeout(max(0.0, args.wait * 1000 - page.evaluate("performance.now()")))
        page.screenshot(path=str(out / "nogl.png"))
        body_text = page.evaluate("() => document.body ? document.body.innerText : ''")
        canvases = page.locator(GLOBE_CANVAS).count()
        state = probe_state(page)
        context.close()
        browser.close()

    report.update(
        {
            "unsupported_screen": shown_at is not None,
            "unsupported_seen_ms": shown_at,
            "globe_canvas_count": canvases,
            "body_text": body_text[:1000],
            "events": state["events"],
            "console_errors": log.console_errors,
            "page_errors": log.page_errors,
            "network": ledger.summary(None, state["timeOrigin"]),
        }
    )
    write_report(out, report)
    print(
        f"[probe] unsupported screen {'shown at ' + _fmt_ms(shown_at) if shown_at else 'NOT shown'}; "
        f"{len(log.page_errors)} page errors",
        flush=True,
    )
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    out = run_dir(OUT_ROOT, _run_parts(args), datetime.now())
    timeout_ms = args.timeout * 1000
    lng, lat, distance = args.pose
    tasks = [t for t in args.bg_tasks.split(",") if t] if args.after_bg else []
    ledger = ByteLedger()
    with sync_playwright() as pw:
        browser = launch(pw, args.gpu)
        context, page, _cdp, log = open_page(browser, args, args.dpr, ledger)
        url = page_url(args.query)
        report = base_report(args, browser, url)
        page.goto(url, wait_until="commit")
        if args.device == "phone":
            pass_phone_gate(page, timeout_ms, out)
        if not wait_js(page, "() => window.__probe.warpEndAt !== null", timeout_ms):
            raise SystemExit(f"the warp did not finish within {args.timeout:.0f} s")
        if tasks and not wait_js(
            page,
            "(tasks) => tasks.every(t => window.__probe.events.some("
            "e => e.n === 'globe_bg' && e.d && e.d.task === t))",
            timeout_ms,
            arg=tasks,
        ):
            raise SystemExit(
                f"background tasks {tasks} did not all finish within {args.timeout:.0f} s"
            )
        page.evaluate("() => { window.__DEMO.hideAllUI(); window.__DEMO.setAutoRotate(false) }")
        page.evaluate(
            "([lng, lat, d]) => window.__DEMO.setCameraPose(lng, lat, d)", [lng, lat, distance]
        )
        page.wait_for_timeout(args.settle * 1000)
        name = f"shot_{lng:g}_{lat:g}_{distance:g}_dpr{args.dpr:g}.png"
        page.locator(GLOBE_CANVAS).screenshot(path=str(out / name))
        camera = page.evaluate("() => window.__DEMO.getCameraState()")
        gl = page.evaluate(GL_INFO_JS)
        state = probe_state(page)
        context.close()
        browser.close()

    report.update(
        {
            "image": name,
            "camera": camera,
            "gl_renderer": gl["renderer"],
            "max_texture_size": gl["maxTextureSize"],
            "warp_end_ms": state["warpEndAt"],
            "events": state["events"],
            "console_errors": log.console_errors,
            "page_errors": log.page_errors,
            "simulated": log.simulated,
            "network": ledger.summary(None, state["timeOrigin"]),
        }
    )
    write_report(out, report)
    print(f"[probe] {out / name}", flush=True)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    with Image.open(args.a) as a, Image.open(args.b) as b:
        stats, diff = image_diff(a, b, threshold=args.threshold)
    if args.out is None:
        out = run_dir(OUT_ROOT, ["diff"], datetime.now()) / "diff.png"
    else:
        out = args.out
        out.parent.mkdir(parents=True, exist_ok=True)
    diff.save(out)
    report = {"a": str(args.a), "b": str(args.b), "diff_image": str(out), **stats}
    out.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


def _run_parts(args: argparse.Namespace) -> list[str]:
    parts = [args.command, args.target, args.device]
    if args.label:
        parts.append(args.label)
    return parts


def _fmt_ms(ms: float | None) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.2f} s"


def _fmt_bytes(n: int | None) -> str:
    return "n/a" if n is None else f"{n / 1_000_000:.2f} MB"


COMMANDS = {"load": cmd_load, "nogl": cmd_nogl, "shot": cmd_shot, "diff": cmd_diff}


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
