"""Screenshots of the founders dashboard (dashboard.html) at phone and desktop width.

The page needs /api/stats/* behind the founder cookie, which `vite preview`
has not, so every endpoint is answered from the fixtures below via route
interception. The land outline is bundled (src/data/world_land.json), so the
map draws itself. Run after `npm run build`:

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


def rows(event: str, pairs: list[tuple[str, int]]) -> list[dict]:
    """A content row in the shape SQL_CONTENT returns: label, country, results, n."""
    return [
        {"event_name": event, "label": label, "country": None, "results": None, "n": n}
        for label, n in pairs
    ]


def site_rows(items: list[tuple[str, str, int]]) -> list[dict]:
    """Sites keep their country — the panel prints "Name · Land"."""
    return [
        {"event_name": "site_open", "label": name, "country": country, "results": None, "n": n}
        for name, country, n in items
    ]


def search_rows(items: list[tuple[str, int, int]]) -> list[dict]:
    """Searches keep their result count; a zero is marked red in the panel."""
    return [
        {"event_name": "search", "label": q, "country": None, "results": hits, "n": n}
        for q, hits, n in items
    ]


#: Sessions per country for the pulse tiles, biggest first — the flag row is
#: clipped, so the fixture needs more countries than fit on a phone.
COUNTRY_WEIGHTS = [
    ("US", 96), ("DE", 71), ("GB", 58), ("TR", 33), ("FR", 27), ("IN", 24),
    ("CA", 19), ("IT", 17), ("BR", 14), ("NL", 11), ("AU", 9), ("MX", 7),
    ("PE", 6), ("EG", 5), ("JP", 4), ("??", 3),
]  # fmt: skip


def country_window(divisor: int) -> dict:
    """One tile's worth of countries, thinned out for the shorter windows."""
    rows = [
        {"country": code, "sessions": max(1, n // divisor)}
        for code, n in COUNTRY_WEIGHTS
        if n // divisor >= 1
    ]
    total = sum(r["sessions"] for r in rows)
    return {"sessions": total, "all": round(total * 1.9), "countries": rows}


FIXTURES: dict[str, dict] = {
    "countries": {
        "now": {
            "sessions": 3,
            "all": 3,
            "countries": [{"country": "US", "sessions": 2}, {"country": "DE", "sessions": 1}],
        },
        "today": country_window(24),
        "d7": country_window(4),
        "d30": country_window(1),
    },
    "overview": {
        "today": {"views": 412, "sessions": 168, "live": 3},
        "yesterday": {"views": 367, "sessions": 151, "live": 0},
        "days": 7,
        "sessions": {"all": 1893, "human": 1121},
        "types": {"reader": 402, "explorer": 388, "researcher": 97, "searcher": 143, "other": 91},
        "hours": hour_buckets(7),
    },
    "map": {"points": map_points()},
    "content": {
        "sites": site_rows(
            [
                ("Göbekli Tepe", "Türkiye", 41),
                ("Stonehenge", "United Kingdom", 37),
                ("Giza Pyramid Complex", "Egypt", 33),
                ("Machu Picchu", "Peru", 29),
                ("Puma Punku", "Bolivia", 24),
                ("Teotihuacan", "Mexico", 19),
                ("Petra", "Jordan", 17),
                ("Nan Madol", "Micronesia", 12),
                ("Sacsayhuamán", "Peru", 11),
                ("Baalbek", "Lebanon", 9),
            ]
        ),
        "stories": rows(
            "story_open",
            [
                ("bronze-age-shipwreck-crete-17ab", 58),
                ("lidar-maya-cities-guatemala-93cd", 44),
                ("neolithic-longhouse-poland-2f10", 31),
                ("roman-villa-mosaic-kent-7e41", 22),
            ],
        ),
        "papers": rows(
            "paper_open",
            [
                ("/research/goebekli-tepe-astronomy", 27),
                ("/research/puma-punku-stone-working", 19),
                ("/research/nan-madol-construction", 11),
            ],
        ),
        "searches": search_rows(
            [
                ("giza", 14, 23),
                ("stonehenge", 9, 18),
                ("atlantis", 0, 15),
                ("pyramids", 61, 12),
                ("göbekli tepe", 3, 11),
                ("ley lines", 0, 9),
                ("roman villa", 7, 7),
                ("ancient egypt", 48, 6),
                ("1200 bc", 2, 4),
            ]
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
    "journeys": {
        "chains": [
            {"chain": "google → story → site_open → site", "sessions": 148},
            {"chain": "direct → globe → site_open → site", "sessions": 121},
            {"chain": "google → site", "sessions": 96},
            {"chain": "ai → home → globe → site_open → site", "sessions": 63},
            {"chain": "youtube → site → share", "sessions": 41},
            {"chain": "direct → search → search → site_open → site → site", "sessions": 34},
            {"chain": "discord.com → stories → story → feedback", "sessions": 27},
            {"chain": "google → papers → paper_open → paper → lyra_chat", "sessions": 19},
            {"chain": "reddit.com → story", "sessions": 12},
            {"chain": "search → country → site_open → site", "sessions": 8},
        ]
    },
    "problems": {
        "problems": [
            {
                "kind": "js_error",
                "label": "Cannot read properties of undefined (reading 'lngLat')",
                "score": 57,
                "detail": "19× on globe",
            },
            {
                "kind": "slow_page",
                "label": "story · LCP",
                "score": 42,
                "detail": "p75 3380 ms against a 2500 ms budget, 42 samples",
            },
            {
                "kind": "shallow_exit",
                "label": "story",
                "score": 38,
                "detail": "38 sessions with one page, under 25 % scrolled",
            },
            {
                "kind": "broken_link",
                "label": "/sites/turkiye/goebekli-tepe",
                "score": 24,
                "detail": "12 views into nothing, from reddit.com",
            },
            {
                "kind": "empty_search",
                "label": "search",
                "score": 17,
                "detail": "17 searches found nothing",
            },
            {
                "kind": "slow_page",
                "label": "site · INP",
                "score": 11,
                "detail": "p75 264 ms against a 200 ms budget, 11 samples",
            },
        ]
    },
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


#: Date, time and visitor on every problem row (owner, 2026-09-19). Added here
#: instead of in each literal above, so the rows stay readable.
PROBLEM_VISITORS = [
    ("CH", "laptop", "chrome", "cf01aa30"),
    ("US", "desktop", "safari", "109a462e"),
    ("PH", "mobile", "ios", "e4eb8bb8"),
    ("DE", "mobile", "crios", "18f6c104"),
    (None, "laptop", "firefox", "b3150e12"),
]
for _i, _row in enumerate(FIXTURES["problems"]["problems"]):
    _country, _device, _browser, _session = PROBLEM_VISITORS[_i % len(PROBLEM_VISITORS)]
    _row["at"] = (datetime.now(UTC) - timedelta(hours=_i * 5 + 1)).isoformat()
    _row["last"] = {
        "session": _session,
        "country": _country,
        "device": _device,
        "browser": _browser,
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
