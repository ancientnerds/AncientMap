"""Screenshots of the founders dashboard (dashboard.html) at phone and desktop width.

The page needs /api/stats/* behind the founder cookie and the land outline
from public/data/, neither of which `vite preview` has, so both are answered
from fixtures here via route interception. Run after `npm run build`:

    python scripts/dashboard_screenshots.py

Writes docs/reports/screenshots/dashboard-mobile.png (390 x 844, 2x) and
dashboard-desktop.png (1280 x 800) and fails when the phone layout scrolls
sideways.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "ancient-nerds-map"
OUT = ROOT / "docs" / "reports" / "screenshots"
LAND = ROOT / "public" / "data" / "layers" / "ne_110m_land.geojson"
PORT = 4173
URL = f"http://127.0.0.1:{PORT}/dashboard.html"


def hour_buckets(days: int) -> list[dict]:
    """A diurnal curve of page views per hour, newest last."""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(days * 24):
        t = now - timedelta(hours=days * 24 - 1 - i)
        views = int(14 + 22 * (1 + math.sin((t.hour - 8) / 24 * 2 * math.pi)) + (i % 7) * 2)
        out.append({"hour": t.isoformat(), "views": views, "sessions": max(1, views // 3)})
    return out


def map_points() -> list[dict]:
    """Sessions per country and hour: a dot for every hour of the day, SG has no centroid."""
    weights = {
        "DE": 9, "US": 14, "GB": 6, "FR": 4, "PE": 3, "EG": 2, "TR": 5, "IN": 4,
        "BR": 3, "AU": 2, "MX": 2, "IT": 3, "NL": 2, "CA": 3, "JP": 1, "SG": 1,
    }  # fmt: skip
    return [
        {
            "country": code,
            "city": None,
            "hour": hour,
            "sessions": max(1, w // (1 + (hour * 7 + i) % 4)),
        }
        for i, (code, w) in enumerate(weights.items())
        for hour in range(24)
    ]


def rows(event: str, key: str, pairs: list[tuple[str, int]]) -> list[dict]:
    return [{"event_name": event, "data_key": key, "string_value": v, "n": n} for v, n in pairs]


FIXTURES: dict[str, dict] = {
    "overview": {
        "today": {"views": 412, "sessions": 168, "live": 3},
        "yesterday": {"views": 367, "sessions": 151, "live": 0},
        "days": 7,
        "sessions": {"all": 1893, "human": 1121},
        "types": {"leser": 402, "entdecker": 388, "forscher": 97, "sucher": 143, "sonstige": 91},
        "hours": hour_buckets(7),
    },
    "map": {"points": map_points()},
    "content": {
        "sites": rows(
            "site_open",
            "name",
            [
                ("Göbekli Tepe", 41),
                ("Stonehenge", 37),
                ("Giza Pyramid Complex", 33),
                ("Machu Picchu", 29),
                ("Puma Punku", 24),
                ("Teotihuacan", 19),
                ("Petra", 17),
                ("Nan Madol", 12),
                ("Sacsayhuamán", 11),
                ("Baalbek", 9),
            ],
        ),
        "stories": rows(
            "story_open",
            "story",
            [
                ("bronze-age-shipwreck-crete-17ab", 58),
                ("lidar-maya-cities-guatemala-93cd", 44),
                ("neolithic-longhouse-poland-2f10", 31),
                ("roman-villa-mosaic-kent-7e41", 22),
            ],
        ),
        "papers": rows(
            "paper_open",
            "paper",
            [
                ("/research/goebekli-tepe-astronomy", 27),
                ("/research/puma-punku-stone-working", 19),
                ("/research/nan-madol-construction", 11),
            ],
        ),
        "searches": rows(
            "search",
            "q",
            [
                ("giza", 23),
                ("stonehenge", 18),
                ("atlantis", 15),
                ("pyramids", 12),
                ("göbekli tepe", 11),
                ("ley lines", 9),
                ("roman villa", 7),
                ("ancient egypt", 6),
                ("1200 bc", 4),
            ],
        ),
    },  # fmt: skip
    "feedback": {
        "items": [
            {
                "created_at": "2026-09-17T14:05:00+00:00",
                "url_path": "/sites/peru/machu-picchu-9c8b7a65",
                "prompt": "site_page",
                "answer": "no",
                "text": "coordinates are a few hundred metres off, the dot sits in the valley",
            },
            {
                "created_at": "2026-09-17T09:41:00+00:00",
                "url_path": "/search.html",
                "prompt": "search_empty",
                "answer": None,
                "text": "atlantis",
            },
            {
                "created_at": "2026-09-16T22:12:00+00:00",
                "url_path": "/news-archive/bronze-age-shipwreck-crete-17ab",
                "prompt": "story_end",
                "answer": "yes",
                "text": None,
            },
            {
                "created_at": "2026-09-16T18:30:00+00:00",
                "url_path": "/lyra.html",
                "prompt": "lyra_answer",
                "answer": "no",
                "text": None,
            },
            {
                "created_at": "2026-09-15T07:02:00+00:00",
                "url_path": "/seo/site/old-slug",
                "prompt": "not_found",
                "answer": None,
                "text": "came from a reddit link",
            },
            {
                "created_at": "2026-09-14T16:45:00+00:00",
                "url_path": "/news-archive/lidar-maya-cities-guatemala-93cd",
                "prompt": "story_end",
                "answer": "yes",
                "text": "more maps please",
            },
        ]
    },  # fmt: skip
    "sources": {
        "sources": [
            {"source": "google.com", "family": "google", "sessions": 612},
            {"source": "direct", "family": "direct", "sessions": 498},
            {"source": "discord.com", "family": "discord.com", "sessions": 143},
            {"source": "youtube", "family": "youtube", "sessions": 96},
            {"source": "chatgpt.com", "family": "ai", "sessions": 61},
            {"source": "reddit.com", "family": "reddit.com", "sessions": 44},
            {"source": "bing.com", "family": "search", "sessions": 39},
            {"source": "t.co", "family": "t.co", "sessions": 12},
        ]
    },
}


def answer_stats(route: Route) -> None:
    name = route.request.url.split("/api/stats/", 1)[1].split("?", 1)[0]
    route.fulfill(json=FIXTURES[name])


def wait_for_server(timeout_s: float = 40) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urlopen(URL, timeout=2).read(1)  # noqa: S310 - local preview server
            return
        except (URLError, ConnectionError, OSError):
            time.sleep(0.5)
    raise SystemExit(f"vite preview did not answer on {URL}")


def main() -> None:
    if not (FRONTEND / "dist" / "dashboard.html").exists():
        raise SystemExit(
            "dist/dashboard.html missing: run `npm run build` in ancient-nerds-map first"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not on PATH")
    server = subprocess.Popen(
        [npx, "vite", "preview", "--port", str(PORT), "--strictPort", "--host", "127.0.0.1"],
        cwd=FRONTEND,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, viewport, scale in (
                ("dashboard-mobile.png", {"width": 390, "height": 844}, 2),
                ("dashboard-desktop.png", {"width": 1280, "height": 800}, 1),
            ):
                page = browser.new_page(viewport=viewport, device_scale_factor=scale)
                page.route("**/api/stats/**", answer_stats)
                page.route(
                    "**/data/layers/ne_110m_land.geojson",
                    lambda r: r.fulfill(path=str(LAND), content_type="application/geo+json"),
                )
                page.goto(URL, wait_until="networkidle")
                page.wait_for_selector(".dash-map-dot")
                page.evaluate("document.fonts.ready")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                page.screenshot(path=str(OUT / name), full_page=True)
                print(f"{name}: {viewport['width']}px, horizontal overflow {overflow}px")
                if overflow > 0:
                    raise SystemExit(f"{name}: the page scrolls sideways by {overflow}px")
                page.close()
            browser.close()
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
        else:
            server.terminate()


if __name__ == "__main__":
    main()
