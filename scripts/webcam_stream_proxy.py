"""
Webcam Stream Proxy for AncientMap
===================================
Extracts HLS stream tokens from SkylineWebcams and proxies the
m3u8 + .ts segments to bypass CORS, so hls.js can play live video
in the browser.

Usage:
    python scripts/webcam_stream_proxy.py

Then open http://localhost:8765 in your browser.
"""

import http.server
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 8765
CACHE_TTL = 300  # Cache stream URLs for 5 minutes (tokens rotate)
# Path prefix when running behind a reverse proxy (e.g. "/webcam-proxy")
PATH_PREFIX = os.environ.get("PATH_PREFIX", "")

# Stream URL cache: {skyline_page_url: (m3u8_url, timestamp)}
_stream_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()

# Common headers to mimic a browser
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_url(url: str, headers: dict | None = None) -> tuple[bytes, dict]:
    """Fetch a URL and return (body_bytes, response_headers)."""
    hdrs = {**BROWSER_HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)

    # Allow unverified SSL for dev/testing
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        body = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        return body, resp_headers


def extract_stream_url(page_url: str) -> dict:
    """
    Fetch a SkylineWebcams page and extract the HLS m3u8 stream URL.

    Returns dict with keys:
        stream_url: str | None
        offline: bool  (True if the page explicitly says OFFLINE)
    """
    # Check cache first
    with _cache_lock:
        if page_url in _stream_cache:
            cached, ts = _stream_cache[page_url]
            if time.time() - ts < CACHE_TTL:
                return cached

    try:
        body, _ = fetch_url(page_url)
        html = body.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[extract] Failed to fetch {page_url}: {e}")
        return {"stream_url": None, "offline": False}

    # Check for explicit OFFLINE marker in the page
    is_offline = bool(re.search(r"<strong>\s*OFFLINE\s*</strong>", html, re.IGNORECASE))

    # Pattern 1: Full URL in source/url attribute
    m = re.search(
        r'(?:url|source)\s*:\s*["\']'
        r'((?:https?:)?//[^\s"\']+\.m3u8[^\s"\']*)',
        html,
    )
    if m:
        stream_url = m.group(1)
        if stream_url.startswith("//"):
            stream_url = "https:" + stream_url
        result = {"stream_url": stream_url, "offline": False}
        with _cache_lock:
            _stream_cache[page_url] = (result, time.time())
        return result

    # Pattern 2: Relative path like "livee.m3u8?a=TOKEN"
    m = re.search(r'["\']([^"\']*livee?\.m3u8\?a=[^"\']+)["\']', html)
    if m:
        path = m.group(1)
        stream_url = urllib.parse.urljoin(
            "https://hd-auth.skylinewebcams.com/", path
        )
        # Normalize: livee.m3u8 -> live.m3u8
        stream_url = stream_url.replace("livee.m3u8", "live.m3u8")
        result = {"stream_url": stream_url, "offline": False}
        with _cache_lock:
            _stream_cache[page_url] = (result, time.time())
        return result

    # Pattern 3: Just the token parameter
    m = re.search(r'\?a=([a-zA-Z0-9_-]+)', html)
    if m:
        token = m.group(1)
        stream_url = f"https://hd-auth.skylinewebcams.com/live.m3u8?a={token}"
        result = {"stream_url": stream_url, "offline": False}
        with _cache_lock:
            _stream_cache[page_url] = (result, time.time())
        return result

    if is_offline:
        print(f"[extract] Cam is OFFLINE: {page_url}")
    else:
        print(f"[extract] No stream URL found in {page_url}")

    result = {"stream_url": None, "offline": is_offline}
    with _cache_lock:
        _stream_cache[page_url] = (result, time.time())
    return result


def rewrite_m3u8(content: str, base_url: str) -> str:
    """
    Rewrite URLs inside m3u8 playlists to route through our proxy.
    This handles both master playlists and media playlists.
    """
    lines = content.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            # This is a URL line (segment or variant playlist)
            if stripped.startswith("http://") or stripped.startswith("https://"):
                abs_url = stripped
            else:
                abs_url = urllib.parse.urljoin(base_url, stripped)
            encoded = urllib.parse.quote(abs_url, safe="")
            result.append(f"{PATH_PREFIX}/proxy?url={encoded}")
        else:
            result.append(line)
    return "\n".join(result)


class WebcamProxyHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the webcam proxy."""

    def log_message(self, fmt, *args):
        # Quieter logging
        path = args[0] if args else ""
        if "/proxy?" not in str(path):  # Don't log every .ts segment
            print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/extract":
            self._handle_extract(params)
        elif path == "/proxy":
            self._handle_proxy(params)
        elif path.startswith("/thumb/"):
            self._handle_thumb(path)
        elif path == "/api/status":
            self._handle_status()
        else:
            self.send_error(404)

    def _serve_html(self):
        """Serve the test HTML file."""
        html_path = Path(__file__).parent.parent / "tests" / "webcam_test.html"
        if not html_path.exists():
            self.send_error(404, "tests/webcam_test.html not found")
            return
        content = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_extract(self, params):
        """Extract HLS stream URL from a SkylineWebcams page."""
        urls = params.get("url", [])
        if not urls:
            self._json_response(400, {"error": "Missing ?url= parameter"})
            return

        page_url = urls[0]
        result = extract_stream_url(page_url)

        if result["stream_url"]:
            # Return the stream URL routed through our proxy
            encoded = urllib.parse.quote(result["stream_url"], safe="")
            proxied_url = f"/proxy?url={encoded}"
            self._json_response(200, {
                "stream_url": proxied_url,
                "raw_stream_url": result["stream_url"],
                "source_page": page_url,
                "offline": False,
                "cached": page_url in _stream_cache,
            })
        else:
            self._json_response(200 if result["offline"] else 404, {
                "stream_url": None,
                "source_page": page_url,
                "offline": result["offline"],
                "error": "Cam is offline" if result["offline"] else "Could not extract stream URL",
            })

    def _handle_proxy(self, params):
        """Proxy any URL, adding CORS headers. Rewrite m3u8 content."""
        urls = params.get("url", [])
        if not urls:
            self.send_error(400, "Missing ?url= parameter")
            return

        target_url = urls[0]

        try:
            # Add Origin/Referer headers that SkylineWebcams expects
            extra_headers = {}
            if "skylinewebcams.com" in target_url:
                extra_headers["Origin"] = "https://www.skylinewebcams.com"
                extra_headers["Referer"] = "https://www.skylinewebcams.com/"

            body, resp_headers = fetch_url(target_url, extra_headers)

            content_type = resp_headers.get("content-type", "application/octet-stream")

            # If this is an m3u8 playlist, rewrite URLs inside it
            if ".m3u8" in target_url or "mpegurl" in content_type.lower():
                text = body.decode("utf-8", errors="replace")
                text = rewrite_m3u8(text, target_url)
                body = text.encode("utf-8")
                content_type = "application/vnd.apple.mpegurl"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._cors_headers()
            # Cache .ts segments for 10 seconds (they're immutable)
            if ".ts" in target_url:
                self.send_header("Cache-Control", "public, max-age=10")
            self.end_headers()
            self.wfile.write(body)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, f"Upstream error: {e.reason}")
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def _handle_thumb(self, path: str):
        """Proxy CDN thumbnail, bypassing hotlink protection."""
        # /thumb/831.jpg -> https://cdn.skylinewebcams.com/live831.jpg
        filename = path.removeprefix("/thumb/")
        if not filename or "/" in filename:
            self.send_error(400, "Invalid thumbnail path")
            return
        skyline_id = filename.removesuffix(".jpg")
        cdn_url = f"https://cdn.skylinewebcams.com/live{skyline_id}.jpg"
        try:
            body, _ = fetch_url(cdn_url, {
                "Referer": "https://www.skylinewebcams.com/",
            })
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=60")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, f"CDN error: {e.reason}")
        except Exception as e:
            self.send_error(502, f"Thumbnail proxy error: {e}")

    def _handle_status(self):
        """Return cache status."""
        with _cache_lock:
            cached = {
                url: {**result, "age_s": int(time.time() - ts)}
                for url, (result, ts) in _stream_cache.items()
            }
        self._json_response(200, {
            "cached_streams": len(cached),
            "entries": cached,
        })

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    """Allow reuse of address for quick restarts."""
    allow_reuse_address = True
    allow_reuse_port = True


def main():
    server = ThreadedHTTPServer(("0.0.0.0", PORT), WebcamProxyHandler)
    print(f"\n  Webcam Stream Proxy running at http://localhost:{PORT}")
    print(f"  Serving test page from tests/webcam_test.html")
    print(f"  Stream token cache TTL: {CACHE_TTL}s\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
