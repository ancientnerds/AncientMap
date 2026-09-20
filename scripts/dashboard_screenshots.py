"""Screenshots of the founders dashboard (dashboard.html) at phone and desktop width.

The page needs /api/stats/* behind the founder cookie, which `vite preview`
has not, so every endpoint is answered from the fixtures below via route
interception. The land outline is bundled (src/data/world_land.json), so the
map draws itself. Run after `npm run build`:

    python scripts/dashboard_screenshots.py

Writes docs/reports/screenshots/dashboard-mobile.png, dashboard-mobile-empty.png
(both 390 x 844, 2x) and dashboard-desktop.png (1280 x 800), and fails when the
phone layout scrolls sideways, cuts a bar label off, or grows past
MAX_MOBILE_HEIGHT.

This is the repo's only *layout* check. The panels' sentences are rendered in
src/components/dashboard/__tests__/panels.test.tsx with renderToString, which
needs no DOM; what cannot be asserted there is how wide anything ends up, and
that is the whole point of this pass.
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


def hour_buckets(hours: int = 48) -> list[dict]:
    """Sessions per hour, newest last — always `hours` of them, including the
    empty ones, which is the bug the fixed axis fixes."""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(hours):
        t = now - timedelta(hours=hours - 1 - i)
        sessions = int(6 + 11 * (1 + math.sin((t.hour - 8) / 24 * 2 * math.pi)) + (i % 7))
        if t.hour in (3, 4):
            sessions = 0  # an empty hour draws as an empty bar, never as a gap
        out.append(
            {
                "hour": t.isoformat(),
                "sessions": sessions,
                "human": sessions // 3,
                "ai": 1 if t.hour == 15 else 0,
            }
        )
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


def live_rows() -> list[dict]:
    """Six visitors. One headline at the live maximum (138 characters), one
    visitor Umami could not place, one who has had the page open over an
    hour — the three cases the row layout has to survive at 390 px."""
    titles = [
        "Inca polygonal masonry in Cusco, Sacsayhuamán and the highland sites: massive irregular blocks fitted without any mortar",
        "Göbekli Tepe",
        "Database",
        "Nan Madol",
        "Bronze age shipwreck off Crete",
        "Puma Punku",
    ]
    countries = ["DE", "US", None, "IN", "BR", "GB"]
    heres = [42, 380, 4100, 95, 12, 1730]
    return [
        {
            "session": f"a1b2c3d{i}",
            "country": countries[i],
            "device": "mobile" if i % 2 else "laptop",
            "browser": "chrome" if i % 3 else "safari",
            "page": "site",
            "title": titles[i],
            "here": heres[i],
            "last_seen": (datetime.now(UTC) - timedelta(minutes=i * 3)).isoformat(),
        }
        for i in range(6)
    ]


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
    "live": {
        "window_minutes": 30,
        "lookback_hours": 24,
        # Six, not nine: LIVE_LIMIT is 6, so a response can never say "9 in the
        # window, 6 shown", and a fixture describing a state the API cannot
        # emit gates nothing.
        "total": 6,
        "shown": 6,
        "visitors": live_rows(),
        "last": None,
    },
    "globe": {
        "loads": 412,
        "reached": 297,
        "gave_up": 115,
        "sessions": {"all": 288, "reached": 214},
        "ready_ms": {"min": 3120.0, "median": 8940.0, "max": 41220.0, "samples": 297},
    },
    "clusters": {
        "min_ids": 3,
        "flagged": 418,
        "clusters": [
            {"screen": "1366x1366", "browser": "chrome", "os": "Mac OS", "sessions": 243},
            {"screen": "1280x1200", "browser": "chrome", "os": "Windows 10", "sessions": 131},
            {"screen": "1920x1080", "browser": "chrome", "os": "Linux", "sessions": 44},
        ],
    },
    "members": {
        "members": 148,
        "founders": 2,
        "newest_signup": "2026-09-18T21:04:00+00:00",
        "last_login": "2026-09-19T08:12:00+00:00",
        "acts": [
            {"act": "Likes", "n": 312, "by": 96, "at": "2026-09-19T07:55:00+00:00"},
            {"act": "Bookmarks", "n": 188, "by": 71, "at": "2026-09-18T19:20:00+00:00"},
            {"act": "Lyra answers", "n": 1204, "by": 44, "at": "2026-09-19T08:41:00+00:00"},
            # One account, to prove the singular in actItem's hint renders.
            {"act": "Research requests", "n": 61, "by": 1, "at": "2026-09-16T11:02:00+00:00"},
        ],
    },
    "devices": {
        # The buckets add up to `sessions`; the language tags deliberately do
        # not, because a client that sent no tag has a device row and none in
        # the language list — the panel's note says so and this proves it.
        "sessions": 1893,
        "devices": [
            {"device": "desktop", "sessions": 1204},
            {"device": "mobile", "sessions": 604},
            {"device": "tablet", "sessions": 61},
            {"device": "unknown", "sessions": 24},
        ],
        "languages": [
            {"language": "en-US", "sessions": 902},
            {"language": "en-GB", "sessions": 311},
            {"language": "de-DE", "sessions": 204},
            {"language": "zh-CN", "sessions": 141},
            {"language": "es-ES", "sessions": 97},
            {"language": "tr-TR", "sessions": 61},
            # The seventh tag, so the LANGUAGE_ROWS = 6 cut is in the picture.
            {"language": "pt-BR", "sessions": 44},
        ],
        "language_groups": [
            {"language": "en", "sessions": 1213},
            {"language": "de", "sessions": 204},
            {"language": "zh", "sessions": 141},
            {"language": "es", "sessions": 97},
            {"language": "tr", "sessions": 61},
            {"language": "pt", "sessions": 44},
        ],
    },
    "overview": {
        "days": 7,
        "sessions": {"all": 1893, "human": 1121, "ai": 214},
        "types": {"reader": 402, "explorer": 388, "researcher": 97, "searcher": 143, "other": 91},
        "hours": hour_buckets(),
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
        ],
        "pages": {
            "sessions": 612,
            "one_page": 291,
            "moving": 321,
            "entries": [
                {"page": "story", "sessions": 248, "stopped": 151},
                {"page": "site", "sessions": 137, "stopped": 44},
                {"page": "globe", "sessions": 96, "stopped": 11},
                {"page": "country", "sessions": 61, "stopped": 61},
                {"page": "home", "sessions": 42, "stopped": 8},
                {"page": "search", "sessions": 14, "stopped": 5},
            ],
            "exits": [
                {"page": "site", "sessions": 219, "views": 588},
                {"page": "story", "sessions": 186, "views": 401},
                {"page": "globe", "sessions": 92, "views": 173},
                {"page": "country", "sessions": 61, "views": 74},
                {"page": "paper", "sessions": 20, "views": 31},
            ],
        },
        "outbound": [
            {"host": "youtube.com", "clicks": 148, "visitors": 121},
            {"host": "journals.plos.org", "clicks": 39, "visitors": 37},
            {"host": "getty.edu", "clicks": 12, "visitors": 12},
            {"host": "en.wikipedia.org", "clicks": 7, "visitors": 1},
        ],
        # The Reading panel reads this key of /journeys, not a route of its
        # own. Five page types is the whole set src/analytics/boot.ts arms the
        # scroll listener on, and four digits is the widest ladder the hint can
        # hold — the 390 px worst case, not today's story 17/15/13/10.
        "reading": {
            "steps": [25, 50, 75, 100],
            "readers": 1284,
            "pages": [
                {"page": "story", "sessions": [1204, 998, 811, 640]},
                {"page": "site", "sessions": [412, 301, 244, 188]},
                {"page": "country", "sessions": [96, 71, 55, 40]},
                {"page": "journal", "sessions": [44, 33, 21, 12]},
                {"page": "paper", "sessions": [7, 5, 5, 4]},
            ],
        },
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
                "kind": "webgl_lost",
                # One of the two strings WEBGL_PHASES can produce; the panel
                # prints it verbatim, so anything else is a sentence the
                # backend cannot emit.
                "label": "globe never started",
                "score": 48,
                "detail": "16 visitors, 19× — no_shader",
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
            {"source": "google.com", "family": "google", "sessions": 612, "views": 903},
            {"source": "direct", "family": "direct", "sessions": 498, "views": 1204},
            {"source": "discord.com", "family": "discord.com", "sessions": 143, "views": 311},
            {"source": "youtube", "family": "youtube", "sessions": 96, "views": 142},
            {"source": "chatgpt.com", "family": "ai", "sessions": 61, "views": 88},
            {"source": "reddit.com", "family": "reddit.com", "sessions": 44, "views": 61},
            {"source": "bing.com", "family": "search", "sessions": 39, "views": 52},
            {"source": "t.co", "family": "t.co", "sessions": 12, "views": 14},
        ],
        "log": {
            "covered_from": "2026-08-21T06:19:00+00:00",
            "covered_days": 29.14,
            "lines": 8842,
            # Referrer spam kept out of the two lists and named in the note
            # (referral_log.UNKNOWN_HOST_MIN); 17 of them live on 2026-09-19.
            "unverified": 204,
            "families": [
                {"family": "search", "visits": 2914, "bots": 411},
                {"family": "social", "visits": 388, "bots": 44},
                {"family": "other", "visits": 204, "bots": 129},
                # One bot: the live value on this family today, and the row
                # that proves familyItem() writes "bot" and not "bots".
                {"family": "ai", "visits": 97, "bots": 1},
            ],
            # REPORT_ROWS = 8, so eight is the widest this list ever gets.
            "hosts": [
                {"host": "google.com", "visits": 2801},
                {"host": "discord.com", "visits": 291},
                {"host": "chatgpt.com", "visits": 88},
                {"host": "bing.com", "visits": 74},
                {"host": "duckduckgo.com", "visits": 39},
                {"host": "perplexity.ai", "visits": 21},
                {"host": "reddit.com", "visits": 14},
                {"host": "news.ycombinator.com", "visits": 9},
            ],
            # Only is_bad_answer() statuses: no 301 (a redirect is followed by
            # its own 200) and no 404 (every live one is a forged referer).
            "statuses": [
                {"status": 410, "visits": 188},
                {"status": 499, "visits": 27},
                {"status": 500, "visits": 2},
            ],
        },
        "log_reason": None,
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
#: The one row the loop below skips. `empty_search` falling back to the session
#: counter is the shape problems() emits with at=None and last=None
#: (stats_analysis.py, the `elif empty_searches` branch), and it is the only
#: row that can reach Problems.tsx's "no date, no visitor" branch — so the
#: phone layout has to be measured with it in the list.
NO_VISITOR_LABEL = "search"
for _i, _row in enumerate(FIXTURES["problems"]["problems"]):
    if _row["kind"] == "empty_search" and _row["label"] == NO_VISITOR_LABEL:
        _row["at"] = None
        _row["last"] = None
        continue
    _country, _device, _browser, _session = PROBLEM_VISITORS[_i % len(PROBLEM_VISITORS)]
    _row["at"] = (datetime.now(UTC) - timedelta(hours=_i * 5 + 1)).isoformat()
    _row["last"] = {
        "session": _session,
        "country": _country,
        "device": _device,
        "browser": _browser,
    }


#: Every panel's day-one production state, at 390 px. What it says is asserted
#: in panels.test.tsx; what it looks like can only be measured here.
#: Measured 2026-09-19: nobody in the live window during 20 % of all
#: minutes, no clusters at all as soon as the scrapers leave, no referral log
#: on any development box, and a members panel whose every act reads zero.
EMPTY_FIXTURES: dict[str, dict] = {
    "countries": {
        w: {"sessions": 0, "all": 0, "countries": []} for w in ("now", "today", "d7", "d30")
    },
    "overview": {
        "days": 7,
        "sessions": {"all": 0, "human": 0, "ai": 0},
        "types": {},
        "hours": [{**h, "sessions": 0, "human": 0, "ai": 0} for h in hour_buckets()],
    },
    "map": {"points": []},
    "content": {"sites": [], "stories": [], "papers": [], "searches": []},
    "feedback": {"items": []},
    "journeys": {
        "chains": [],
        "pages": {"sessions": 0, "one_page": 0, "moving": 0, "entries": [], "exits": []},
        "outbound": [],
        # Required, not optional: the Reading panel reads r.steps and r.pages
        # the moment /journeys answers, so a response without this key blanks
        # the whole page instead of one panel.
        "reading": {"steps": [25, 50, 75, 100], "readers": 0, "pages": []},
    },
    "problems": {"problems": []},
    # The VPS state, not the development box: the log is readable and holds no
    # referred arrival in the window, so the coverage block draws three empty
    # lists and its note. `log: None` (no log file at all) renders a single
    # paragraph and is asserted in panels.test.tsx, which needs no browser.
    "sources": {
        "sources": [],
        "log": {
            "covered_from": (datetime.now(UTC) - timedelta(days=7)).isoformat(),
            "covered_days": 7.0,
            "lines": 0,
            "unverified": 0,
            "families": [],
            "hosts": [],
            "statuses": [],
        },
        "log_reason": None,
    },
    "live": {
        "window_minutes": 30,
        "lookback_hours": 24,
        "total": 0,
        "shown": 0,
        "visitors": [],
        "last": {
            "session": "9f0e1d2c",
            "country": "IN",
            "device": "mobile",
            "browser": "chrome",
            "page": "story",
            "title": "Ramp construction theories for the great pyramid",
            "here": 2220,
            # Relative, like live_rows(): the panel prints "last seen N ago"
            # against the clock, so a fixed stamp makes every run's PNG differ.
            "last_seen": (datetime.now(UTC) - timedelta(minutes=37)).isoformat(),
        },
    },
    "globe": {
        "loads": 0,
        "reached": 0,
        "gave_up": 0,
        "sessions": {"all": 0, "reached": 0},
        "ready_ms": {"min": None, "median": None, "max": None, "samples": 0},
    },
    "clusters": {"min_ids": 3, "flagged": 0, "clusters": []},
    "members": {
        "members": 5,
        "founders": 2,
        "newest_signup": "2026-08-28T01:33:22+00:00",
        "last_login": "2026-09-19T08:12:00+00:00",
        "acts": [
            {"act": "Likes", "n": 0, "by": 0, "at": None},
            {"act": "Bookmarks", "n": 0, "by": 0, "at": None},
            {"act": "Lyra answers", "n": 0, "by": 0, "at": None},
            {"act": "Research requests", "n": 0, "by": 0, "at": None},
        ],
    },
    # A one-day window with no session reaches this; it is the only state in
    # which the panel prints "No session in this window." under both lists.
    "devices": {"sessions": 0, "devices": [], "languages": [], "language_groups": []},
}

#: The phone page's height budget, still OFF: 0 skips the check below. The
#: build plan's step 26i says to set this from the first measurement, unless
#: that measurement passes ~8 000 px - and it does, so the number waits for
#: the owner's ruling on blocker B5 (the three-band collapse) instead of being
#: raised to fit. Measured 2026-09-19 with fourteen panels at 390 px: 11 766
#: px on the full fixtures, 6 089 px on the empty ones. Day one is inside the
#: plan's estimate; a busy week is not. Where it goes, full pass: Sources
#: 1 889, Paths 1 466, TopContent 1 438, Devices 806, Problems 798, LiveNow
#: 736. Three things the number does not say: both re-instated panels together
#: are 1 414 px, so dropping them again would not reach 8 000 either; 11 766 is
#: not the ceiling, because /content is capped at 15/15/15/30 rows and this
#: fixture carries 10/4/3/9; and TopContent is 1 438 px here but 236 px on the
#: empty pass, because three of its four lists have never had a row to draw.
MAX_MOBILE_HEIGHT = 0  # set it with the B5 ruling, never before it


#: Bar rows whose label does not fit the space it was given. `.dash-bar-label`
#: is the flexible column of a two-column grid, so anything nowrap in the other
#: column is taken out of the name of the row: with the hint inside the value
#: column, Members read "L.", "B", "" and "Re…" at 360 px, and `title` is a
#: hover tooltip, which a phone does not have. The title is what the panel is
#: about, so nothing here may be clipped at 390 px.
CLIPPED_LABELS = """
Array.from(document.querySelectorAll('.dash-bar-label'))
  .filter(el => el.scrollWidth > el.clientWidth + 1)
  .map(el => `${el.textContent.slice(0, 24)} [${el.clientWidth}/${el.scrollWidth}]`)
"""


def route_handler(fixtures: dict[str, dict]):
    def answer_stats(route: Route) -> None:
        name = route.request.url.split("/api/stats/", 1)[1].split("?", 1)[0]
        route.fulfill(json=fixtures[name])

    return answer_stats


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
            for name, viewport, scale, fixtures in (
                ("dashboard-mobile.png", {"width": 390, "height": 844}, 2, FIXTURES),
                ("dashboard-mobile-empty.png", {"width": 390, "height": 844}, 2, EMPTY_FIXTURES),
                ("dashboard-desktop.png", {"width": 1280, "height": 800}, 1, FIXTURES),
            ):
                page = browser.new_page(viewport=viewport, device_scale_factor=scale)
                page.route("**/api/stats/**", route_handler(fixtures))
                page.goto(URL, wait_until="networkidle")
                # The strip, not .dash-map-dot: the map has no dots in the
                # empty pass, and the strip is the first thing every pass draws.
                page.wait_for_selector(".dash-spark")
                page.evaluate("document.fonts.ready")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                height = page.evaluate("document.body.scrollHeight")
                clipped = page.evaluate(CLIPPED_LABELS)
                page.screenshot(path=str(OUT / name), full_page=True)
                print(
                    f"{name}: {viewport['width']}px, overflow {overflow}px, "
                    f"height {height}px, clipped labels {len(clipped)}"
                )
                if overflow > 0:
                    raise SystemExit(f"{name}: the page scrolls sideways by {overflow}px")
                if clipped:
                    raise SystemExit(
                        f"{name}: {len(clipped)} bar labels are cut off: {clipped[:6]}"
                    )
                if MAX_MOBILE_HEIGHT and viewport["width"] == 390 and height > MAX_MOBILE_HEIGHT:
                    raise SystemExit(
                        f"{name}: the phone page is {height}px tall, "
                        f"over the {MAX_MOBILE_HEIGHT}px budget"
                    )
                page.close()
            browser.close()
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
        else:
            server.terminate()


if __name__ == "__main__":
    main()
